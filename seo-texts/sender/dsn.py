"""Разбор отчётов о недоставке (NDR/DSN): КТО именно отбился и ПОЧЕМУ.

Зачем отдельный модуль. Раньше отбивка разбиралась двумя строчками в
`imap_watcher`: адресат брался из `In-Reply-To`, а «жёсткость» определялась
регуляркой `5.\\d+.\\d+` по всему телу. На реальных отчётах это не работает:

* NDR почти никогда не ставит `In-Reply-To` — исходное письмо приложено
  внутрь отчёта (`message/rfc822`), и его `Message-ID` надо оттуда достать.
  Без этого `recipient_id` = None, обработчик выходит на первой строке, и
  отбивка не попадает НИ в стоп-лист, НИ в гейты (bounce-rate = 0 навсегда).
* Половина шлюзов не ставит расширенный код вовсе. Отчёт SecurityGateway
  (MDaemon) 05.08.2026 по el5-energo.ru — это «500 Message rejected» в
  транскрипте и «PERMANENT fatal delivery errors» в тексте: ни одного
  `5.x.x`, то есть для старой регулярки отбивки как бы не было.
* Обратная ошибка опаснее: `5.7.1` (политика/антиспам) старым кодом считался
  «жёстким» и адрес улетал в стоп-лист навсегда, хотя ящик жив и дело в
  контенте или репутации. Так теряются живые лиды.

Поэтому вердикт тут ТРЁХЗНАЧНЫЙ, а не «hard/soft»:

* ``hard``   — мёртв именно ящик (5.1.x, «user unknown»): адрес в стоп-лист.
* ``soft``   — временный отказ (4.x.x, переполнен, greylist): можно повторить.
* ``policy`` — письмо отвергнуто по политике/контенту/репутации (5.7.x,
  «message rejected», антивирус): ящик ЖИВОЙ, в стоп-лист НЕ кладём, но
  событие пишем — для гейтов это сигнал репутации.
* ``unknown``— не разобрали: только событие, никаких действий.

Правило разбора одно: суппрессить адрес только при явном свидетельстве, что
он мёртв. Всё неоднозначное — в ``policy``/``unknown``.
"""

from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass, field
from html import unescape as _html_unescape
from email.message import EmailMessage
from typing import Optional

__all__ = ["DsnInfo", "parse_dsn", "looks_like_dsn"]


# Адреса служб — они попадают в текст отчёта, но получателями не являются.
_SERVICE_LOCALS = {
    "postmaster", "mailer-daemon", "mailerdaemon", "noreply", "no-reply",
    "abuse", "bounce", "bounces", "root", "daemon",
}

# --- маркеры вердикта (по тексту, когда расширенного кода нет) ---

# Мёртвый ящик. Только формулировки про АДРЕС — «permanent»/«fatal» сюда не
# входят: у MDaemon эта пара стоит в каждом отчёте, включая отказы по контенту.
_HARD_TEXT = (
    "user unknown", "unknown user", "no such user", "no such recipient",
    "recipient not found", "user not found", "unknown recipient",
    "mailbox unavailable", "mailbox not found", "mailbox does not exist",
    "mailbox is disabled", "mailbox disabled", "account disabled",
    "address does not exist", "does not exist", "invalid recipient",
    "invalid mailbox", "unrouteable address", "unroutable address",
    "no mailbox here", "address rejected", "recipient rejected",
    "нет такого пользователя", "адрес не существует", "почтовый ящик не найден",
    "получатель не найден", "пользователь не найден",
)

# Временный отказ.
_SOFT_TEXT = (
    "quota", "over quota", "mailbox full", "mailbox is full",
    "insufficient storage", "try again", "temporarily", "temporary failure",
    "greylist", "greylisted", "deferred", "timed out", "timeout",
    "connection refused", "service unavailable", "too many connections",
    "rate limit", "ящик переполнен", "превышен лимит", "попробуйте позже",
    "временн",
)

# Отказ по политике/контенту/репутации — ящик жив.
_POLICY_TEXT = (
    "message rejected", "rejected by", "spam", "спам", "blocked", "blacklist",
    "blocklist", "denied by policy", "policy violation", "policy reject",
    "content", "virus", "malware", "attachment", "dmarc", "dkim", "spf",
    "not authorized", "access denied", "заблокирован", "отклонено",
    "нежелательн", "репутаци",
)

