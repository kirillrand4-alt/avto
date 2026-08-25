# -*- coding: utf-8 -*-
"""Ответ без References всё равно становится карточкой лида.

Сверка 25.08.2026: 129 ответов клиентов против 112 карточек. Пятнадцать
потерянных — корпоративные почтовики срезают References, thread_id пустой,
а карточка заводилась только при непустом. Среди потерянных был живой
интерес: «Сафит» — «с удовольствием рассмотрим».
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.imap_watcher import ImapWatcher  # noqa: E402


class _Получатель:
    id, email, company_name, inn = 5, "kto@zavod.ru", 'ООО "Завод"', "7700000000"


class _Стор:
    def get_recipient(self, _rid):
        return _Получатель()

    def append_event(self, _e):
        return (1, True)


class _Лиддеск:
    def __init__(self):
        self.заведены = []

    def push_warm_lead(self, recipient, thread_id, snippet, *, otvetil=None):
        self.заведены.append((recipient.email, thread_id, snippet, otvetil))
        return 1


class _Событие:
    def __init__(self, thread_id):
        self.thread_id = thread_id
        self.snippet = "С удовольствием рассмотрим ваше предложение"
        self.dedup_key = "imap:1:2:reply"
        self.from_addr = "otvetil@zavod.ru"
        self.kind = "reply"


class _Сигнал:
    def __init__(self, kind="interested"):
        self.kind, self.phone = kind, None


def _сторож(лиддеск):
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = _Стор()
    w._reply_desk = лиддеск
    w._reply_pipeline = None
    w._suppression = None
    w._auto_suppress_bounce = False
    return w


def test_otvet_bez_vetki_stanovitsya_lidom():
    лд = _Лиддеск()
    _сторож(лд)._handle_reply(5, None, _Событие(""), _Сигнал())
    assert лд.заведены, "ответ без References обязан стать карточкой"
    assert лд.заведены[0][3] == "otvetil@zavod.ru", "адрес ответившего в карточке"


def test_otvet_s_vetkoy_kak_i_ran_she():
    лд = _Лиддеск()
    _сторож(лд)._handle_reply(5, None, _Событие("<t-1@zavod.ru>"), _Сигнал())
    assert лд.заведены[0][1] == "<t-1@zavod.ru>"


def test_avtootvet_bez_vetki_tozhe_v_lentu():
    лд = _Лиддеск()
    с = _Сигнал("auto_reply")
    _сторож(лд)._handle_reply(5, None, _Событие(""), с)
    assert лд.заведены, "автоответ без ветки тоже нужен в ленте"
    assert "[автоответ]" in лд.заведены[0][2]
