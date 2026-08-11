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
