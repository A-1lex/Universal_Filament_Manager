"""Bounded read/transfer client for the HaspelSync authority capability API.

This client does not establish a global single-writer lock. It only observes or
changes the capability advertised by the selected HaspelSync service instance.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from http.client import HTTPMessage
from typing import IO, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import uuid4

from ufm.application.ports.secrets import SecretValue

AuthorityOwner = Literal["LEGACY_ACTIVE", "UFM_ACTIVE", "REVIEW_ONLY"]
_OWNERS = frozenset({"LEGACY_ACTIVE", "UFM_ACTIVE", "REVIEW_ONLY"})
_MAX_RESPONSE_BYTES = 64 * 1024
_TIMEOUT_SECONDS = 4
_BOOKING_STATUSES = frozenset({"pending", "booked", "uncertain", "dismissed"})
_BOOKING_RESOLUTIONS = frozenset({"applied", "not_applied"})
_TERMINAL_STATES = frozenset({"FINISH", "FAILED", "CANCEL"})


class HaspelAuthorityUnavailable(RuntimeError):
    """The configured Haspel service cannot provide a trusted authority answer."""

    def __init__(self) -> None:
        super().__init__("haspelsync.authority_unavailable")


class HaspelAuthorityConflict(RuntimeError):
    """The service rejected the expected owner revision or transition."""

    def __init__(self) -> None:
        super().__init__("haspelsync.authority_conflict")


class HaspelBookingResolutionUnknown(RuntimeError):
    """A resolution write may have landed but cannot yet be confirmed safely."""

    def __init__(self) -> None:
        super().__init__("haspelsync.booking_resolution_unknown")


@dataclass(frozen=True, slots=True)
class HaspelAuthoritySnapshot:
    printer_id: str
    owner: AuthorityOwner
    revision: int
    pending_count: int
    uncertain_count: int
    active_count: int
    capability_version: int = 1


@dataclass(frozen=True, slots=True)
class HaspelBookingRecord:
    """A validated booking row returned by the selected HaspelSync service."""

    id: str
    printer_id: str
    started_at: int
    item_key: str
    spool_id: int
    grams: float
    job_name: str | None
    terminal_state: str
    status: str
    created_at: int
    updated_at: int
    resolution: str | None = None
    resolution_note: str | None = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
        new_url: str,
    ) -> None:
        # Never forward an API key to another origin, including same-host redirects.
        return None


def _private_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return (
        not address.is_multicast
        and not address.is_reserved
        and (address.is_loopback or address.is_link_local or address.is_private)
    )


def _validate_endpoint(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 2_000:
        raise HaspelAuthorityUnavailable()
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme not in {"https", "http"}
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise HaspelAuthorityUnavailable()

        normalized_host = hostname.rstrip(".").casefold()
        loopback = normalized_host == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(normalized_host).is_loopback
        except ValueError:
            pass

        if parsed.scheme == "http":
            # Haspel keys are full-access service keys. Cleartext is permitted
            # only for a same-machine development/service endpoint.
            if not loopback:
                raise HaspelAuthorityUnavailable()
        else:
            try:
                addresses = {ipaddress.ip_address(normalized_host).compressed}
            except ValueError:
                addresses = {
                    str(item[4][0]).split("%", 1)[0]
                    for item in socket.getaddrinfo(
                        hostname,
                        port or 443,
                        type=socket.SOCK_STREAM,
                    )
                }
            if not addresses or not all(_private_address(address) for address in addresses):
                raise HaspelAuthorityUnavailable()

        netloc_host = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
        netloc = netloc_host if port is None else f"{netloc_host}:{port}"
        return urlunsplit((parsed.scheme, netloc, "", "", ""))
    except (OSError, ValueError):
        raise HaspelAuthorityUnavailable() from None


def _nonnegative_count(value: object) -> bool:
    return type(value) is int and 0 <= value <= 10_000_000


def _snapshot(value: object, expected_printer_id: str) -> HaspelAuthoritySnapshot:
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise HaspelAuthorityUnavailable()
    raw = value.get("authority")
    if not isinstance(raw, dict):
        raise HaspelAuthorityUnavailable()
    owner = raw.get("owner")
    printer_id = raw.get("printerId")
    version = raw.get("capabilityVersion")
    revision = raw.get("revision")
    pending = raw.get("pendingCount")
    uncertain = raw.get("uncertainCount")
    active = raw.get("activeCount")
    if (
        type(version) is not int
        or version != 1
        or not isinstance(printer_id, str)
        or printer_id != expected_printer_id
        or not isinstance(owner, str)
        or owner not in _OWNERS
        or type(revision) is not int
        or not 0 <= revision <= 2**53 - 1
        or not all(_nonnegative_count(item) for item in (pending, uncertain, active))
    ):
        raise HaspelAuthorityUnavailable()
    return HaspelAuthoritySnapshot(
        printer_id=printer_id,
        owner=cast(AuthorityOwner, owner),
        revision=revision,
        pending_count=cast(int, pending),
        uncertain_count=cast(int, uncertain),
        active_count=cast(int, active),
        capability_version=version,
    )


def _booking_grams(value: object) -> float:
    if type(value) is int:
        grams = float(value)
    elif type(value) is float:
        grams = value
    else:
        raise HaspelAuthorityUnavailable()
    if not 0 < grams <= 1_000_000_000:
        raise HaspelAuthorityUnavailable()
    return grams


def _booking(value: object, expected_printer_id: str) -> HaspelBookingRecord:
    if not isinstance(value, dict):
        raise HaspelAuthorityUnavailable()
    record_id = value.get("id")
    printer_id = value.get("printerId")
    started_at = value.get("startedAt")
    item_key = value.get("itemKey")
    spool_id = value.get("spoolId")
    grams = _booking_grams(value.get("grams"))
    job_name = value.get("jobName")
    terminal_state = value.get("terminalState")
    status = value.get("status")
    created_at = value.get("createdAt")
    updated_at = value.get("updatedAt")
    resolution = value.get("resolution")
    resolution_note = value.get("resolutionNote")
    if (
        not isinstance(record_id, str)
        or len(record_id) != 64
        or any(char not in "0123456789abcdef" for char in record_id)
        or not isinstance(printer_id, str)
        or printer_id != expected_printer_id
        or type(started_at) is not int
        or not 0 < started_at <= 2**53 - 1
        or not isinstance(item_key, str)
        or not 1 <= len(item_key) <= 200
        or type(spool_id) is not int
        or not 0 < spool_id <= 2**53 - 1
        or (job_name is not None and (not isinstance(job_name, str) or len(job_name) > 500))
        or not isinstance(terminal_state, str)
        or terminal_state not in _TERMINAL_STATES
        or not isinstance(status, str)
        or status not in _BOOKING_STATUSES
        or type(created_at) is not int
        or not 0 < created_at <= 2**53 - 1
        or type(updated_at) is not int
        or not 0 < updated_at <= 2**53 - 1
        or (resolution is not None and (
            not isinstance(resolution, str) or resolution not in _BOOKING_RESOLUTIONS
        ))
        or (resolution_note is not None and (not isinstance(resolution_note, str) or len(resolution_note) > 500))
    ):
        raise HaspelAuthorityUnavailable()
    if resolution is not None:
        expected_status = "booked" if resolution == "applied" else "dismissed"
        if status != expected_status or not isinstance(resolution_note, str) or not resolution_note.strip():
            raise HaspelAuthorityUnavailable()
    elif resolution_note is not None:
        raise HaspelAuthorityUnavailable()
    return HaspelBookingRecord(
        id=record_id,
        printer_id=printer_id,
        started_at=started_at,
        item_key=item_key,
        spool_id=spool_id,
        grams=grams,
        job_name=job_name,
        terminal_state=terminal_state,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        resolution=resolution,
        resolution_note=resolution_note,
    )


def _bookings(value: object, expected_printer_id: str) -> tuple[HaspelBookingRecord, ...]:
    if (
        not isinstance(value, dict)
        or value.get("ok") is not True
        or not isinstance(value.get("bookings"), list)
        or len(value["bookings"]) > 100
    ):
        raise HaspelAuthorityUnavailable()
    return tuple(_booking(item, expected_printer_id) for item in value["bookings"])


class HaspelAuthorityClient:
    """Access one explicitly selected HaspelSync API using an OS-held API key."""

    def __init__(
        self,
        endpoint: str,
        printer_id: str,
        api_key: SecretValue,
    ) -> None:
        if (
            type(printer_id) is not str
            or not 1 <= len(printer_id) <= 200
            or any(ord(char) < 33 for char in printer_id)
            or not isinstance(api_key, SecretValue)
        ):
            raise HaspelAuthorityUnavailable()
        self._endpoint = _validate_endpoint(endpoint)
        self._printer_id = printer_id
        self._api_key = api_key
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def read(self) -> HaspelAuthoritySnapshot:
        payload = self._request("GET")
        return _snapshot(payload, self._printer_id)

    def transfer(self, owner: AuthorityOwner, expected_revision: int) -> HaspelAuthoritySnapshot:
        if (
            not isinstance(owner, str)
            or owner not in _OWNERS
            or type(expected_revision) is not int
            or not 0 <= expected_revision <= 2**53 - 1
        ):
            raise HaspelAuthorityUnavailable()
        payload = self._request(
            "POST",
            {
                "owner": owner,
                "expectedRevision": expected_revision,
                "requestId": str(uuid4()),
            },
        )
        snapshot = _snapshot(payload, self._printer_id)
        if snapshot.owner != owner or snapshot.revision != expected_revision + 1:
            raise HaspelAuthorityUnavailable()
        return snapshot

    def list_bookings(self) -> tuple[HaspelBookingRecord, ...]:
        """Reads the latest bounded journal rows for this exact printer only."""
        payload = self._request("GET", resource="bookings")
        return _bookings(payload, self._printer_id)

    def resolve_booking(
        self, booking_id: str, resolution: str, note: str,
    ) -> HaspelBookingRecord:
        """Records an explicit journal decision without retrying Spoolman consumption."""
        if (
            not isinstance(booking_id, str)
            or len(booking_id) != 64
            or any(char not in "0123456789abcdef" for char in booking_id)
            or not isinstance(resolution, str)
            or resolution not in _BOOKING_RESOLUTIONS
            or not isinstance(note, str)
            or not note.strip()
            or len(note) > 500
        ):
            raise HaspelAuthorityUnavailable()
        before = next((item for item in self.list_bookings() if item.id == booking_id), None)
        if before is None:
            raise HaspelAuthorityConflict()
        if before.status not in {"pending", "uncertain"}:
            if before.resolution == resolution and before.resolution_note == note.strip():
                return before
            raise HaspelAuthorityConflict()
        try:
            self._request(
                "POST",
                {"resolution": resolution, "note": note.strip()},
                resource=f"bookings/{quote(booking_id, safe='')}/resolve",
            )
        except HaspelAuthorityConflict:
            raise
        except HaspelAuthorityUnavailable:
            # The POST may have committed before its response was lost. Only a
            # read can confirm it; never issue another POST from this client.
            try:
                observed = next(
                    (item for item in self.list_bookings() if item.id == booking_id), None,
                )
            except HaspelAuthorityUnavailable:
                raise HaspelBookingResolutionUnknown() from None
            if (
                observed is not None
                and observed.resolution == resolution
                and observed.resolution_note == note.strip()
            ):
                return observed
            raise HaspelBookingResolutionUnknown() from None
        try:
            observed = next((item for item in self.list_bookings() if item.id == booking_id), None)
        except HaspelAuthorityUnavailable:
            raise HaspelBookingResolutionUnknown() from None
        if (
            observed is None
            or observed.resolution != resolution
            or observed.resolution_note != note.strip()
        ):
            raise HaspelBookingResolutionUnknown()
        return observed

    def _request(
        self,
        method: str,
        body: dict[str, object] | None = None,
        *,
        resource: str = "accounting-authority",
    ) -> object:
        printer_segment = quote(self._printer_id, safe="")
        url = f"{self._endpoint}/api/print/{printer_segment}/{resource}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key.reveal()}",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
                content = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(content) > _MAX_RESPONSE_BYTES:
                raise HaspelAuthorityUnavailable()
            payload = json.loads(content.decode("utf-8"))
        except HTTPError as error:
            if error.code == 409:
                raise HaspelAuthorityConflict() from None
            raise HaspelAuthorityUnavailable() from None
        except (URLError, OSError, TimeoutError, UnicodeError, json.JSONDecodeError):
            raise HaspelAuthorityUnavailable() from None
        return payload
