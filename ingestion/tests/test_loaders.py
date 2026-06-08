"""Loader extraction: title + text for each supported filetype."""

from __future__ import annotations

from ingestion.pipeline.loaders import filetype_for, load_document


def test_markdown_title_from_h1():
    data = b"# Onboarding Guide\n\nWelcome aboard. Reset your password here."
    title, text = load_document(data, "onboarding.md")
    assert title == "Onboarding Guide"
    assert "Reset your password" in text


def test_text_title_from_filename():
    data = b"Expenses are reimbursed within 30 days."
    title, text = load_document(data, "expense_policy.txt")
    assert title == "expense policy"
    assert "reimbursed" in text


def test_html_title_and_text_strips_tags():
    data = (
        b"<html><head><title>VPN</title></head>"
        b"<body><p>Use the client.</p><script>x()</script></body></html>"
    )
    title, text = load_document(data, "vpn.html")
    assert title == "VPN"
    assert "Use the client." in text
    assert "x()" not in text  # script content removed


def test_filetype_normalization():
    assert filetype_for("a.HTM") == "html"
    assert filetype_for("b.markdown") == "md"
    assert filetype_for("c.TXT") == "txt"
