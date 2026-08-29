"""Служебные отчёты почтовиков — вон из ленты и вон из карточек компаний.

Владелец 29.08 прислал ленту, где вперемешку с работой висели:
  * «PK□□□□□CJ ]юд⊥пЙ□□□u□□□8□□□google.com!compressor-store.ru!1786320000…» —
    zip агрегированного отчёта DMARC, отданный как текст письма;
  * «This is an aggregate DMARC report from el5-energo.ru», привязанный к
    карточке ПАО «ЭЛ5-Энерго» — по совпадению домена отправителя, будто
    компания нам написала;
Замер того дня: 253 записи «входящее вне переписки», из них 106 отчётов DMARC
и 48 обломков их вложений. Работы там — 23 письма от людей.
"""

import email
import email.policy
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.dtos import EventIn  # noqa: E402
from sender.imap_watcher import ImapWatcher  # noqa: E402
from sender.store import Store  # noqa: E402

UTC = timezone.utc


def _письмо(сырое: str):
    """Как в бою: watcher разбирает БАЙТЫ, а не строку."""
    return email.message_from_bytes(сырое.encode("utf-8", "surrogateescape"),
                                    policy=email.policy.default)


ОТЧЁТ_ZIP = (
    "From: noreply-dmarc-support@google.com\r\n"
    "Subject: Report domain: compressor-store.ru Submitter: google.com\r\n"
    'Content-Type: application/zip; name="google.com!compressor-store.ru'
    '!1786320000!1786406399.zip"\r\n'
    "\r\n"
    "PK\x03\x04\n\x00\x00\x00\x08\x00\xd0\xd1\xd2\xd3\xd4\xd5")

ОТЧЁТ_ТЕКСТ = (
    "From: noreply@el5-energo.ru\r\n"
    "Subject: Report Domain: compressor-store.ru Submitter: el5-energo.ru\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "This is an aggregate DMARC report from el5-energo.ru\r\n")

ЖИВОЕ = (
    "From: \"Васильев Алексей\" <vasileav@cryo-gas.ru>\r\n"
    "Subject: компрессор КИП.\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n"
    "\r\n"
    "Добрый день Олег. Спасибо за ваше обращение, но планов по замене нет.\r\n")


def test_otchyot_po_teme_opoznan():
    м = _письмо(ОТЧЁТ_ТЕКСТ)
    assert ImapWatcher._eto_otchyot(
        м, м.get("Subject"), "noreply@el5-energo.ru") is True


def test_otchyot_po_vlozheniyu_opoznan():
    м = _письмо(ОТЧЁТ_ZIP)
    assert ImapWatcher._eto_otchyot(
        м, м.get("Subject"), "noreply-dmarc-support@google.com") is True


def test_zhivoe_pismo_ne_otchyot():
    """Человек, написавший про компрессор, отчётом быть не должен ни при какой
    похожести — иначе мы вычеркнем из работы живого клиента."""
    м = _письмо(ЖИВОЕ)
    assert ImapWatcher._eto_otchyot(
        м, м.get("Subject"), "vasileav@cryo-gas.ru") is False


def test_dvoichnoe_vlozhenie_ne_stanovitsya_tekstom():
    """Байты zip в теле письма рисовались в ленте как «PK□□□□□CJ ]юд⊥пЙ»."""
    м = _письмо(ОТЧЁТ_ZIP)
    тело = ImapWatcher._extract_body(ImapWatcher.__new__(ImapWatcher), м)
    assert тело.startswith("[вложение application/zip")
    assert "PK" not in тело


def test_obychnyy_tekst_ne_tronut():
    м = _письмо(ЖИВОЕ)
    тело = ImapWatcher._extract_body(ImapWatcher.__new__(ImapWatcher), м)
    assert "планов по замене нет" in тело


# ---- лента ---------------------------------------------------------------- #

@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "lenta.db"))
    s.init_schema()
    yield s
    s.close()


def _событие(store, тип, ключ):
    store.append_event(EventIn(
        dedup_key=ключ, event_type=тип, event_ts=datetime.now(UTC),
        mailbox_id="box1@ru", detail={"snippet": "текст", "headers": {}}))


def test_otchyoty_ne_v_lente(store):
    _событие(store, "reply", "k1")
    _событие(store, "otchet", "k2")
    _событие(store, "bounce", "k3")
    виды = {e.event_type for e in store.list_events()}
    assert виды == {"reply", "bounce"}


def test_otchyot_mozhno_sprosit_yavno(store):
    """Из журнала он никуда не делся — просто не лезет в глаза."""
    _событие(store, "otchet", "k4")
    assert len(store.list_events(event_type="otchet")) == 1


# ---- кодировки ------------------------------------------------------------ #

def test_utf8_pod_shapkoy_cp1251_ne_prevrashchaetsya_v_krakozyabry():
    """Письмо в utf-8, объявленное как windows-1251. cp1251 «расшифрует» такие
    байты без ошибки — и в ленте 29.08 письма texno-gm.com выглядели как
    «РњС‹ СЂР°РґС‹ РїСЂРёРІРµС‚СЃС‚РІРѕРІР°С‚СЊ»."""
    сырое = ("From: kolomiets@texno-gm.com\r\n"
             "Subject: test\r\n"
             "Content-Type: text/plain; charset=windows-1251\r\n"
             "\r\n").encode("ascii") + "Мы рады приветствовать вас".encode("utf-8")
    м = email.message_from_bytes(сырое, policy=email.policy.default)
    тело = ImapWatcher._extract_body(ImapWatcher.__new__(ImapWatcher), м)
    assert "Мы рады приветствовать вас" in тело
    assert "Рњ" not in тело


def test_nastoyashchiy_cp1251_chitaetsya_kak_prezhde():
    """Обратную сторону не ломаем: письмо ДЕЙСТВИТЕЛЬНО в cp1251 читается."""
    сырое = ("From: a@b.ru\r\nSubject: test\r\n"
             "Content-Type: text/plain; charset=windows-1251\r\n"
             "\r\n").encode("ascii") + "Нам это не актуально".encode("cp1251")
    м = email.message_from_bytes(сырое, policy=email.policy.default)
    тело = ImapWatcher._extract_body(ImapWatcher.__new__(ImapWatcher), м)
    assert "Нам это не актуально" in тело
