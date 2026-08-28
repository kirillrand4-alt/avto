"""Дата события — дата письма, а повтор ловится по Message-ID.

28.08.2026 опрос почты перевели с порядковых номеров на UID. Флаг «прочитано»
до этого ставился не тому письму, поэтому весь архив ящиков выглядел
непрочитанным и лёг в журнал ВТОРОЙ раз: 132 двойные записи, а сводка
приписала сегодняшнему дню 87 отбивок и 75 ответов чужих дней (BR% 8.76%
вместо 3.8%). Два независимых лекарства:

  1. событию ставим время из заголовка Date самого письма — тогда повторное
     чтение архива ложится на свои дни и сегодняшний день не портит;
  2. повтор ловим по Message-ID — он у письма один и не зависит от того, как
     мы нумеруем ящик.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.dtos import EventIn, RecipientIn  # noqa: E402
from sender.imap_watcher import ImapWatcher  # noqa: E402
from sender.store import Store  # noqa: E402

UTC = timezone.utc
КОГДА = ImapWatcher._kogda_prishlo


# ---- 1. дата письма ------------------------------------------------------ #

def test_beryom_datu_iz_pisma():
    т = КОГДА({"Date": "Fri, 28 Aug 2026 12:29:42 +0300"})
    assert t_utc(т) == datetime(2026, 8, 28, 9, 29, 42, tzinfo=UTC)


def t_utc(т):
    return т.astimezone(UTC).replace(microsecond=0)


def test_bez_zagolovka_seychas():
    до = datetime.now(UTC)
    т = КОГДА({})
    assert до - timedelta(seconds=5) <= т <= datetime.now(UTC)


def test_krivaya_data_ne_lomaet():
    """«Дата» из мусора не должна ронять приём письма и не должна давать
    1970 год — иначе письмо навсегда уедет в начало всех сводок."""
    for мусор in ("вчера", "", "Mon, 32 Zzz 2026 99:99:99", "0"):
        т = КОГДА({"Date": мусор})
        assert т >= datetime.now(UTC) - timedelta(seconds=5)


def test_bredovaya_data_otkatyvaetsya():
    """Часы отправителя врут — 1998 год и 2031-й одинаково негодны."""
    старьё = КОГДА({"Date": "Tue, 06 Jan 1998 10:00:00 +0000"})
    будущее = КОГДА({"Date": "Sat, 06 Jan 2035 10:00:00 +0000"})
    сейчас = datetime.now(UTC)
    assert старьё >= сейчас - timedelta(seconds=5)
    assert будущее >= сейчас - timedelta(seconds=5)


def test_data_bez_zony_schitaetsya_utc():
    т = КОГДА({"Date": "Fri, 28 Aug 2026 09:00:00"})
    assert t_utc(т) == datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


def test_zavtrashnyaya_data_prinimaetsya():
    """Часовые пояса и небольшой сдвиг часов — не повод врать: до суток вперёд
    берём как есть, дальше откатываемся."""
    завтра = datetime.now(UTC) + timedelta(hours=6)
    т = КОГДА({"Date": завтра.strftime("%a, %d %b %Y %H:%M:%S +0000")})
    assert abs((т - завтра).total_seconds()) < 60


# ---- 2. повтор по Message-ID --------------------------------------------- #

@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "sob.db"))
    s.init_schema()
    yield s
    s.close()


def _событие(store, *, ключ, msgid, ящик="box1@ru", rid=None, когда=None):
    return store.append_event(EventIn(
        dedup_key=ключ, event_type="reply",
        event_ts=когда or datetime(2026, 8, 26, 8, 30, tzinfo=UTC),
        recipient_id=rid, mailbox_id=ящик,
        detail={"snippet": "Добрый день, пришлите каталог",
                "headers": {"Message-ID": msgid, "Subject": "Re: КП"}}))


def test_tot_zhe_msgid_pri_smene_numeracii(store):
    """Ровно случай 28.08: ключ сменился, письмо то же."""
    первый, создали = _событие(store, ключ="imap:123:27:reply", msgid="<a@x.ru>")
    assert создали is True
    второй, создали2 = _событие(store, ключ="imap:123:901:reply", msgid="<a@x.ru>")
    assert создали2 is False
    assert второй == первый


def test_odin_msgid_v_raznyh_yashchikah_raznye_pisma(store):
    """Письмо, посланное на два наших адреса, — два касания, а не одно."""
    a, _ = _событие(store, ключ="imap:1:5:reply", msgid="<b@x.ru>", ящик="box1@ru")
    b, создали = _событие(store, ключ="imap:2:5:reply", msgid="<b@x.ru>",
                          ящик="box2@ru")
    assert создали is True and a != b


def test_bez_msgid_rabotaet_staryy_zaslon(store):
    """DSN почти никогда не несёт Message-ID — там остаётся ключ ящика."""
    a, _ = _событие(store, ключ="imap:1:7:dsn", msgid="")
    b, создали = _событие(store, ключ="imap:1:7:dsn", msgid="")
    assert создали is False and a == b
    _, новое = _событие(store, ключ="imap:1:8:dsn", msgid="")
    assert новое is True                       # другой ключ — другое событие


def test_msgid_normalizuetsya(store):
    """<A@X.RU> и a@x.ru — один и тот же идентификатор."""
    a, _ = _событие(store, ключ="imap:1:9:reply", msgid="  <A@X.RU> ")
    b, создали = _событие(store, ключ="imap:1:99:reply", msgid="a@x.ru")
    assert создали is False and a == b


def test_sobytie_ne_teryaet_svoyu_datu(store):
    """Событие пишется с датой письма, а не «сейчас»."""
    rid = store.upsert_recipient(RecipientIn(
        email="snab@zavod.ru", domain="zavod.ru", inn="7701234567"))
    _событие(store, ключ="imap:1:11:reply", msgid="<c@x.ru>", rid=rid,
             когда=datetime(2026, 8, 19, 6, 45, tzinfo=UTC))
    (item,) = [i for i in store.dialog_thread(rid) if i["direction"] == "in"]
    assert str(item["ts"]).startswith("2026-08-19T06:45")
