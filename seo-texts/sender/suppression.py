# FILE: sender/suppression.py
"""Suppression-модуль сендера «Руспром».

Отвечает за проверку и добавление получателей в стоп-лист по трём областям
видимости (scope): email → domain → inn. Реализует нормализацию email/домена/ИНН,
загрузку competitor/suppression-списков из текстовых файлов и быстрый lookup
через индексы БД (делегируется в `store`).

Инварианты (см. §5 контракта):
  * suppression-first: сам модуль в БД не пишет напрямую — только через `store`;
  * идемпотентность добавления строится на UNIQUE(scope, value) в БД
    (`store.suppression_add` → (id, created?)), а не на «проверил-потом-вставил»;
  * `is_suppressed` проверяет строго в порядке email → domain → inn и игнорирует
    истёкшие записи (`expires_at`).

Зависимости: только stdlib. Общие типы/исключения импортируются из пакета, а при
изолированном запуске (тесты одного файла) используются встроенные фолбэки.
"""

from __future__ import annotations

import glob
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Optional,
    Protocol,
    runtime_checkable,
)

__all__ = [
    "Suppression",
    "normalize_email",
    "normalize_domain",
    "normalize_inn",
    "VALID_SCOPES",
    "VALID_REASONS",
    "SenderError",
    "StoreError",
    "SuppressedError",
    "ValidationError",
    "SuppressionIn",
    "SuppressionEntry",
    "Recipient",
]

log = logging.getLogger("sender.suppression")

# --------------------------------------------------------------------------- #
# Исключения: берём общий хребет пакета, иначе — локальный фолбэк.
# --------------------------------------------------------------------------- #
try:  # pragma: no cover - зависит от окружения
    from .errors import (  # type: ignore
        SenderError,
        StoreError,
        SuppressedError,
        ValidationError,
    )
except Exception:  # noqa: BLE001 - фолбэк для изолированного запуска

    class SenderError(Exception):
        """Базовое исключение сендера."""

    class StoreError(SenderError):
        """Ошибка слоя доступа к данным."""

    class SuppressedError(SenderError):
        """Получатель находится под suppression."""

    class ValidationError(SenderError):
        """Невалидные входные данные."""


# --------------------------------------------------------------------------- #
# DTO: берём общие из §3, иначе — совместимый фолбэк.
# --------------------------------------------------------------------------- #
try:  # pragma: no cover - зависит от окружения
    from .dtos import Recipient, SuppressionEntry, SuppressionIn  # type: ignore
except Exception:  # noqa: BLE001 - фолбэк для изолированного запуска

    @dataclass(frozen=True)
    class SuppressionIn:
        scope: str  # email|domain|inn
        value: str
        reason: str
        source: str = ""
        campaign_id: Optional[int] = None
        expires_at: Optional[datetime] = None

    @dataclass(frozen=True)
    class SuppressionEntry:
        id: int
        scope: str
        value: str
        reason: str
        source: Optional[str]
        campaign_id: Optional[int]
        created_at: datetime
        expires_at: Optional[datetime]

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


if TYPE_CHECKING:  # pragma: no cover
    from .store import Store  # noqa: F401


# --------------------------------------------------------------------------- #
# Константы контракта.
# --------------------------------------------------------------------------- #
VALID_SCOPES: frozenset[str] = frozenset({"email", "domain", "inn"})
VALID_REASONS: frozenset[str] = frozenset(
    {"competitor", "unsubscribe", "complaint", "bounce_hard", "manual", "dsn"}
)

_LEADING_WWW = re.compile(r"^www\d*\.", re.IGNORECASE)
_NON_DIGIT = re.compile(r"\D+")


@runtime_checkable
class SuppressionStore(Protocol):
    """Минимальный контракт store, нужный suppression-модулю."""

    def suppression_lookup(
        self, *, email: str, domain: str, inn: str | None
    ) -> "SuppressionEntry | None": ...

    def suppression_add(self, e: "SuppressionIn") -> tuple[int, bool]: ...


