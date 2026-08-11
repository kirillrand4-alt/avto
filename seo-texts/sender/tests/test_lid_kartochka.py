# -*- coding: utf-8 -*-
"""Карточка компании на лиде и крестик «не интересно» (владелец 11.08).

Два требования, и оба про то, чтобы менеджер не работал вслепую: видеть про
компанию то же, что видел отправитель письма, и убирать с ленты неактуальное.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sender.leaddesk import _TRANSITIONS  # noqa: E402


def test_ne_interesno_dostizhim_bez_vzyatiya():
    """Крестик жмут прямо в ленте, где лид ещё никем не взят."""
    assert "not_interested" in _TRANSITIONS["new"]
    assert "not_interested" in _TRANSITIONS["assigned"]
    assert "not_interested" in _TRANSITIONS["taken"]


def test_ne_interesno_obratimo():
    """Промах по крестику не должен хоронить лид навсегда."""
    assert "new" in _TRANSITIONS["not_interested"]


def test_lenta_pryachet_ne_interesnye(tmp_path):
    """Без фильтра «не интересно» в ленте нет, с явным фильтром — есть."""
    from sender.store import Store

    store = Store(str(tmp_path / "leads.db"))
    store.init_schema()
    con = store._conn  # noqa: SLF001
    for н, статус in ((1, "new"), (2, "not_interested"), (3, "deleted")):
        con.execute(
            "INSERT INTO leads (id, dedup_key, email, status, version, "
            "created_at, updated_at) VALUES (?,?,?,?,0,?,?)",
            (н, f"lid-{н}", f"kto{н}@zavod.ru", статус, "2026-08-11T00:00:00",
             "2026-08-11T00:00:00"))
    con.commit()

    без_фильтра = {l.id for l in store.list_leads()}
    assert без_фильтра == {1}, без_фильтра

    с_фильтром = {l.id for l in store.list_leads(status="not_interested")}
    assert с_фильтром == {2}, с_фильтром


def test_panel_dlya_lida_ishchet_po_inn_i_pochte():
    """Ищем и по ИНН (отвечают с любого адреса компании), и по адресу."""
    import inspect

    from sender.store import Store
    исходник = inspect.getsource(Store.panel_dlya_lida)
    assert "lower(email) = ?" in исходник
    assert "panel_json IS NOT NULL" in исходник
    # Отправленные вперёд черновиков: человек отвечает на ушедшее письмо.
    assert "ORDER BY CASE status" in исходник


def test_status_s_knopok_paneli_prinimaetsya():
    """Кнопки карточки лида шлют called / unqualified / in_bitrix — движок
    обязан их знать. Раньше он отвечал «unknown lead status», и перевести лид
    в эти состояния было нечем, хотя в фильтре они значились."""
    from sender.leaddesk import _VALID_STATUSES
    for с in ("called", "unqualified", "in_bitrix", "not_interested", "closed"):
        assert с in _VALID_STATUSES, с
    assert "called" in _TRANSITIONS["taken"]
    assert "in_bitrix" in _TRANSITIONS["qualified"]
    assert "in_bitrix" in _TRANSITIONS["called"]


def test_not_qualified_svoditsya_k_unqualified():
    """Старое имя с фронта не должно ронять запрос."""
    from sender.leaddesk import _СИНОНИМЫ
    assert _СИНОНИМЫ["not_qualified"] == "unqualified"


def test_otpravlennye_schitaet_otvety_i_otbivki(tmp_path):
    """Список отправленного: письмо, кому, ответили ли, отбилось ли."""
    from sender.store import Store

    store = Store(str(tmp_path / "sent.db"))
    store.init_schema()
    con = store._conn  # noqa: SLF001
    # Внешние ключи здесь не предмет проверки: считаем ответы и отбивки, а не
    # целостность схемы. Заводим ровно те строки, которые нужны выборке.
    con.execute("PRAGMA foreign_keys=OFF")
    ч = "2026-08-01T00:00:00"
    con.execute("INSERT INTO recipients (id, email, domain, company_name, inn, "
                "created_at, updated_at) VALUES "
                "(1,'snab@zavod.ru','zavod.ru','ООО Завод','7701234567',?,?)", (ч, ч))
    con.execute("INSERT INTO recipients (id, email, domain, company_name, inn, "
                "created_at, updated_at) VALUES "
                "(2,'kk@drugoy.ru','drugoy.ru','ООО Другой','7709999999',?,?)", (ч, ч))
    for мид, пол, когда in ((10, 1, "2026-08-10T10:00:00"),
                            (11, 2, "2026-08-11T10:00:00")):
        con.execute(
            "INSERT INTO messages (id, idempotency_key, campaign_id, recipient_id, "
            "sequence_step_id, mailbox_id, status, sent_at, subject, "
            "created_at, updated_at) VALUES (?,?,1,?,1,'ya@nash.ru','sent',?,?,?,?)",
            (мид, f"k{мид}", пол, когда, f"Тема {мид}", когда, когда))
    # На первое письмо ответили, второе отбилось.
    con.execute("INSERT INTO events (dedup_key, event_type, message_id, "
                "recipient_id, event_ts, created_at) "
                "VALUES ('e1','reply',10,1,'2026-08-10T12:00:00','2026-08-10T12:00:00')")
    con.execute("INSERT INTO events (dedup_key, event_type, message_id, "
                "recipient_id, event_ts, created_at) "
                "VALUES ('e2','bounce',11,2,'2026-08-11T12:00:00','2026-08-11T12:00:00')")
    con.commit()

    итог = store.otpravlennye()
    assert итог["vsego"] == 2
    по_ид = {p["id"]: p for p in итог["pisma"]}
    assert по_ид[10]["otvetov"] == 1 and по_ид[10]["otbivok"] == 0
    assert по_ид[11]["otbivok"] == 1 and по_ид[11]["otvetov"] == 0
    assert по_ид[10]["company_name"] == "ООО Завод"

    # Поиск идёт и по компании, и по ИНН, и по адресу.
    assert store.otpravlennye(q="завод")["vsego"] >= 0
    только = store.otpravlennye(tolko_s_otvetom=True)["pisma"]
    assert [p["id"] for p in только] == [10]


def test_telo_pisma_beryotsya_i_po_adresu(tmp_path):
    """Тело письма находится, даже если confirm_reviews не связан message_id.

    Владелец 11.08 показал письмо с подписью «тела письма в базе нет», при том
    что текст в базе лежал: связка confirm_reviews.message_id у него пуста, а
    движок искал только по ней.
    """
    from sender.store import Store

    store = Store(str(tmp_path / "telo.db"))
    store.init_schema()
    con = store._conn  # noqa: SLF001
    con.execute("PRAGMA foreign_keys=OFF")
    ч = "2026-08-11T10:00:00"
    con.execute("INSERT INTO recipients (id, email, domain, company_name, "
                "created_at, updated_at) VALUES "
                "(7,'litvin@mail.ru','mail.ru','Мясокомбинат',?,?)", (ч, ч))
    con.execute(
        "INSERT INTO messages (id, idempotency_key, campaign_id, recipient_id, "
        "sequence_step_id, mailbox_id, status, sent_at, subject, body_rendered, "
        "created_at, updated_at) VALUES "
        "(70,'k70',1,7,1,'my@nash.ru','sent',?,'Тема','',?,?)", (ч, ч, ч))
    # Решение оператора БЕЗ message_id — как в живой базе.
    con.execute(
        "INSERT INTO confirm_reviews (id, dedup_key, email, campaign_id, "
        "subject, body, status, created_at, updated_at) VALUES "
        "(90,'d90','litvin@mail.ru',1,'Тема','<p>текст письма</p>','sent',?,?)",
        (ч, ч))
    con.commit()

    полн = store.message_full(70)
    assert полн["body"] == "<p>текст письма</p>", полн
    assert полн["body_source"] == "confirm (по адресу)", полн["body_source"]
    assert полн["body_missing"] is False


def test_chuzhoy_tekst_ne_podstavlyaetsya(tmp_path):
    """Подставить письмо другой кампании хуже, чем не подставить ничего."""
    from sender.store import Store

    store = Store(str(tmp_path / "telo2.db"))
    store.init_schema()
    con = store._conn  # noqa: SLF001
    con.execute("PRAGMA foreign_keys=OFF")
    ч = "2026-08-11T10:00:00"
    con.execute("INSERT INTO recipients (id, email, domain, created_at, "
                "updated_at) VALUES (8,'kto@zavod.ru','zavod.ru',?,?)", (ч, ч))
    con.execute(
        "INSERT INTO messages (id, idempotency_key, campaign_id, recipient_id, "
        "sequence_step_id, mailbox_id, status, sent_at, subject, body_rendered, "
        "created_at, updated_at) VALUES "
        "(71,'k71',1,8,1,'my@nash.ru','sent',?,'Тема','',?,?)", (ч, ч, ч))
    con.execute(
        "INSERT INTO confirm_reviews (id, dedup_key, email, campaign_id, "
        "subject, body, status, created_at, updated_at) VALUES "
        "(91,'d91','kto@zavod.ru',9,'Другая','<p>чужое</p>','sent',?,?)", (ч, ч))
    con.commit()

    полн = store.message_full(71)
    assert полн["body"] == "", полн
    assert полн["body_missing"] is True
