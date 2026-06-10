"""FX: ECB feed parsing + pure conversion/cross-rate math."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.finance.fx import convert, cross_rate, parse_ecb_rates

ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2026-06-09">
      <Cube currency="USD" rate="1.0840"/>
      <Cube currency="GBP" rate="0.8420"/>
    </Cube>
    <Cube time="2026-06-08">
      <Cube currency="USD" rate="1.0810"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""


def test_parse_ecb_rates():
    rows = parse_ecb_rates(ECB_XML)
    assert (date(2026, 6, 9), "EUR", "USD", Decimal("1.0840")) in rows
    assert (date(2026, 6, 9), "EUR", "GBP", Decimal("0.8420")) in rows
    assert (date(2026, 6, 8), "EUR", "USD", Decimal("1.0810")) in rows
    assert len(rows) == 3


def test_cross_rate_via_eur():
    # USD→GBP = (EUR→GBP) / (EUR→USD)
    rate = cross_rate(Decimal("1.0840"), Decimal("0.8420"))
    assert rate == Decimal("0.8420") / Decimal("1.0840")
    with pytest.raises(ValueError):
        cross_rate(Decimal("0"), Decimal("1"))


def test_convert_quantizes_money():
    rate = cross_rate(Decimal("1.0840"), Decimal("0.8420"))
    converted = convert(Decimal("94930000000"), rate)
    assert converted == (Decimal("94930000000") * rate).quantize(Decimal("0.01"))
    assert convert(Decimal("100"), Decimal("0.9215")) == Decimal("92.15")
