# FILE: sender/sender.py
"""Модуль отправки холодной рассылки «Руспром».

Реализует публичный API `Sender` из контракта: провайдер-сплит выбор ящика,
дневные лимиты по рамп-кривой, окно отправки/праздники, пейсинг, SMTP-доставку
через smtplib (с dry-run в локальную песочницу, совместимую с aiosmtpd),
формирование заголовков с List-Unsubscribe + RFC 8058 и идемпотентную отправку.

Модуль зависит только от stdlib. Зависимости (Config/Store/Suppression/Gates)
описаны Protocol-интерфейсами — их конкретные реализации живут в своих модулях.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import random
import re
import smtplib
import socket
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any, Optional, Protocol, Sequence, runtime_checkable
from sender.errors import ConfigError, GateTrippedError, PersonalizationGateError, RateLimitExceeded, SendError, SenderError, StoreError, SuppressedError, TransientError, ValidationError, YoungDomainGateError  # noqa: E402
from sender.gates import young_domain_reason  # noqa: E402
from sender.napravlenie_pisma import napravlenie_pisma  # noqa: E402
from sender.otkaz_spam import (СОБЫТИЕ as СОБЫТИЕ_ОТКАЗА,  # noqa: E402
                               eto_otkaz_spam, nachalo_sutok,
                               porogi, prichina_pauzy)
from sender.vne_bazy import razreshena as razreshena_vne_bazy  # noqa: E402

logger = logging.getLogger("sender.sender")

try:  # zoneinfo есть в 3.9+, оставляем безопасный фолбэк
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

__all__ = [
    "SenderError", "ConfigError", "StoreError", "SuppressedError",
    "ValidationError", "PersonalizationGateError", "SendError",
    "RateLimitExceeded", "GateTrippedError", "TransientError",
    "MailboxCfg", "WindowCfg", "GatesCfg", "LegalCfg",
    "Recipient", "Campaign", "Message", "MailboxState", "SuppressionEntry",
    "RenderedMessage", "SendResult", "GateDecision", "EventIn",
    "Sender",
]


# --------------------------------------------------------------------------- #
# Иерархия исключений (общий хребет §2): общие классы из sender.errors, чтобы
# orchestrator ловил их по идентичности; фолбэк держит модуль автономным.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# DTO из §3, используемые сендером
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Readiness:
    """Композитный флаг «ящик готов к бою» (Фаза 2.1, экран ящиков/конструктор)."""
    mailbox_id: str
    ready: bool
    ramp_day: int
    daily_limit: int
    sent_today: int
    paused: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MailboxCfg:
    mailbox_id: str
    provider: str
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    login: str
    password_env: str
    from_name: str
    signature: Optional[str] = None
    pool: Optional[str] = None
    is_warmup_node: bool = False


@dataclass(frozen=True)
class WindowCfg:
    tz: str
    days: tuple[int, ...]
    start: str
    end: str


@dataclass(frozen=True)
class GatesCfg:
    domain_bounce_pct: float
    domain_complaint_pct: float
    mailbox_bounce_pct: float
    global_complaint_pct: float
    min_volume: int
    # отказы почтовика × ящик за сутки (см. sender/otkaz_spam.py)
    mailbox_reject_pct: float = 2.0


@dataclass(frozen=True)
class LegalCfg:
    entity: str
    inn: str
    unsub_base_url: str
    unsub_secret_env: str
    refusal_log_max_lag_hours: int


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
class Message:
    id: int
    idempotency_key: str
    campaign_id: int
    recipient_id: int
    sequence_step_id: int
    mailbox_id: Optional[str]
    status: str
    scheduled_at: Optional[datetime]
    claimed_at: Optional[datetime]
    sent_at: Optional[datetime]
    rfc_message_id: Optional[str]
    in_reply_to: Optional[str]
    thread_id: Optional[str]
    subject: Optional[str]
    body_rendered: Optional[str]
    unsub_token: Optional[str]
    attempt_count: int
    last_error: Optional[str]


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


@dataclass
class MailboxState:
    mailbox_id: str
    provider: str
    day_key: str
    sent_today: int
    sent_total: int
    ramp_day: int
    daily_limit: int
    last_sent_at: Optional[datetime]
    paused: bool
    pause_reason: Optional[str]


@dataclass(frozen=True)
class RenderedMessage:
    subject: str
    body: str
    unfilled_fields: tuple[str, ...] = ()
    used_ai: bool = False


@dataclass(frozen=True)
class SendResult:
    ok: bool
    rfc_message_id: Optional[str]
    mailbox_id: str
    sent_at: Optional[datetime]
    error: Optional[str] = None
    retryable: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class GateDecision:
    scope: str
    target: str
    tripped: bool
    metric: str
    value: float
    threshold: float
    action: str


@dataclass(frozen=True)
class EventIn:
    dedup_key: str
    event_type: str
    event_ts: datetime
    message_id: Optional[int] = None
    recipient_id: Optional[int] = None
    campaign_id: Optional[int] = None
    mailbox_id: Optional[str] = None
    provider: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)


# Бренд направления для подписи. «Компрессор Центр» и Meyer — подразделения
# ОДНОГО юрлица: меняется только строка бренда, юрлицо и ИНН в подписи общие
# (ФЗ-38 требует атрибуцию по юрлицу, а не по направлению).
_BRAND_BY_DIVISION = {"kc": "Компрессор Центр", "meyer": "Руспром Мейер"}


def brand_for_division(config: Any, division: Optional[str]) -> str:
    """Название направления для подписи; переопределяется конфигом
    personalization.brand_by_division: {kc: "...", meyer: "..."}."""
    table = dict(_BRAND_BY_DIVISION)
    try:
        extra = config.get("personalization.brand_by_division", None)
    except Exception:  # noqa: BLE001 - фейк-конфиг в тестах
        extra = None
    if isinstance(extra, dict):
        table.update({str(k).lower(): str(v) for k, v in extra.items()})
    return table.get(str(division or "").lower()) or table["kc"]


# --------------------------------------------------------------------------- #
# Protocol-интерфейсы зависимостей (duck typing, конкретика в своих модулях)
# --------------------------------------------------------------------------- #
@runtime_checkable
class ConfigLike(Protocol):
    def mailboxes(self) -> list[MailboxCfg]: ...
    def provider_pools(self) -> dict[str, list[str]]: ...
    def ramp_curve(self, provider: str) -> list[int]: ...
    def sending_window(self) -> WindowCfg: ...
    def holidays(self) -> set[date]: ...
    def gates(self) -> GatesCfg: ...
    def legal(self) -> LegalCfg: ...
    def get(self, dotted_key: str, default: Any = ...) -> Any: ...


@runtime_checkable
class StoreLike(Protocol):
    def get_recipient(self, recipient_id: int) -> Optional[Recipient]: ...
    def get_campaign(self, campaign_id: int) -> Optional[Campaign]: ...
    def get_message(self, message_id: int) -> Optional[Message]: ...
    def mark_sent(self, message_id: int, rfc_message_id: str, sent_at: datetime) -> None: ...
    def mark_failed(self, message_id: int, error: str, *, retryable: bool,
                    mailbox_id: Optional[str] = None) -> None: ...
    def mark_skipped(self, message_id: int, reason: str) -> None: ...
    def increment_sent(self, mailbox_id: str, *, now: datetime) -> MailboxState: ...
    def append_event(self, e: EventIn) -> tuple[int, bool]: ...
    def get_mailbox_state(self, mailbox_id: str) -> Optional[MailboxState]: ...


@runtime_checkable
class SuppressionLike(Protocol):
    def is_suppressed(self, recipient: Recipient) -> Optional[SuppressionEntry]: ...


@runtime_checkable
class GatesLike(Protocol):
    def check_domain(self, domain: str, campaign_id: Optional[int] = None) -> GateDecision: ...
    def check_mailbox(self, mailbox_id: str) -> GateDecision: ...
    def check_global(self) -> GateDecision: ...


# --------------------------------------------------------------------------- #
# Вспомогательные функции
# --------------------------------------------------------------------------- #
def _parse_hhmm(value: str) -> time:
    hh, _, mm = value.partition(":")
    return time(hour=int(hh), minute=int(mm or 0))


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _strip_crlf(value: Optional[str]) -> str:
    """П2: значение заголовка в одну строку (CR/LF → пробел).

    Merge-поля приходят из CSV/extra/AI; \\r\\n в теме — это либо инъекция
    заголовков, либо «ядовитое» письмо: EmailMessage бросает ValueError,
    сообщение зависает в 'sending' и травит каждый тик. Санируем на границе.
    """
    if not value:
        return ""
    return " ".join(value.splitlines())


# --------------------------------------------------------------------------- #
# Sender
# --------------------------------------------------------------------------- #
class Sender:
    """Отправитель: выбор ящика, гейты лимитов/окна и SMTP-доставка.

    Инварианты §5, за которые отвечает сендер:
      * гейт незаполненных {} (п.4): непустой ``unfilled_fields`` → mark_failed
        (retryable=False) + PersonalizationGateError, ни одно письмо с сырым
        плейсхолдером не уходит;
      * suppression-first: перед отправкой повторно проверяется suppression;
      * kill-switch (п.5): при tripped-гейте отправка отклоняется;
      * идемпотентность: уже ``sent`` сообщение не переотправляется;
      * юр-гейт ФЗ-38/152: build_headers всегда добавляет List-Unsubscribe и
        List-Unsubscribe-Post: List-Unsubscribe=One-Click (RFC 8058).
    """

    def __init__(self, config: ConfigLike, store: StoreLike,
                 suppression: SuppressionLike, gates: GatesLike,
                 dry_run: bool = False, *, cards=None) -> None:
        self.config = config
        self.store = store
        self.suppression = suppression
        self.gates = gates
        self.dry_run = dry_run
        # Гейт направлений (ТЗ BASE-MERGE §4): CompanyCards с индексом обзвона.
        # None/неактивен (нет индекса) — гейт выключен (песочница/старые тесты);
        # на боевом сервере индекс ОБЯЗАТЕЛЕН — без него направление «пустое».
        self._cards = cards
        self._timeout = int(config.get("service.smtp_timeout_sec", 30) or 30)
        # Фабрика SMTP-соединений — переопределяема в тестах.
        self._smtp_opener = self._default_smtp_opener
        # open-tracking: трекер строится лениво и только при tracking.open_enabled
        self._open_tracker = None

    # ---- публичный API --------------------------------------------------- #
    def pick_mailbox(self, recipient: Recipient, campaign: Campaign,
                     *, now: Optional[datetime] = None,
                     manual: bool = False, message=None) -> Optional[str]:
        """Провайдер-сплит + лимиты + окно + пауза.

        Возвращает id наименее загруженного пригодного ящика из целевого пула,
        либо None, если слать сейчас некому. ``now`` инжектируется оркестратором
        (часы тика едины по всему пайплайну); без него — реальные часы.
        manual=True — ручная отправка: окно/пейсинг не учитываются при выборе.
        """
        now = _as_utc(now) if now is not None else datetime.now(timezone.utc)
        pool_name = self._route_pool(recipient, campaign)
        if not pool_name:
            return None
        mailbox_ids = self.config.provider_pools().get(pool_name, [])

        def _пригодные(ящики) -> list:
            годные: list[tuple[int, str]] = []
            for mid in ящики:
                # Гейт направлений (§4): непригодный по направлению ящик не
                # выбираем вовсе (компания без направления → пригодных нет —
                # заблокирована). message пробрасывается, чтобы подбор НЕ
                # предлагал ящик чужого направления: иначе компрессорное
                # письмо получит Meyer-адрес и уйдёт за подписью «Руспром
                # Мейер» (случай Омскводоканала).
                if self.division_block(recipient, mid, message=message) is not None:
                    continue
                if not self.can_send_now(mid, now=now, manual=manual):
                    continue
                state = self.store.get_mailbox_state(mid)
                if state is None or state.day_key != self._day_key(now):
                    load = 0
                else:
                    load = state.sent_today
                годные.append((load, mid))
            return годные

        eligible = _пригодные(mailbox_ids)
        if not eligible:
            # ПЕРЕЛИВ В ДРУГОЙ ПУЛ (владелец 18.08). Письмо на mail.ru ждёт
            # только наши mail.ru-ящики, и когда их дневной лимит выбран или
            # их закрыл гейт, оно лежит до завтра — при свободных яндексовых.
            # Перелив это меняет: свой пул сначала, чужой только если своего
            # не осталось.
            #
            # Плата за это понятна: репутацию за чужих получателей начинают
            # набирать наши другие домены. Поэтому берём в запасные ТОЛЬКО
            # чистые ящики — доля мёртвых отбивок ниже порога, — и рубильник
            # держим в конфиге, чтобы выключить одним движением.
            запасные = self._zapasnye_yashchiki(mailbox_ids)
            if запасные:
                eligible = _пригодные(запасные)
                if eligible:
                    mailbox_ids = запасные
        if not eligible:
            return None
        # Ротация по кругу (#59, владелец: «не с одного всё отправлялось, а с
        # разных по очереди»): следующий ящик — следующий ЗА последним реально
        # использованным по порядку пула. Раньше при равной загрузке (утро,
        # у всех 0) выигрывал первый по алфавиту — и вся ручная пачка уходила
        # с одного ящика. Указатель durable: последний sent-событие в БД.
        eligible.sort(key=lambda t: (t[0], t[1]))
        min_load = eligible[0][0]
        круг = [mid for load, mid in eligible if load <= min_load + 1]
        last = self._last_sent_mailbox()
        if last:
            порядок = list(mailbox_ids)
            if last in порядок:
                после = порядок.index(last)
                # первый пригодный по кругу ПОСЛЕ последнего использованного
                for шаг in range(1, len(порядок) + 1):
                    кандидат = порядок[(после + шаг) % len(порядок)]
                    if кандидат in круг:
                        return кандидат
        return eligible[0][1]

    def _zapasnye_yashchiki(self, свой_пул) -> list:
        """Ящики других пулов, куда можно перелить, когда свой выбран.

        Пусто, если перелив выключен (по умолчанию — выключен: до 18.08
        системы такого поведения не было, и включать его молча нельзя).
        Берём только те, у кого доля ЖЁСТКИХ отбивок ниже порога: смысл
        перелива — догрузить свободный ресурс, а не размазать плохую
        репутацию по всем доменам сразу.
        """
        try:
            вкл = bool(self.config.get("provider_split.overflow", False))
        except Exception:  # noqa: BLE001
            вкл = False
        if not вкл:
            return []
        try:
            порог = float(self.config.get(
                "provider_split.overflow_max_bounce_pct", 3.0) or 3.0)
        except Exception:  # noqa: BLE001
            порог = 3.0
        свои = set(свой_пул or ())
        прочие: list = []
        try:
            for имя, ящики in (self.config.provider_pools() or {}).items():
                for mid in ящики:
                    if mid in свои or mid in прочие:
                        continue
                    try:
                        d = self.gates.check_mailbox(mid)
                        if float(getattr(d, "value", 0.0)) > порог:
                            continue
                    except Exception:  # noqa: BLE001 - нет гейтов: не мешаем
                        pass
                    прочие.append(mid)
        except Exception:  # noqa: BLE001
            return []
        return прочие

    def _last_sent_mailbox(self) -> Optional[str]:
        """Ящик последней реальной отправки (авто или ручной) — указатель
        ротации. Нет метода/событий — None, выбор откатывается к загрузке."""
        getter = getattr(self.store, "last_sent_mailbox", None)
        if callable(getter):
            try:
                return getter()
            except Exception:  # noqa: BLE001
                return None
        return None

    def _napravlenie_pisma(self, message) -> Optional[str]:
        """kc|meyer|None — про КАКОЕ направление письмо, привязанное к message.

        Разбор ОБЩИЙ с ручным экраном (sender.napravlenie_pisma): поле
        panel.letter_division от генератора, а если его нет — товарная
        лексика самого письма.

        ЛЕКСИКА ЗДЕСЬ ПОЯВИЛАСЬ 21.08, И ВОТ ПОЧЕМУ. Раньше авто-путь читал
        только поле и метку компании, а ручной экран — ещё и лексику. Копии
        второму контакту карточку получают, а поля letter_division у них
        нет: 20.08 два письма «Гастрофабрике» про рентген-инспекцию и
        оптическую сортировку ушли с компрессорных ящиков
        (m.pavlov@kompressor-pro-trade.ru, v.melnikov@kompressor-air-trade.ru)
        за подписью «Компрессор Центр». Метка компании их не спасла:
        «kc+meyer» составное и направления не решает.

        Метка компании остаётся ПОСЛЕ лексики: текст письма — прямая улика,
        метка — косвенная.
        """
        mid = getattr(message, "id", None)
        if mid is None:
            return None
        try:
            row = self.store.confirm_review_for_message(int(mid))
        except Exception:  # noqa: BLE001 - нет метода/строки: гейт не строже
            return None
        if not row:
            return None
        d = napravlenie_pisma(row)
        if d:
            return d
        # ПОЛЕ ПУСТОЕ И ЛЕКСИКА МОЛЧИТ — НЕ ПОВОД ПРОПУСКАТЬ ЛЮБОЙ ЯЩИК
        # (владелец 17.08: «при автоотправке ящик не мог чужого направления
        # подтянуться, отправленные несколько мейер так были»).
        #
        # Запасной источник берём из ТОЙ ЖЕ панели: карточка компании несёт
        # своё направление (infopanel._company_block). Лишних чтений нет.
        # Составное «kc+meyer» не решает: там оба ящика законны, и гейт
        # остаётся на прежнем правиле «подходит ли компании направление
        # ящика».
        panel = row.get("panel") if isinstance(row.get("panel"), dict) else {}
        c = (panel or {}).get("company")
        if isinstance(c, dict):
            d2 = str(c.get("division") or "").strip().lower()
            if d2 in ("kc", "meyer"):
                return d2
        return None

    def division_block(self, recipient, mailbox_id: str,
                       message=None) -> Optional[str]:
        """Гейт направлений (ТЗ BASE-MERGE §4): причина блока или None (ок).

        Правило (решение владельца 25.07): ящик направления шлёт компании, если
        это направление ей ПОДХОДИТ — по метке базы (в т.ч. составной «kc+meyer»)
        ИЛИ по потребностям («Все категории оборудования»). Раньше сверялась одна
        метка, из-за чего 23709 компаний Meyer-сегмента с компрессорной
        потребностью были недоступны КЦ-ящикам. Ящик без division не участвует;
        компания вне базы обзвона заблокирована С ЛЮБЫХ ящиков (без изменений).
        Гейт активен, когда подключён индекс обзвона (cards.active); без него —
        None (песочница), на боевом сервере индекс обязателен.
        """
        cards = self._cards
        if cards is None or not getattr(cards, "active", False):
            return None
        mb = self._mailbox_cfg(mailbox_id)
        mb_div = getattr(mb, "division", None) if mb is not None else None
        if mb_div is None:
            return f"mailbox_without_division:{mailbox_id}"
        # ЯЩИК ОБЯЗАН СОВПАДАТЬ С ПИСЬМОМ, А НЕ ТОЛЬКО С КОМПАНИЕЙ (17.08).
        # Ниже гейт спрашивает «подходит ли компании направление этого ящика»,
        # и у фирмы с меткой kc+meyer ответ «да» для обоих. Но письмо всегда
        # про ОДНО направление, а подпись строится по направлению ЯЩИКА
        # (brand_for_division) — поэтому компрессорное письмо уходило с
        # Meyer-адреса за подписью «Руспром Мейер». Так получил письмо
        # Омскводоканал. Ручной экран этого не допускал: он подбирает ящик по
        # letter_division. Здесь читаем то же поле последним рубежом.
        письмо_div = self._napravlenie_pisma(message)
        if письмо_div and письмо_div != mb_div:
            return (f"letter_vs_mailbox:letter={письмо_div},"
                    f"mailbox={mb_div}")
        inn = getattr(recipient, "inn", None)
        allowed = None
        getter = getattr(cards, "divisions", None)
        if callable(getter):
            allowed = getter(inn)
        if allowed is None:                      # старый фасад/мок — прежний путь
            comp_div = cards.division(inn)
            if comp_div is None:
                # ИНН не из базы обзвона. Тумблер владельца «слать вне базы»
                # (13.08): экран подтверждения его УЖЕ уважал (жёлтое
                # предупреждение, кнопка работает), а этот рубеж — нет, и
                # убивал письмо после нажатия. Читаем тумблер из общего места,
                # чтобы слои снова не разошлись.
                if razreshena_vne_bazy(self.store, self.config):
                    return None
                return "company_division_empty"
            allowed = {p for p in str(comp_div).split("+") if p}
        if not allowed:
            # В базе есть, но ни метки, ни потребностей. Тумблер сюда НЕ
            # относится (на экране подтверждения это тоже красный флаг).
            return "company_division_empty"
        if mb_div not in allowed:
            return (f"division_mismatch:mailbox={mb_div},"
                    f"company={'+'.join(sorted(allowed))}")
        return None

    def _log_division_block(self, *, message, recipient, mailbox_id: str,
                            reason: str, now: datetime, point: str) -> None:
        """Журнал division_gate_block (inn, email, mailbox, ts) — §4 ТЗ."""
        try:
            from sender.dtos import EventIn
            mb = self._mailbox_cfg(mailbox_id)
            self.store.append_event(EventIn(
                dedup_key=f"divgate|{point}|{message.id}",
                event_type="division_gate_block",
                message_id=message.id,
                recipient_id=message.recipient_id,
                campaign_id=message.campaign_id,
                mailbox_id=mailbox_id,
                provider=getattr(mb, "provider", None) if mb else None,
                event_ts=now,
                detail={"inn": getattr(recipient, "inn", None),
                        "email": getattr(recipient, "email", None),
                        "mailbox": mailbox_id, "reason": reason,
                        "point": point, "ts": now.isoformat()},
            ))
        except Exception:  # noqa: BLE001 - журнал не должен ронять блок
            logger.exception("division_gate_block: событие не записалось")

    def _otkaz_spam(self, message, mailbox_id: str, oshibka: str) -> None:
        """Записать отказ по спаму и НЕМЕДЛЕННО остановить, что пора.

        Два рубежа, оба считают ЗА СУТКИ (репутация на отказах меняется за
        часы, вчерашние отказы держать ящик не должны):
          * ящик — порог gates.otkaz_stop_yashchik (по умолчанию 2);
          * направление — порог gates.otkaz_stop_napravlenie (5): домены у
            направления общие, придушивают их вместе, и ждать, пока каждый
            ящик наберёт свои два, значит отдать почтовику ещё десяток писем.
        Порог 0 выключает рубеж.

        Событие пишем ВСЕГДА, даже если порог не достигнут: без него отказ
        снова окажется виден только в messages.last_error, куда не смотрит ни
        экран, ни гейт.
        """
        now = datetime.now(timezone.utc)
        сутки = nachalo_sutok(now)
        try:
            self.store.append_event(EventIn(
                dedup_key=f"otkaz|{message.id}|{int(now.timestamp())}",
                event_type=СОБЫТИЕ_ОТКАЗА,
                message_id=getattr(message, "id", None),
                recipient_id=getattr(message, "recipient_id", None),
                campaign_id=getattr(message, "campaign_id", None),
                mailbox_id=mailbox_id,
                provider=getattr(self._mailbox_cfg(mailbox_id), "provider", None),
                event_ts=now,
                detail={"error": str(oshibka)[:400]},
            ))
        except Exception:  # noqa: BLE001
            logger.exception("отказ по спаму: событие не записалось")

        порог_ящика, порог_напр = porogi(self.config)

        def _счёт(**фильтр) -> int:
            try:
                return int(self.store.count_events(
                    event_type=СОБЫТИЕ_ОТКАЗА, since=сутки, **фильтр))
            except Exception:  # noqa: BLE001 - старый стор без фильтров
                logger.warning("count_events не принял фильтр отказов")
                return 0

        if порог_ящика:
            свои = _счёт(mailbox_id=mailbox_id)
            if свои >= порог_ящика:
                self._pauza(mailbox_id, prichina_pauzy(свои, "ящик"))

        if not порог_напр:
            return
        mb = self._mailbox_cfg(mailbox_id)
        напр = getattr(mb, "division", None) if mb else None
        if not напр:
            return
        соседи = [x.mailbox_id for x in self.config.mailboxes()
                  if getattr(x, "division", None) == напр]
        всего = sum(_счёт(mailbox_id=m) for m in соседи)
        if всего >= порог_напр:
            for m in соседи:
                self._pauza(m, prichina_pauzy(всего, f"направление {напр}"))

    def _pometit_sboy(self, message_id: int, oshibka: str, retryable: bool,
                      mailbox_id: str) -> None:
        """mark_failed с ящиком, но не ломаясь о стор без этого параметра.

        Ящик в неудачной отправке начали писать 21.08 (без него отказы не
        разложить по ящикам). Старый стор и тестовые двойники такого
        параметра не знают — для них зовём по-прежнему, иначе правка учёта
        уронила бы саму отправку.
        """
        try:
            self.store.mark_failed(message_id, oshibka, retryable=retryable,
                                   mailbox_id=mailbox_id)
        except TypeError:
            self.store.mark_failed(message_id, oshibka, retryable=retryable)

    def _pauza(self, mailbox_id: str, prichina: str) -> None:
        """Поставить ящик на паузу, если он ещё не стоит. Идемпотентно."""
        try:
            ст = self.store.get_mailbox_state(mailbox_id)
            if ст is not None and getattr(ст, "paused", False):
                return
            self.store.set_mailbox_paused(mailbox_id, True, prichina)
            logger.warning("ЯЩИК НА ПАУЗЕ: %s — %s", mailbox_id, prichina)
        except Exception:  # noqa: BLE001
            logger.exception("не удалось поставить ящик %s на паузу", mailbox_id)

    def can_send_now(self, mailbox_id: str, *, now: datetime,
                     manual: bool = False, force: bool = False) -> bool:
        """Можно ли слать с ящика прямо сейчас (гейты, пауза, лимит, окно, пейсинг).

        manual=True — РУЧНАЯ отправка оператором (нажал «Отправить»): окно
        отправки и межписьменный пейсинг ПРОПУСКАЮТСЯ (оператор осознанно шлёт
        одно письмо сейчас), но kill-switch/пауза/лимит дня остаются.

        force=True — ВТОРОЕ, личное подтверждение оператора на конкретном
        письме (решение владельца 26.07: «при двойном подтверждении письмо
        должно уходить в любом случае»). Снимает и пауза/лимит/kill-switch.
        Автоматическая рассылка этот путь не использует: force приходит только
        из очереди подтверждений, по нажатию человека, и пишется в аудит.
        """
        now = _as_utc(now)
        mb = self._mailbox_cfg(mailbox_id)
        if mb is None:
            return False
        if force:
            return True
        if self.gates.check_global().tripped:
            return False
        if self.gates.check_mailbox(mailbox_id).tripped:
            return False

        state = self.store.get_mailbox_state(mailbox_id)
        if state is not None and state.paused:
            return False

        if not manual and not self._within_window(now):
            return False

        today = self._day_key(now)
        if state is None:
            ramp_day, sent_today, last_sent_at = 0, 0, None
        elif state.day_key != today:
            # смена дня: счётчик обнулён, рамп-день инкрементируется
            ramp_day, sent_today, last_sent_at = state.ramp_day + 1, 0, None
        else:
            ramp_day = state.ramp_day
            sent_today = state.sent_today
            last_sent_at = _as_utc(state.last_sent_at)

        limit = self._daily_limit(mb.provider, ramp_day, mb.mailbox_id)
        if sent_today >= limit:
            return False

        if not manual and last_sent_at is not None:
            # НЕ «or 90»: явный 0 в конфиге легален (пейсинг выключен)
            raw_gap = self.config.get("send_pacing.min_interval_sec", 90)
            min_gap = 90 if raw_gap is None else int(raw_gap)
            if (now - last_sent_at).total_seconds() < min_gap:
                return False
        return True

    def build_headers(self, message: Message, campaign: Optional[Campaign],
                      mailbox_id: str) -> dict[str, str]:
        """Формирует заголовки письма, включая List-Unsubscribe (RFC 8058)."""
        mb = self._mailbox_cfg(mailbox_id)
        if mb is None:
            raise ConfigError(f"unknown mailbox {mailbox_id!r}")
        recipient = self.store.get_recipient(message.recipient_id)
        if recipient is None:
            raise ValidationError(f"recipient {message.recipient_id} not found")

        rfc_id = message.rfc_message_id or self._gen_message_id(mailbox_id)
        # П2: CR/LF в значениях из данных (тема из merge-полей, from_name,
        # email старых строк БД) санируются — см. _strip_crlf.
        headers: dict[str, str] = {
            "Message-ID": rfc_id,
            "Date": format_datetime(datetime.now(timezone.utc)),
            "From": formataddr((_strip_crlf(mb.from_name), mb.mailbox_id)),
            "To": _strip_crlf(recipient.email),
            "Subject": _strip_crlf(message.subject),
            "MIME-Version": "1.0",
        }
        if message.in_reply_to:
            # П2 (хвост ревью №0): in_reply_to приходит из БД, куда попадает из
            # заголовков ВХОДЯЩЕЙ почты (imap_watcher/confirm) — чужой Message-ID
            # не доверяем так же, как merge-полям: CR/LF здесь либо инъекция,
            # либо «ядовитое» значение, на котором EmailMessage бросает
            # ValueError и письмо навсегда виснет в 'sending'.
            headers["In-Reply-To"] = _strip_crlf(message.in_reply_to)
            headers["References"] = _strip_crlf(message.in_reply_to)

        # Юр-гейт: заголовок отписки ставится, пока его не выключили явно
        # (legal.list_unsub_header: false — см. _list_unsubscribe_headers).
        # Токен считаем в любом случае: он же лежит в messages.unsub_token и
        # нужен http-отписке, если её когда-нибудь поднимут.
        token = message.unsub_token or self._make_unsub_token(
            message.recipient_id, message.campaign_id)
        headers.update(self._list_unsubscribe_headers(token, mb))
        return headers

    def send(self, message: Message, rendered: RenderedMessage,
             mailbox_id: str, *, now: Optional[datetime] = None,
             manual: bool = False, to_email: Optional[str] = None,
             force: bool = False) -> SendResult:
        """Отправляет одно письмо; в dry_run — в локальную песочницу.

        ``now`` — инжектируемые часы тика (лимит/окно/sent_at); без него —
        реальные. manual=True — РУЧНАЯ отправка оператором (нажал «Отправить»):
        окно/пейсинг пропускаются, но suppression/has_reply/kill-switch/пауза/
        лимит дня остаются (см. can_send_now). force=True — второе, ЛИЧНОЕ
        подтверждение оператора на письме с заслонами: снимает suppression
        (обход пишется в лог и в аудит панели). raises: RateLimitExceeded |
        GateTrippedError | SendError | TransientError | PersonalizationGateError
        | SuppressedError
        """
        injected_now = _as_utc(now) if now is not None else None
        # (1) Гейт незаполненных {} — до любых сетевых действий. §3 BASE-MERGE:
        # лид уходит в очередь «дозаполнить данные», не в могилу failed.
        if rendered.unfilled_fields:
            reason = "unfilled_placeholders:" + ",".join(rendered.unfilled_fields)
            if hasattr(self.store, "mark_needs_data"):
                self.store.mark_needs_data(message.id, reason)
            else:
                self.store.mark_failed(message.id, reason, retryable=False)
            raise PersonalizationGateError(reason)

        # (2) Идемпотентность: уже отправленное не переотправляем.
        current = self.store.get_message(message.id) or message
        if current.status == "sent":
            return SendResult(
                ok=True, rfc_message_id=current.rfc_message_id,
                mailbox_id=mailbox_id, sent_at=_as_utc(current.sent_at),
                dry_run=self.dry_run)

        # (3) Suppression-first.
        recipient = self.store.get_recipient(message.recipient_id)
        if recipient is None:
            self.store.mark_failed(message.id, "recipient_not_found", retryable=False)
            raise SendError(f"recipient {message.recipient_id} not found")
        # Правка адреса оператором (ревью №40): без подмены письмо физически
        # уходило на СТАРЫЙ адрес, а панель показывала новый. Копия получателя
        # с новым email/domain применяет к итоговому адресу и suppression (оба
        # прохода), и доставку, и send_log/consent.
        if to_email and to_email.strip().lower() != (recipient.email or "").strip().lower():
            import dataclasses as _dc
            _new_mail = to_email.strip()
            recipient = _dc.replace(recipient, email=_new_mail,
                                    domain=_new_mail.split("@")[-1].lower())
        entry = self.suppression.is_suppressed(recipient)
        if entry is not None and force:
            # Ручной обход по двойному подтверждению оператора (решение
            # владельца 26.07). Предупреждение в лог обязательно: среди причин
            # suppression бывают отписка и жалоба — это ФЗ-38, а не гигиена.
            logger.warning("ОБХОД suppression по решению оператора: %s (%s)",
                           recipient.email, entry.reason)
            entry = None
        if entry is not None:
            self.store.mark_skipped(message.id, f"suppressed:{entry.reason}")
            raise SuppressedError(f"{recipient.email} suppressed ({entry.reason})")

        # (3b) П1.5: ответ мог прийти МЕЖДУ claim и send (claim фильтрует
        # reply-события, но окно между ними ненулевое) — followup после ответа
        # недопустим. Guard hasattr: у мок-store в юнитах метода может не быть.
        if (not force and hasattr(self.store, "has_reply")
                and self.store.has_reply(message.recipient_id, message.campaign_id)):
            self.store.mark_skipped(message.id, "reply_received")
            raise SuppressedError(
                f"{recipient.email}: получен ответ, followup отменён")

        # (4) Kill-switch: глобальный → домен → ящик. force снимает и его:
        # это одно письмо, отправленное человеком вручную вторым подтверждением.
        if not force:
            if self.gates.check_global().tripped:
                raise GateTrippedError("global gate tripped")
            if self.gates.check_domain(recipient.domain, message.campaign_id).tripped:
                raise GateTrippedError(f"domain gate tripped: {recipient.domain}")
            if self.gates.check_mailbox(mailbox_id).tripped:
                raise GateTrippedError(f"mailbox gate tripped: {mailbox_id}")

        # (4b) Жёсткий гейт направлений (ТЗ BASE-MERGE §4, точка 3 — последний
        # рубеж перед SMTP). Держит и письма, попавшие в очередь ДО внедрения
        # гейта или мимо UI; ручную отправку тоже — это комплаенс, не тайминг.
        div_reason = None if force else self.division_block(
            recipient, mailbox_id, message=message)
        if div_reason is not None:
            gate_now = injected_now if injected_now is not None \
                else datetime.now(timezone.utc)
            self.store.mark_skipped(
                message.id, f"division_gate_block:{div_reason}")
            self._log_division_block(
                message=message, recipient=recipient, mailbox_id=mailbox_id,
                reason=div_reason, now=gate_now, point="smtp")
            raise SuppressedError(f"division gate: {div_reason}")

        # (4c) Гейт молодых доменов (решение владельца 05.08, урок трёх
        # отбивок): получатель на СОБСТВЕННОМ корп. сервере (mx_provider
        # other/unknown), а домену ящика меньше gates.young_domain.min_age_days
        # — корпоративный шлюз отрежет по NRD-списку, письмо не дойдёт и сожжёт
        # репутацию домена. Письмо НЕ убиваем (mark не ставим): заслон
        # временный, после созревания домена оно отправляемо как есть.
        # Ручной адрес (to_email) уже применён к recipient выше, но mx_provider
        # у копии — от БАЗОВОГО адреса; для вписанного оператором адреса
        # валидации нет (unknown) — это тоже держим.
        #
        # force ЭТОТ заслон НЕ снимает (решение владельца 06.08: «мне надо,
        # чтобы именно корпоративным не мог отправлять»). Раньше снимал, и это
        # была тихая дыра: гейт честно давал 409, панель предлагала «отправить
        # всё равно», второе подтверждение открывало ВСЁ разом — так письмо
        # ушло на iz.npo-saturn.ru и вернулось «550 5.7.1 blocked due to
        # security reason». Обход остаётся только через конфиг
        # gates.young_domain.allow_force: true — то есть осознанным решением
        # владельца, а не случайным кликом в диалоге.
        разрешён_обход = False
        try:
            разрешён_обход = bool(
                self.config.get("gates.young_domain.allow_force", False))
        except Exception:  # noqa: BLE001 - нет ключа -> обхода нет
            разрешён_обход = False
        if not (force and разрешён_обход):
            yd_reason = young_domain_reason(
                self.config, mailbox_id,
                getattr(recipient, "mx_provider", None), now=injected_now)
            if yd_reason is not None:
                if force:
                    logger.warning(
                        "young_domain: обход ЗАПРЕЩЁН даже по force (%s -> %s)",
                        mailbox_id, getattr(recipient, "email", "?"))
                raise YoungDomainGateError(yd_reason)

        # (5) Лимит/окно/пейсинг. manual → окно/пейсинг обходятся (см. метод),
        # но лимит дня/пауза/kill-switch остаются.
        now = injected_now if injected_now is not None else datetime.now(timezone.utc)
        if not self.can_send_now(mailbox_id, now=now, manual=manual, force=force):
            raise RateLimitExceeded(f"{mailbox_id}: cannot send now")

        # (5b) Пер-регион пейсинг (P1.5): «каждые N сек для компаний ЭТОГО
        # региона» — интервал считается по последнему sent-событию региона,
        # независимо от ящика. 0/не задан = выключено (как раньше).
        # manual пропускает и его: оператор шлёт одно письмо осознанно.
        region_gap = int(self.config.get("send_pacing.per_region_interval_sec", 0) or 0)
        if not manual and region_gap > 0:
            region = getattr(recipient, "region", None)
            if region and hasattr(self.store, "last_sent_ts_for_region"):
                last_regional = self.store.last_sent_ts_for_region(region)
                if last_regional is not None:
                    last_regional = _as_utc(last_regional)
                    if (now - last_regional).total_seconds() < region_gap:
                        raise RateLimitExceeded(
                            f"region pacing {region}: жду {region_gap}с между письмами")

        # (6) Сборка письма.
        campaign = self.store.get_campaign(message.campaign_id)
        headers = self.build_headers(message, campaign, mailbox_id)
        if to_email:
            headers["To"] = _strip_crlf(recipient.email)
        if rendered.subject:
            headers["Subject"] = _strip_crlf(rendered.subject)
        rfc_id = headers["Message-ID"]
        # Подпись менеджера: имя привязано к ЯЩИКУ отправителя (канон владельца
        # 23.07). Ставится здесь, а не на render, потому что ящик выбирается
        # ПОСЛЕ рендера — на этапе панели/черновика имя ещё неизвестно.
        rendered = self._apply_signature(rendered, mailbox_id, campaign)
        mime_bytes = self._build_mime(
            headers, rendered, pixel_url=self._open_pixel_url(message, campaign))
        mb = self._mailbox_cfg(mailbox_id)
        assert mb is not None  # проверено в build_headers/can_send_now

        # (6b) TOCTOU-зазор (ревью, подтверждено): между шагом (3) и доставкой
        # проходят обращения к store (кампания/заголовки/лимиты) — IMAP-ридер
        # успевает добавить bounce/unsub в suppression. Последняя проверка
        # ПРЯМО перед сетью, когда всё уже собрано.
        entry = self.suppression.is_suppressed(recipient)
        if entry is not None and force:
            logger.warning("ОБХОД позднего suppression по решению оператора: "
                           "%s (%s)", recipient.email, entry.reason)
            entry = None
        if entry is not None:
            self.store.mark_skipped(message.id, f"suppressed:{entry.reason}")
            raise SuppressedError(
                f"{recipient.email} suppressed late ({entry.reason})")

        # (7) Доставка + классификация ошибок.
        try:
            self._deliver(mb, mb.mailbox_id, recipient.email, mime_bytes)
        except TransientError as e:
            self._pometit_sboy(message.id, str(e), True, mailbox_id)
            raise
        except SendError as e:
            self._pometit_sboy(message.id, str(e), False, mailbox_id)
            # ОТКАЗ ПОЧТОВИКА ПО СПАМУ — ОСТАНАВЛИВАЕМСЯ СРАЗУ, А НЕ ПО
            # ОБХОДУ ГЕЙТОВ. 21.08 три мейеровских домена за час ушли с
            # одного отказа на 114 писем до двадцати девяти на сорок восемь,
            # и никто не остановился: отказ нигде не считался и лежал только
            # в messages.last_error. Владелец: «остановка отправки должна
            # идти сразу при начале попадания в спам».
            if eto_otkaz_spam(e):
                try:
                    self._otkaz_spam(message, mailbox_id, str(e))
                except Exception:  # noqa: BLE001 - учёт не смеет ронять отправку
                    logger.exception("отказ по спаму не записался")
            raise

        # (8) Фиксация успеха.
        sent_at = injected_now if injected_now is not None else datetime.now(timezone.utc)
        self.store.mark_sent(message.id, rfc_id, sent_at, mailbox_id=mailbox_id)
        # ЧТО ИМЕННО УШЛО. body_rendered писал только confirm_decide при
        # постановке в очередь отправки, а у ручной отправки из панели статус
        # сразу 'sent' — и тело письма не сохранялось нигде (в базе 0 писем с
        # телом из 14 отправленных). «Провалиться в письмо» из карточки
        # открытий было не во что. Пишем ФАКТИЧЕСКИЙ текст с подписью и
        # согласованием рода — ровно то, что получил адресат.
        if hasattr(self.store, "save_sent_body"):
            try:
                self.store.save_sent_body(
                    message.id, subject=headers.get("Subject", "") or rendered.subject,
                    body=rendered.body or "")
            except Exception:  # noqa: BLE001 - журнал не роняет отправку
                logger.exception("save_sent_body failed message_id=%s", message.id)
        # Копия в IMAP-папку «Отправленные». SMTP её НЕ создаёт: при ручной работе
        # копию кладёт почтовый клиент отдельной операцией. Без этого в ящике не
        # остаётся никаких следов отправки — владелец 27.07 открыл все 14 ящиков
        # и увидел пустые «Отправленные» при реально ушедших письмах.
        # Никогда не роняет отправку: письмо уже доставлено, копия — удобство.
        self._append_to_sent(mb, mime_bytes, sent_at)
        # Задача 3 (confirm-send): send_log — история контактов и 90-дневный
        # заслон повторного касания. Guard hasattr: мок-store юнитов.
        if hasattr(self.store, "send_log_add"):
            try:
                self.store.send_log_add(
                    email=recipient.email, inn=recipient.inn,
                    campaign_id=message.campaign_id, ts=sent_at,
                    message_id=message.id, rfc_message_id=rfc_id,
                    subject=headers.get("Subject", ""), outcome="sent")
            except Exception:  # noqa: BLE001 - лог не роняет отправку
                logger.exception("send_log_add failed message_id=%s", message.id)
        # ФЗ-152: фиксируем правовое основание касания (guard: у мок-store в
        # юнитах метода может не быть — журнал не должен ронять отправку)
        if hasattr(self.store, "log_consent"):
            try:
                self.store.log_consent(
                    email=recipient.email,
                    action="send",
                    recipient_id=recipient.id,
                    basis="direct_b2b_offer",
                    source=f"send:{message.id}",
                    campaign_id=message.campaign_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception("log_consent failed message_id=%s", message.id)
        # П2.7: день считаем в зоне конфига (та же, что у окна отправки), а не
        # по UTC — иначе счётчик/рамп катились бы в 03:00 МСК. Guard hasattr
        # для мок-store юнитов со старой сигнатурой.
        try:
            self.store.increment_sent(
                mailbox_id, now=sent_at, day_key=self._day_key(sent_at))
        except TypeError:
            self.store.increment_sent(mailbox_id, now=sent_at)
        self.store.append_event(EventIn(
            dedup_key=f"send:{message.id}", event_type="sent", event_ts=sent_at,
            message_id=message.id, recipient_id=message.recipient_id,
            campaign_id=message.campaign_id, mailbox_id=mailbox_id,
            provider=mb.provider))
        return SendResult(ok=True, rfc_message_id=rfc_id, mailbox_id=mailbox_id,
                          sent_at=sent_at, dry_run=self.dry_run)

    def send_reply(self, *, to_email: str, subject: str, body: str,
                   mailbox_id: str, in_reply_to: Optional[str] = None,
                   thread_id: Optional[str] = None,
                   recipient_id: Optional[int] = None,
                   references: Optional[str] = None) -> SendResult:
        """Отправить РУЧНОЙ ответ в тред (реакция на входящее письмо клиента).

        Это диалог, а не рассылка: окно/пейсинг/каденция не применяются, но
        юр-заслон отписки/жалобы ОСТАЁТСЯ (отписавшемуся не пишем даже в ответ),
        как и kill-switch ящика. In-Reply-To/References держат письмо в треде.
        List-Unsubscribe в ответе не ставим (это не рекламная рассылка).
        Атрибуция «ООО «Руспром»» уже в теле (render_reply/qa_reply следят).
        """
        to_email = (to_email or "").strip().lower()
        if not to_email:
            raise ValidationError("send_reply: пустой адрес")

        # Юр-заслон: отписка/жалоба сильнее ответа.
        from types import SimpleNamespace
        domain = to_email.rsplit("@", 1)[-1] if "@" in to_email else ""
        inn = None
        if recipient_id is not None:
            rcp = self.store.get_recipient(recipient_id)
            if rcp is not None:
                inn = rcp.inn
        entry = self.suppression.is_suppressed(
            SimpleNamespace(email=to_email, domain=domain, inn=inn))
        if entry is not None and entry.reason in ("unsubscribe", "complaint"):
            raise SuppressedError(
                f"{to_email} отписан/пожаловался ({entry.reason}) — не отвечаем")

        # kill-switch ящика (горящий ящик не используем даже для ответа).
        if self.gates.check_global().tripped:
            raise GateTrippedError("global gate tripped")
        if self.gates.check_mailbox(mailbox_id).tripped:
            raise GateTrippedError(f"mailbox gate tripped: {mailbox_id}")

        mb = self._mailbox_cfg(mailbox_id)
        if mb is None:
            raise ConfigError(f"unknown mailbox {mailbox_id!r}")

        rfc_id = self._gen_message_id(mailbox_id)
        headers: dict[str, str] = {
            "Message-ID": rfc_id,
            "Date": format_datetime(datetime.now(timezone.utc)),
            "From": formataddr((_strip_crlf(mb.from_name), mb.mailbox_id)),
            "To": _strip_crlf(to_email),
            "Subject": _strip_crlf(subject),
            "MIME-Version": "1.0",
        }
        if in_reply_to:
            headers["In-Reply-To"] = _strip_crlf(in_reply_to)
            # ВЕТКА ДИАЛОГА (правка владельца 26.07): клиент должен видеть ОТВЕТ
            # в своей переписке, а не отдельное письмо. Почтовики сшивают тред по
            # References — там должна быть ВСЯ цепочка (References входящего +
            # его Message-ID), а не один идентификатор. Дубли убираем, порядок
            # сохраняем (RFC 5322 §3.6.4).
            chain = []
            for token in (_strip_crlf(references or "")).split():
                if token and token not in chain:
                    chain.append(token)
            irt = _strip_crlf(in_reply_to)
            if irt not in chain:
                chain.append(irt)
            headers["References"] = " ".join(chain)
        # «Re:» в теме — второй признак ветки (Outlook и мобильные клиенты
        # группируют по нему); не дублируем, если оператор уже написал Re:.
        subj_clean = (subject or "").strip()
        if in_reply_to and not re.match(r'^\s*(re|ре)\s*:', subj_clean, re.I):
            subject = "Re: " + subj_clean
            headers["Subject"] = _strip_crlf(subject)

        # Подвал ответа = подвал первого касания (#65): та же подпись тем же
        # _apply_signature (имя менеджера из ящика, юр-атрибуция с ИНН).
        # Черновики, собранные ДО правки, несут старый обезличенный подвал
        # автоответчика — срезаем его по точной форме трёх последних строк.
        body = re.sub(
            r"\n[^\n]{0,60}\nООО «Руспром»\nprokompressor\.ru\s*$", "", body or "")
        rendered = self._apply_signature(
            RenderedMessage(subject=subject, body=body), mailbox_id)
        mime_bytes = self._build_mime(headers, rendered)
        body = rendered.body   # в лог/события уходит то, что реально отправили
        self._deliver(mb, mb.mailbox_id, to_email, mime_bytes)

        sent_at = datetime.now(timezone.utc)
        if hasattr(self.store, "send_log_add"):
            try:
                self.store.send_log_add(
                    email=to_email, inn=inn, ts=sent_at, rfc_message_id=rfc_id,
                    subject=subject, outcome="reply_sent")
            except Exception:  # noqa: BLE001
                logger.exception("send_log_add failed (reply) to=%s", to_email)
        with suppress(Exception):
            self.store.increment_sent(mailbox_id, now=sent_at,
                                      day_key=self._day_key(sent_at))
        # СТРОКА ПИСЬМА ДЛЯ ОТВЕТА (владелец 19.08: «оператор ответила на
        # письмо, но нигде нету информации об этом»). Раньше ответ жил только
        # в send_log и событии: в «Отправленных» его не было, в статистике
        # ящика тоже, а событие приходило без message_id. Виден он был лишь в
        # диалоге компании, который читает confirm_reviews.
        #
        # Отправка уже состоялась, поэтому ошибка здесь не смеет её отменить:
        # не завелась строка - пишем в лог и живём дальше.
        _mid = None
        if recipient_id is not None and hasattr(self.store, "otvet_kak_pismo"):
            try:
                _mid = self.store.otvet_kak_pismo(
                    recipient_id=int(recipient_id), mailbox_id=mailbox_id,
                    subject=subject, body=body, rfc_message_id=rfc_id,
                    sent_at=sent_at, in_reply_to=in_reply_to,
                    thread_id=thread_id)
            except Exception:  # noqa: BLE001
                logger.exception("ответ не записался письмом to=%s", to_email)
        with suppress(Exception):
            self.store.append_event(EventIn(
                dedup_key=f"reply_sent:{thread_id or to_email}:{rfc_id}",
                event_type="reply_sent", event_ts=sent_at,
                message_id=_mid,
                recipient_id=recipient_id, mailbox_id=mailbox_id,
                provider=mb.provider))
        return SendResult(ok=True, rfc_message_id=rfc_id, mailbox_id=mailbox_id,
                          sent_at=sent_at, dry_run=self.dry_run,
                          message_id=_mid)

    def pacing_interval(self) -> int:
        """Случайный интервал (сек) между письмами одного ящика для планировщика."""
        lo = int(self.config.get("send_pacing.min_interval_sec", 90) or 90)
        hi = int(self.config.get("send_pacing.max_interval_sec", 420) or 420)
        if self.config.get("send_pacing.jitter", True) and hi > lo:
            return random.randint(lo, hi)
        return lo

    # ---- приватные помощники -------------------------------------------- #
    def _route_pool(self, recipient: Recipient, campaign: Campaign) -> Optional[str]:
        routing = self.config.get("provider_split.routing", {}) or {}
        if self.config.get("provider_split.match_recipient_provider", True):
            provider = (recipient.mx_provider or "unknown").lower()
            pool = routing.get(provider) or routing.get("other")
            if pool:
                return pool
        if campaign is not None and campaign.provider_pool:
            return campaign.provider_pool
        return routing.get("other")

    def _mailbox_cfg(self, mailbox_id: str) -> Optional[MailboxCfg]:
        for mb in self.config.mailboxes():
            if mb.mailbox_id == mailbox_id:
                return mb
        return None

    def mailbox_readiness(self, mailbox_id: str, *, now: Optional[datetime] = None) -> Readiness:
        """Композитный флаг готовности ящика (локальные сигналы, без сети).

        NEW-BACKEND для веб-панели: флаг «Готов к бою» на экране ящиков и
        дропдаун-гейт в конструкторе. DNS/Постофис подключаются отдельно
        (sender/dns.py, postoffice.py) — здесь только паузa/гейт/квота/окно.
        """
        now = _as_utc(now) if now is not None else datetime.now(timezone.utc)
        state = self.store.get_mailbox_state(mailbox_id)
        # Ящик из конфига, у которого ещё нет строки состояния (ни одной
        # отправки), — это НЕ «неизвестный ящик»: он полноправно участвует в
        # ёмкости пула, просто счётчики нулевые. Раньше отдавали no_state, и
        # «Ёмкость пулов» такие ящики пропускала (владелец 28.07: «пулы не
        # обновились от добавления почт»).
        mb = None
        try:
            mb = next((m for m in self.config.mailboxes()
                       if m.mailbox_id == mailbox_id), None)
        except Exception:  # noqa: BLE001 - фейк-конфиг в тестах
            mb = None
        if state is None and mb is None:
            return Readiness(mailbox_id=mailbox_id, ready=False, ramp_day=0,
                             daily_limit=0, sent_today=0, paused=False,
                             reasons=("no_state",))
        # Строка состояния обновляется ТОЛЬКО при отправке, поэтому до первого
        # письма в новых сутках там лежат вчерашние sent_today и ramp_day.
        # can_send_now это учитывает (день сменился → счётчик 0, рамп +1), а
        # экраны читали строку как есть — и показывали вчерашнюю отправку и
        # вчерашний лимит (владелец 28.07: «пулы не обновляются по дням»).
        if state is None:
            ramp_day, sent_today, paused = 0, 0, False
            provider = getattr(mb, "provider", "") or ""
        elif state.day_key != self._day_key(now):
            ramp_day, sent_today = int(state.ramp_day) + 1, 0
            paused = bool(state.paused)
            provider = getattr(state, "provider", "") or getattr(mb, "provider", "") or ""
        else:
            ramp_day, sent_today = int(state.ramp_day), int(state.sent_today)
            paused = bool(state.paused)
            provider = getattr(state, "provider", "") or getattr(mb, "provider", "") or ""
        reasons: list[str] = []
        if paused:
            reasons.append("paused")
        try:
            if self.gates.check_mailbox(mailbox_id).tripped:
                reasons.append("gate_tripped")
        except Exception:  # noqa: BLE001
            pass
        # Лимит считаем ЗАНОВО, а не берём из строки состояния: в БД он записан
        # на момент сидирования (ramp_day=0), а фактический зависит от дня рампы
        # и от ручного потолка владельца. Иначе экран показывал бы одно, а
        # отправка руководствовалась другим.
        limit = self._daily_limit(provider, ramp_day, mailbox_id)
        if sent_today >= limit:
            reasons.append("quota_exhausted")
        if not self._within_window(now):
            reasons.append("outside_window")
        return Readiness(
            mailbox_id=mailbox_id, ready=not reasons, ramp_day=ramp_day,
            daily_limit=int(limit), sent_today=sent_today,
            paused=paused, reasons=tuple(reasons),
        )

    def _daily_limit(self, provider: str, ramp_day: int,
                     mailbox_id: str = "") -> int:
        """Дневной лимит ящика: рамп-кривая, но владелец может её ПРИЖАТЬ.

        Ручной потолок задаётся из панели (panel_settings['send_limits']:
        {"all": N, "per_mailbox": {"ящик": N}}) и работает только ВНИЗ — поднять
        выше рампы нельзя, иначе прогрев теряет смысл и репутация домена летит.
        Приоритет: лимит конкретного ящика > общий > рампа.

        Раньше настройка существовала (ручки /send-limits были в панели), но
        отправка её не читала — то есть тумблер ничего не ограничивал.
        """
        from sender.ramp import daily_send_limit
        base = daily_send_limit(self.config, provider, ramp_day)
        try:
            cfg = self.store.get_setting("send_limits")
        except Exception:  # noqa: BLE001 - нет стора/таблицы
            return base
        if isinstance(cfg, str) and cfg:
            import json as _json
            try:
                cfg = _json.loads(cfg)
            except Exception:  # noqa: BLE001
                cfg = None
        if not isinstance(cfg, dict):
            return base
        cap = None
        per = cfg.get("per_mailbox")
        if isinstance(per, dict) and mailbox_id and per.get(mailbox_id) is not None:
            cap = per.get(mailbox_id)
        elif cfg.get("all") is not None:
            cap = cfg.get("all")
        try:
            cap = int(cap) if cap is not None else None
        except (TypeError, ValueError):
            cap = None
        return base if cap is None else max(0, min(base, cap))

    def _window_override(self):
        """Окно отправки, заданное владельцем из панели (panel_settings), или None.
        Формат: {days:[1..7], start:"09:00", end:"11:00", tz:"Europe/Moscow"}.
        Живая настройка без рестарта/правки yaml — только для АВТО-отправки."""
        try:
            ov = self.store.get_setting("sending_window")
        except Exception:  # noqa: BLE001 - нет таблицы/стора
            return None
        if not isinstance(ov, dict) or not ov.get("days"):
            return None
        return ov

    def _within_window(self, now: datetime) -> bool:
        ov = self._window_override()
        по_получателю = False
        if ov is not None:
            tz = ov.get("tz") or self.config.get("timezone", "Europe/Moscow")
            days = [int(d) for d in ov.get("days", [])]
            start_s, end_s = ov.get("start", "09:00"), ov.get("end", "18:00")
            по_получателю = bool(ov.get("by_recipient_tz"))
        else:
            win = self.config.sending_window()
            tz, days, start_s, end_s = win.tz, list(win.days), win.start, win.end
        local = now.astimezone(self._zone(tz))
        if local.isoweekday() not in days:
            return False
        if local.date() in self.config.holidays():
            return False
        # «По времени получателя» (владелец 06.08). Час письма УЖЕ посчитан в
        # зоне получателя: cadence._shift_into_window(tz_name=recipient.tz)
        # ставит 09:00-11:00 по региону регистрации. Если после этого воротник
        # ещё раз проверит час по ОДНОЙ зоне, он зарубит именно то, ради чего
        # тумблер включён: утро Владивостока это ночь Москвы. Поэтому здесь
        # остаются дни и праздники, а час отдан расписанию письма.
        if по_получателю:
            return True
        return _parse_hhmm(start_s) <= local.time() <= _parse_hhmm(end_s)

    def _day_key(self, now: datetime) -> str:
        tz_name = self.config.get("timezone", "UTC")
        return now.astimezone(self._zone(tz_name)).strftime("%Y-%m-%d")

    @staticmethod
    def _zone(name: str):
        if ZoneInfo is None or not name:
            return timezone.utc
        try:
            return ZoneInfo(name)
        except Exception:
            return timezone.utc

    def _gen_message_id(self, mailbox_id: str) -> str:
        domain = mailbox_id.split("@")[-1] if "@" in mailbox_id else "localhost"
        return make_msgid(domain=domain)

    def _make_unsub_token(self, recipient_id: int, campaign_id: int) -> str:
        """Подписанный токен one-click отписки.

        FIX (сверх ревью-списка, юр-критично): раньше здесь был СВОЙ формат
        ``b64(rid:cid).sig``, а unsub_server проверяет формат sender.tokens
        (JSON {"rid","cid","ts"}) — ссылка из боевого письма давала 400 и
        отписка не работала вообще. Теперь токен выпускает то же ядро
        sender.tokens, которым его проверяет Unsub._verify_token.
        """
        legal = self.config.legal()
        secret = os.environ.get(legal.unsub_secret_env)
        if not secret:
            raise ConfigError(f"missing unsub secret env {legal.unsub_secret_env}")
        from sender.tokens import sign_token
        payload = {
            "rid": int(recipient_id),
            "cid": int(campaign_id),
            "ts": int(datetime.now(timezone.utc).timestamp()),
        }
        return sign_token(secret.encode(), payload)

    # Кандидаты имени папки «Отправленные» в порядке предпочтения. Сначала
    # спрашиваем сервер про спецфлаг \Sent (RFC 6154) — Яндекс и mail.ru его
    # отдают; список ниже нужен для серверов без SPECIAL-USE.
    _SENT_FALLBACKS = ('Sent', 'INBOX.Sent', 'Sent Items', 'Отправленные',
                       '&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-')

    def _sent_folder(self, imap) -> Optional[str]:
        """Имя папки отправленных: по флагу \\Sent, иначе по списку кандидатов."""
        try:
            typ, boxes = imap.list()
            if typ == 'OK' and boxes:
                names = []
                for raw in boxes:
                    line = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else str(raw)
                    m = re.match(r'\((?P<flags>[^)]*)\)\s+"[^"]*"\s+"?(?P<name>[^"]+)"?\s*$', line)
                    if not m:
                        continue
                    names.append((m.group('flags'), m.group('name')))
                for flags, name in names:
                    if '\\Sent' in flags:
                        return name
                have = {n for _, n in names}
                for cand in self._SENT_FALLBACKS:
                    if cand in have:
                        return cand
        except Exception:  # noqa: BLE001
            pass
        return 'Sent'

    def _append_to_sent(self, mb: MailboxCfg, mime_bytes: bytes,
                        sent_at: datetime) -> None:
        """Положить копию отправленного письма в IMAP-папку «Отправленные».

        SMTP копию не создаёт — при ручной переписке её кладёт почтовый клиент.
        Без этого шага в самом ящике нет никаких следов работы рассыльщика.

        Никогда не бросает: письмо на этот момент УЖЕ доставлено получателю,
        и неудача с копией не должна ни ронять отправку, ни помечать её failed.
        Выключается флагом imap.append_sent: false.
        """
        if self.dry_run:
            return          # письмо ушло в песочницу — в боевом ящике ему не место
        if not bool(self.config.get('imap.append_sent', True)):
            return
        imap = None
        try:
            import imaplib
            import os
            password = os.getenv(mb.password_env, '')
            if not password:
                logger.warning('append-to-sent: нет пароля в %s', mb.password_env)
                return
            timeout = float(self.config.get('imap.connect_timeout_sec', 20) or 20)
            imap = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=timeout)
            imap.login(mb.login, password)
            folder = self._sent_folder(imap)
            stamp = imaplib.Time2Internaldate(sent_at.timestamp())
            typ, _ = imap.append(f'"{folder}"', '\\Seen', stamp, mime_bytes)
            if typ != 'OK':
                logger.warning('append-to-sent: сервер отклонил APPEND в %r (%s)',
                               folder, typ)
        except Exception:  # noqa: BLE001 - копия не критична
            logger.exception('append-to-sent: копия в «Отправленные» не создана '
                             '(письмо доставлено, это не влияет на отправку)')
        finally:
            if imap is not None:
                try:
                    imap.logout()
                except Exception:  # noqa: BLE001
                    pass

    def _list_unsubscribe_headers(self, token: str, mb: MailboxCfg) -> dict[str, str]:
        """Заголовки отписки. HTTP-часть — опциональна (решение владельца 27.07).

        Модель владельца: ссылки отписки нет, повторных писем не ответившим не шлём.
        HTTPS-эндпоинт отписки при этом не поднят, а домен unsub_base_url не имеет
        A-записи — заявлять `List-Unsubscribe-Post: One-Click` и не обслуживать его
        хуже для репутации отправителя, чем не заявлять вовсе: почтовые провайдеры
        считают это сломанным механизмом, а не его отсутствием.

        Поэтому по умолчанию остаётся только `mailto:` — валидно по RFC 2369,
        рабочий канал отказа (письмо приходит на наш же ящик) и ничего не требует
        поднимать. Чтобы вернуть HTTP-вариант, достаточно поднять unsub_server
        наружу и выставить legal.unsub_http_enabled: true.
        """
        # Решение владельца 05.08: заголовка может не быть вовсе. Почтовики
        # рисуют по нему СВОЮ кнопку «Отписаться» рядом с отправителем — для
        # письма, которое пишет продажник от своего имени, это метка «рассылка».
        # Канал отказа при этом не исчезает: он в теле письма («не актуально —
        # напишите, больше не побеспокою») и в приёме входящих, где ответ с
        # просьбой отписаться идёт в стоп-лист и в журнал согласий (ФЗ-38 не
        # требует ни ссылки, ни заголовка — требует прекратить по требованию).
        # Вернуть заголовок: legal.list_unsub_header: true.
        if not bool(self.config.get("legal.list_unsub_header", True)):
            return {}
        mailto = f"mailto:{mb.mailbox_id}?subject=unsubscribe"
        if not bool(self.config.get("legal.unsub_http_enabled", False)):
            return {"List-Unsubscribe": f"<{mailto}>"}
        legal = self.config.legal()
        base = legal.unsub_base_url.rstrip("/")
        sep = "&" if "?" in base else "?"
        # Параметр строго `t` — его читает unsub_server._parse_token (раньше
        # писали `token=`, сервер отвечал «Missing token parameter»).
        url = f"{base}{sep}t={token}"
        return {
            "List-Unsubscribe": f"<{url}>, <{mailto}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    # Канон подписи владельца (23.07): {name} — имя менеджера из from_name
    # ящика, {inn} — юр-ИНН. Юр-атрибуция ВХОДИТ в подпись (ФЗ-38), поэтому
    # авто-футер render'а («-- entity, ИНН») перед подписью срезается, чтобы
    # не задваивать наименование юрлица.
    # Бренд в подписи — НЕ константа: «Компрессор Центр» и Meyer это разные
    # направления одного юрлица, и письмо про фотосепараторы, подписанное
    # «Компрессор Центр», выглядит как ошибка адресом (владелец 28.07).
    # Юрлицо и ИНН при этом общие — их подменять нельзя (ФЗ-38).
    _DEFAULT_SIGNATURE = (
        "С уважением,\n"
        "{role},\n"
        "{name}\n"
        "«{brand}»\n"
        "ООО «Руспром», ИНН {inn}")

    def _apply_signature(self, rendered: RenderedMessage, mailbox_id: str,
                         campaign: Optional[Campaign] = None) -> RenderedMessage:
        """Дописать подпись менеджера (имя из ящика) в тело письма.

        Выключается personalization.signature_enabled=false. Шаблон —
        personalization.signature_template (по умолчанию канон владельца).

        §8 (задача 57): кампания может задать своего подписанта — поля
        manager_name / manager_role в config_json кампании. Заданы — они
        сильнее имени из ящика; нет — как раньше, имя из from_name ящика и
        должность «Менеджер по продажам»."""
        import dataclasses
        try:
            if not bool(self.config.get("personalization.signature_enabled", True)):
                return rendered
            tmpl = self.config.get("personalization.signature_template",
                                   self._DEFAULT_SIGNATURE) or self._DEFAULT_SIGNATURE
            mb = self._mailbox_cfg(mailbox_id)
            brand = brand_for_division(self.config,
                                       getattr(mb, "division", None))
            # имя менеджера: from_name «Владислав Мельников, Компрессор Центр»
            # → «Владислав Мельников» (до первой запятой)
            raw_name = (getattr(mb, "from_name", "") or "").split(",")[0].strip()
            camp_cfg = getattr(campaign, "config", None) if campaign else None
            camp_cfg = camp_cfg if isinstance(camp_cfg, dict) else {}
            raw_name = str(camp_cfg.get("manager_name") or "").strip() or raw_name
            role = (str(camp_cfg.get("manager_role") or "").strip()
                    or "Менеджер по продажам")
            # ИНН юрлица: приоритет кампании (как у юр-футера), фолбэк config.legal
            inn = str(getattr(campaign, "legal_inn", "") or "") if campaign else ""
            if not inn:
                legal_fn = getattr(self.config, "legal", None)
                if callable(legal_fn):
                    with suppress(Exception):
                        inn = str(getattr(legal_fn(), "inn", "") or "")
            body = rendered.body or ""
            # срезать авто-футер атрибуции render'а («\n\n--\n…ИНН…\n»), чтобы
            # наименование юрлица не задвоилось внутри подписи.
            body = re.sub(r"\n+--\n[^\n]*ИНН[^\n]*\n?\s*$", "", body).rstrip()
            # РОД ОТПРАВИТЕЛЯ: письмо пишется до выбора ящика и всегда мужскими
            # формами, а ящик может быть женским — «Прочитал… Анастасия
            # Мирошниченко» (скрин владельца 28.07). Здесь ящик уже известен.
            from sender.gender_agree import agree_for_mailbox
            body = agree_for_mailbox(body, raw_name, self.config, mailbox_id)
            # {role} есть только в новом каноне; старые шаблоны из конфига
            # живут с {name}/{inn} — лишний kwarg format безвреден
            sig = tmpl.format(name=raw_name, inn=inn, role=role,
                              brand=brand)
            # Ревью №22: AI-письма ПО ПРАВИЛАМ заканчиваются строкой
            # «С уважением,» (это требование гейта генерации), а подпись
            # начинается с неё же — в каждом письме выходило двойное
            # «С уважением,». Если тело уже завершено этой строкой, дописываем
            # подпись БЕЗ её первой строки.
            body_tail = body.rstrip()
            sig_lines = sig.split("\n")
            if sig_lines and body_tail.endswith(sig_lines[0].rstrip()):
                sig = "\n".join(sig_lines[1:]).lstrip("\n")
                new_body = body_tail + "\n" + sig if sig else body_tail
            else:
                new_body = body + "\n\n" + sig
            return dataclasses.replace(rendered, body=new_body)
        except Exception:  # noqa: BLE001 - подпись не должна ронять отправку
            logger.exception("signature: не удалось применить, шлём как есть")
            return rendered

    def _open_pixel_url(self, message: Message, campaign: Optional[Campaign]) -> Optional[str]:
        """URL трекинг-пикселя или None (выключено/нет секрета/ошибка).

        Ошибка построения пикселя НИКОГДА не блокирует отправку — просто
        письмо уходит без трекинга (open — справочный сигнал).
        """
        if not bool(self.config.get("tracking.open_enabled", False)):
            return None
        try:
            from sender.tracking import OpenTracker
            if self._open_tracker is None:
                self._open_tracker = OpenTracker(self.config, self.store)
            tracker = self._open_tracker
            if not tracker.enabled_for(campaign):
                return None
            token = tracker.make_token(
                message.id, message.recipient_id, message.campaign_id)
            return tracker.pixel_url(token)
        except Exception:  # noqa: BLE001
            logger.exception("open-tracking: пиксель не построен, шлём без него")
            return None

    def _build_mime(self, headers: dict[str, str], rendered: RenderedMessage,
                    *, pixel_url: Optional[str] = None) -> bytes:
        msg = EmailMessage()
        msg.set_content(rendered.body or "")  # управляет Content-Type/CTE
        if pixel_url:
            # Пиксель живёт только в HTML-альтернативе; text/plain остаётся
            # каноничным телом (multipart/alternative, HTML — предпочтительный).
            from sender.tracking import inject_pixel, text_to_html
            msg.add_alternative(
                inject_pixel(text_to_html(rendered.body or ""), pixel_url),
                subtype="html")
        skip = {"Content-Type", "Content-Transfer-Encoding", "MIME-Version"}
        for key, value in headers.items():
            if key in skip or value is None:
                continue
            # П2 (хвост ревью №0): последний рубеж против header injection —
            # что бы ни насобирали вызывающие (build_headers, send_reply,
            # будущие пути), в MIME значение уходит одной логической строкой.
            # Иначе CR/LF из данных = либо второй Bcc/Subject, либо ValueError
            # от EmailMessage и «ядовитое» письмо, травящее каждый тик.
            msg[key] = _strip_crlf(value)
        # SMTP-policy: концы строк CRLF (RFC 5321). Дефолтный as_bytes даёт
        # LF-only, а smtplib.sendmail для bytes их НЕ конвертирует — боевой
        # SMTP тогда видит одну «строку» на всё письмо и режет «Line too long».
        from email.policy import SMTP as _SMTP_POLICY
        return msg.as_bytes(policy=_SMTP_POLICY)

    def _sandbox_addr(self) -> tuple[str, int]:
        raw = self.config.get("service.sandbox_smtp", "localhost:8025") or "localhost:8025"
        host, _, port = raw.partition(":")
        return host or "localhost", int(port or 25)

    def _default_smtp_opener(self, host: str, port: int, use_ssl: bool):
        if use_ssl:
            return smtplib.SMTP_SSL(host, port, timeout=self._timeout)
        return smtplib.SMTP(host, port, timeout=self._timeout)

    def _deliver(self, mb: MailboxCfg, from_addr: str, to_addr: str,
                 mime_bytes: bytes) -> None:
        """Открывает соединение и шлёт письмо. Классифицирует SMTP-ошибки."""
        if self.dry_run:
            host, port = self._sandbox_addr()
            use_ssl = False
            password = None
        else:
            host, port = mb.smtp_host, mb.smtp_port
            use_ssl = (mb.smtp_port == 465)
            password = os.environ.get(mb.password_env)
            if not password:
                raise SendError(f"missing password env {mb.password_env}")

        try:
            client = self._smtp_opener(host, port, use_ssl)
        except (smtplib.SMTPConnectError, socket.error, ConnectionError,
                TimeoutError, OSError) as e:
            raise TransientError(f"connect failed: {e}") from e

        try:
            # П2: submission-порт (587 и любой не-SSL, кроме песочницы) обязан
            # подняться в TLS ДО login — иначе пароль ушёл бы открытым текстом.
            # Раньше starttls() не вызывался вовсе: провайдеры резали AUTH, а
            # на разрешающих серверах пароль улетал в plaintext.
            if not self.dry_run and not use_ssl:
                try:
                    client.starttls()
                    # RFC 3207: после STARTTLS сессия начинается заново
                    with suppress(Exception):
                        client.ehlo()
                except smtplib.SMTPException as e:
                    raise SendError(
                        f"STARTTLS недоступен на {host}:{port} — "
                        f"пароль открытым текстом не отправляем: {e}") from e
                except (socket.error, ConnectionError, TimeoutError, OSError) as e:
                    raise TransientError(f"starttls io: {e}") from e
            if not self.dry_run and password:
                try:
                    client.login(mb.login, password)
                except smtplib.SMTPAuthenticationError as e:
                    raise SendError(f"auth failed: {e}") from e
                except smtplib.SMTPException as e:
                    raise TransientError(f"login io: {e}") from e
            try:
                client.sendmail(from_addr, [to_addr], mime_bytes)
            except smtplib.SMTPRecipientsRefused as e:
                raise self._classify_recipients(e) from e
            except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError,
                    smtplib.SMTPResponseException) as e:
                raise self._classify_code(getattr(e, "smtp_code", 554), str(e)) from e
            except (smtplib.SMTPServerDisconnected, socket.error, ConnectionError,
                    TimeoutError, OSError) as e:
                raise TransientError(f"smtp io: {e}") from e
        finally:
            with suppress(Exception):
                client.quit()

    @staticmethod
    def _classify_code(code: int, msg: str) -> SenderError:
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 554
        if 400 <= code < 500:
            return TransientError(msg)
        return SendError(msg)

    @staticmethod
    def _classify_recipients(e: smtplib.SMTPRecipientsRefused) -> SenderError:
        codes = [c for (c, _m) in e.recipients.values()]
        if codes and all(400 <= int(c) < 500 for c in codes):
            return TransientError(str(e))
        return SendError(str(e))
