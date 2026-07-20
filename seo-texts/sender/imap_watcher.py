import imaplib
import email
import email.policy
import re
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, Optional
from email.message import EmailMessage
from sender.errors import SenderError, StoreError  # noqa: E402

logger = logging.getLogger(__name__)

# Суб-классификация ответов (hot/интерес/автоответ/отказ) — опциональный модуль:
# до его появления/при сбое поведение прежнее (все reply равнозначны).
try:  # pragma: no cover - наличие модуля зависит от сборки
    from sender.reply_classify import classify_reply  # type: ignore
except Exception:  # noqa: BLE001
    classify_reply = None

# ---- Exceptions ----


# ---- DTO (из контракта) ----
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
    extra: dict
    created_at: datetime
    updated_at: datetime

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
    detail: dict = field(default_factory=dict)

@dataclass(frozen=True)
class InboundEvent:
    kind: str
    mailbox_id: str
    dedup_key: str
    rfc_message_id: Optional[str]
    from_addr: str
    thread_id: Optional[str]
    recipient_id: Optional[int]
    snippet: str
    raw_headers: dict

@dataclass(frozen=True)
class MessageIn:
    idempotency_key: str
    campaign_id: int
    recipient_id: int
    sequence_step_id: int
    scheduled_at: datetime
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None

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
    signature: Optional[str]
    pool: Optional[str]
    is_warmup_node: bool = False

# ---- Protocols ----
class Config(Protocol):
    def mailboxes(self) -> list[MailboxCfg]: ...
    def get(self, dotted_key: str, default=...) -> any: ...

class Store(Protocol):
    def find_message_by_rfc_id(self, rfc_message_id: str): ...
    def get_recipient(self, recipient_id: int) -> Optional[Recipient]: ...
    def append_event(self, e: EventIn) -> tuple[int, bool]: ...
    def enqueue_message(self, m: MessageIn) -> tuple[int, bool]: ...
    def has_reply(self, recipient_id: int, campaign_id: int) -> bool: ...
    def transaction(self): ...

class Suppression(Protocol):
    def add_email(self, email: str, reason: str, *, source: str = "", campaign_id: Optional[int] = None) -> bool: ...

class ReplyDeskSink(Protocol):
    def push_warm_lead(self, recipient: Recipient, thread_id: str, snippet: str) -> None: ...

