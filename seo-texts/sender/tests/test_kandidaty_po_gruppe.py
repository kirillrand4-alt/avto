# -*- coding: utf-8 -*-
"""Кнопка видит партию, набранную по ГРУППЕ, а не по колонке segment.

Отбор кандидатов шёл запросом query_recipients({"segment": seg}) - только по
колонке. Группа получателя это segment ПЛЮС список extra_json.gruppy (одно
поле segment одно-значное, см. store.recipient_groups).

Замер 17.08: в группе «Партия 935» 920 получателей, с segment == «Партия 935»
- НОЛЬ. Кнопка отвечала «нет получателей без письма в этом сегменте» и не
генерировала ничего.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_quota import AiQuota  # noqa: E402


class _Rec:
    def __init__(self, rid, email, inn=""):
        self.id, self.email, self.inn = rid, email, inn


class _Store:
    def __init__(self, группы, стоп=()):
        self._группы = группы
        self._стоп = set(стоп)
        self.звали = 0

    def recipient_groups(self):
        self.звали += 1
        return {"по_id": self._группы}

    def get_recipient(self, rid):
        return _Rec(rid, f"a{rid}@zavod.ru", inn=str(7700000000 + rid))

    def suppression_lookup(self, email=None, domain=None, inn=None):
        return object() if email in self._стоп else None


def _кво(store):
    q = AiQuota.__new__(AiQuota)
    q._store = store
    return q


ГРУППЫ = {1: ["Партия 935"], 2: ["Партия 935", "новостные"],
          3: ["Солянка"], 4: ["Партия 935"]}


def test_nahodit_po_gruppe():
    q = _кво(_Store(ГРУППЫ))
    got = q._kandidaty_po_gruppe("Партия 935", set(), 10)
    assert [r.id for r in got] == [1, 2, 4], [r.id for r in got]


def test_uzhe_s_pismom_propuskaem():
    q = _кво(_Store(ГРУППЫ))
    got = q._kandidaty_po_gruppe("Партия 935", {2}, 10)
    assert [r.id for r in got] == [1, 4], [r.id for r in got]


def test_stop_list_otsekaetsya():
    """Фильтр suppressed=False обычного пути терять нельзя."""
    q = _кво(_Store(ГРУППЫ, стоп={"a1@zavod.ru"}))
    got = q._kandidaty_po_gruppe("Партия 935", set(), 10)
    assert [r.id for r in got] == [2, 4], [r.id for r in got]


def test_zapas_ogranichivaet():
    q = _кво(_Store(ГРУППЫ))
    assert len(q._kandidaty_po_gruppe("Партия 935", set(), 2)) == 2


def test_chuzhaya_gruppa_ne_lezet():
    q = _кво(_Store(ГРУППЫ))
    assert [r.id for r in q._kandidaty_po_gruppe("Солянка", set(), 10)] == [3]


def test_pustoy_segment_ne_hodit_v_bazu():
    s = _Store(ГРУППЫ)
    assert _кво(s)._kandidaty_po_gruppe("", set(), 10) == []
    assert s.звали == 0, "при пустом сегменте база читаться не должна"


def test_sboy_indeksa_ne_ronyaet():
    class _Сбой:
        def recipient_groups(self):
            raise RuntimeError("database is locked")
    assert _кво(_Сбой())._kandidaty_po_gruppe("Партия 935", set(), 10) == []


# --- имя кампании несёт направление, группа — нет ------------------------- #

def test_gruppa_i_napravlenie():
    """«Партия 935 — КЦ» -> группа «Партия 935», направление kc.

    Сегмент кампании 10 это «Партия 935 — КЦ», а группа в базе просто
    «Партия 935» (920 человек). Без разбора имени запасной путь искал бы
    несуществующую группу и снова дал ноль.
    """
    q = _кво(_Store({}))
    assert q._gruppa_i_napravlenie("Партия 935 — КЦ") == ("Партия 935", "kc")
    assert q._gruppa_i_napravlenie("Партия 935 — Meyer") == ("Партия 935", "meyer")
    assert q._gruppa_i_napravlenie("металлообработка") == ("металлообработка", "")


def test_nahodit_po_imeni_gruppy_iz_kampanii():
    """Кандидаты ищутся и по полному имени сегмента, и по группе из него."""
    q = _кво(_Store(ГРУППЫ))
    q._card_for = lambda inn: {}
    got = q._kandidaty_po_gruppe("Партия 935 — КЦ", set(), 10, campaign_id=10)
    assert [r.id for r in got] == [1, 2, 4], [r.id for r in got]


def test_chuzhoe_napravlenie_otsekaetsya():
    """Карточка говорит meyer — в компрессорную кампанию человек не идёт.

    Партия набрана ОДНОЙ группой на оба направления, кампаний две. Без этого
    фильтра письмо про рентген легло бы в компрессорную кампанию.
    """
    q = _кво(_Store(ГРУППЫ))
    q._card_for = lambda inn: {"enrich": {"company": {
        "division": "meyer" if str(inn).endswith("1") else "kc"}}}
    got = q._kandidaty_po_gruppe("Партия 935 — КЦ", set(), 10, campaign_id=10)
    assert 1 not in [r.id for r in got], [r.id for r in got]
    assert [r.id for r in got] == [2, 4], [r.id for r in got]


def test_sostavnoe_napravlenie_ne_otsekaem():
    """«kc+meyer» карточка не решила — не отсекаем, доопределит генерация."""
    q = _кво(_Store(ГРУППЫ))
    q._card_for = lambda inn: {"enrich": {"company": {"division": "kc+meyer"}}}
    got = q._kandidaty_po_gruppe("Партия 935 — Meyer", set(), 10, campaign_id=11)
    assert [r.id for r in got] == [1, 2, 4], [r.id for r in got]


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {ex}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
