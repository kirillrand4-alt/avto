# FILE: sender/tests/test_personalize.py
"""Юнит-тесты персонализатора: happy-path, гейт, AI-хук, границы, идемпотентность."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.personalize import (  # noqa: E402
    Campaign,
    LegalCfg,
    Personalizer,
    PersonalizationGateError,
    Recipient,
    SequenceStep,
)

UTC = timezone.utc
NOW = datetime(2025, 1, 1, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Тестовые дублёры и билдеры
# --------------------------------------------------------------------------- #
class FakeConfig:
    """Duck-typed конфиг: get() из dict + опциональный legal()."""

    def __init__(self, values: dict | None = None, legal: LegalCfg | None = None):
        self._values = values or {}
        self._legal = legal

    def get(self, dotted_key: str, default=None):
        return self._values.get(dotted_key, default)

    def legal(self) -> LegalCfg:
        if self._legal is None:
            raise RuntimeError("legal-секция не задана")
        return self._legal


class FakeGen:
    """Мок AI-провайдера с записью вызовов."""

    def __init__(self, mapping: dict | None = None, raises: bool = False, value=None):
        self.calls: list[tuple[str, str | None]] = []
        self.mapping = mapping or {}
        self.raises = raises
        self.value = value

    def suggest_equipment(self, okved: str, segment: str | None) -> str:
        self.calls.append((okved, segment))
        if self.raises:
            raise RuntimeError("ai down")
        if self.value is not None:
            return self.value
        return self.mapping.get(okved, f"оборудование под ОКВЭД {okved}")


def _legal() -> LegalCfg:
    return LegalCfg(
        entity="ООО «Руспром»",
        inn="7700000000",
        unsub_base_url="https://parsercompressor.online/u",
        unsub_secret_env="UNSUB_SIGNING_SECRET",
        refusal_log_max_lag_hours=24,
    )


def make_personalizer(gen=None, values: dict | None = None, legal: bool = True) -> Personalizer:
    cfg = FakeConfig(values=values, legal=_legal() if legal else None)
    return Personalizer(cfg, gen_provider=gen)


def make_recipient(**over) -> Recipient:
    base = dict(
        id=1,
        email="ceo@acme.ru",
        domain="acme.ru",
        inn="7712345678",
        company_name="Акме",
        okved="28.412",
        segment="mid",
        bitrix_id="B1",
        contact_name="Иван Петров",
        mx_provider="yandex",
        valid_status="valid",
        catch_all=False,
        role_based=False,
        disposable=False,
        source="parser",
        extra={},
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(over)
    return Recipient(**base)


def make_campaign(**over) -> Campaign:
    base = dict(
        id=1,
        name="Q1 холодная",
        status="active",
        legal_entity="ООО «Руспром»",
        legal_inn="7700000000",
        provider_pool="pool_yandex",
        config={},
        created_at=NOW,
        started_at=None,
    )
    base.update(over)
    return Campaign(**base)


def make_step(**over) -> SequenceStep:
    base = dict(
        id=1,
        campaign_id=1,
        step_index=0,
        delay_hours=0,
        subject_tmpl="Тема",
        body_tmpl="Тело",
        engagement_gate="all",
        include_legal=False,
        active=True,
    )
    base.update(over)
    return SequenceStep(**base)


# --------------------------------------------------------------------------- #
# Happy-path
# --------------------------------------------------------------------------- #
def test_render_happy_path_with_ai():
    gen = FakeGen(value="промышленные компрессоры")
    p = make_personalizer(gen=gen)
    step = make_step(
        subject_tmpl="Предложение для {company_name}",
        body_tmpl="{greeting}\nМы поставляем {equipment_pitch}.",
    )
    result = p.render(step, make_recipient(), make_campaign())

    assert result.subject == "Предложение для Акме"
    assert result.body == "Здравствуйте, Иван!\nМы поставляем промышленные компрессоры."
    assert result.unfilled_fields == ()
    assert result.used_ai is True
    assert gen.calls == [("28.412", "mid")]


def test_render_no_ai_field_used_ai_false():
    p = make_personalizer()
    step = make_step(subject_tmpl="Привет {company}", body_tmpl="ИНН {inn}")
    result = p.render(step, make_recipient(), make_campaign())
    assert result.subject == "Привет Акме"
    assert result.body == "ИНН 7712345678"
    assert result.used_ai is False


# --------------------------------------------------------------------------- #
# Гейт незаполненных {}
# --------------------------------------------------------------------------- #
def test_render_gate_raises_on_unfilled():
    p = make_personalizer()
    step = make_step(body_tmpl="Здравствуйте, {contact_name}!")
    rcpt = make_recipient(contact_name=None)
    with pytest.raises(PersonalizationGateError):
        p.render(step, rcpt, make_campaign())


def test_preview_does_not_gate_and_keeps_raw():
    p = make_personalizer()
    step = make_step(body_tmpl="Здравствуйте, {contact_name}!")
    rcpt = make_recipient(contact_name=None)
    result = p.preview(step, rcpt, make_campaign())
    assert result.unfilled_fields == ("contact_name",)
    assert "{contact_name}" in result.body


def test_empty_placeholder_is_unfilled():
    p = make_personalizer()
    step = make_step(body_tmpl="Пусто {}")
    result = p.preview(step, make_recipient(), make_campaign())
    assert "{}" in result.unfilled_fields
    assert result.body == "Пусто {}"


def test_unfilled_deduped_across_subject_and_body():
    p = make_personalizer()
    step = make_step(subject_tmpl="{x}", body_tmpl="{x} и {y}")
    result = p.preview(step, make_recipient(), make_campaign())
    assert result.unfilled_fields == ("x", "y")


def test_fail_on_unfilled_disabled_returns_result():
    p = make_personalizer(values={"personalization.fail_on_unfilled": False})
    step = make_step(body_tmpl="Здравствуйте, {contact_name}!")
    rcpt = make_recipient(contact_name=None)
    result = p.render(step, rcpt, make_campaign())  # не бросает
    assert result.unfilled_fields == ("contact_name",)


# --------------------------------------------------------------------------- #
# AI-хук: ОКВЭД → оборудование
# --------------------------------------------------------------------------- #
def test_ai_called_once_for_subject_and_body():
    gen = FakeGen(value="станки")
    p = make_personalizer(gen=gen)
    step = make_step(subject_tmpl="{equipment_pitch}", body_tmpl="ещё {equipment_pitch}")
    result = p.render(step, make_recipient(), make_campaign())
    assert result.subject == "станки"
    assert result.body == "ещё станки"
    assert len(gen.calls) == 1  # значение кэшируется в merge-словаре


def test_ai_disabled_leaves_field_unfilled():
    gen = FakeGen(value="станки")
    p = make_personalizer(gen=gen, values={"personalization.ai_enabled": False})
    step = make_step(body_tmpl="{equipment_pitch}")
    result = p.preview(step, make_recipient(), make_campaign())
    assert "equipment_pitch" in result.unfilled_fields
    assert gen.calls == []


def test_ai_no_provider_leaves_field_unfilled():
    p = make_personalizer(gen=None)
    step = make_step(body_tmpl="{equipment_pitch}")
    with pytest.raises(PersonalizationGateError):
        p.render(step, make_recipient(), make_campaign())


def test_ai_no_okved_not_called():
    gen = FakeGen(value="станки")
    p = make_personalizer(gen=gen)
    step = make_step(body_tmpl="{equipment_pitch}")
    rcpt = make_recipient(okved=None)
    result = p.preview(step, rcpt, make_campaign())
    assert "equipment_pitch" in result.unfilled_fields
    assert gen.calls == []


def test_ai_provider_failure_does_not_crash():
    gen = FakeGen(raises=True)
    p = make_personalizer(gen=gen)
    step = make_step(body_tmpl="{equipment_pitch}")
    result = p.preview(step, make_recipient(), make_campaign())
    assert "equipment_pitch" in result.unfilled_fields
    assert len(gen.calls) == 1  # вызов был, но упал
    assert result.used_ai is False


def test_ai_not_called_when_field_not_referenced():
    gen = FakeGen(value="станки")
    p = make_personalizer(gen=gen)
    step = make_step(body_tmpl="Без AI-поля, {company}")
    result = p.render(step, make_recipient(), make_campaign())
    assert gen.calls == []
    assert result.used_ai is False


def test_ai_receives_okved_and_segment():
    gen = FakeGen(mapping={"62.01": "серверы"})
    p = make_personalizer(gen=gen)
    step = make_step(body_tmpl="{equipment_pitch}")
    rcpt = make_recipient(okved="62.01", segment="ent")
    result = p.render(step, rcpt, make_campaign())
    assert result.body == "серверы"
    assert gen.calls == [("62.01", "ent")]


# --------------------------------------------------------------------------- #
# extra / core / escaping / legal / greeting
# --------------------------------------------------------------------------- #
def test_extra_fields_are_available():
    p = make_personalizer()
    step = make_step(body_tmpl="Ваш промокод: {promo}")
    rcpt = make_recipient(extra={"promo": "SALE10"})
    result = p.render(step, rcpt, make_campaign())
    assert result.body == "Ваш промокод: SALE10"


def test_extra_does_not_override_core_field():
    p = make_personalizer()
    step = make_step(body_tmpl="{domain}")
    rcpt = make_recipient(extra={"domain": "evil.example"})
    result = p.render(step, rcpt, make_campaign())
    assert result.body == "acme.ru"


def test_escaped_braces_are_literal():
    p = make_personalizer()
    step = make_step(body_tmpl="Скидка {{10}}% для {company_name}")
    result = p.render(step, make_recipient(), make_campaign())
    assert result.body == "Скидка {10}% для Акме"


def test_legal_fields_from_campaign():
    p = make_personalizer()
    step = make_step(
        include_legal=True,
        body_tmpl="{legal_entity}, ИНН {legal_inn}",
    )
    camp = make_campaign(legal_entity="ООО «Руспром»", legal_inn="7700000000")
    result = p.render(step, make_recipient(), camp)
    assert result.body == "ООО «Руспром», ИНН 7700000000"


def test_greeting_and_first_name_derivation():
    p = make_personalizer()
    fields = p.available_fields(make_recipient(contact_name="Иван Петров"))
    assert fields["first_name"] == "Иван"
    assert fields["greeting"] == "Здравствуйте, Иван!"


def test_greeting_none_without_name():
    p = make_personalizer()
    fields = p.available_fields(make_recipient(contact_name=None))
    assert fields["first_name"] is None
    assert fields["greeting"] is None


# --------------------------------------------------------------------------- #
# available_fields
# --------------------------------------------------------------------------- #
def test_available_fields_includes_ai_and_legal():
    gen = FakeGen(value="компрессоры")
    p = make_personalizer(gen=gen)
    fields = p.available_fields(make_recipient())
    for key in ("email", "domain", "company_name", "first_name", "greeting", "okved"):
        assert key in fields
    assert fields["equipment_pitch"] == "компрессоры"
    assert fields["legal_entity"] == "ООО «Руспром»"
    assert fields["legal_inn"] == "7700000000"


def test_available_fields_without_gen_has_no_ai_field():
    p = make_personalizer(gen=None)
    fields = p.available_fields(make_recipient())
    assert "equipment_pitch" not in fields


# --------------------------------------------------------------------------- #
# Идемпотентность рендера
# --------------------------------------------------------------------------- #
def test_render_is_deterministic():
    gen = FakeGen(value="насосы")
    p = make_personalizer(gen=gen)
    step = make_step(
        subject_tmpl="Для {company}",
        body_tmpl="{greeting}\n{equipment_pitch}",
    )
    rcpt = make_recipient()
    camp = make_campaign()
    r1 = p.preview(step, rcpt, camp)
    r2 = p.preview(step, rcpt, camp)
    assert (r1.subject, r1.body, r1.unfilled_fields, r1.used_ai) == (
        r2.subject,
        r2.body,
        r2.unfilled_fields,
        r2.used_ai,
    )