# ---- ImapWatcher ----
class ImapWatcher:
    def __init__(
        self,
        config: Config,
        store: Store,
        suppression: Suppression,
        reply_desk: Optional[ReplyDeskSink] = None
    ):
        self._config = config
        self._store = store
        self._suppression = suppression
        self._reply_desk = reply_desk
        self._mailbox_map = {mb.mailbox_id: mb for mb in config.mailboxes()}
        self._uidvalidity_cache: dict[str, int] = {}
        self._auto_suppress_bounce = config.get("imap.auto_suppress_on_bounce", True)
        self._auto_suppress_complaint = config.get("imap.auto_suppress_on_complaint", True)
        # Greylist/soft-bounce 4.x.x: НЕ suppress (RU-провайдеры часто гриллистят) —
        # переотправить позже, с потолком попыток. 0 ретраев = поведение как раньше.
        self._soft_retry_max = int(config.get("imap.soft_bounce_max_retries", 2))
        self._soft_retry_delay_min = int(config.get("imap.soft_bounce_retry_delay_min", 45))

    def poll_once(self, mailbox_id: str) -> list[InboundEvent]:
        mb_cfg = self._mailbox_map.get(mailbox_id)
        if not mb_cfg:
            logger.warning(f"Unknown mailbox_id: {mailbox_id}")
            return []

        import os
        password = os.getenv(mb_cfg.password_env, "")
        if not password:
            logger.error(f"Missing password env {mb_cfg.password_env} for {mailbox_id}")
            return []

        events = []
        try:
            # timeout обязателен: без него недоступный IMAP вешает tick навечно
            imap_timeout = float(self._config.get("imap.connect_timeout_sec", 20) or 20)
            imap = imaplib.IMAP4_SSL(mb_cfg.imap_host, mb_cfg.imap_port,
                                     timeout=imap_timeout)
            imap.login(mb_cfg.login, password)
            imap.select("INBOX")

            uidvalidity = self._get_uidvalidity(imap, mailbox_id)
            batch_size = self._config.get("imap.batch", 50)

            typ, data = imap.search(None, "UNSEEN")
            if typ != "OK":
                logger.warning(f"IMAP search failed for {mailbox_id}: {typ}")
                imap.logout()
                return []

            uids = data[0].split()
            if not uids:
                imap.logout()
                return []

            uids = uids[:batch_size]
            for uid in uids:
                uid_str = uid.decode("utf-8")
                typ, msg_data = imap.fetch(uid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_bytes = msg_data[0][1]
                try:
                    ev = self.classify(raw_bytes)
                    ev = InboundEvent(
                        kind=ev.kind,
                        mailbox_id=mailbox_id,
                        dedup_key=f"imap:{uidvalidity}:{uid_str}:{ev.kind}",
                        rfc_message_id=ev.rfc_message_id,
                        from_addr=ev.from_addr,
                        thread_id=ev.thread_id,
                        recipient_id=ev.recipient_id,
                        snippet=ev.snippet,
                        raw_headers=ev.raw_headers
                    )
                    events.append(ev)
                    self._process_event(ev, mailbox_id)
                except Exception as e:
                    logger.exception(f"Error classifying message uid={uid_str}: {e}")

            imap.logout()
        except Exception as e:
            logger.exception(f"IMAP poll error for {mailbox_id}: {e}")

        return events

    def run(self, *, interval_sec: int, stop) -> None:
        import time
        while not stop.is_set():
            for mb_id in self._mailbox_map.keys():
                if stop.is_set():
                    break
                try:
                    self.poll_once(mb_id)
                except Exception as e:
                    logger.exception(f"Error polling {mb_id}: {e}")
            stop.wait(interval_sec)

    def classify(self, raw: bytes) -> InboundEvent:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        from_addr = self._extract_email(msg.get("From", ""))
        in_reply_to = msg.get("In-Reply-To", "").strip()
        references = msg.get("References", "").strip()
        subject = msg.get("Subject", "")
        
        rfc_message_id = None
        if in_reply_to:
            rfc_message_id = in_reply_to
        elif references:
            refs = references.split()
            if refs:
                rfc_message_id = refs[0]

        thread_id = self._extract_thread_id(msg)
        body = self._extract_body(msg)
        snippet = body[:200]

        raw_headers = {k: v for k, v in msg.items()}

        kind = "other"
        if self._is_dsn(msg, subject, body):
            kind = "dsn"
        elif self._is_complaint(msg, subject, body):
            kind = "complaint"
        elif self._is_reply(msg, in_reply_to, references):
            kind = "reply"

        recipient_id = None
        if rfc_message_id:
            orig_msg = self._store.find_message_by_rfc_id(rfc_message_id)
            if orig_msg:
                recipient_id = orig_msg.recipient_id

        return InboundEvent(
            kind=kind,
            mailbox_id="",
            dedup_key="",
            rfc_message_id=rfc_message_id,
            from_addr=from_addr,
            thread_id=thread_id,
            recipient_id=recipient_id,
            snippet=snippet,
            raw_headers=raw_headers
        )

    def _process_event(self, ev: InboundEvent, mailbox_id: str) -> None:
        orig_msg = None
        if ev.rfc_message_id:
            orig_msg = self._store.find_message_by_rfc_id(ev.rfc_message_id)

        recipient_id = ev.recipient_id or (orig_msg.recipient_id if orig_msg else None)
        campaign_id = orig_msg.campaign_id if orig_msg else None

        # суб-классификация ответа: автоответ/отказ/горячий (модуль опционален)
        signal = None
        event_type = ev.kind
        detail = {"snippet": ev.snippet, "headers": ev.raw_headers}
        if ev.kind == "reply" and classify_reply is not None:
            try:
                subject = (ev.raw_headers or {}).get("Subject", "")
                signal = classify_reply(subject, ev.snippet, ev.raw_headers)
                detail["reply_kind"] = signal.kind
                if signal.phone:
                    detail["phone"] = signal.phone
                if signal.kind == "auto_reply":
                    # автоответ (отпуск/OOO) НЕ должен стопить цепочку: claim и
                    # has_reply смотрят на event_type='reply' — пишем reply_auto
                    event_type = "reply_auto"
            except Exception:  # noqa: BLE001
                logger.exception("classify_reply failed; treating as plain reply")
                signal = None

        event_in = EventIn(
            dedup_key=ev.dedup_key,
            event_type=event_type,
            event_ts=datetime.now(timezone.utc),
            message_id=orig_msg.id if orig_msg else None,
            recipient_id=recipient_id,
            campaign_id=campaign_id,
            mailbox_id=mailbox_id,
            provider=self._mailbox_map[mailbox_id].provider,
            detail=detail
        )
        event_id, created = self._store.append_event(event_in)
        if not created:
            return

        if ev.kind == "reply":
            self._handle_reply(recipient_id, campaign_id, ev, signal)
        elif ev.kind == "dsn":
            self._handle_dsn(recipient_id, campaign_id, ev, orig_msg)
        elif ev.kind == "complaint":
            self._handle_complaint(recipient_id, campaign_id, ev)

    def _handle_reply(self, recipient_id: Optional[int], campaign_id: Optional[int],
                      ev: InboundEvent, signal=None) -> None:
        if not recipient_id:
            return

        # Автоответ (отпуск/OOO): цепочку не стопим (событие ушло как reply_auto),
        # лид не создаём — человек ещё не ответил по существу.
        if signal is not None and signal.kind == "auto_reply":
            return

        # Инвариант №1: стоп цепочки скоуплен на пару (recipient_id, campaign_id).
        # Без известного campaign_id (исходное письмо не сопоставлено) стопить нечего —
        # не эмитим отдельное skip-событие, иначе задваиваем журнал для реплая без чейна.
        if campaign_id is not None:
            skip_event = EventIn(
                dedup_key=f"{ev.dedup_key}:stop_chain",
                event_type="skip",
                event_ts=datetime.now(timezone.utc),
                recipient_id=recipient_id,
                campaign_id=campaign_id,
                detail={"reason": "replied"}
            )
            self._store.append_event(skip_event)

        # «Отпишите меня» текстом — юридически равен one-click: suppression + журнал.
        if signal is not None and signal.kind == "unsub_request":
            recipient = self._store.get_recipient(recipient_id)
            if recipient:
                self._suppression.add_email(
                    recipient.email, reason="unsubscribe",
                    source="reply_text", campaign_id=campaign_id)
                if hasattr(self._store, "log_consent"):
                    try:
                        self._store.log_consent(
                            email=recipient.email, action="unsubscribe",
                            recipient_id=recipient_id, source="reply_text",
                            campaign_id=campaign_id)
                    except Exception:  # noqa: BLE001
                        logger.exception("log_consent failed for reply unsub")
            return  # отказ — не лид

        if signal is not None and signal.kind == "not_interested":
            return  # вежливый отказ: цепочка остановлена, менеджера не дёргаем

        if self._reply_desk and recipient_id:
            recipient = self._store.get_recipient(recipient_id)
            if recipient and ev.thread_id:
                snippet = ev.snippet
                if signal is not None:
                    tags = [signal.kind] + ([f"тел {signal.phone}"] if signal.phone else [])
                    snippet = f"[{', '.join(tags)}] {snippet}"
                self._reply_desk.push_warm_lead(recipient, ev.thread_id, snippet)

    def _handle_dsn(self, recipient_id: Optional[int], campaign_id: Optional[int],
                    ev: InboundEvent, orig_msg=None) -> None:
        if not recipient_id:
            return

        is_hard = self._is_hard_bounce(ev.snippet, ev.raw_headers)
        if is_hard and self._auto_suppress_bounce:
            recipient = self._store.get_recipient(recipient_id)
            if recipient:
                self._suppression.add_email(
                    recipient.email,
                    reason="bounce_hard",
                    source="imap_dsn",
                    campaign_id=campaign_id
                )
                suppress_event = EventIn(
                    dedup_key=f"{ev.dedup_key}:suppress",
                    event_type="suppress",
                    event_ts=datetime.now(timezone.utc),
                    recipient_id=recipient_id,
                    campaign_id=campaign_id,
                    detail={"reason": "bounce_hard"}
                )
                self._store.append_event(suppress_event)
            return

        # 4.x.x (greylist/полный ящик/временный отказ) — ретрай, НЕ suppress.
        # Только при явном 4.x.x-статусе: непарсибельный DSN не трогаем, как раньше.
        if not is_hard and self._is_soft_bounce(ev.snippet, ev.raw_headers):
            self._schedule_soft_retry(recipient_id, campaign_id, ev, orig_msg)

    @staticmethod
    def _is_soft_bounce(body: str, headers: dict) -> bool:
        status = headers.get("Status", "")
        return bool(re.search(r"\b4\.\d+\.\d+\b", status + " " + body))

    def _schedule_soft_retry(self, recipient_id: int, campaign_id: Optional[int],
                             ev: InboundEvent, orig_msg) -> None:
        """Перепостановка письма после soft-bounce: новый message с суффиксом
        ``:sbr<N>`` в idempotency_key (идемпотентно через ON CONFLICT), отложенный
        на N*delay минут. Потолок — imap.soft_bounce_max_retries."""
        if orig_msg is None or self._soft_retry_max <= 0:
            return
        # стоп-на-ответ: если получатель уже ответил, цепочку не продолжаем
        # (страховка; claim_due_messages отсекает ответивших и на уровне БД)
        if campaign_id is not None and self._store.has_reply(recipient_id, campaign_id):
            return

        base_key = orig_msg.idempotency_key
        depth = 0
        m = re.match(r"^(.*):sbr(\d+)$", base_key)
        if m:
            base_key, depth = m.group(1), int(m.group(2))
        if depth >= self._soft_retry_max:
            return

        delay = timedelta(minutes=self._soft_retry_delay_min * (depth + 1))
        retry = MessageIn(
            idempotency_key=f"{base_key}:sbr{depth + 1}",
            campaign_id=orig_msg.campaign_id,
            recipient_id=orig_msg.recipient_id,
            sequence_step_id=orig_msg.sequence_step_id,
            scheduled_at=datetime.now(timezone.utc) + delay,
            thread_id=orig_msg.thread_id,
            in_reply_to=orig_msg.in_reply_to,
        )
        retry_id, created = self._store.enqueue_message(retry)
        if created:
            self._store.append_event(EventIn(
                dedup_key=f"{ev.dedup_key}:retry",
                event_type="retry_scheduled",
                event_ts=datetime.now(timezone.utc),
                message_id=orig_msg.id,
                recipient_id=recipient_id,
                campaign_id=campaign_id,
                detail={"reason": "soft_bounce", "retry_message_id": retry_id,
                        "depth": depth + 1},
            ))

    def _handle_complaint(self, recipient_id: Optional[int], campaign_id: Optional[int], ev: InboundEvent) -> None:
        if not recipient_id:
            return

        if self._auto_suppress_complaint:
            recipient = self._store.get_recipient(recipient_id)
            if recipient:
                self._suppression.add_email(
                    recipient.email,
                    reason="complaint",
                    source="imap_complaint",
                    campaign_id=campaign_id
                )
                suppress_event = EventIn(
                    dedup_key=f"{ev.dedup_key}:suppress",
                    event_type="suppress",
                    event_ts=datetime.now(timezone.utc),
                    recipient_id=recipient_id,
                    campaign_id=campaign_id,
                    detail={"reason": "complaint"}
                )
                self._store.append_event(suppress_event)
                # ФЗ-152: жалоба = отказ, фиксируем в журнале оснований
                if hasattr(self._store, "log_consent"):
                    try:
                        self._store.log_consent(
                            email=recipient.email,
                            action="complaint",
                            recipient_id=recipient_id,
                            source="imap_complaint",
                            campaign_id=campaign_id,
                        )
                    except Exception:
                        logger.exception("log_consent failed for complaint")

    def _is_dsn(self, msg: EmailMessage, subject: str, body: str) -> bool:
        content_type = msg.get_content_type()
        if content_type in ("multipart/report", "message/delivery-status"):
            return True
        dsn_markers = [
            "delivery status notification",
            "delivery failure",
            "undelivered mail",
            "returned mail",
            "mail delivery failed",
            "postmaster"
        ]
        text = (subject + " " + body).lower()
        return any(marker in text for marker in dsn_markers)

    def _is_complaint(self, msg: EmailMessage, subject: str, body: str) -> bool:
        content_type = msg.get_content_type()
        if content_type == "message/feedback-report":
            return True
        complaint_markers = ["abuse", "spam", "complaint", "feedback-type"]
        text = (subject + " " + body).lower()
        return any(marker in text for marker in complaint_markers)

    def _is_reply(self, msg: EmailMessage, in_reply_to: str, references: str) -> bool:
        return bool(in_reply_to or references)

    def _is_hard_bounce(self, body: str, headers: dict) -> bool:
        status = headers.get("Status", "")
        match = re.search(r"\b5\.\d+\.\d+\b", status + " " + body)
        return bool(match)

    def _extract_email(self, from_header: str) -> str:
        match = re.search(r"<([^>]+)>", from_header)
        if match:
            return match.group(1).strip().lower()
        parts = from_header.split()
        for part in parts:
            if "@" in part:
                return part.strip("<>").lower()
        return from_header.strip().lower()

    def _extract_thread_id(self, msg: EmailMessage) -> Optional[str]:
        thread_id = msg.get("Thread-ID") or msg.get("X-Thread-ID")
        if thread_id:
            return thread_id.strip()
        references = msg.get("References", "").strip()
        if references:
            refs = references.split()
            if refs:
                return hashlib.sha256(refs[0].encode()).hexdigest()[:16]
        in_reply_to = msg.get("In-Reply-To", "").strip()
        if in_reply_to:
            return hashlib.sha256(in_reply_to.encode()).hexdigest()[:16]
        return None

    def _extract_body(self, msg: EmailMessage) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="ignore")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="ignore")
        return ""

    def _get_uidvalidity(self, imap: imaplib.IMAP4_SSL, mailbox_id: str) -> int:
        typ, data = imap.status("INBOX", "(UIDVALIDITY)")
        if typ == "OK" and data:
            match = re.search(r"UIDVALIDITY (\d+)", data[0].decode())
            if match:
                uidvalidity = int(match.group(1))
                self._uidvalidity_cache[mailbox_id] = uidvalidity
                return uidvalidity
        return self._uidvalidity_cache.get(mailbox_id, 0)
