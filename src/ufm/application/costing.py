"""Immutable purchase-cost snapshots for confirmed filament debits."""

from typing import Any

from ufm.domain.entities import Spool
from ufm.domain.value_objects import ExactDecimal, Mass

# These are the currencies supported by the current HaspelSync price workflow.
# Other 3-letter codes remain valid catalogue metadata, but are not priced until
# their minor-unit precision is explicitly defined.
_TWO_DECIMAL_CURRENCIES = frozenset({"UAH", "EUR", "USD", "PLN"})
_MAX_MINOR_UNITS = 9_000_000_000_000_000


def _minor_units(value: ExactDecimal) -> int | None:
    """Round a nonnegative exact price to cents without a float/context path."""
    decimal = value.value
    sign, digits, exponent = decimal.as_tuple()
    if sign or not isinstance(exponent, int):
        return None
    coefficient = int("".join(str(digit) for digit in digits) or "0")
    shift = exponent + 2
    if shift >= 0:
        result = coefficient * (10 ** shift)
    else:
        divisor = 10 ** (-shift)
        quotient, remainder = divmod(coefficient, divisor)
        result = quotient + (1 if remainder * 2 >= divisor else 0)
    return result if result <= _MAX_MINOR_UNITS else None


def confirmed_consumption_cost(
    spool: Spool, consumed: Mass,
) -> tuple[ExactDecimal, str, dict[str, Any]] | None:
    """Return a booking-time total-cost snapshot, or None if profile is incomplete."""
    if (spool.purchase_price is None or spool.purchase_basis is None
        or spool.currency not in _TWO_DECIMAL_CURRENCIES or consumed.milligrams <= 0):
        return None
    price_minor = _minor_units(spool.purchase_price)
    basis_mg = spool.purchase_basis.milligrams
    if price_minor is None or basis_mg <= 0:
        return None
    # Integer half-up rounding mirrors HaspelSync and avoids binary floating point.
    cost_minor = (2 * price_minor * consumed.milligrams + basis_mg) // (2 * basis_mg)
    if cost_minor > _MAX_MINOR_UNITS:
        return None
    amount = ExactDecimal.parse(f"{cost_minor // 100}.{cost_minor % 100:02d}")
    snapshot = {
        "version": 1,
        "price_minor": price_minor,
        "basis_mg": basis_mg,
        "consumed_mg": consumed.milligrams,
        "cost_minor": cost_minor,
        "purchase_date": spool.purchase_date,
    }
    return amount, spool.currency, snapshot


def with_cost_snapshot(
    spool: Spool, consumed: Mass, metadata_json: str,
) -> tuple[ExactDecimal | None, str | None, str]:
    """Preserve existing provenance while appending an optional frozen cost."""
    import json

    result = confirmed_consumption_cost(spool, consumed)
    if result is None:
        return None, None, metadata_json
    amount, currency, snapshot = result
    metadata = json.loads(metadata_json)
    metadata["cost_snapshot_v1"] = snapshot
    return amount, currency, json.dumps(metadata, sort_keys=True, separators=(",", ":"))
