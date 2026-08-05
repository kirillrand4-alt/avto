"""Группы получателей и фильтр очереди по ним (владелец 05.08).

Проверяю не «метод не падает», а то, ради чего он написан:

  * компания состоит в НЕСКОЛЬКИХ группах — `segment` одно-значный, и без
    списка `extra_json.gruppy` заливка отраслевой партии выкидывала бы
    компанию из новостной (так и случилось 05.08 с восемью адресами);
  * искать группу можно по id получателя, по почте и по ИНН — в очереди
    встречаются письма без `recipient_id`;
  * счётчик групп считает ПОЛУЧАТЕЛЕЙ, а не строки, и не врёт при пересечении.

Тест обязан уметь провалиться: если убрать чтение `gruppy`, падает первый же
случай.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.store import Store, RecipientIn  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "g.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def seeded(store):
    """Трое: только новостной, только металл, и состоящий в обеих группах."""
    store.upsert_recipient(RecipientIn(
        email="news@alfa.ru", domain="alfa.ru", inn="7701234567",
        company_name="Альфа", segment="новостные"))
    store.upsert_recipient(RecipientIn(
        email="snab@beta.ru", domain="beta.ru", inn="7709876543",
        company_name="Бета", segment="металлообработка"))
    store.upsert_recipient(RecipientIn(
        email="ogm@gamma.ru", domain="gamma.ru", inn="7702223334",
        company_name="Гамма", segment="новостные",
        extra={"gruppy": ["новостные", "металлообработка"]}))
    return store


def test_gruppy_iz_spiska_ne_teryayutsya(seeded):
    """Состоящий в двух группах виден в ОБЕИХ, хотя segment у него один."""
    г = seeded.recipient_groups()
    по_почте = г["по_почте"]
    assert по_почте["ogm@gamma.ru"] == {"новостные", "металлообработка"}
    # и при этом его segment по-прежнему новостной — отраслевая заливка
    # не должна была выкидывать его из новостной выборки
    assert "новостные" in по_почте["ogm@gamma.ru"]


def test_poisk_po_trem_klyucham(seeded):
    """Группа находится по id, по почте и по ИНН — в очереди бывает любое."""
    г = seeded.recipient_groups()
    assert г["по_инн"]["7709876543"] == {"металлообработка"}
    assert г["по_почте"]["snab@beta.ru"] == {"металлообработка"}
    ids = [i for i, наб in г["по_id"].items() if "металлообработка" in наб]
    assert len(ids) == 2          # Бета и Гамма


def test_schyot_grupp_ne_vryot_pri_peresechenii(seeded):
    """Счётчик: новостных 2 (Альфа, Гамма), металла 2 (Бета, Гамма)."""
    все = dict(seeded.recipient_groups()["все"])
    assert все["новостные"] == 2
    assert все["металлообработка"] == 2


def test_bez_gruppy_ne_popadaet_nikuda(store):
    """Получатель без segment и без списка не числится ни в одной группе:
    иначе фильтр «металлообработка» показал бы всё подряд."""
    store.upsert_recipient(RecipientIn(
        email="x@delta.ru", domain="delta.ru", inn="7700000001"))
    г = store.recipient_groups()
    assert "x@delta.ru" not in г["по_почте"]
    assert г["все"] == []


def test_krivoy_extra_ne_lomaet_ochered(store):
    """Битый extra_json не должен ронять очередь — она важнее аккуратности."""
    store.upsert_recipient(RecipientIn(
        email="y@eps.ru", domain="eps.ru", inn="7700000002",
        segment="новостные"))
    with store._lock:                                    # noqa: SLF001
        store._conn.execute(                             # noqa: SLF001
            "UPDATE recipients SET extra_json=? WHERE email=?",
            ('{"gruppy": [сломано', "y@eps.ru"))
        store._conn.commit()                             # noqa: SLF001
    г = store.recipient_groups()
    assert г["по_почте"]["y@eps.ru"] == {"новостные"}


def test_extra_perezhivaet_upsert(seeded):
    """Повторная заливка не должна терять список групп: панель пишет
    получателя ON CONFLICT(email), и extra уезжает целиком."""
    seeded.upsert_recipient(RecipientIn(
        email="ogm@gamma.ru", domain="gamma.ru", inn="7702223334",
        company_name="Гамма", segment="новостные",
        extra={"gruppy": ["новостные", "металлообработка"], "ball": 42}))
    with seeded._lock:                                   # noqa: SLF001
        ex = seeded._conn.execute(                       # noqa: SLF001
            "SELECT extra_json FROM recipients WHERE email=?",
            ("ogm@gamma.ru",)).fetchone()[0]
    assert set(json.loads(ex).get("gruppy") or []) == {"новостные", "металлообработка"}
