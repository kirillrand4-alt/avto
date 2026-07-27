# -*- coding: utf-8 -*-
"""Склейка ленты в НАСТОЯЩИЕ почтовые ветки (задача владельца 27.07).

Проверяем, что группировка ведёт себя как почтовый клиент: связывает по
In-Reply-To/References и thread_id, а разные переписки НЕ сливает в одну.
"""
from sender.store import _subject_key, group_dialog_threads


def out(rfc, subj, ts, email, thread_id=""):
    return {"direction": "out", "ts": ts, "subject": subj, "email": email,
            "rfc_message_id": rfc, "thread_id": thread_id, "body": "текст"}


def inc(subj, ts, email, in_reply_to="", references="", thread_id="", rfc=""):
    return {"direction": "in", "ts": ts, "subject": subj, "email": email,
            "in_reply_to": in_reply_to, "references": references,
            "thread_id": thread_id, "rfc_message_id": rfc, "body": "ответ"}


def test_subject_key_снимает_цепочку_префиксов():
    assert _subject_key("Re: Fwd: RE: компрессоры") == "компрессоры"
    assert _subject_key("Отв: Тема") == "тема"
    assert _subject_key(None) == ""


def test_ответ_склеивается_с_письмом_по_in_reply_to():
    items = [
        out("<a@x.ru>", "компрессоры под метанол", "2026-07-26T07:00", "k@z.ru"),
        inc("Re: компрессоры под метанол", "2026-07-26T14:00", "k@z.ru",
            in_reply_to="<a@x.ru>"),
    ]
    th = group_dialog_threads(items)
    assert len(th) == 1
    assert th[0]["n_out"] == 1 and th[0]["n_in"] == 1
    assert th[0]["items"][0]["direction"] == "out"   # хронология внутри ветки


def test_склейка_по_references_когда_in_reply_to_пуст():
    items = [
        out("<a@x.ru>", "тема", "2026-07-26T07:00", "k@z.ru"),
        inc("Re: тема", "2026-07-26T09:00", "k@z.ru",
            references="<old@y.ru> <a@x.ru>"),
    ]
    assert len(group_dialog_threads(items)) == 1


def test_разные_переписки_НЕ_сливаются():
    """Главное требование: письма к разным адресам с разными темами и без
    RFC-связи — это РАЗНЫЕ ветки, а не один тред."""
    items = [
        out("<a@x.ru>", "компрессоры под метанол", "2026-07-26T07:00", "one@z.ru"),
        out("<b@x.ru>", "[ТЕСТ] компрессорная под метанол", "2026-07-26T14:00",
            "two@z.ru"),
        out("<c@x.ru>", "для главного инженера", "2026-07-26T15:00", "three@z.ru"),
    ]
    th = group_dialog_threads(items)
    assert len(th) == 3, [t["subject"] for t in th]


def test_общий_thread_id_склеивает():
    items = [
        out("<a@x.ru>", "первое", "2026-07-26T07:00", "k@z.ru", thread_id="T1"),
        inc("совсем другая тема", "2026-07-26T08:00", "k@z.ru", thread_id="T1"),
    ]
    assert len(group_dialog_threads(items)) == 1


def test_фолбэк_по_теме_и_адресу():
    """Почтовик не сохранил References — склеиваем по теме + собеседнику."""
    items = [
        out("<a@x.ru>", "запрос КП", "2026-07-26T07:00", "k@z.ru"),
        inc("Re: запрос КП", "2026-07-26T08:00", "k@z.ru"),
    ]
    assert len(group_dialog_threads(items)) == 1


def test_одна_тема_но_разные_собеседники_не_склеиваются():
    items = [
        out("<a@x.ru>", "запрос КП", "2026-07-26T07:00", "one@z.ru"),
        out("<b@x.ru>", "запрос КП", "2026-07-26T08:00", "two@z.ru"),
    ]
    assert len(group_dialog_threads(items)) == 2


def test_ветки_отсортированы_свежая_последней():
    items = [
        out("<a@x.ru>", "старая", "2026-07-20T07:00", "one@z.ru"),
        out("<b@x.ru>", "свежая", "2026-07-26T07:00", "two@z.ru"),
    ]
    th = group_dialog_threads(items)
    assert [t["subject"] for t in th] == ["старая", "свежая"]


def test_пустой_вход():
    assert group_dialog_threads([]) == []


def test_цепочка_из_трёх_писем_одна_ветка():
    items = [
        out("<a@x.ru>", "тема", "2026-07-26T07:00", "k@z.ru"),
        inc("Re: тема", "2026-07-26T08:00", "k@z.ru", in_reply_to="<a@x.ru>",
            rfc="<b@z.ru>"),
        out("<c@x.ru>", "Re: тема", "2026-07-26T09:00", "k@z.ru"),
    ]
    th = group_dialog_threads(items)
    assert len(th) == 1 and len(th[0]["items"]) == 3
    assert th[0]["last_ts"] == "2026-07-26T09:00"