# --- регулярки ---

_ADDR = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"

_RE_STATUS = re.compile(r"^\s*Status:\s*([245]\.\d{1,3}\.\d{1,3})", re.M | re.I)
_RE_ACTION = re.compile(r"^\s*Action:\s*(\w+)", re.M | re.I)
_RE_DIAG = re.compile(r"^\s*Diagnostic-Code:\s*(.+)$", re.M | re.I)
# Запасной путь: Mail.ru пишет отказ ПРОСТЫМ ТЕКСТОМ, без заголовка
# Diagnostic-Code — «550 Message was not accepted -- invalid mailbox. Local
# mailbox … is unavailable: user not found». Из-за этого причина отбивки в
# журнале панели оставалась пустой (07.08: три отбивки подряд без единого
# слова о том, что случилось), хотя классификация hard срабатывала по тексту.
# Берём первую строку, начинающуюся с кода 4xx/5xx и содержащую слова.
_RE_DIAG_BODY = re.compile(
    r"^[ \t>]*((?:4|5)\d{2}(?:[ \t-]+\d\.\d{1,3}\.\d{1,3})?[ \t-]+"
    r"[^\n]*[A-Za-zА-Яа-яЁё][^\n]*)$", re.M)
# Хвост отбивки — приложенный оригинал нашего письма. Дальше него не смотрим:
# там свои заголовки и цитаты, и «550» из транскрипта соседнего письма увело
# бы диагноз в чужую историю.
_RE_ORIG_START = re.compile(
    r"^\s*(?:Return-path:|Received:\s+by|--- Below this line|"
    r"Content-Type:\s*message/rfc822|Message-ID:)", re.M | re.I)
_RE_FINAL_RCPT = re.compile(
    r"^\s*(?:Final|Original)-Recipient:\s*(?:rfc822;)?\s*<?(" + _ADDR + r")>?",
    re.M | re.I)
_RE_X_FAILED = re.compile(r"^\s*X-Failed-Recipients:\s*(.+)$", re.M | re.I)

# Форматы «кто не дошёл» у разных шлюзов.
_RE_FAILED_LINES = (
    # MDaemon / SecurityGateway: «Failed address: user@dom»
    re.compile(r"failed\s+address:\s*<?(" + _ADDR + r")>?", re.I),
    # Postfix: «<user@dom>: host said: 550 …»
    re.compile(r"^\s*<(" + _ADDR + r")>:", re.M),
    # Exim: «user@dom: … Unrouteable address»
    re.compile(r"^\s*(" + _ADDR + r"):\s+", re.M),
    # Exchange: «Your message to user@dom couldn't be delivered»
    re.compile(r"message\s+to\s+<?(" + _ADDR + r")>?\s+(?:could|couldn|was)", re.I),
    # Общая формула рунета: «письмо для user@dom не доставлено»
    re.compile(r"(?:для|адрес(?:у|ат)?)\s+<?(" + _ADDR + r")>?[^\n]{0,40}"
               r"не\s+(?:доставлен|достав)", re.I),
)

# Коды SMTP из транскрипта сессии: «<-- 550 …», «said: 550 …», «SMTP error … 554».
_RE_SMTP_CODE = (
    re.compile(r"<--\s*(\d{3})\b"),
    re.compile(r"said:\s*(\d{3})\b", re.I),
    re.compile(r"smtp\s+error[^\n]{0,60}?:\s*(\d{3})\b", re.I),
    re.compile(r"\b(\d{3})\s+[245]\.\d{1,3}\.\d{1,3}\b"),
)

_DSN_SUBJECT_MARKERS = (
    "delivery status notification", "delivery failure", "delivery report",
    "undelivered mail", "undeliverable", "returned mail", "returned to sender",
    "mail delivery failed", "non-delivery report", "failure notice",
    "delivery has failed", "postmaster",
    "не доставлено", "недоставленное", "ошибка доставки", "почтовый отчёт",
)