# --------------------------------------------------------------------------- #
# Нормализация.
# --------------------------------------------------------------------------- #
def normalize_domain(domain: str) -> str:
    """Приводит домен к каноничному виду.

    Убирает схему, путь, порт, ведущий ``www.``, завершающую точку; понижает
    регистр и применяет IDNA (punycode) для интернационализированных доменов.
    Принимает и «грязный» ввод из списков (URL, ``user@domain``).
    """
    if not isinstance(domain, str):
        raise ValidationError("domain must be a string")
    d = domain.strip().lower()
    if not d:
        raise ValidationError("empty domain")

    if "://" in d:
        d = d.split("://", 1)[1]
    if "@" in d:  # на случай, когда передали email
        d = d.rsplit("@", 1)[1]
    # обрезаем путь/запрос/фрагмент
    for sep in ("/", "?", "#"):
        d = d.split(sep, 1)[0]
    # обрезаем порт (без затрагивания IPv6, которого в доменах не ждём)
    if d.count(":") == 1:
        d = d.split(":", 1)[0]
    d = _LEADING_WWW.sub("", d, count=1)
    d = d.strip().strip(".")
    if not d or "." not in d and not d.isascii():
        # одиночная метка допустима, но пустой домен — нет
        if not d:
            raise ValidationError(f"invalid domain: {domain!r}")

    try:
        d = d.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        # underscore-домены (_dmarc), уже-punycode и т.п. — оставляем как есть
        pass
    return d


def normalize_email(email: str) -> str:
    """Нормализует email: понижает регистр, снимает ``mailto:`` и угловые скобки,
    нормализует доменную часть. Локальную часть не трогает, кроме регистра.
    """
    if not isinstance(email, str):
        raise ValidationError("email must be a string")
    e = email.strip().lower()
    if not e:
        raise ValidationError("empty email")
    if e.startswith("mailto:"):
        e = e[len("mailto:"):].strip()
    if "<" in e and ">" in e:  # 'Name <addr>' → addr
        start = e.rfind("<")
        end = e.rfind(">")
        if end > start:
            e = e[start + 1:end]
    e = e.strip().strip("<>").strip()

    if e.count("@") != 1:
        raise ValidationError(f"invalid email: {email!r}")
    local, _, domain_part = e.partition("@")
    local = local.strip()
    if not local:
        raise ValidationError(f"invalid email (empty local part): {email!r}")
    domain = normalize_domain(domain_part)
    return f"{local}@{domain}"


def normalize_inn(inn: str | int) -> str:
    """Нормализует ИНН: оставляет только цифры, проверяет длину (10 или 12)."""
    if inn is None:
        raise ValidationError("empty inn")
    digits = _NON_DIGIT.sub("", str(inn))
    if not digits:
        raise ValidationError(f"invalid inn: {inn!r}")
    if len(digits) not in (10, 12):
        raise ValidationError(f"inn must be 10 or 12 digits, got {len(digits)}: {inn!r}")
    return digits


