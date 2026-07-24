"""{equipment}/{equipment_all} из продуктовой разметки базы обзвона в шаблонах.

Правила: разметка есть → детерминированная подстановка (без ИИ); разметки
нет → поле unfilled (гейт уведёт в «дозаполнить данные»); ИИ-питч получает
разметку контекстом, если реализация умеет kwarg hint (совместимость со
старыми GenProvider без hint сохраняется).
"""

import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from sender.company_card import CompanyCards  # noqa: E402
from sender.errors import PersonalizationGateError  # noqa: E402
from sender.personalize import Personalizer  # noqa: E402
from sender.tests.test_company_card import _build_index  # noqa: E402
from sender.dtos import Campaign, Recipient, SequenceStep  # noqa: E402
from datetime import datetime, timezone

UTC = timezone.utc


class _Cfg:
    def __init__(self, **over):
        self._d = over

    def get(self, key, default=None):
        return self._d.get(key, default)


def _recipient(inn="4201000625"):
    return Recipient(
        id=1, email="a@zavod.ru", domain="zavod.ru", inn=inn,
        company_name="ООО Завод", okved="25.11", segment="КЦ",
        bitrix_id=None, contact_name="Пётр Иванов", mx_provider="yandex",
        valid_status="valid", catch_all=None, role_based=None,
        disposable=None, source=None, extra={},
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC))


def _campaign():
    return Campaign(id=1, name="c", status="active",
                    legal_entity="ООО «Руспром»", legal_inn="2221239841",
                    provider_pool=None, config={},
                    created_at=datetime.now(UTC), started_at=None)


def _step(subject, body):
    return SequenceStep(id=1, campaign_id=1, step_index=0, delay_hours=0,
                        subject_tmpl=subject, body_tmpl=body,
                        engagement_gate="", include_legal=True, active=True)


def _cards(tmp_path):
    db, _ = _build_index(tmp_path)
    return CompanyCards(index_path=db)


def test_equipment_filled_from_markup(tmp_path):
    p = Personalizer(_Cfg(), cards=_cards(tmp_path))
    r = p.render(_step("Подбор: {equipment}", "Также: {equipment_all}"),
                 _recipient(), _campaign())
    assert r.subject == "Подбор: Компрессоры поршневые"
    assert "Компрессоры | Осушители" in r.body
    assert r.unfilled_fields == ()
    assert r.used_ai is False  # детерминированно, без ИИ


def test_no_markup_goes_unfilled(tmp_path):
    p = Personalizer(_Cfg(), cards=_cards(tmp_path))
    # ИНН не из базы обзвона → разметки нет → гейт (оркестратор уведёт
    # письмо в очередь «дозаполнить данные»)
    with pytest.raises(PersonalizationGateError, match="equipment"):
        p.render(_step("Подбор: {equipment}", "текст"),
                 _recipient(inn="7700000000"), _campaign())


def test_inactive_cards_backcompat():
    p = Personalizer(_Cfg())  # cards не передан — поведение прежнее
    with pytest.raises(PersonalizationGateError, match="equipment"):
        p.render(_step("Подбор: {equipment}", "текст"),
                 _recipient(), _campaign())


class _GenWithHint:
    def __init__(self):
        self.calls = []

    def suggest_equipment(self, okved, segment=None, *, hint=None):
        self.calls.append((okved, segment, hint))
        return f"питч про {hint or 'ОКВЭД ' + okved}"


class _GenLegacy:
    def __init__(self):
        self.calls = []

    def suggest_equipment(self, okved, segment=None):
        self.calls.append((okved, segment))
        return "легаси-питч"


def test_ai_pitch_gets_markup_as_hint(tmp_path):
    gen = _GenWithHint()
    p = Personalizer(_Cfg(), gen_provider=gen, cards=_cards(tmp_path))
    r = p.render(_step("s", "{equipment_pitch}"), _recipient(), _campaign())
    assert gen.calls[0][2] == "Компрессоры поршневые"  # hint = разметка AJ
    assert "питч про Компрессоры поршневые" in r.body
    assert r.used_ai is True


def test_ai_legacy_signature_still_works(tmp_path):
    gen = _GenLegacy()
    p = Personalizer(_Cfg(), gen_provider=gen, cards=_cards(tmp_path))
    r = p.render(_step("s", "{equipment_pitch}"), _recipient(), _campaign())
    assert gen.calls == [("25.11", "КЦ")]  # старый вызов без hint
    assert "легаси-питч" in r.body


def test_available_fields_exposes_equipment(tmp_path):
    p = Personalizer(_Cfg(), cards=_cards(tmp_path))
    fields = p.available_fields(_recipient())
    assert fields["equipment"] == "Компрессоры поршневые"
    assert fields["equipment_all"] == "Компрессоры | Осушители"


def test_internal_labels_replaced_with_display_names(tmp_path):
    """«Промышленные компрессоры от 200 000 ₽» — внутренняя сегментация
    владельца; клиент видит «компрессорное оборудование» (слово владельца)."""
    p = Personalizer(_Cfg(), cards=_cards(tmp_path))

    assert p._display_equipment(
        "Промышленные компрессоры от 200 000 ₽ | Генераторы азота"
    ) == "компрессорное оборудование | Генераторы азота"
    # дубли после маппинга схлопываются
    assert p._display_equipment(
        "Промышленные компрессоры от 200 000 ₽ | компрессорное оборудование"
    ) == "компрессорное оборудование"
    # конфиг-переопределение расширяет карту
    p2 = Personalizer(_Cfg(**{"personalization.equipment_display": {
        "Фотосепараторы": "оборудование для сортировки"}}),
        cards=_cards(tmp_path))
    assert p2._display_equipment("Фотосепараторы") == "оборудование для сортировки"
