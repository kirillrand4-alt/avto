# FILE: sender/tests/test_validation.py
"""Unit tests for sender.validation.

Network (DNS/SMTP) is always mocked via monkeypatching the private
resolution/probe methods; no external calls are made. There is no store
dependency in this module, so no sqlite fixture is required here.
"""

from __future__ import annotations

import sys
import pathlib

# Ensure the repo root (parent of the `sender` package) is importable.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest

from sender.validation import Validation, ValidationResult, ValidationError
from sender.validation import _ResolverError  # internal, used to simulate failure


class FakeConfig:
    """Minimal Config stand-in exposing only the `get` accessor used here."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, dotted_key, default=None):
        return self._data.get(dotted_key, default)


def make_validation(**overrides) -> Validation:
    data = {
        "validation.check_mx": True,
        "validation.detect_catch_all": True,
        "validation.detect_role": True,
        "validation.detect_disposable": True,
        "validation.role_prefixes": ["info", "sales", "office", "admin", "support", "mail"],
        "validation.smtp_probe": False,
    }
    data.update(overrides)
    return Validation(FakeConfig(data))


def stub_mx(hosts):
    """Return a callable replacing Validation._resolve_mx."""
    return lambda domain: list(hosts)


# --------------------------------------------------------------------------
# detect_provider
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "domain,expected",
    [
        ("gmail.com", "google"),
        ("GMAIL.COM", "google"),
        ("googlemail.com", "google"),
        ("yandex.ru", "yandex"),
        ("ya.ru", "yandex"),
        ("mail.ru", "mailru"),
        ("bk.ru", "mailru"),
        ("outlook.com", "outlook"),
        ("hotmail.com", "outlook"),
        ("vk.com", "vk"),
    ],
)
def test_detect_provider_direct(domain, expected):
    v = make_validation()
    # Direct consumer-domain map must resolve without touching the network.
    v._resolve_mx = lambda d: pytest.fail("MX lookup must not run for known domains")
    assert v.detect_provider(domain) == expected


@pytest.mark.parametrize(
    "mx,expected",
    [
        (["aspmx.l.google.com"], "google"),
        (["mx.yandex.net"], "yandex"),
        (["emx.mail.ru"], "mailru"),
        (["acme-ru.mail.protection.outlook.com"], "outlook"),
        (["mx.vk.example"], "vk"),
    ],
)
def test_detect_provider_via_mx(monkeypatch, mx, expected):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(mx))
    assert v.detect_provider("acme.example") == expected


def test_detect_provider_other_for_unknown_mx(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.customhost.net"]))
    assert v.detect_provider("acme.example") == "other"


def test_detect_provider_unknown_when_no_mx(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx([]))
    assert v.detect_provider("no-such-domain.example") == "unknown"


def test_detect_provider_empty_domain():
    v = make_validation()
    assert v.detect_provider("") == "unknown"


def test_detect_provider_raises_on_system_failure(monkeypatch):
    v = make_validation()

    def boom(domain):
        raise _ResolverError("resolver down")

    monkeypatch.setattr(v, "_resolve_mx", boom)
    with pytest.raises(ValidationError):
        v.detect_provider("acme.example")


# --------------------------------------------------------------------------
# validate — happy path
# --------------------------------------------------------------------------

def test_validate_valid_consumer(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["aspmx.l.google.com"]))
    r = v.validate("john.doe@gmail.com")
    assert isinstance(r, ValidationResult)
    assert r.valid_status == "valid"
    assert r.provider == "google"
    assert r.mx_ok is True
    assert r.catch_all is False  # consumer provider is never catch-all
    assert r.role_based is False
    assert r.disposable is False


def test_validate_custom_domain_valid(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.acme.example"]))
    r = v.validate("bob@acme.example")
    assert r.valid_status == "valid"
    assert r.provider == "other"
    assert r.mx_ok is True
    assert r.catch_all is None  # smtp_probe disabled → cannot determine


# --------------------------------------------------------------------------
# validate — boundary / signal cases
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    ["not-an-email", "no-at-sign", "a@b", "@nodomain.com", "user@", "user@localhost", ""],
)
def test_validate_invalid_syntax(bad):
    v = make_validation()
    r = v.validate(bad)
    assert r.valid_status == "invalid"
    assert r.mx_ok is False
    assert "invalid_syntax" in r.detail.get("reasons", [])


def test_validate_role_based_is_risky(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.acme.example"]))
    r = v.validate("info@acme.example")
    assert r.role_based is True
    assert r.valid_status == "risky"


def test_validate_role_prefix_token(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.acme.example"]))
    r = v.validate("sales.team@acme.example")
    assert r.role_based is True
    assert r.valid_status == "risky"


def test_validate_disposable_is_risky(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.mailinator.com"]))
    r = v.validate("someone@mailinator.com")
    assert r.disposable is True
    assert r.valid_status == "risky"


def test_validate_no_mx_no_a_is_invalid(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx([]))
    monkeypatch.setattr(v, "_has_a_record", lambda d: False)
    r = v.validate("ghost@dead-domain.example")
    assert r.valid_status == "invalid"
    assert r.mx_ok is False
    assert "no_mx" in r.detail["reasons"]


def test_validate_a_record_fallback_is_risky(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx([]))
    monkeypatch.setattr(v, "_has_a_record", lambda d: True)
    r = v.validate("bob@only-a.example")
    assert r.valid_status == "risky"
    assert r.mx_ok is False
    assert "mx_only_a" in r.detail["reasons"]


def test_validate_resolver_error_is_unknown(monkeypatch):
    v = make_validation()

    def boom(domain):
        raise _ResolverError("resolver down")

    monkeypatch.setattr(v, "_resolve_mx", boom)
    r = v.validate("bob@acme.example")
    assert r.valid_status == "unknown"
    assert r.detail["mx_error"] is True


# --------------------------------------------------------------------------
# catch-all SMTP probe
# --------------------------------------------------------------------------

def test_validate_catch_all_probe_true(monkeypatch):
    v = make_validation(**{"validation.smtp_probe": True})
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mx.acme.example"]))
    monkeypatch.setattr(v, "_smtp_accepts", lambda host, addr: True)
    r = v.validate("bob@acme.example")
    assert r.catch_all is True
    assert r.valid_status == "risky"
    assert "catch_all" in r.detail["reasons"]


def test_validate_catch_all_probe_false(monkeypatch):
    v = make_validation(**{"validation.smtp_probe": True})
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mx.acme.example"]))
    monkeypatch.setattr(v, "_smtp_accepts", lambda host, addr: False)
    r = v.validate("bob@acme.example")
    assert r.catch_all is False
    assert r.valid_status == "valid"


def test_validate_catch_all_probe_unknown(monkeypatch):
    v = make_validation(**{"validation.smtp_probe": True})
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mx.acme.example"]))
    monkeypatch.setattr(v, "_smtp_accepts", lambda host, addr: None)
    r = v.validate("bob@acme.example")
    assert r.catch_all is None
    assert r.valid_status == "valid"


# --------------------------------------------------------------------------
# feature toggles
# --------------------------------------------------------------------------

def test_check_mx_disabled_yields_unknown():
    v = make_validation(**{"validation.check_mx": False})
    # _resolve_mx must never be invoked when MX checking is off.
    v._resolve_mx = lambda d: pytest.fail("MX lookup must not run when check_mx=False")
    r = v.validate("bob@acme.example")
    assert r.valid_status == "unknown"
    assert r.mx_ok is False


def test_role_detection_off(monkeypatch):
    v = make_validation(**{"validation.detect_role": False})
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.acme.example"]))
    r = v.validate("info@acme.example")
    assert r.role_based is None
    assert r.valid_status == "valid"


def test_disposable_detection_off(monkeypatch):
    v = make_validation(**{"validation.detect_disposable": False})
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.mailinator.com"]))
    r = v.validate("someone@mailinator.com")
    assert r.disposable is None
    assert r.valid_status == "valid"


def test_custom_disposable_domain(monkeypatch):
    v = make_validation(**{"validation.disposable_domains": ["throwaway.local"]})
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.throwaway.local"]))
    r = v.validate("x@throwaway.local")
    assert r.disposable is True
    assert r.valid_status == "risky"


# --------------------------------------------------------------------------
# normalization
# --------------------------------------------------------------------------

def test_normalization_case_and_whitespace(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["aspmx.l.google.com"]))
    r = v.validate("  John.Doe@GMAIL.COM  ")
    assert r.email == "John.Doe@gmail.com"
    assert r.provider == "google"


def test_normalization_display_name(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["aspmx.l.google.com"]))
    r = v.validate("John Doe <john@gmail.com>")
    assert r.email == "john@gmail.com"
    assert r.provider == "google"


# --------------------------------------------------------------------------
# batch + idempotency invariant
# --------------------------------------------------------------------------

def test_validate_batch_preserves_order(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["aspmx.l.google.com"]))
    monkeypatch.setattr(v, "_has_a_record", lambda d: True)
    emails = ["a@gmail.com", "bad", "info@gmail.com"]
    results = v.validate_batch(emails)
    assert [r.email for r in results] == ["a@gmail.com", "", "info@gmail.com"]
    assert results[0].valid_status == "valid"
    assert results[1].valid_status == "invalid"
    assert results[2].valid_status == "risky"  # role-based


def test_validation_is_idempotent(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["aspmx.l.google.com"]))
    r1 = v.validate("john.doe@gmail.com")
    r2 = v.validate("john.doe@gmail.com")
    # Pure function under a deterministic (mocked) resolver → identical output.
    assert r1 == r2


def test_detail_carries_mx_hosts(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mx1.acme.example", "mx2.acme.example"]))
    r = v.validate("bob@acme.example")
    assert r.detail["mx"] == ["mx1.acme.example", "mx2.acme.example"]
    assert r.detail["mx_error"] is False


# --------------------------------------------------------------------------
# Null MX (RFC 7505), typo-подсказка, provider_class, DNS-кэш
# --------------------------------------------------------------------------

def test_null_mx_is_hard_invalid(monkeypatch):
    """MX '.' (RFC 7505) → invalid с reason null_mx; A-запись НЕ смотрим."""
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["."]))
    monkeypatch.setattr(
        v, "_has_a_record",
        lambda d: pytest.fail("null MX не должен приводить к A-фолбэку"))
    r = v.validate("user@deadmail.example")
    assert r.valid_status == "invalid"
    assert r.mx_ok is False
    assert "null_mx" in r.detail["reasons"]
    assert "no_mx" not in r.detail["reasons"]


def test_null_mx_beats_a_record(monkeypatch):
    """Домен с сайтом (A есть), но null MX → всё равно invalid, не risky."""
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["."]))
    # даже если бы A-запись существовала — она не должна быть спрошена;
    # здесь проверяем итоговый статус
    r = v.validate("user@website-only.example")
    assert r.valid_status == "invalid"


def test_mixed_dot_entries_are_noise(monkeypatch):
    """'.' рядом с настоящим MX — мусор, не null-MX; хост остаётся."""
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mx1.acme.example", "."]))
    r = v.validate("user@acme.example")
    assert r.mx_ok is True
    assert "null_mx" not in r.detail["reasons"]
    assert r.detail["mx"] == ["mx1.acme.example"]


def test_detect_provider_null_mx_unknown(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["."]))
    assert v.detect_provider("deadmail.example") == "unknown"


def test_typo_suggestion(monkeypatch):
    """mial.ru → подсказка user@mail.ru в detail; адрес НЕ переписан."""
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx([]))
    monkeypatch.setattr(v, "_has_a_record", lambda d: False)
    r = v.validate("user@mial.ru")
    assert r.email == "user@mial.ru"  # без авто-переписывания
    assert r.detail["typo_suggestion"] == "user@mail.ru"
    assert "domain_typo" in r.detail["reasons"]


def test_typo_map_config_extension(monkeypatch):
    v = make_validation(**{"validation.typo_domains": {"maik.ru": "mail.ru"}})
    monkeypatch.setattr(v, "_resolve_mx", stub_mx([]))
    monkeypatch.setattr(v, "_has_a_record", lambda d: False)
    r = v.validate("user@maik.ru")
    assert r.detail["typo_suggestion"] == "user@mail.ru"


def test_no_typo_for_legit_domain(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mxs.mail.ru"]))
    r = v.validate("user@mail.ru")
    assert "typo_suggestion" not in r.detail
    assert "domain_typo" not in r.detail["reasons"]


def test_provider_class_consumer(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mxs.mail.ru"]))
    r = v.validate("user@mail.ru")
    assert r.detail["provider_class"] == "consumer"


def test_provider_class_hosted(monkeypatch):
    """Корп-домен с MX Яндекса → hosted (репутация делится с провайдером)."""
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mx.yandex.net"]))
    r = v.validate("director@zavod.example")
    assert r.provider == "yandex"
    assert r.detail["provider_class"] == "hosted"


def test_provider_class_corp(monkeypatch):
    """Свой почтовый сервер → corp."""
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx(["mail.zavod.example"]))
    r = v.validate("director@zavod.example")
    assert r.provider == "other"
    assert r.detail["provider_class"] == "corp"


def test_provider_class_unknown(monkeypatch):
    v = make_validation()
    monkeypatch.setattr(v, "_resolve_mx", stub_mx([]))
    monkeypatch.setattr(v, "_has_a_record", lambda d: True)
    r = v.validate("user@nodns.example")
    assert r.detail["provider_class"] == "unknown"


def test_mx_cache_prevents_repeat_resolution(monkeypatch):
    """Один домен в батче резолвится один раз (161к строк ≈ единицы доменов)."""
    v = make_validation()
    calls = []

    def counting_mx(domain):
        calls.append(domain)
        return ["mxs.mail.ru"]

    monkeypatch.setattr(v, "_resolve_mx", counting_mx)
    v.validate_batch(["a@corp-a.example", "b@corp-a.example", "c@corp-a.example"])
    assert calls == ["corp-a.example"]


def test_a_record_cache(monkeypatch):
    v = make_validation()
    calls = []
    monkeypatch.setattr(v, "_resolve_mx", stub_mx([]))
    monkeypatch.setattr(v, "_has_a_record",
                        lambda d: (calls.append(d), True)[1])
    v.validate_batch(["a@web-only.example", "b@web-only.example"])
    assert calls == ["web-only.example"]


def test_resolver_error_not_cached(monkeypatch):
    """Системный сбой DNS не кэшируется: следующий вызов пробует снова."""
    v = make_validation()
    state = {"n": 0}

    def flaky(domain):
        state["n"] += 1
        if state["n"] == 1:
            raise _ResolverError("temporary resolver outage")
        return ["mxs.mail.ru"]

    monkeypatch.setattr(v, "_resolve_mx", flaky)
    r1 = v.validate("a@flaky.example")
    assert r1.valid_status == "unknown"
    r2 = v.validate("b@flaky.example")
    assert r2.valid_status == "valid"
    assert state["n"] == 2
