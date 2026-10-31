"""Filament inventory aggregate snapshots."""

from dataclasses import dataclass
from datetime import date

from ufm.domain.entities.base import EntityRecord
from ufm.domain.enums import InventoryHealth, SpoolLifecycle
from ufm.domain.value_objects import EntityId, ExactDecimal, Mass, UtcDateTime


def _nonnegative(value: Mass | None, code: str) -> None:
    if value is not None and value.milligrams < 0:
        raise ValueError(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class Spool(EntityRecord):
    display_name: str
    filament_profile_id: EntityId
    brand_id: EntityId | None = None
    product_line: str | None = None
    batch_number: str | None = None
    lot_number: str | None = None
    color_name: str | None = None
    color_hex: str | None = None
    secondary_color_hex: str | None = None
    image_uri: str | None = None
    notes: str | None = None
    opened_at: UtcDateTime | None = None
    manufactured_at: UtcDateTime | None = None
    expires_at: UtcDateTime | None = None
    lifecycle: SpoolLifecycle = SpoolLifecycle.NEW
    inventory_health: InventoryHealth = InventoryHealth.CONSISTENT
    nominal_filament: Mass | None = None
    empty_spool: Mass | None = None
    purchase_price: ExactDecimal | None = None
    purchase_basis: Mass | None = None
    currency: str | None = None
    purchase_date: str | None = None
    estimated_remaining: Mass | None = None
    measured_remaining: Mass | None = None
    effective_remaining: Mass | None = None
    low_threshold: Mass | None = None
    storage_location_id: EntityId | None = None
    ledger_sequence: int = 0
    archived_at: UtcDateTime | None = None

    def __post_init__(self) -> None:
        super(Spool, self).__post_init__()
        if type(self.display_name) is not str or not self.display_name.strip() or len(self.display_name) > 200:
            raise ValueError("spool.name_invalid")
        for field_name in (
            "product_line", "batch_number", "lot_number", "color_name",
            "color_hex", "secondary_color_hex", "image_uri", "notes",
        ):
            value = getattr(self, field_name)
            if value is not None and type(value) is not str:
                raise TypeError(f"spool.{field_name}_invalid")
        for field_name in ("product_line", "batch_number", "lot_number", "color_name"):
            value = getattr(self, field_name)
            if value is not None and len(value) > 200:
                raise ValueError(f"spool.{field_name}_invalid")
        for field_name in ("color_hex", "secondary_color_hex"):
            value = getattr(self, field_name)
            if value is not None and (
                len(value) not in (7, 9) or value[0] != "#"
                or any(char not in "0123456789abcdefABCDEF" for char in value[1:])
            ):
                raise ValueError(f"spool.{field_name}_invalid")
        if self.image_uri is not None and len(self.image_uri) > 2048:
            raise ValueError("spool.image_uri_invalid")
        if self.notes is not None and len(self.notes) > 4000:
            raise ValueError("spool.notes_invalid")
        if (
            self.manufactured_at is not None and self.expires_at is not None
            and self.expires_at < self.manufactured_at
        ):
            raise ValueError("spool.date_order_invalid")
        _nonnegative(self.nominal_filament, "spool.nominal_mass_invalid")
        _nonnegative(self.empty_spool, "spool.empty_mass_invalid")
        if self.purchase_price is not None:
            if not isinstance(self.purchase_price, ExactDecimal) or self.purchase_price.value < 0:
                raise ValueError("spool.purchase_price_invalid")
            whole, _, fraction = self.purchase_price.canonical().partition(".")
            if len(whole) > 9 or len(fraction) > 2 or len(self.purchase_price.canonical()) > 30:
                raise ValueError("spool.purchase_price_invalid")
        _nonnegative(self.purchase_basis, "spool.purchase_basis_invalid")
        if self.purchase_basis is not None and self.purchase_basis.milligrams == 0:
            raise ValueError("spool.purchase_basis_invalid")
        if self.purchase_basis is not None and self.purchase_price is None:
            raise ValueError("spool.purchase_price_required")
        if self.currency is not None and (
            type(self.currency) is not str or len(self.currency) != 3
            or not self.currency.isascii() or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ValueError("spool.currency_invalid")
        if (self.purchase_price is None) != (self.currency is None):
            raise ValueError("spool.purchase_money_shape_invalid")
        if self.purchase_basis is not None and self.purchase_price is None:
            raise ValueError("spool.purchase_price_required")
        if self.purchase_date is not None:
            if type(self.purchase_date) is not str or len(self.purchase_date) != 10:
                raise ValueError("spool.purchase_date_invalid")
            try:
                parsed_purchase_date = date.fromisoformat(self.purchase_date)
            except ValueError:
                raise ValueError("spool.purchase_date_invalid") from None
            if parsed_purchase_date.isoformat() != self.purchase_date:
                raise ValueError("spool.purchase_date_invalid")
        _nonnegative(self.measured_remaining, "spool.measured_mass_invalid")
        _nonnegative(self.low_threshold, "spool.low_threshold_invalid")
        if type(self.ledger_sequence) is not int or self.ledger_sequence < 0:
            raise ValueError("spool.ledger_sequence_invalid")
        if (self.lifecycle is SpoolLifecycle.ARCHIVED) != (self.archived_at is not None):
            raise ValueError("spool.archived_shape_invalid")
        if (
            self.effective_remaining is not None
            and self.effective_remaining.milligrams < 0
            and self.inventory_health is not InventoryHealth.QUARANTINED
        ):
            raise ValueError("spool.negative_stock_not_quarantined")

    def available(self, active_reservations: Mass) -> Mass | None:
        if active_reservations.milligrams < 0:
            raise ValueError("spool.reservations_invalid")
        if self.effective_remaining is None:
            return None
        return self.effective_remaining - active_reservations
