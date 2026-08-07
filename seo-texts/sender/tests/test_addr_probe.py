"""Проверка адресов без отправки писем.

Главное, что здесь защищается, — правило «5xx ещё не значит, что адреса нет».
07.08 прогон по очереди дал восемь ответов 5xx, и четыре из них были про НАШУ
пробу: «нужно шифрование сессии», «нет PTR-записи у вашего хоста», «не прошла
проверка обратного адреса». Выброс по коду убил бы четыре живых контакта.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.addr_probe import (AddrProbe, AddrProbeLoop, ЕСТЬ,  # noqa: E402
                               НЕТ_MX, НЕТ_ЯЩИКА, НЕЯСНО, ОТКАЗ_ПРОБЕ,
                               классифицировать)


# ---- классификация ответа сервера ---- #

@pytest.mark.parametrize("код,ответ,ждём", [
    (250, "OK", ЕСТЬ),
    (550, "5.7.1 No such user!", НЕТ_ЯЩИКА),
    (554, "5.1.1 <x@y.ru>: Recipient address rejected: User unknown", НЕТ_ЯЩИКА),
    (550, "Message was not accepted -- invalid mailbox ... user not found", НЕТ_ЯЩИКА),
    # ниже — ответы, где сервер отверг ПРОБУ, а про адрес не сказал ничего
    (550, "5.7.1 Session encryption is required", ОТКАЗ_ПРОБЕ),
    (550, "There is no reverse (PTR) record found for your host", ОТКАЗ_ПРОБЕ),
    (550, "REJECTED. IP name lookup failed for 91.206.14.169", ОТКАЗ_ПРОБЕ),
    (550, "Verification failed for <postmaster@our-domain.ru>", ОТКАЗ_ПРОБЕ),
    (450, "4.7.1 Try again later", НЕЯСНО),
    (None, "timed out", НЕЯСНО),
])
def test_klassifikatsiya(код, ответ, ждём):
    assert классифицировать(код, ответ) == ждём


# ---- кэш ---- #

def test_kesh_ne_povtoryaet_probu(tmp_path):
    p = AddrProbe(str(tmp_path / "p.db"))
    p._save("a@z.ru", ЕСТЬ, 250, "OK", "mx.z.ru")
    assert (p.cached("a@z.ru") or {})["verdict"] == ЕСТЬ
    assert p.cached("A@Z.RU") is not None          # регистр не важен
    assert p.cached("нет@z.ru") is None


def test_myortvyy_ne_protuhaet(tmp_path):
    """Живой адрес перепроверяем по TTL, мёртвый — нет: ящик не воскреснет."""
    from datetime import datetime, timedelta, timezone

    p = AddrProbe(str(tmp_path / "p.db"), ttl_days=30)
    p._save("живой@z.ru", ЕСТЬ, 250, "OK", "mx")
    p._save("мёртвый@z.ru", НЕТ_ЯЩИКА, 550, "no such user", "mx")
    старьё = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with p._conn() as c:                       # состарим обе записи
        c.execute("UPDATE addr_probe SET ts=?", (старьё,))
    assert p.cached("живой@z.ru") is None          # протух, перепроверим
    assert (p.cached("мёртвый@z.ru") or {})["verdict"] == НЕТ_ЯЩИКА


def test_bez_mx_ne_lezem_v_set(tmp_path):
    p = AddrProbe(str(tmp_path / "p.db"))
    p.mx_for = lambda домен: None
    assert p.probe("x@nomx.ru")["verdict"] == НЕТ_MX


# ---- цикл ---- #

class _Store:
    def __init__(self, письма, enabled=True):
        self.письма = письма
        self.enabled = enabled
        self.решения = []
        self.suppression = []

    def get_setting(self, key, default=None):
        return self.enabled if key == "addr_probe_enabled" else default

    def confirm_list(self, **kw):
        return list(self.письма)

    def confirm_decide(self, rid, **kw):
        self.решения.append((rid, kw.get("status"), kw.get("reason")))
        return True

    def suppression_add(self, entry):
        self.suppression.append((entry.scope, entry.value, entry.reason))
        return (1, True)


def _цикл(tmp_path, письма, вердикты):
    p = AddrProbe(str(tmp_path / "p.db"))
    p.probe = lambda email, force=False: {  # noqa: A002
        "email": email, "verdict": вердикты[email], "code": 550,
        "answer": "тест"}
    p.cached = lambda email: None
    p.new_pass = lambda: None
    store = _Store(письма)
    return AddrProbeLoop(store=store, probe=p), store


ПИСЬМА = [{"id": 1, "email": "живой@z.ru", "kind": "outbound"},
          {"id": 2, "email": "мёртвый@z.ru", "kind": "outbound"},
          {"id": 3, "email": "отказ@z.ru", "kind": "outbound"}]


def test_snimaem_tolko_myortvye(tmp_path):
    цикл, store = _цикл(tmp_path, ПИСЬМА, {
        "живой@z.ru": ЕСТЬ, "мёртвый@z.ru": НЕТ_ЯЩИКА,
        "отказ@z.ru": ОТКАЗ_ПРОБЕ})
    итог = цикл.tick()
    assert итог["проверено"] == 3 and итог["снято_писем"] == 1
    assert [r[0] for r in store.решения] == [2]          # только мёртвое
    assert store.решения[0][1] == "skipped"
    assert store.suppression == [("email", "мёртвый@z.ru", "bounce_hard")]


def test_vyklyuchennyy_tsikl_nichego_ne_delaet(tmp_path):
    цикл, store = _цикл(tmp_path, ПИСЬМА, {e["email"]: НЕТ_ЯЩИКА for e in ПИСЬМА})
    цикл.store.enabled = False
    assert цикл.tick()["проверено"] == 0
    assert store.решения == [] and store.suppression == []


def test_otvety_klientov_ne_trogaem(tmp_path):
    письма = ПИСЬМА + [{"id": 9, "email": "клиент@z.ru", "kind": "reply"}]
    цикл, store = _цикл(tmp_path, письма, {
        "живой@z.ru": ЕСТЬ, "мёртвый@z.ru": НЕТ_ЯЩИКА,
        "отказ@z.ru": ОТКАЗ_ПРОБЕ, "клиент@z.ru": НЕТ_ЯЩИКА})
    цикл.tick()
    assert 9 not in [r[0] for r in store.решения]


# ---- генерация не пишет мёртвым ---- #

def test_generatsiya_propuskaet_myortvye(tmp_path):
    """ai_quota не тратит генерацию на адрес, которого нет.

    Читает тот же кэш пробы: вердикт «нет ящика» = письмо не сочиняем.
    Прочие вердикты не участвуют — «не подтверждён» не повод молчать."""
    from sender.ai_quota import AiQuota

    база = str(tmp_path / "s.db")
    p = AddrProbe(база)
    p._save("мёртвый@z.ru", НЕТ_ЯЩИКА, 550, "no such user", "mx")
    p._save("живой@z.ru", ЕСТЬ, 250, "OK", "mx")
    p._save("неясный@z.ru", ОТКАЗ_ПРОБЕ, 550, "no PTR", "mx")

    q = AiQuota.__new__(AiQuota)
    q._db_path = база
    мёртвые = q._dead_addresses(["мёртвый@z.ru", "живой@z.ru", "неясный@z.ru"])
    assert мёртвые == {"мёртвый@z.ru"}


def test_bez_tablitsy_nikogo_ne_rezhem(tmp_path):
    from sender.ai_quota import AiQuota

    q = AiQuota.__new__(AiQuota)
    q._db_path = str(tmp_path / "пусто.db")
    assert q._dead_addresses(["кто@то.ru"]) == set()


def test_otdelnyy_ip_peredayotsya_v_soedinenie(tmp_path, monkeypatch):
    """Проба выходит с указанного IP, а не с основного адреса сервера.

    Отдельный адрес нужен, чтобы риск чёрных списков не касался основного:
    сгоревший проверочный IP меняют, панель и дроп продолжают работать."""
    поймано = {}

    class _SMTP:
        def __init__(self, host, port, timeout=None, local_hostname=None,
                     source_address=None):
            поймано["source_address"] = source_address
            поймано["helo"] = local_hostname

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo_or_helo_if_needed(self):
            pass

        def has_extn(self, name):
            return False

        def mail(self, addr):
            поймано["mail_from"] = addr

        def rcpt(self, addr):
            return 250, b"OK"

    import sender.addr_probe as AP
    monkeypatch.setattr(AP.smtplib, "SMTP", _SMTP)
    p = AP.AddrProbe(str(tmp_path / "p.db"), source_ip="91.206.14.170",
                     helo="probe.example.ru", mail_from="postmaster@example.ru",
                     pause_sec=0)
    p.mx_for = lambda домен: "mx.z.ru"
    assert p.probe("кто@z.ru")["verdict"] == ЕСТЬ
    assert поймано["source_address"] == ("91.206.14.170", 0)
    assert поймано["helo"] == "probe.example.ru"
    assert поймано["mail_from"] == "postmaster@example.ru"


def test_bez_otdelnogo_ip_soedinenie_kak_ranshe(tmp_path, monkeypatch):
    поймано = {}

    class _SMTP:
        def __init__(self, host, port, timeout=None, local_hostname=None,
                     source_address=None):
            поймано["source_address"] = source_address

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo_or_helo_if_needed(self):
            pass

        def has_extn(self, name):
            return False

        def mail(self, addr):
            pass

        def rcpt(self, addr):
            return 250, b"OK"

    import sender.addr_probe as AP
    monkeypatch.setattr(AP.smtplib, "SMTP", _SMTP)
    p = AP.AddrProbe(str(tmp_path / "p2.db"), pause_sec=0)
    p.mx_for = lambda домен: "mx.z.ru"
    p.probe("кто@z.ru")
    assert поймано["source_address"] is None
