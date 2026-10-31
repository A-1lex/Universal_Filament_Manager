"""Observed package license metadata is collected without legal interpretation."""

import unittest
from email.message import Message

from scripts.collect_studio_notices import _observed_license_metadata


class ObservedLicenseMetadataTests(unittest.TestCase):
    @staticmethod
    def observe(metadata: Message) -> str:
        return _observed_license_metadata(
            metadata.get("License-Expression"),
            metadata.get("License"),
            metadata.get_all("Classifier", []),
        )

    def test_expression_takes_precedence_over_license_and_classifiers(self) -> None:
        metadata = Message()
        metadata["License-Expression"] = "MIT"
        metadata["License"] = "Other"
        metadata.add_header("Classifier", "License :: OSI Approved :: BSD License")

        self.assertEqual(self.observe(metadata), "MIT")

    def test_license_field_takes_precedence_over_classifiers(self) -> None:
        metadata = Message()
        metadata["License"] = "BSD-3-Clause"
        metadata.add_header("Classifier", "License :: OSI Approved :: MIT License")

        self.assertEqual(self.observe(metadata), "BSD-3-Clause")

    def test_classifier_fallback_is_explicit_and_deterministic(self) -> None:
        metadata = Message()
        metadata.add_header("Classifier", "License :: OSI Approved :: BSD License")
        metadata.add_header("Classifier", "License :: OSI Approved :: MIT License")
        metadata.add_header("Classifier", "License :: OSI Approved :: MIT License")

        self.assertEqual(
            self.observe(metadata),
            "Classifier metadata only: OSI Approved :: BSD License | OSI Approved :: MIT License",
        )

    def test_missing_license_metadata_stays_unspecified(self) -> None:
        self.assertEqual(self.observe(Message()), "not specified")


if __name__ == "__main__":
    unittest.main()
