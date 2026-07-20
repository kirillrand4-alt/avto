# FILE: sender/personalize.py
"""Персонализация писем холодной рассылки «Руспром».

Модуль отвечает за рендер merge-полей шаблона касания в готовый текст
письма «от продажника» и за ГЕЙТ незаполненных плейсхолдеров.

Ключевые свойства (инварианты §5.4 контракта):
    * ``render`` возвращает ``RenderedMessage`` с кортежем ``unfilled_fields``;
      если он непуст и включён ``personalization.fail_on_unfilled`` — бросает
      :class:`PersonalizationGateError`. Ни одно письмо с сырым ``{плейсхолдером}``
      не должно уходить в отправку.
    * ``preview`` рендерит без гейта (для тестов/предпросмотра).
    * AI-хук :class:`GenProvider` (ОКВЭД→оборудование) вызывается лениво и
      только для полей, реально упомянутых в шаблоне; сбой AI не роняет рендер,
      поле просто остаётся незаполненным и его ловит гейт.

Зависимости: только стандартная библиотека.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable
from sender.errors import PersonalizationGateError, SenderError  # noqa: E402

__all__ = [
    "Personalizer",
    "GenProvider",
    "RenderedMessage",
    "Recipient",
    "Campaign",
    "SequenceStep",
    "LegalCfg",
    "PersonalizationGateError",
    "SenderError",
]

_log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Исключения. В интегрированной сборке приходят из sender.errors; для
# автономной работы модуля определяем совместимый фолбэк.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# DTO. В интегрированной сборке приходят из sender.types; ниже — фолбэк,
# строго повторяющий контракт §3 (нужные модулю поля).
# --------------------------------------------------------------------------- #
try:  # pragma: no cover - зависит от окружения
    from sender.dtos import (  # type: ignore
        Campaign,
        LegalCfg,
        Recipient,
        RenderedMessage,
        SequenceStep,
    )
except Exception:  # pragma: no cover - автономный режим

    @dataclass(frozen=True)
    class Recipient:
        id: int
        email: str
        domain: str
        inn: Optional[str]
        company_name: Optional[str]
        okved: Optional[str]
        segment: Optional[str]
        bitrix_id: Optional[str]
        contact_name: Optional[str]
        mx_provider: Optional[str]
        valid_status: str
        catch_all: Optional[bool]
        role_based: Optional[bool]
        disposable: Optional[bool]
        source: Optional[str]
        extra: dict[str, Any]
        created_at: datetime
        updated_at: datetime

    @dataclass(frozen=True)
    class Campaign:
        id: int
        name: str
        status: str
        legal_entity: str
        legal_inn: str
        provider_pool: Optional[str]
        config: dict[str, Any]
        created_at: datetime
        started_at: Optional[datetime]

    @dataclass(frozen=True)
    class SequenceStep:
        id: int
        campaign_id: int
        step_index: int
        delay_hours: int
        subject_tmpl: str
        body_tmpl: str
        engagement_gate: str
        include_legal: bool
        active: bool

    @dataclass(frozen=True)
    class RenderedMessage:
        subject: str
        body: str
        unfilled_fields: tuple[str, ...] = ()
        used_ai: bool = False

    @dataclass(frozen=True)
    class LegalCfg:
        entity: str
        inn: str
        unsub_base_url: str
        unsub_secret_env: str
        refusal_log_max_lag_hours: int


# --------------------------------------------------------------------------- #
# Протоколы
# --------------------------------------------------------------------------- #
@runtime_checkable
class GenProvider(Protocol):
    """AI-хук: по коду ОКВЭД и сегменту предлагает питч по оборудованию."""

    def suggest_equipment(self, okved: str, segment: str | None) -> str: ...


@runtime_checkable
class ConfigProto(Protocol):
    """Минимальный контракт конфига, нужный персонализатору."""

    def get(self, dotted_key: str, default: Any = ...) -> Any: ...


# --------------------------------------------------------------------------- #
# Разбор шаблона
# --------------------------------------------------------------------------- #
# Порядок альтернатив важен: экранированные скобки матчатся раньше плейсхолдера.
#   ``{{`` / ``}}`` → литеральные ``{`` / ``}``
#   ``{name}``      → merge-поле (name может быть пустым: ``{}`` = незаполнено)
_PLACEHOLDER = re.compile(r"\{\{|\}\}|\{(?P<name>[^{}]*)\}")

_MISSING = object()


def _resolve(key: str, fields: dict[str, Any]) -> str | None:
    """Вернуть строковое значение поля или ``None``, если оно незаполнено.

    Незаполнено = ключ отсутствует, значение ``None`` или пустая строка.
    """
    if not key:
        return None
    value = fields.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _first_name(contact_name: str | None) -> str | None:
    """Извлечь имя для обращения (первый токен) из ``contact_name``."""
    if not contact_name:
        return None
    parts = str(contact_name).split()
    return parts[0] if parts else None


def _greeting(contact_name: str | None) -> str | None:
    """Персональное приветствие «от продажника» или ``None`` без имени."""
    first = _first_name(contact_name)
    if not first:
        return None
    return f"Здравствуйте, {first}!"


def _cfg_get(config: ConfigProto, key: str, default: Any) -> Any:
    """Безопасно прочитать значение из конфига с дефолтом."""
    try:
        return config.get(key, default)
    except Exception:  # pragma: no cover - защита от чужого конфига
        return default


# --------------------------------------------------------------------------- #
# Персонализатор
# --------------------------------------------------------------------------- #
class Personalizer:
    """Рендер merge-полей шаблонов касаний с гейтом незаполненных ``{}``.

    Формат «от продажника»: помимо полей получателя доступны производные
    ``first_name`` и ``greeting`` для личного обращения. AI-поля (по умолчанию
    ``equipment_pitch``) заполняются через :class:`GenProvider` на основе ОКВЭД.
    """

    def __init__(self, config: ConfigProto, gen_provider: "GenProvider | None" = None) -> None:
        self._config = config
        self._gen = gen_provider
        self._fail_on_unfilled = bool(_cfg_get(config, "personalization.fail_on_unfilled", True))
        self._ai_enabled = bool(_cfg_get(config, "personalization.ai_enabled", True))
        ai_fields = _cfg_get(config, "personalization.ai_fields", ["equipment_pitch"])
        self._ai_fields: tuple[str, ...] = tuple(ai_fields or ())

    # -- публичный API ----------------------------------------------------- #
    def render(
        self, step: SequenceStep, recipient: Recipient, campaign: Campaign
    ) -> RenderedMessage:
        """Отрендерить касание с гейтом.

        raises:
            PersonalizationGateError: если остались незаполненные merge-поля
                и включён ``personalization.fail_on_unfilled``.
        """
        result = self._render(step, recipient, campaign)
        if result.unfilled_fields and self._fail_on_unfilled:
            raise PersonalizationGateError(
                "незаполненные merge-поля: " + ", ".join(result.unfilled_fields)
            )
        return result

    def preview(
        self, step: SequenceStep, recipient: Recipient, campaign: Campaign
    ) -> RenderedMessage:
        """Отрендерить без гейта — сырые плейсхолдеры остаются в тексте."""
        return self._render(step, recipient, campaign)

    def available_fields(self, recipient: Recipient) -> dict[str, Any]:
        """Все доступные для шаблона merge-поля данного получателя.

        Включает поля получателя, произвольные ``extra`` и (если задан
        gen_provider и код ОКВЭД) сгенерированные AI-поля. Юр-поля берутся
        из ``config.legal()``, т.к. кампания на этом уровне неизвестна.
        """
        fields = self._base_fields(recipient, campaign=None)
        self._apply_ai(fields, recipient, only=None)
        return dict(fields)

    # -- внутреннее -------------------------------------------------------- #
    def _render(
        self, step: SequenceStep, recipient: Recipient, campaign: Campaign
    ) -> RenderedMessage:
        # AI дорогой — генерируем только для полей, реально упомянутых в шаблоне.
        referenced = self._referenced_fields(step.subject_tmpl) | self._referenced_fields(
            step.body_tmpl
        )
        fields = self._base_fields(recipient, campaign)
        ai_names = self._apply_ai(fields, recipient, only=referenced)

        subject, subj_unfilled, subj_ai = self._render_template(
            step.subject_tmpl, fields, ai_names
        )
        body, body_unfilled, body_ai = self._render_template(step.body_tmpl, fields, ai_names)
        body = self._ensure_attribution(body, fields)

        unfilled = tuple(dict.fromkeys([*subj_unfilled, *body_unfilled]))
        return RenderedMessage(
            subject=subject,
            body=body,
            unfilled_fields=unfilled,
            used_ai=bool(subj_ai or body_ai),
        )

    @staticmethod
    def _ensure_attribution(body: str, fields: dict[str, Any]) -> str:
        """ФЗ-38 ст.18: рекламодатель идентифицируем в КАЖДОМ письме.

        Раньше юр-поля были лишь merge-полями: шаблон без {legal_inn} уходил
        вообще без атрибуции (include_legal ничем не управлял). Теперь футер
        «entity, ИНН …» дописывается безусловно, если ИНН ещё не в теле.
        Юр-линия владельца: адресное B2B-предложение (2026-07-18)."""
        entity = str(fields.get("legal_entity") or "").strip()
        inn = str(fields.get("legal_inn") or "").strip()
        if not entity and not inn:
            return body  # конфиг/кампания без юр-полей: подписывать нечем
        if inn and inn in body:
            return body  # атрибуция уже есть в шаблоне
        if not inn and entity and entity in body:
            return body
        parts = [p for p in (entity, f"ИНН {inn}" if inn else "") if p]
        return body.rstrip() + "\n\n--\n" + ", ".join(parts) + "\n"

    def _base_fields(self, recipient: Recipient, campaign: Campaign | None) -> dict[str, Any]:
        """Собрать merge-словарь. Core-поля получателя не перезаписываются ``extra``."""
        fields: dict[str, Any] = {
            "email": recipient.email,
            "domain": recipient.domain,
            "inn": recipient.inn,
            "company_name": recipient.company_name,
            "company": recipient.company_name,  # удобный алиас
            "okved": recipient.okved,
            "segment": recipient.segment,
            "bitrix_id": recipient.bitrix_id,
            "contact_name": recipient.contact_name,
            "source": recipient.source,
            "first_name": _first_name(recipient.contact_name),
            "greeting": _greeting(recipient.contact_name),
        }
        # Произвольные merge-поля заполняют только незанятые ключи.
        for key, value in (getattr(recipient, "extra", None) or {}).items():
            fields.setdefault(str(key), value)

        if campaign is not None:
            # Юр-атрибуция кампании имеет приоритет над extra.
            fields["legal_entity"] = campaign.legal_entity
            fields["legal_inn"] = campaign.legal_inn
        else:
            self._apply_legal_defaults(fields)
        return fields

    def _apply_legal_defaults(self, fields: dict[str, Any]) -> None:
        """Подставить юр-поля из ``config.legal()`` (если конфиг его отдаёт)."""
        legal = None
        legal_fn = getattr(self._config, "legal", None)
        if callable(legal_fn):
            try:
                legal = legal_fn()
            except Exception:  # pragma: no cover - конфиг без legal-секции
                legal = None
        if legal is not None:
            fields.setdefault("legal_entity", getattr(legal, "entity", None))
            fields.setdefault("legal_inn", getattr(legal, "inn", None))

    def _apply_ai(
        self, fields: dict[str, Any], recipient: Recipient, only: set[str] | None
    ) -> set[str]:
        """Заполнить AI-поля через gen_provider. Вернуть множество имён, что заполнены.

        Сбой провайдера или отсутствие ОКВЭД не роняют рендер — поле остаётся
        незаполненным, и его ловит гейт.
        """
        used: set[str] = set()
        if not self._ai_enabled or self._gen is None:
            return used

        okved = getattr(recipient, "okved", None)
        for name in self._ai_fields:
            if only is not None and name not in only:
                continue
            current = fields.get(name)
            if current is not None and str(current).strip():
                continue  # уже задано явно (например, через extra)
            if not okved:
                continue  # генерировать не из чего → пусть решает гейт
            try:
                value = self._gen.suggest_equipment(okved, getattr(recipient, "segment", None))
            except Exception as exc:
                _log.warning(
                    "gen_provider.suggest_equipment упал для okved=%s: %s", okved, exc
                )
                continue
            if value and str(value).strip():
                fields[name] = value
                used.add(name)
        return used

    @staticmethod
    def _referenced_fields(template: str | None) -> set[str]:
        """Множество непустых имён полей, упомянутых в шаблоне."""
        names: set[str] = set()
        for match in _PLACEHOLDER.finditer(template or ""):
            raw = match.group("name")
            if raw is None:
                continue  # экранированные скобки
            key = raw.strip()
            if key:
                names.add(key)
        return names

    @staticmethod
    def _render_template(
        template: str | None, fields: dict[str, Any], ai_names: set[str]
    ) -> tuple[str, list[str], bool]:
        """Подставить поля. Вернуть (текст, список_незаполненных, использован_ли_AI)."""
        unfilled: list[str] = []
        used_ai = False

        def repl(match: re.Match[str]) -> str:
            nonlocal used_ai
            matched = match.group(0)
            if matched == "{{":
                return "{"
            if matched == "}}":
                return "}"
            key = (match.group("name") or "").strip()
            value = _resolve(key, fields)
            if value is None:
                unfilled.append(key if key else "{}")
                return matched  # сохранить сырой плейсхолдер для наглядности
            if key in ai_names:
                used_ai = True
            return value

        rendered = _PLACEHOLDER.sub(repl, template or "")
        return rendered, unfilled, used_ai