@dataclass(frozen=True)
class DsnInfo:
    """Что удалось вытащить из отчёта о недоставке."""

    verdict: str = "unknown"          # hard|soft|policy|unknown
    status: Optional[str] = None      # расширенный код 5.1.1 и т.п.
    action: Optional[str] = None      # failed|delayed|relayed
    smtp_code: Optional[int] = None   # первый 4xx/5xx из транскрипта
    diagnostic: str = ""              # Diagnostic-Code, если был
    failed: list[str] = field(default_factory=list)   # адреса, которые не дошли
    orig_message_id: Optional[str] = None             # Message-ID нашего письма
    orig_to: list[str] = field(default_factory=list)  # кому мы писали (из оригинала)
    reason: str = ""                  # по какому признаку выбран вердикт

    def as_detail(self) -> dict:
        """Компактный слепок в detail_json события (для панели и разборов)."""
        return {"verdict": self.verdict, "status": self.status,
                "smtp_code": self.smtp_code, "failed": self.failed,
                "diagnostic": self.diagnostic[:200], "reason": self.reason}


def dsn_po_strukture(msg: EmailMessage) -> bool:
    """УЛИКА отчёта в структуре письма, а не в словах и не в отправителе.

    Настоящий отчёт о недоставке всегда несёт машинную часть: сам тип
    multipart/report либо вложенную message/delivery-status. По ней отчёт
    отличается от чего угодно другого, что пришло с адреса postmaster@.
    """
    if msg.get_content_type() in ("multipart/report", "message/delivery-status"):
        return True
    if msg.is_multipart():
        return any(p.get_content_type() == "message/delivery-status"
                   for p in msg.walk())
    return False


def looks_like_dsn(msg: EmailMessage, subject: str, body: str) -> bool:
    """Похоже ли письмо на отчёт о недоставке (по типу, теме, отправителю).

    ЭТО ПРЕДПОЛОЖЕНИЕ, А НЕ ПРИГОВОР. Два последних признака - отправитель
    postmaster@ и слова в теме - дают ложные срабатывания: с postmaster@
    приходят ещё и агрегированные отчёты DMARC, которые о недоставке не
    говорят ничего. Решает вызывающий: у него после parse_dsn есть данные
    (адреса, код, статус), и пустой разбор без улики в структуре отбивкой
    считать нельзя.
    """
    if dsn_po_strukture(msg):
        return True
    from_addr = (msg.get("From", "") or "").lower()
    if any(f"{loc}@" in from_addr for loc in ("mailer-daemon", "postmaster")):
        return True
    text = f"{subject} {body}".lower()
    return any(m in text for m in _DSN_SUBJECT_MARKERS)


def _plain(text: str, *, html: bool) -> str:
    """Текст части в виде, пригодном для регулярок.

    Половина шлюзов шлёт отчёт HTML-ом, и транскрипт сессии там экранирован:
    строка «<-- 500 Message rejected» приезжает как «&lt;-- 500 …», а код из
    неё не достаётся. Снимаем разметку и entity-экранирование.
    """
    if html:
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    if "&" in text:
        text = _html_unescape(text)
    return text


def _clean_addr(addr: str) -> str:
    return addr.strip().strip("<>").strip().lower()


def _is_service(addr: str) -> bool:
    local = addr.split("@", 1)[0]
    return local in _SERVICE_LOCALS


