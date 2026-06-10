"""FX conversion helpers + ECB reference-rate parsing.

Rates come from the ECB daily reference feed (EUR-based; free, no key) loaded
by `python -m ingestion.pipeline.fx_load`. Conversion is **annotated, never
silent**: callers attach the rate and its as-of date next to the converted
value so a reader can always see what was applied (see /metrics `converted`).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def convert(value: Decimal, rate: Decimal) -> Decimal:
    """value × rate, money-quantized (2 decimals, half-up)."""
    return (value * rate).quantize(_CENT, ROUND_HALF_UP)


def cross_rate(eur_to_base: Decimal, eur_to_quote: Decimal) -> Decimal:
    """base→quote derived from two EUR-based reference rates."""
    if eur_to_base == 0:
        raise ValueError("zero base rate")
    return eur_to_quote / eur_to_base


def parse_ecb_rates(xml_bytes: bytes) -> list[tuple[date, str, str, Decimal]]:
    """(rate_date, "EUR", currency, rate) rows from an ECB reference XML
    (daily or 90-day history — same envelope format)."""
    root = ET.fromstring(xml_bytes)
    ns = "{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}"
    rows: list[tuple[date, str, str, Decimal]] = []
    for day_cube in root.iter(f"{ns}Cube"):
        day = day_cube.get("time")
        if not day:
            continue
        rate_date = date.fromisoformat(day)
        for rate_cube in day_cube:
            currency = rate_cube.get("currency")
            rate = rate_cube.get("rate")
            if currency and rate:
                rows.append((rate_date, "EUR", currency, Decimal(rate)))
    return rows
