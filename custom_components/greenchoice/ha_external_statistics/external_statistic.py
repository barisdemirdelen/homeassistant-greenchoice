"""
external_statistic
==================

Generic, integration-agnostic building block for HA external statistics.

``ExternalStatistic[T]`` bundles a statistic's recorder metadata with the
logic needed to turn a list of raw API entries of type *T* into
``StatisticData`` objects and push them to the HA recorder.

This package contains no integration-specific code and can be copied or
shared across any HA custom integration that writes external statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Generic, TypeVar

from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
    async_add_external_statistics,
)
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class ExternalStatistic(Generic[T]):
    """
    A single HA external statistic — metadata and injection logic bundled together.

    *T* is the raw API entry type supplied by the caller.

    Each instance describes one time-series and knows how to:

    * build a ``StatisticMetaData`` for the recorder,
    * turn a list of raw API entries into ``StatisticData`` objects,
    * inject them into the HA recorder in one call.

    Parameters
    ----------
    statistic_id:
        Fully-qualified statistic ID, e.g. ``"my_domain:electricity_consumed"``.
    name:
        Human-readable name shown in the Energy Dashboard.
    source:
        Source domain of the statistic (typically the integration domain).
    unit_of_measurement:
        Physical unit string, e.g. ``"kWh"``, ``"m³"``, ``"EUR"``, ``"W"``.
    unit_class:
        HA unit class (``"energy"``, ``"volume"``, ``"power"``, …) or ``None``.
    period_start_fn:
        Converts a raw entry and a reference date into a timezone-aware UTC
        ``datetime`` that becomes the ``start`` of the ``StatisticData`` point.
    value_fn:
        Extracts the numeric value from a raw entry.  For sum statistics this
        is the hourly *delta*; for mean-only statistics it becomes the
        ``state`` field (instantaneous snapshot).
    has_sum:
        Whether the statistic accumulates a running sum (default ``True``).
    mean_type:
        Mean type for the statistic (default ``StatisticMeanType.NONE``).
        Set to ``StatisticMeanType.ARITHMETIC`` when providing ``mean_fn``.
    mean_fn:
        Optional. Extracts the average value over the period from a raw entry.
        When provided, ``mean`` is included in every ``StatisticData`` point.
    min_fn:
        Optional. Extracts the minimum value over the period.
    max_fn:
        Optional. Extracts the maximum value over the period.
    """

    statistic_id: str
    name: str
    source: str
    unit_of_measurement: str
    unit_class: str | None
    period_start_fn: Callable[[T, date], datetime] = field(compare=False)
    value_fn: Callable[[T], float] = field(compare=False)
    has_sum: bool = True
    mean_type: StatisticMeanType = field(default=StatisticMeanType.NONE)
    mean_fn: Callable[[T], float] | None = field(default=None, compare=False)
    min_fn: Callable[[T], float] | None = field(default=None, compare=False)
    max_fn: Callable[[T], float] | None = field(default=None, compare=False)

    @property
    def metadata(self) -> StatisticMetaData:
        """Return the ``StatisticMetaData`` for this statistic."""
        return StatisticMetaData(
            mean_type=self.mean_type,
            has_sum=self.has_sum,
            name=self.name,
            source=self.source,
            statistic_id=self.statistic_id,
            unit_class=self.unit_class,
            unit_of_measurement=self.unit_of_measurement,
        )

    def build_stat_data(
        self,
        entries: list[T],
        for_date: date,
        seed_sum: float = 0.0,
    ) -> tuple[list[StatisticData], float]:
        """
        Build ``StatisticData`` objects from *entries* for *for_date*.

        Returns ``(stat_data, end_sum)`` where *end_sum* is the running total
        at the end of the day, ready to seed the next consecutive day.
        When ``has_sum`` is ``False``, *seed_sum* / *end_sum* are meaningless
        (passed through unchanged).
        """
        running_sum = seed_sum
        stat_data: list[StatisticData] = []
        for entry in entries:
            start_utc = self.period_start_fn(entry, for_date)
            value = self.value_fn(entry)

            point: dict = {"start": start_utc, "state": value}

            if self.has_sum:
                running_sum += value
                point["sum"] = running_sum

            if self.mean_fn is not None:
                point["mean"] = self.mean_fn(entry)
            if self.min_fn is not None:
                point["min"] = self.min_fn(entry)
            if self.max_fn is not None:
                point["max"] = self.max_fn(entry)

            stat_data.append(point)  # type: ignore[arg-type]

        return stat_data, running_sum

    def inject(
        self,
        hass: HomeAssistant,
        entries: list[T],
        for_date: date,
        seed_sum: float = 0.0,
    ) -> float:
        """
        Build and inject statistics for *for_date* into the HA recorder.

        Returns the running sum at end-of-day for chaining across consecutive
        days without extra database queries.  When ``has_sum`` is ``False``
        the return value equals *seed_sum* (no accumulation).
        """
        stat_data, end_sum = self.build_stat_data(entries, for_date, seed_sum)

        if stat_data:
            if self.has_sum:
                _LOGGER.debug(
                    "Injecting %d entries for %s on %s (sum: %.4f → %.4f)",
                    len(stat_data),
                    self.statistic_id,
                    for_date,
                    seed_sum,
                    end_sum,
                )
            else:
                _LOGGER.debug(
                    "Injecting %d entries for %s on %s",
                    len(stat_data),
                    self.statistic_id,
                    for_date,
                )
            async_add_external_statistics(hass, self.metadata, stat_data)
        else:
            _LOGGER.debug(
                "Skipping %s on %s — no entries.",
                self.statistic_id,
                for_date,
            )

        return end_sum