def _collect_text(msg: EmailMessage):
    """Текст отчёта, части delivery-status, Message-ID и адресаты оригинала."""
    chunks: list[str] = []
    status_parts: list[EmailMessage] = []
    orig_mid: Optional[str] = None
    orig_to: list[str] = []

    parts = list(msg.walk()) if msg.is_multipart() else [msg]
    for part in parts:
        ctype = part.get_content_type()
        if ctype == "message/delivery-status":
            status_parts.append(part)
            # payload — список Message с полями DSN; печатаем как текст,
            # чтобы работали общие регулярки Status/Final-Recipient.
            payload = part.get_payload()
            if isinstance(payload, list):
                chunks.extend(str(p) for p in payload)
            else:
                chunks.append(str(payload))
            continue
        fname = (part.get_filename() or "").lower()
        # Оригинал письма шлюзы прикладывают тремя способами: message/rfc822,
        # text/rfc822-headers и — MDaemon/SecurityGateway — просто файлом
        # `*.eml` с типом application/octet-stream. Третий случай раньше терялся
        # целиком, вместе с Message-ID: отбивка оставалась без нашего письма.
        if (ctype in ("message/rfc822", "text/rfc822-headers")
                or fname.endswith((".eml", ".msg"))):
            inner = part.get_payload()
            if isinstance(inner, list) and inner:
                inner = inner[0]
            if not hasattr(inner, "get"):
                blob = None
                try:
                    blob = part.get_payload(decode=True)
                except Exception:  # noqa: BLE001
                    blob = None
                if blob:
                    try:
                        inner = email.message_from_bytes(
                            blob, policy=email.policy.default)
                    except Exception:  # noqa: BLE001
                        inner = None
            if hasattr(inner, "get"):
                orig_mid = orig_mid or (inner.get("Message-ID") or "").strip() or None
                for hdr in ("To", "X-Original-To", "Delivered-To"):
                    val = inner.get(hdr)
                    if val:
                        orig_to.extend(_clean_addr(a) for a in
                                       re.findall(_ADDR, str(val)))
            elif inner is not None:
                m = re.search(r"^\s*Message-ID:\s*(<[^>]+>)", str(inner), re.M | re.I)
                if m:
                    orig_mid = orig_mid or m.group(1).strip()
            continue
        if ctype.startswith("text/"):
            try:
                payload = part.get_payload(decode=True)
            except Exception:  # noqa: BLE001 - битая часть не должна ронять разбор
                payload = None
            text_part = ""
            if payload:
                charset = part.get_content_charset() or "utf-8"
                for enc in (charset, "utf-8", "cp1251", "koi8-r"):
                    try:
                        text_part = payload.decode(enc)
                        break
                    except (LookupError, UnicodeDecodeError):
                        continue
            else:
                text_part = str(part.get_payload())
            chunks.append(_plain(text_part, html=(ctype == "text/html")))

    text = "\n".join(chunks)
    if orig_mid is None:
        # Некоторые шлюзы вкладывают оригинал не отдельной частью, а текстом.
        m = re.search(r"^\s*Message-ID:\s*(<[^>]+>)", text, re.M | re.I)
        if m:
            orig_mid = m.group(1).strip()
    seen_to: set[str] = set()
    uniq_to = [a for a in orig_to
               if a and not _is_service(a) and not (a in seen_to or seen_to.add(a))]
    return text, status_parts, orig_mid, uniq_to


def _verdict(status: Optional[str], smtp_code: Optional[int],
             text: str) -> tuple[str, str]:
    """Вердикт + человекочитаемая причина выбора."""
    low = text.lower()

    if status:
        if status.startswith("4."):
            return "soft", f"status {status}"
        if status.startswith("5."):
            # 5.2.2 — «ящик переполнен»: адрес жив, это временное состояние.
            if status.startswith("5.2.2"):
                return "soft", f"status {status} (переполнен)"
            if status.startswith("5.1."):
                return "hard", f"status {status}"
            if status.startswith("5.2."):
                return "hard", f"status {status}"
            if status.startswith("5.7."):
                return "policy", f"status {status}"
            # 5.0.x/5.3.x/5.4.x/5.5.x/5.6.x — системные и протокольные: адрес
            # мёртвым не считаем, решаем по тексту.
            if any(m in low for m in _HARD_TEXT):
                return "hard", f"status {status} + текст"
            if any(m in low for m in _SOFT_TEXT):
                return "soft", f"status {status} + текст"
            return "policy", f"status {status}"

    if any(m in low for m in _HARD_TEXT):
        return "hard", "текст отчёта"
    if any(m in low for m in _SOFT_TEXT):
        return "soft", "текст отчёта"
    if any(m in low for m in _POLICY_TEXT):
        return "policy", "текст отчёта"

    if smtp_code is not None:
        if 400 <= smtp_code < 500:
            return "soft", f"SMTP {smtp_code}"
        if smtp_code >= 500:
            # Постоянный отказ без объяснения: адрес мог быть жив (контент,
            # репутация, правило шлюза). Суппрессить по догадке нельзя.
            return "policy", f"SMTP {smtp_code} без пояснения"
    return "unknown", "не разобрано"


