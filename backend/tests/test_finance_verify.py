"""Citation-faithfulness verifier + advice guardrails."""

from __future__ import annotations

from decimal import Decimal

from app.finance.guardrails import is_advice_request
from app.finance.verify import extract_numbers, is_faithful, unverified_numbers

# ── extract_numbers ──────────────────────────────────────────────────────────


def test_extracts_scaled_and_percent_numbers():
    mentions = extract_numbers("Revenue was $94.9 billion, up 6.1% from last year.")
    values = {m.value for m in mentions}
    assert Decimal("94900000000") in values
    assert Decimal("6.1") in values


def test_ignores_years_citations_and_period_labels():
    text = "In Q3 FY2024, revenue grew [1] compared with 2023 levels."
    assert extract_numbers(text) == []


def test_plain_dollar_amount_with_separators():
    (m,) = extract_numbers("Net sales were $94,930 million.")
    assert m.value == Decimal("94930000000")


# ── unverified_numbers ───────────────────────────────────────────────────────

ALLOWED = [Decimal("94930000000"), Decimal("6.069")]


def test_faithful_when_all_numbers_backed():
    text = "Revenue was $94.9 billion [1], up 6.1% year over year."
    # 94.9B is within 0.5% of the fact; 6.1 within tolerance of computed 6.069.
    assert is_faithful(text, ALLOWED)


def test_fabricated_number_is_flagged():
    text = "Revenue was $94.9 billion and operating costs fell 12.5%."
    bad = unverified_numbers(text, ALLOWED)
    assert [m.value for m in bad] == [Decimal("12.5")]


def test_wrong_magnitude_is_flagged():
    # "$9.5 billion" is NOT the backed 94.93B — must not silently pass.
    bad = unverified_numbers("Revenue was $9.5 billion.", ALLOWED)
    assert len(bad) == 1


def test_scale_renditions_of_backed_value_pass():
    # The same backed value narrated in millions.
    assert is_faithful("Revenue was 94,930 million.", ALLOWED)


# ── guardrails ───────────────────────────────────────────────────────────────


def test_advice_requests_detected():
    for q in (
        "Should I buy Apple stock?",
        "Is NVDA a good investment right now?",
        "What's your price target for MSFT?",
        "Which stocks should I buy this quarter?",
        "Do you recommend selling my shares?",
        "Will the stock go up after earnings?",
    ):
        assert is_advice_request(q), q


def test_factual_questions_pass():
    for q in (
        "What was Apple's revenue in Q3 FY2024?",
        "Why did gross margin decline year over year?",
        "Summarize the risk factors in the latest 10-K.",
        "How much did the company spend on R&D?",
    ):
        assert not is_advice_request(q), q
