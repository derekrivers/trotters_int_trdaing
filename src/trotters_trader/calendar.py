from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TradingCalendar:
    dates: tuple[date, ...]

    def next_date(self, current_date: date) -> date | None:
        for index, item in enumerate(self.dates):
            if item == current_date:
                if index + 1 >= len(self.dates):
                    return None
                return self.dates[index + 1]
        return None
