"""Chart-of-accounts mapping: conservative, exact-synonym only."""

from __future__ import annotations

from app.core.finance import StatementType
from app.finance.chart import map_line_item, normalize_label


def test_revenue_synonyms_map():
    for label in ("Revenue", "Net sales", "Total net sales", "TOTAL REVENUES",
                  "Revenues", "Net revenue"):
        item = map_line_item(label)
        assert item is not None, label
        assert item.canonical == "revenue"


def test_footnote_markers_and_punctuation_stripped():
    assert normalize_label("Total revenue (1)") == "total revenue"
    assert normalize_label("Net sales*") == "net sales"
    assert map_line_item("Total revenue (1)").canonical == "revenue"


def test_statement_and_unit_metadata():
    assert map_line_item("Total assets").statement is StatementType.BALANCE
    assert map_line_item("Diluted EPS").unit == "per_share"


def test_unknown_labels_do_not_map():
    # Conservative: similar-but-not-synonym labels stay unmapped.
    for label in ("Revenue from widgets", "Adjusted EBITDA", "Total costs and expenses"):
        assert map_line_item(label) is None