def parse_dsn(raw: bytes | EmailMessage) -> DsnInfo:
    """Разобрать отчёт о недоставке. Никогда не бросает — при сбое `unknown`."""
    try:
        msg = (raw if isinstance(raw, EmailMessage)
               else email.message_from_bytes(raw, policy=email.policy.default))
        text, _status_parts, orig_mid, orig_to = _collect_text(msg)

        m = _RE_STATUS.search(text)
        status = m.group(1) if m else None
        if not status:
            # МИНИМАЛЬНЫЙ ОТЧЁТ КЛАДЁТ СТАТУС ЗАГОЛОВКОМ ВЕРХНЕГО УРОВНЯ.
            # Простые шлюзы шлют не multipart/report, а обычное письмо с
            # «Status: 5.1.1» в шапке; _collect_text берёт тела частей, и
            # такой статус терялся целиком - отчёт получал вердикт по одним
            # словам. Читаем и его: это единственная машинная улика,
            # отличающая такой отчёт от письма, просто похожего на отчёт.
            заголовок = str(msg.get("Status", "") or "").strip()
            if re.fullmatch(r"[245]\.\d{1,3}\.\d{1,3}", заголовок):
                status = заголовок
        m = _RE_ACTION.search(text)
        action = (m.group(1).lower() if m else None)
        m = _RE_DIAG.search(text)
        diagnostic = (m.group(1).strip() if m else "")
        if not diagnostic:
            голова = text[:_RE_ORIG_START.search(text).start()] \
                if _RE_ORIG_START.search(text) else text
            m2 = _RE_DIAG_BODY.search(голова)
            if m2:
                diagnostic = re.sub(r"\s+", " ", m2.group(1)).strip()

        smtp_code = None
        # Код из самого диагноза: у Mail.ru строка начинается прямо с «550 …»,
        # а шаблоны ниже ждут «said: 550», «<-- 550» или код рядом с 5.x.x —
        # поэтому код терялся вместе с причиной.
        m_code = re.match(r"^(?:smtp;\s*)?([45]\d{2})\b", diagnostic or "")
        if m_code:
            smtp_code = int(m_code.group(1))
        for rx in _RE_SMTP_CODE:
            if smtp_code is not None:
                break                     # код уже взят из самого диагноза
            found = [int(x) for x in rx.findall(text) if x.isdigit()]
            # Берём худший (5xx важнее 4xx, а 2xx из транскрипта — шум).
            bad = [c for c in found if c >= 400]
            if bad:
                smtp_code = max(bad)
                break

        failed: list[str] = []
        for addr in _RE_FINAL_RCPT.findall(text):
            failed.append(_clean_addr(addr))
        hdr = _RE_X_FAILED.search(text) or None
        if hdr is None and msg.get("X-Failed-Recipients"):
            failed.extend(_clean_addr(a) for a in
                          str(msg.get("X-Failed-Recipients")).split(","))
        elif hdr is not None:
            failed.extend(_clean_addr(a) for a in hdr.group(1).split(","))
        if not failed:
            for rx in _RE_FAILED_LINES:
                for addr in rx.findall(text):
                    failed.append(_clean_addr(addr))
                if failed:
                    break

        seen: set[str] = set()
        clean: list[str] = []
        for addr in failed:
            if not addr or "@" not in addr or _is_service(addr) or addr in seen:
                continue
            seen.add(addr)
            clean.append(addr)

        verdict, reason = _verdict(status, smtp_code, text)
        # Action: delayed = отложено, а не отказ (Exchange/Postfix шлют такие
        # уведомления «письмо ещё в очереди»). Жёстким это быть не может.
        if action == "delayed" and verdict == "hard":
            verdict, reason = "soft", "Action: delayed"

        return DsnInfo(verdict=verdict, status=status, action=action,
                       smtp_code=smtp_code, diagnostic=diagnostic,
                       failed=clean, orig_message_id=orig_mid, orig_to=orig_to,
                       reason=reason)
    except Exception:  # noqa: BLE001 - разбор отчёта не имеет права ронять приём почты
        return DsnInfo(verdict="unknown", reason="ошибка разбора")
