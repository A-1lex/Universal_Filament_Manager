import inspect
import unittest
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from ufm.application.dto import CurrentJobObservation, Observed
from ufm.application.ports import PrinterControl, PrinterProvider, ProviderError
from ufm.domain.enums import Availability
from ufm.domain.value_objects import UtcDateTime


def now() -> UtcDateTime:
    return UtcDateTime(datetime(2026, 9, 10, tzinfo=UTC))


class ObservationContractTests(unittest.TestCase):
    def test_known_false_differs_from_unknown_and_unavailable(self) -> None:
        known_false = Observed(Availability.KNOWN, now(), now(), False)
        self.assertIs(known_false.value, False)
        for availability in (Availability.UNKNOWN, Availability.UNAVAILABLE, Availability.UNSUPPORTED):
            with self.subTest(availability=availability):
                self.assertIsNone(Observed[bool](availability, now(), now()).value)
                with self.assertRaises(ValueError):
                    Observed(availability, now(), now(), False)

    def test_only_known_none_means_confirmed_idle(self) -> None:
        idle = CurrentJobObservation(Availability.KNOWN, now(), now())
        unavailable = CurrentJobObservation(Availability.UNAVAILABLE, now(), now())
        self.assertIsNone(idle.job)
        self.assertIsNone(unavailable.job)
        self.assertIs(idle.availability, Availability.KNOWN)
        self.assertIsNot(unavailable.availability, Availability.KNOWN)

    def test_known_generic_observation_requires_a_value(self) -> None:
        with self.assertRaises(ValueError):
            Observed[bool](Availability.KNOWN, now(), now())


class ProviderPortTests(unittest.TestCase):
    def test_subscription_is_direct_async_iterator_not_coroutine(self) -> None:
        self.assertFalse(inspect.iscoroutinefunction(PrinterProvider.subscribe_events))
        self.assertTrue(inspect.iscoroutinefunction(PrinterProvider.connect))
        self.assertTrue(issubclass(AsyncIterator, object))

    def test_monitoring_and_control_authority_are_separate(self) -> None:
        self.assertFalse(hasattr(PrinterProvider, "pause"))
        self.assertTrue(hasattr(PrinterControl, "pause"))

    def test_provider_error_is_stable_and_sanitized(self) -> None:
        error = ProviderError("provider.unavailable", retryable=True)
        self.assertEqual(str(error), "provider.unavailable")
        self.assertTrue(error.retryable)
