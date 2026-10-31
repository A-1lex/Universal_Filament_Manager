"""Slicer parsing port; concrete parsers own no inventory authority."""

from typing import Protocol

from ufm.application.dto import ParseLimits, ProjectInput, SlicerProject


class ParseRejected(ValueError):
    code = "slicer.parse_rejected"

    def __init__(self) -> None:
        super().__init__(self.code)


class SlicerProvider(Protocol):
    def can_parse(self, source: ProjectInput) -> bool: ...

    def parse_project(self, source: ProjectInput, limits: ParseLimits) -> SlicerProject: ...
