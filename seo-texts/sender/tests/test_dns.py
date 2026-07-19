"""Тесты sender.dns (DKIM/SPF/DMARC/MX preflight). Резолверы _txt/_mx мокаются;
сети нет.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.dns import DnsHealth, DnsReport  # noqa: E402


def _mk(txt_map=None, mx_map=None):
    """DnsHealth с подменёнными резолверами по словарям имя->записи."""
    h = DnsHealth()
    txt_map = txt_map or {}
    mx_map = mx_map or {}
    h._txt = lambda name: txt_map.get(name, [])  # type: ignore
    h._mx = lambda domain: mx_map.get(domain, [])  # type: ignore
    return h


def test_all_good():
    h = _mk(
        txt_map={
            "acme.ru": ["v=spf1 include:_spf.yandex.net ~all"],
            "_dmarc.acme.ru": ["v=DMARC1; p=quarantine; rua=mailto:a@acme.ru"],
            "mail._domainkey.acme.ru": ["v=DKIM1; k=rsa; p=MIGf..."],
        },
        mx_map={"acme.ru": ["mx.yandex.net"]},
    )
    r = h.check("acme.ru")
    assert r.spf is True and "spf1" in r.spf_record
    assert r.dmarc is True and r.dmarc_policy == "quarantine"
    assert r.dkim is True
    assert r.mx_ok is True
    assert r.issues == ()


def test_no_spf_dmarc_dkim():
    h = _mk(txt_map={"bad.ru": ["some unrelated txt"]}, mx_map={"bad.ru": ["mx.bad.ru"]})
    r = h.check("bad.ru")
    assert r.spf is False and r.dmarc is False and r.dkim is False
    assert set(r.issues) >= {"no_spf", "no_dmarc", "no_dkim"}


def test_dmarc_policy_none_flagged():
    h = _mk(
        txt_map={
            "x.ru": ["v=spf1 -all"],
            "_dmarc.x.ru": ["v=DMARC1; p=none"],
            "mail._domainkey.x.ru": ["v=DKIM1; p=abc"],
        },
        mx_map={"x.ru": ["mx.x.ru"]},
    )
    r = h.check("x.ru")
    assert r.dmarc is True and r.dmarc_policy == "none"
    assert "dmarc_policy_none" in r.issues


def test_dkim_alternate_selector():
    # найдётся по селектору default, не mail
    h = _mk(
        txt_map={
            "y.ru": ["v=spf1 -all"],
            "default._domainkey.y.ru": ["k=rsa; p=xyz"],
        },
        mx_map={"y.ru": ["mx.y.ru"]},
    )
    r = h.check("y.ru")
    assert r.dkim is True


def test_null_mx():
    h = _mk(txt_map={"dead.ru": ["v=spf1 -all"]}, mx_map={"dead.ru": ["."]})
    r = h.check("dead.ru")
    assert r.mx_ok is False and "null_mx" in r.issues
    assert "no_mx" not in r.issues


def test_no_mx():
    h = _mk(txt_map={"z.ru": ["v=spf1 -all"]}, mx_map={"z.ru": []})
    r = h.check("z.ru")
    assert r.mx_ok is False and "no_mx" in r.issues


def test_resolver_unavailable_gives_none():
    """_txt возвращает None (резолвер сломан) → поля None, не исключение."""
    h = DnsHealth()
    h._txt = lambda name: None  # type: ignore
    h._mx = lambda domain: []  # type: ignore
    r = h.check("any.ru")
    assert r.spf is None and r.dmarc is None and r.dkim is None
    # issues по SPF/DMARC/DKIM НЕ добавляются (None ≠ False), только по MX
    assert "no_spf" not in r.issues and "no_dkim" not in r.issues
    assert "no_mx" in r.issues


def test_dkim_none_when_all_selectors_unresolvable():
    h = DnsHealth()
    h._txt = lambda name: [] if name in ("q.ru", "_dmarc.q.ru") else None  # type: ignore
    h._mx = lambda domain: ["mx.q.ru"]  # type: ignore
    r = h.check("q.ru")
    assert r.dkim is None  # все DKIM-селекторы не резолвятся
    assert "no_dkim" not in r.issues


def test_report_is_frozen_dataclass():
    r = _mk(mx_map={"a.ru": ["mx"]}).check("a.ru")
    assert isinstance(r, DnsReport)
    with pytest.raises(Exception):
        r.spf = True  # type: ignore
