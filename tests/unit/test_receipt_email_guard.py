"""Receipts must not republish participant addresses in the public repository."""

from pathlib import Path

import pytest

from scripts.check_receipt_emails import find_email_lines, main

pytestmark = pytest.mark.unit


def test_rejects_an_unapproved_address_without_echoing_it(tmp_path, capsys):
    receipt = tmp_path / "receipt.json"
    address = "participant@unapproved-domain.com"
    receipt.write_text('{"email": "' + address + '"}\n')

    assert main([str(receipt)]) == 1
    diagnostic = capsys.readouterr().err
    assert f"{receipt}:1" in diagnostic
    assert address not in diagnostic
    assert "unapproved-domain.com" not in diagnostic


@pytest.mark.parametrize("address", [
    "owner@deniedart.com", "hello@aquex.ai", "verify@tracelab.aquex.ai",
    "fixture@tracelab.local", "person@example.com", "person@example.org",
    "person@example.net", "person@example.test", "person@unit.invalid",
])
def test_owner_and_reserved_example_domains_are_allowed(address):
    assert find_email_lines(address) == []


@pytest.mark.parametrize("address", [
    "person@notexample.com", "person@example.com.attacker.org",
    "person@aquex.ai.attacker.org", "person@deniedart.com.attacker.org",
])
def test_allowlist_cannot_be_bypassed_with_a_similar_domain(address):
    assert find_email_lines(address) == [1]


def test_package_versions_are_not_email_addresses():
    assert find_email_lines("tracelab@1.2.3 @scope/tokens@0.1.0") == []


def test_sentence_punctuation_does_not_hide_an_address():
    assert find_email_lines("Contact person@unapproved-domain.com.") == [1]


def test_a_missing_receipt_fails_loudly(tmp_path, capsys):
    assert main([str(tmp_path / "missing.json")]) == 2
    assert "unable to read" in capsys.readouterr().err


def test_tracked_mode_checks_nested_receipts_but_not_application_fixtures(tmp_path, monkeypatch):
    from scripts import check_receipt_emails

    monkeypatch.chdir(tmp_path)
    receipt = Path("cmos/reports/sprint-66/fixture/receipt.json")
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"email":"person@unapproved-domain.com"}')
    fixture = Path("tests/fixture.json")
    fixture.parent.mkdir()
    fixture.write_text(receipt.read_text())
    monkeypatch.setattr(check_receipt_emails, "_tracked_paths", lambda: [receipt, fixture])
    assert main(["--tracked"]) == 1

    receipt.write_text('{"email":"participant@example.com"}')
    assert main(["--tracked"]) == 0
