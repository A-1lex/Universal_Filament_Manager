"""Normalized scale readings with explicit knowledge and calibration scope."""

from dataclasses import dataclass

from ufm.application.dto.providers import Observed
from ufm.domain.value_objects import EntityId, Mass, UtcDateTime


@dataclass(frozen=True, slots=True)
class WeightReading:
    sensor_id: EntityId
    associated_spool_id: EntityId | None
    gross_mass: Observed[Mass]
    tare_mass: Observed[Mass]
    net_mass: Observed[Mass]
    stable: Observed[bool]
    interval_start: UtcDateTime
    interval_end: UtcDateTime
    observed_at: UtcDateTime
    received_at: UtcDateTime
    calibration_id: EntityId | None = None
    calibration_version: int | None = None

    def __post_init__(self) -> None:
        for observation in (self.gross_mass, self.tare_mass, self.net_mass):
            if observation.value is not None and not isinstance(observation.value, Mass):
                raise TypeError("weight_reading.mass_invalid")
        if self.stable.value is not None and type(self.stable.value) is not bool:
            raise TypeError("weight_reading.stability_invalid")
        if self.interval_end < self.interval_start:
            raise ValueError("weight_reading.interval_invalid")
        if (self.calibration_id is None) != (self.calibration_version is None):
            raise ValueError("weight_reading.calibration_scope_invalid")
        if self.calibration_version is not None and (
            type(self.calibration_version) is not int or self.calibration_version < 1
        ):
            raise ValueError("weight_reading.calibration_version_invalid")
        gross = self.gross_mass.value
        tare = self.tare_mass.value
        net = self.net_mass.value
        if gross is not None and tare is not None and net is not None and gross - tare != net:
            raise ValueError("weight_reading.mass_relation_invalid")


@dataclass(frozen=True, slots=True)
class TareResult:
    accepted: bool
    observed_at: UtcDateTime
    received_at: UtcDateTime
    reason_code: str

    def __post_init__(self) -> None:
        if type(self.accepted) is not bool:
            raise TypeError("tare_result.accepted_invalid")
        if type(self.reason_code) is not str or not self.reason_code or len(self.reason_code) > 500:
            raise ValueError("tare_result.reason_invalid")
