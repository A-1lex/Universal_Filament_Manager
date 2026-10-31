"""Reservation lifecycle commands with serialized capacity acquisition."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace

from ufm.application.ports.persistence import (
    IdempotencyConflict,
    NotFound,
    RevisionConflict,
    UnitOfWork,
)
from ufm.domain.entities import AuditEvent, Reservation
from ufm.domain.enums import FinalizationState, PrintStatus, ReservationState
from ufm.domain.policies.accounting import reservation_settlement
from ufm.domain.policies.transitions import validate_transition
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime

UnitOfWorkFactory = Callable[[], UnitOfWork]

_EXPIRY_ELIGIBLE = frozenset({PrintStatus.DETECTED, PrintStatus.PREPARING})


class ReservationCommands:
    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def reserve(
        self,
        *,
        reservation_id: EntityId,
        spool_id: EntityId,
        material_id: EntityId,
        amount: Mass,
        actor_device_id: EntityId,
        command_key: str,
        activate: bool,
        expected_spool_revision: int | None = None,
        expires_at: UtcDateTime | None = None,
        at: UtcDateTime | None = None,
    ) -> Reservation:
        occurred_at = at or UtcDateTime.now()
        if amount.milligrams <= 0:
            raise ValueError("reservation.mass_invalid")
        fingerprint = self._fingerprint(
            operation="reserve", reservation_id=str(reservation_id), spool_id=str(spool_id),
            material_id=str(material_id), amount=amount.milligrams, actor=str(actor_device_id),
            activate=activate, expected_spool_revision=expected_spool_revision,
            expires_at=None if expires_at is None else expires_at.value.isoformat(),
        )
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "reservation.created", reservation_id, fingerprint)
            if replay is not None:
                return replay
            try:
                existing = work.reservations.get(reservation_id)
            except NotFound:
                existing = None
            if existing is not None:
                raise IdempotencyConflict()
            spool = work.spools.get(spool_id)
            if activate:
                if expected_spool_revision is None or spool.revision != expected_spool_revision:
                    raise RevisionConflict()
                state, activated_at = ReservationState.ACTIVE, occurred_at
            else:
                state, activated_at = ReservationState.PENDING, None
            reservation = Reservation(
                id=reservation_id, device_id=actor_device_id, created_at=occurred_at,
                updated_at=occurred_at, revision=1, spool_id=spool_id,
                print_job_material_id=material_id, reserved=amount, state=state,
                activated_at=activated_at, expires_at=expires_at,
            )
            work.reservations.add(reservation)
            self._audit(work, reservation, actor_device_id, command_key, occurred_at,
                        "reservation.created", fingerprint=fingerprint)
            work.commit()
            return reservation

    def activate(
        self,
        *,
        reservation_id: EntityId,
        expected_revision: int,
        expected_spool_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Reservation:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="activate", reservation_id=str(reservation_id),
            expected_revision=expected_revision, expected_spool_revision=expected_spool_revision,
            actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "reservation.activated", reservation_id, fingerprint)
            if replay is not None:
                return replay
            current = work.reservations.get(reservation_id)
            if current.state is ReservationState.ACTIVE:
                raise IdempotencyConflict()
            spool = work.spools.get(current.spool_id)
            if spool.revision != expected_spool_revision:
                raise RevisionConflict()
            state = validate_transition(current.state, ReservationState.ACTIVE)
            updated = replace(
                current, state=state, activated_at=occurred_at,
                updated_at=occurred_at, revision=current.revision + 1,
            )
            work.reservations.save(updated, expected_revision)
            self._audit(work, updated, actor_device_id, command_key, occurred_at,
                        "reservation.activated", fingerprint=fingerprint)
            work.commit()
            return updated

    def resize(
        self,
        *,
        reservation_id: EntityId,
        new_reservation_id: EntityId,
        amount: Mass,
        expected_revision: int,
        expected_spool_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Reservation:
        occurred_at = at or UtcDateTime.now()
        if new_reservation_id == reservation_id:
            raise ValueError("reservation.resize_requires_new_id")
        if amount.milligrams <= 0:
            raise ValueError("reservation.mass_invalid")
        fingerprint = self._fingerprint(
            operation="resize", reservation_id=str(reservation_id),
            new_reservation_id=str(new_reservation_id), amount=amount.milligrams,
            expected_revision=expected_revision, expected_spool_revision=expected_spool_revision,
            actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay(
                work, command_key, "reservation.resized", new_reservation_id, fingerprint,
            )
            if replay is not None:
                return replay
            try:
                existing = work.reservations.get(new_reservation_id)
            except NotFound:
                existing = None
            if existing is not None:
                raise IdempotencyConflict()
            current = work.reservations.get(reservation_id)
            if current.state not in {ReservationState.PENDING, ReservationState.ACTIVE}:
                raise ValueError("reservation.resize_requires_open")
            if current.state is ReservationState.ACTIVE:
                self._require_unused_job(work, current, "reservation.resize_job_protected")
            spool = work.spools.get(current.spool_id)
            if spool.revision != expected_spool_revision:
                raise RevisionConflict()
            released = replace(
                current, state=ReservationState.RELEASED, released_at=occurred_at,
                reason="resized", updated_at=occurred_at, revision=current.revision + 1,
            )
            work.reservations.save(released, expected_revision)
            active = current.state is ReservationState.ACTIVE
            replacement = Reservation(
                id=new_reservation_id, device_id=actor_device_id, created_at=occurred_at,
                updated_at=occurred_at, revision=1, spool_id=current.spool_id,
                print_job_material_id=current.print_job_material_id, reserved=amount,
                state=ReservationState.ACTIVE if active else ReservationState.PENDING,
                activated_at=occurred_at if active else None,
                expires_at=current.expires_at, reason="resize_replacement",
            )
            work.reservations.add(replacement)
            self._audit(
                work, replacement, actor_device_id, command_key, occurred_at,
                "reservation.resized",
                fingerprint=fingerprint,
            )
            work.commit()
            return replacement

    def release(
        self,
        *,
        reservation_id: EntityId,
        expected_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        reason: str,
        at: UtcDateTime | None = None,
    ) -> Reservation:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="release", reservation_id=str(reservation_id), expected_revision=expected_revision,
            actor=str(actor_device_id), reason=reason,
        )
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "reservation.released", reservation_id, fingerprint)
            if replay is not None:
                return replay
            current = work.reservations.get(reservation_id)
            if current.state is ReservationState.RELEASED:
                raise IdempotencyConflict()
            if current.state is ReservationState.ACTIVE:
                self._require_unused_job(work, current, "reservation.release_job_protected")
            state = validate_transition(current.state, ReservationState.RELEASED)
            updated = replace(
                current, state=state, released_at=occurred_at, reason=reason,
                updated_at=occurred_at, revision=current.revision + 1,
            )
            work.reservations.save(updated, expected_revision)
            self._audit(work, updated, actor_device_id, command_key, occurred_at,
                        "reservation.released", fingerprint=fingerprint)
            work.commit()
            return updated

    def expire(
        self,
        *,
        reservation_id: EntityId,
        expected_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Reservation:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="expire", reservation_id=str(reservation_id), expected_revision=expected_revision,
            actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "reservation.expired", reservation_id, fingerprint)
            if replay is not None:
                return replay
            current = work.reservations.get(reservation_id)
            if current.state is ReservationState.EXPIRED:
                raise IdempotencyConflict()
            if current.expires_at is None or occurred_at < current.expires_at:
                raise ValueError("reservation.not_expired")
            self._require_unused_job(work, current, "reservation.expiry_job_protected")
            state = validate_transition(current.state, ReservationState.EXPIRED)
            updated = replace(
                current, state=state, reason="expired",
                updated_at=occurred_at, revision=current.revision + 1,
            )
            work.reservations.save(updated, expected_revision)
            self._audit(work, updated, actor_device_id, command_key, occurred_at,
                        "reservation.expired", fingerprint=fingerprint)
            work.commit()
            return updated

    def settle(
        self,
        *,
        reservation_id: EntityId,
        finalization_id: EntityId,
        actual: Mass,
        expected_revision: int,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime | None = None,
    ) -> Reservation:
        occurred_at = at or UtcDateTime.now()
        fingerprint = self._fingerprint(
            operation="settle", reservation_id=str(reservation_id), finalization_id=str(finalization_id),
            actual=actual.milligrams, expected_revision=expected_revision, actor=str(actor_device_id),
        )
        with self._unit_of_work() as work:
            replay = self._replay(work, command_key, "reservation.settled", reservation_id, fingerprint)
            if replay is not None:
                return replay
            current = work.reservations.get(reservation_id)
            if current.settled_finalization_id is not None:
                raise IdempotencyConflict()
            if current.state is not ReservationState.ACTIVE:
                raise ValueError("reservation.settlement_requires_active")
            work.finalizations.get(finalization_id)
            allocated, released = reservation_settlement(current.reserved, actual)
            if allocated.milligrams == 0:
                state = validate_transition(current.state, ReservationState.RELEASED)
                updated = replace(
                    current, state=state, released_at=occurred_at,
                    settled_finalization_id=finalization_id,
                    allocated_consumption=allocated, released=released,
                    reason="zero_consumption", updated_at=occurred_at,
                    revision=current.revision + 1,
                )
            else:
                state = validate_transition(current.state, ReservationState.CONSUMED)
                updated = replace(
                    current, state=state, consumed_at=occurred_at,
                    settled_finalization_id=finalization_id,
                    allocated_consumption=allocated, released=released,
                    updated_at=occurred_at, revision=current.revision + 1,
                )
            work.reservations.save(updated, expected_revision)
            self._audit(work, updated, actor_device_id, command_key, occurred_at,
                        "reservation.settled", fingerprint=fingerprint)
            work.commit()
            return updated

    @staticmethod
    def _require_unused_job(work: UnitOfWork, claim: Reservation, code: str) -> None:
        job = work.jobs.for_material(claim.print_job_material_id)
        if (
            job.status not in _EXPIRY_ELIGIBLE
            or job.started_at is not None
            or job.finalization_state is not FinalizationState.NOT_STARTED
        ):
            raise ValueError(code)

    @staticmethod
    def _fingerprint(**values: str | int | bool | None) -> str:
        encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _replay(
        work: UnitOfWork, command_key: str, event_code: str,
        reservation_id: EntityId, fingerprint: str,
    ) -> Reservation | None:
        events = work.audit.for_command(command_key)
        if not events:
            return None
        if len(events) != 1:
            raise IdempotencyConflict()
        event = events[0]
        if (
            event.event_code != event_code or event.entity_type != "reservation"
            or event.entity_id != reservation_id
            or json.loads(event.parameters_json) != {"request_hash_v1": fingerprint}
        ):
            raise IdempotencyConflict()
        return work.reservations.get(reservation_id)

    @staticmethod
    def _audit(
        work: UnitOfWork,
        reservation: Reservation,
        actor_device_id: EntityId,
        command_key: str,
        at: UtcDateTime,
        event_code: str,
        *,
        fingerprint: str | None = None,
    ) -> None:
        work.audit.append(AuditEvent(
            id=EntityId.new(), device_id=actor_device_id, created_at=at,
            event_code=event_code, actor_device_id=actor_device_id,
            correlation_id=command_key, entity_type="reservation",
            entity_id=reservation.id,
            parameters_json=("{}" if fingerprint is None else
                             json.dumps({"request_hash_v1": fingerprint}, sort_keys=True)),
        ))
