"""
Shared data models for the forex rate archiver.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, order=True)
class RateRecord:
    """Immutable representation of a single bank's rate reading."""
    bank: str
    label: str
    rate: float
    fetch_date: date = field(default_factory=date.today, compare=False)

    def as_row(self) -> list:
        """Return a flat list suitable for writing to Excel/CSV."""
        return [self.bank, self.label, self.rate, self.fetch_date.isoformat()]

    @classmethod
    def csv_header(cls) -> list[str]:
        return ["Bank", "Slab_Type", "Rate", "Date"]