# --------------------------------------------------------------------------- #
# Основной класс.
# --------------------------------------------------------------------------- #
class Suppression:
    """Стоп-лист получателей. Проверка и добавление по email → domain → inn."""

    def __init__(self, store: "Store | SuppressionStore"):
        self._store = store

    # ---- проверка ------------------------------------------------------- #
    def is_suppressed(self, recipient: Recipient) -> SuppressionEntry | None:
        """Возвращает первую активную запись по приоритету email → domain → inn.

        Нормализует значения получателя и делегирует индексный lookup в `store`.
        Истёкшие записи (`expires_at` в прошлом) не считаются активными.
        """
        email = self._safe(normalize_email, recipient.email)
        if email is None:
            # частичный фолбэк, чтобы не потерять проверку из-за «грязного» ввода
            raw = (recipient.email or "").strip().lower()
            email = raw or None

        raw_domain = recipient.domain or (
            email.split("@", 1)[1] if email and "@" in email else None
        )
        domain = self._safe(normalize_domain, raw_domain) if raw_domain else None
        if domain is None and raw_domain:
            domain = raw_domain.strip().lower() or None

        inn = self._safe(normalize_inn, recipient.inn) if recipient.inn else None

        entry = self._store.suppression_lookup(
            email=email or "", domain=domain or "", inn=inn
        )
        if entry is not None and self._is_expired(entry):
            return None
        return entry

    # ---- добавление ----------------------------------------------------- #
    def add_email(
        self,
        email: str,
        reason: str,
        *,
        source: str = "",
        campaign_id: int | None = None,
    ) -> bool:
        """Добавляет email в стоп-лист. Возвращает True, если запись создана."""
        value = normalize_email(email)
        return self._add(
            "email", value, reason, source=source, campaign_id=campaign_id
        )

    def add_domain(self, domain: str, reason: str, *, source: str = "") -> bool:
        """Добавляет домен в стоп-лист. Возвращает True, если запись создана."""
        value = normalize_domain(domain)
        return self._add("domain", value, reason, source=source)

    def add_inn(self, inn: str, reason: str, *, source: str = "") -> bool:
        """Добавляет ИНН в стоп-лист. Возвращает True, если запись создана."""
        value = normalize_inn(inn)
        return self._add("inn", value, reason, source=source)

    def import_competitors(self, values: Iterable[str], scope: str = "domain") -> int:
        """Импортирует список конкурентов (reason='competitor').

        Значения нормализуются под `scope`, дублируются внутри партии убираются,
        невалидные пропускаются с логом. Возвращает число реально созданных записей.
        """
        return self._import_values(
            values, scope=scope, reason="competitor", source="competitor_list"
        )

    # ---- загрузка из файлов -------------------------------------------- #
    def import_file(
        self,
        path: str | Path,
        *,
        scope: str = "domain",
        reason: str = "competitor",
        source: str | None = None,
    ) -> int:
        """Загружает stop-список из текстового файла (одно значение на строку).

        Поддерживает пустые строки и комментарии: строка, начинающаяся с ``#``,
        и «хвост» после ``#`` игнорируются. Возвращает число созданных записей.
        """
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise StoreError(f"cannot read suppression file {p}: {exc}") from exc
        src = source if source is not None else f"file:{p.name}"
        lines = text.splitlines()
        return self._import_values(lines, scope=scope, reason=reason, source=src)

    def import_glob(
        self,
        pattern: str | Path,
        *,
        scope: str = "domain",
        reason: str = "competitor",
        source: str | None = None,
    ) -> int:
        """Загружает все файлы по glob-шаблону (например ``suppression-*.txt``)."""
        total = 0
        for match in sorted(glob.glob(str(pattern))):
            total += self.import_file(
                match, scope=scope, reason=reason, source=source
            )
        return total

    # ---- внутреннее ----------------------------------------------------- #
    def _add(
        self,
        scope: str,
        value: str,
        reason: str,
        *,
        source: str = "",
        campaign_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> bool:
        if scope not in VALID_SCOPES:
            raise ValidationError(f"unknown scope: {scope!r}")
        if reason not in VALID_REASONS:
            raise ValidationError(f"unknown reason: {reason!r}")
        if not value:
            raise ValidationError("empty suppression value")
        entry = SuppressionIn(
            scope=scope,
            value=value,
            reason=reason,
            source=source,
            campaign_id=campaign_id,
            expires_at=expires_at,
        )
        _id, created = self._store.suppression_add(entry)
        return bool(created)

    def _import_values(
        self,
        values: Iterable[str],
        *,
        scope: str,
        reason: str,
        source: str,
    ) -> int:
        if scope not in VALID_SCOPES:
            raise ValidationError(f"unknown scope: {scope!r}")
        seen: set[str] = set()
        created = 0
        for raw in values:
            if raw is None:
                continue
            line = str(raw).strip()
            if not line or line.startswith("#"):
                continue
            line = line.split("#", 1)[0].strip()  # inline-комментарий
            if not line:
                continue
            try:
                norm = self._normalize_for_scope(scope, line)
            except ValidationError:
                log.warning("skip invalid suppression value %r (scope=%s)", raw, scope)
                continue
            if norm in seen:
                continue
            seen.add(norm)
            try:
                if self._add(scope, norm, reason, source=source):
                    created += 1
            except (ValidationError, StoreError) as exc:
                log.warning("failed to add %r (scope=%s): %s", norm, scope, exc)
        return created

    @staticmethod
    def _normalize_for_scope(scope: str, value: str) -> str:
        if scope == "email":
            return normalize_email(value)
        if scope == "domain":
            return normalize_domain(value)
        if scope == "inn":
            return normalize_inn(value)
        raise ValidationError(f"unknown scope: {scope!r}")

    @staticmethod
    def _is_expired(entry: SuppressionEntry, now: datetime | None = None) -> bool:
        if entry.expires_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        exp = entry.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= now

    @staticmethod
    def _safe(fn, value):
        """Пробует нормализацию, возвращает None при ValidationError."""
        if value is None:
            return None
        try:
            return fn(value)
        except ValidationError:
            return None
