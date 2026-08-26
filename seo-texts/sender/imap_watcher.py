import imaplib
from contextlib import suppress
import email
import email.policy
import re
import hashlib
import logging
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, Optional
from email.message import EmailMessage
from sender.errors import SenderError, StoreError  # noqa: E402

from sender.ruchnye_otvety import chey_otvet
from sender.ruchnye_otvety import sobrat as sobrat_ruchnye

logger = logging.getLogger(__name__)

# Суб-классификация ответов (hot/интерес/автоответ/отказ) — опциональный модуль:
# до его появления/при сбое поведение прежнее (все reply равнозначны).
try:  # pragma: no cover - наличие модуля зависит от сборки
    from sender.reply_classify import classify_reply  # type: ignore
except Exception:  # noqa: BLE001
    classify_reply = None

# Разбор отчётов о недоставке (кто отбился и почему). Модуль обязателен, но
# импорт защищён по тому же канону: приём почты не должен падать из-за него.
try:  # pragma: no cover - зависит от сборки пакета
    from sender.dsn import (dsn_po_strukture, looks_like_dsn,  # type: ignore
                            parse_dsn)
except Exception:  # noqa: BLE001
    looks_like_dsn = None
    parse_dsn = None
    dsn_po_strukture = None

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
    # Разобранный отчёт о недоставке (sender.dsn.DsnInfo.as_detail): вердикт
    # hard|soft|policy|unknown, коды и адреса, которые не дошли. Для не-DSN
    # писем пустой. Поле с дефолтом — старые конструкторы (юниты) не ломаются.
    dsn: dict = field(default_factory=dict)

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
    def push_warm_lead(self, recipient: Recipient, thread_id: str, snippet: str,
                       *, otvetil: Optional[str] = None) -> None: ...

# ---- ImapWatcher ----
class ImapWatcher:
    def __init__(
        self,
        config: Config,
        store: Store,
        suppression: Suppression,
        reply_desk: Optional[ReplyDeskSink] = None,
        reply_pipeline=None,
    ):
        self._config = config
        self._store = store
        self._suppression = suppression
        self._reply_desk = reply_desk
        # Генератор черновиков ответа (ReplyPipeline). Если задан — на
        # «отвечабельный» входящий готовит черновик в confirm-очередь;
        # оператор жмёт «Отправить». None → поведение как раньше (только лид).
        self._reply_pipeline = reply_pipeline
        self._mailbox_map = {mb.mailbox_id: mb for mb in config.mailboxes()}
        self._uidvalidity_cache: dict[str, int] = {}
        # Наибольший UID «Отправленных», который уже разобрали (ручные
        # ответы). В памяти, не в базе: после рестарта первый заход берёт
        # последние сутки — этого хватает, чтобы не потерять вчерашний
        # ответ и не перечитывать три тысячи писем рассылки.
        self._uid_otpravlennyh: dict[str, int] = {}
        self._auto_suppress_bounce = config.get("imap.auto_suppress_on_bounce", True)
        self._auto_suppress_complaint = config.get("imap.auto_suppress_on_complaint", True)
        # Greylist/soft-bounce 4.x.x: НЕ suppress (RU-провайдеры часто гриллистят) —
        # переотправить позже, с потолком попыток. 0 ретраев = поведение как раньше.
        self._soft_retry_max = int(config.get("imap.soft_bounce_max_retries", 2))
        self._soft_retry_delay_min = int(config.get("imap.soft_bounce_retry_delay_min", 45))

    def poll_once(self, mailbox_id: str, *,
                  criteria: Optional[tuple[str, ...]] = None,
                  batch: Optional[int] = None,
                  mark_seen: Optional[bool] = None) -> list[InboundEvent]:
        """Один проход по ящику.

        criteria — критерий IMAP-поиска, по умолчанию UNSEEN (штатный режим:
        новое разобрали и пометили прочитанным). Разовый добор задним числом
        идёт как ("SINCE", "26-Jul-2026"): владелец читает ящики руками, и всё
        уже прочитанное в UNSEEN не попадает — иначе отбивки за прошлые недели
        не разобрать никогда. В таком режиме \\Seen НЕ ставим (не трогаем
        непрочитанное владельца), от повторов защищает dedup_key события.
        """
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
            batch_size = batch or self._config.get("imap.batch", 50)
            crit = tuple(criteria) if criteria else ("UNSEEN",)
            do_mark = mark_seen if mark_seen is not None else (crit == ("UNSEEN",))

            typ, data = imap.search(None, *crit)
            if typ != "OK":
                logger.warning(f"IMAP search failed for {mailbox_id}: {typ}")
                imap.logout()
                return []

            uids = data[0].split()
            if not uids:
                imap.logout()
                return []

            # Ревью (подтверждено): стабильный порядок — старые письма первыми
            # (search не гарантирует сортировку, срез batch мог отбрасывать
            # старые навсегда).
            uids.sort(key=lambda b: int(b) if b.isdigit() else 0)
            uids = uids[:batch_size]
            for uid in uids:
                uid_str = uid.decode("utf-8")
                # Ревью (подтверждено): BODY.PEEK — обычный RFC822-fetch на
                # части серверов сам ставит \Seen, и упавшее ДО обработки
                # письмо навсегда выпадало из UNSEEN-выборки.
                typ, msg_data = imap.fetch(uid, "(BODY.PEEK[])")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    logger.warning("IMAP fetch пуст для uid=%s (%s) — письмо "
                                   "останется UNSEEN, возьмём в следующий тик",
                                   uid_str, typ)
                    continue
                raw_bytes = msg_data[0][1]
                try:
                    ev = self.classify(raw_bytes)
                    # replace, а не пересборка по полям: разобранный отчёт
                    # (ev.dsn) и всё, что добавят позже, доезжает до обработчика
                    # само — раньше новое поле молча терялось здесь.
                    ev = dataclasses.replace(
                        ev,
                        mailbox_id=mailbox_id,
                        dedup_key=f"imap:{uidvalidity}:{uid_str}:{ev.kind}",
                    )
                    events.append(ev)
                    self._process_event(ev, mailbox_id)
                    # Ревью (подтверждено): успешно обработанное письмо
                    # помечаем \Seen — иначе каждый poll заново качал и
                    # классифицировал одни и те же UNSEEN (rate-limit IMAP,
                    # нарастающий лаг). БД-dedup при этом остаётся второй
                    # линией защиты.
                    if do_mark:
                        try:
                            imap.store(uid, "+FLAGS", "\\Seen")
                        except Exception:  # noqa: BLE001 - флаг не критичен
                            logger.warning("IMAP store \\Seen failed uid=%s", uid_str)
                except Exception as e:
                    logger.exception(f"Error classifying message uid={uid_str}: {e}")

            imap.logout()
        except Exception as e:
            logger.exception(f"IMAP poll error for {mailbox_id}: {e}")

        # РУЧНЫЕ ОТВЕТЫ ИЗ ВЕБ-ПОЧТЫ. Оператор отвечает клиенту прямо у
        # почтовика, минуя панель, и для системы такого ответа не
        # существует: карточка лида пуста, стол ответов готов предложить
        # черновик тому, кому уже ответили. Подбираем их из
        # «Отправленных» — только читаем, ошибки глушим: не подобрали —
        # потеряли удобство, а не письмо.
        if self._config.get("imap.ruchnye_otvety", True):
            try:
                self.podobrat_ruchnye(mailbox_id)
            except Exception:  # noqa: BLE001
                logger.exception("ручные ответы: сбор упал (%s)", mailbox_id)

        return events

    def podobrat_ruchnye(self, mailbox_id: str) -> int:
        """Завести в диалог ответы, написанные руками из веб-почты.

        Возвращает, сколько писем завели. Своё от ручного отличаем по
        Message-ID: панельные письма лежат в messages.rfc_message_id.
        """
        mb = self._mailbox_map.get(mailbox_id)
        if mb is None:
            return 0

        def наше_ли(mid: str) -> bool:
            try:
                return self._store.find_message_by_rfc_id(mid) is not None
            except Exception:  # noqa: BLE001 - не знаем → считаем чужим
                return False

        письма, верх = sobrat_ruchnye(
            mb, nash_li=наше_ли,
            s_uid=self._uid_otpravlennyh.get(mailbox_id, 0))
        self._uid_otpravlennyh[mailbox_id] = верх
        заведено = 0
        for п in письма:
            rid = chey_otvet(self._store, п)
            if not rid:
                logger.info("ручной ответ без хозяина: %s -> %s",
                            mailbox_id, п.get("komu"))
                continue
            когда = п.get("kogda") or datetime.now(timezone.utc)
            mid = None
            try:
                mid = self._store.otvet_kak_pismo(
                    recipient_id=rid, mailbox_id=mailbox_id,
                    subject=п.get("tema") or "", body=п.get("telo") or "",
                    rfc_message_id=п["rfc_message_id"], sent_at=когда,
                    in_reply_to=п.get("in_reply_to"), thread_id=None)
            except Exception:  # noqa: BLE001
                logger.exception("ручной ответ не записался письмом")
            with suppress(Exception):
                self._store.append_event(EventIn(
                    dedup_key="ruchnoy:%s" % п["rfc_message_id"],
                    event_type="reply_sent", event_ts=когда,
                    message_id=mid, recipient_id=rid, mailbox_id=mailbox_id,
                    detail={"ruchnoy": True, "komu": п.get("komu"),
                            "tema": (п.get("tema") or "")[:200]}))
            заведено += 1
        if заведено:
            logger.info("подобрано ручных ответов: %d (%s)", заведено, mailbox_id)
        return заведено

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
        # 4000, а не 200 (#63): обрыв на полуслове ломал не только показ —
        # классификатор и ревьюеры черновика работали по огрызку («невозможно
        # классифицировать без полного текста»), и потребность лида в карточке
        # обрывалась. Показ укорачивает UI, данные храним целиком; 4000 хватает
        # на любое деловое письмо и держит detail_json событий в разумном весе.
        snippet = body[:4000]

        raw_headers = {k: v for k, v in msg.items()}

        kind = "other"
        # ПИСЬМО ОТ МАЯКА — НЕ ЛИД. Маяк это наш собственный ящик у чужого
        # почтовика, куда мы шлём копию письма, чтобы увидеть папку. Его
        # автоответ («нет на месте», «письмо получено») пришёл бы к нам как
        # обычный ответ и завёл карточку лида на самих себя. Разбираем его
        # как служебное и дальше не ведём.
        if self._ot_mayaka(from_addr):
            kind = "other"
        elif self._is_dsn(msg, subject, body):
            kind = "dsn"
        elif self._is_complaint(msg, subject, body):
            kind = "complaint"
        elif self._is_reply(msg, in_reply_to, references):
            kind = "reply"

        # Отчёт о недоставке разбираем ДО поиска получателя: наше письмо
        # приложено внутрь отчёта, и его Message-ID лежит только там —
        # заголовков In-Reply-To/References у NDR обычно нет вовсе.
        dsn_detail: dict = {}
        failed_addrs: list[str] = []
        orig_to: list[str] = []
        if kind == "dsn" and parse_dsn is not None:
            info = parse_dsn(msg)
            dsn_detail = info.as_detail()
            failed_addrs = list(info.failed)
            orig_to = list(info.orig_to)
            # ПУСТОЙ РАЗБОР БЕЗ УЛИКИ В СТРУКТУРЕ - НЕ ОТБИВКА.
            #
            # looks_like_dsn относит к отчётам всё, что пришло с адреса
            # postmaster@, и это ловит агрегированные отчёты DMARC: их шлёт
            # каждый крупный почтовик раз в сутки с того же адреса. 21.08
            # такой отчёт от snemaservis.ru про наш домен лёг в события как
            # bounce - при нулевой отправке за день панель показала отбивку.
            # Настоящий отчёт всегда даёт хоть что-то: адрес, код, статус или
            # машинную часть message/delivery-status. Нет ничего из этого -
            # письмо разбираем дальше обычным порядком, а не хороним в
            # счётчике недоставки.
            _пусто = not (failed_addrs or info.smtp_code or info.status)
            _улика = (dsn_po_strukture(msg)
                      if dsn_po_strukture is not None else True)
            if _пусто and not _улика:
                kind = ("complaint"
                        if self._is_complaint(msg, subject, body)
                        else "reply"
                        if self._is_reply(msg, in_reply_to, references)
                        else "other")
                dsn_detail, failed_addrs, orig_to = {}, [], []
            elif not rfc_message_id and info.orig_message_id:
                rfc_message_id = info.orig_message_id

        recipient_id = None
        if rfc_message_id:
            orig_msg = self._store.find_message_by_rfc_id(rfc_message_id)
            if orig_msg:
                recipient_id = orig_msg.recipient_id
        # Последний шанс привязки: адрес из отчёта, а если он чужой (письмо
        # переслали внутри конторы получателя) — адресат нашего письма, взятый
        # из приложенного оригинала. Иначе отбивка повисает без получателя и
        # гейт по домену её не видит.
        if recipient_id is None and failed_addrs:
            recipient_id = self._recipient_by_emails(failed_addrs)
        if recipient_id is None and orig_to:
            recipient_id = self._recipient_by_emails(orig_to)
        # ОТВЕТ С ДРУГОГО АДРЕСА ТОЙ ЖЕ КОНТОРЫ. Письмо уходит на приёмную,
        # внутри его передают, и отвечает человек со своего ящика — часто
        # НОВЫМ письмом, без In-Reply-To. Тогда привязки не было вовсе:
        # 19.08 «Шато де Талю» спросило «в какую стоимость данное
        # оборудование, возможно ли получить КП» с andryushchenko@, а мы
        # писали на sale@ — ответ лёг событием «other» без получателя и
        # пролежал неделю.
        if recipient_id is None and kind != "dsn" and from_addr:
            recipient_id = self._recipient_by_emails([from_addr])
        if recipient_id is None and kind != "dsn":
            recipient_id = self._recipient_by_domain(from_addr)

        return InboundEvent(
            kind=kind,
            mailbox_id="",
            dedup_key="",
            rfc_message_id=rfc_message_id,
            from_addr=from_addr,
            thread_id=thread_id,
            recipient_id=recipient_id,
            snippet=snippet,
            raw_headers=raw_headers,
            dsn=dsn_detail,
        )

    def _recipient_by_emails(self, emails: list[str]) -> Optional[int]:
        """id получателя по адресу из отчёта (первое совпадение) или None."""
        finder = getattr(self._store, "find_recipient_by_email", None)
        if not callable(finder):
            return None
        for addr in emails:
            try:
                row = finder(addr)
            except Exception:  # noqa: BLE001 - сбой поиска не роняет приём
                logger.exception("find_recipient_by_email failed for %s", addr)
                continue
            if row:
                rid = row.get("id") if isinstance(row, dict) else getattr(row, "id", None)
                if rid:
                    return int(rid)
        return None

    # Публичные почтовики: у них домен ничего не говорит о компании, и
    # привязка по нему склеила бы чужие письма. 25.08 такая ошибка уже была
    # в замере ответов: любое письмо с bk.ru считалось ответом нашего
    # получателя.
    ОБЩИЕ_ДОМЕНЫ = frozenset({
        "mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru",
        "yandex.ru", "ya.ru", "yandex.com", "gmail.com", "googlemail.com",
        "rambler.ru", "lenta.ru", "autorambler.ru", "outlook.com",
        "hotmail.com", "live.com", "icloud.com", "me.com", "mail.com",
        "protonmail.com", "proton.me", "bk.com", "narod.ru",
    })

    def _recipient_by_domain(self, from_addr: str) -> Optional[int]:
        """Получатель по ДОМЕНУ отправителя — когда ветка не сошлась.

        Только корпоративный домен и только если он у нас один на компанию:
        иначе непонятно, кому засчитывать ответ. Публичные почтовики
        исключены — там домен не значит ничего.
        """
        адрес = str(from_addr or "").strip().lower()
        if "@" not in адрес:
            return None
        домен = адрес.rsplit("@", 1)[-1]
        if not домен or домен in self.ОБЩИЕ_ДОМЕНЫ:
            return None
        finder = getattr(self._store, "recipients_by_domain", None)
        if not callable(finder):
            return None
        try:
            строки = finder(домен) or []
        except Exception:  # noqa: BLE001 - сбой поиска не роняет приём
            logger.exception("recipients_by_domain failed for %s", домен)
            return None
        if not строки:
            return None

        def поле(r, имя):
            return r.get(имя) if isinstance(r, dict) else getattr(r, имя, None)

        инны = {str(поле(r, "inn") or "").strip() for r in строки}
        инны.discard("")
        if len(инны) > 1:
            # На одном домене две разные компании — бывает у холдингов и у
            # арендованных доменов. Гадать нельзя.
            logger.info("привязка по домену %s пропущена: компаний %d",
                        домен, len(инны))
            return None
        rid = поле(строки[0], "id")
        return int(rid) if rid else None

    def _process_event(self, ev: InboundEvent, mailbox_id: str) -> None:
        orig_msg = None
        if ev.rfc_message_id:
            orig_msg = self._store.find_message_by_rfc_id(ev.rfc_message_id)

        recipient_id = ev.recipient_id or (orig_msg.recipient_id if orig_msg else None)
        campaign_id = orig_msg.campaign_id if orig_msg else None

        # суб-классификация ответа: автоответ/отказ/горячий (модуль опционален)
        signal = None
        event_type = ev.kind
        # Ревью №0 (критично): все гейты (bounce-rate ящика/домена/провайдера,
        # канарейка волны, engagement) читают event_type='bounce', а DSN писался
        # как 'dsn' — kill-switch не срабатывал НИКОГДА. Пишем канонический тип
        # 'bounce', исходный класс сохраняем в detail.kind (лента диалога и
        # выборка входящих переведены на оба типа).
        if ev.kind == "dsn":
            event_type = "bounce"
        detail = {"snippet": ev.snippet, "headers": ev.raw_headers,
                  "kind": ev.kind,
                  # цепочка ветки: нужна, чтобы НАШ ответ пришёл клиенту как
                  # ответ в его переписке, а не отдельным письмом
                  "references": (ev.raw_headers or {}).get("References", ""),
                  "in_reply_to_hdr": (ev.raw_headers or {}).get("Message-ID", ""),
                  "inbox_mailbox": ev.mailbox_id}
        if ev.dsn:
            # Разобранная отбивка: вердикт, коды и адрес, который не дошёл —
            # чтобы оператор в ленте видел ПРИЧИНУ, а не «письмо вернулось».
            detail["dsn"] = ev.dsn
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

        # Автоответ (отпуск/OOO, «пишите на общий ящик»). Цепочку не стопим:
        # событие уже ушло как reply_auto. Раньше здесь стоял голый return, и
        # письмо не показывалось никому — а 11.08 выяснилось, что за месяц
        # автоответов было два и НОВЫЙ АДРЕС был в обоих: «обращайтесь к
        # Белоусу belous.a@gladium.ru», «создан общий адрес client@farmoborona.ru».
        # Владелец: «верни в лиды автоответы, с возможностью отправить то же
        # письмо по новому адресу». Поэтому теперь: лид создаём с пометкой, а
        # найденный адрес получает копию последнего письма в очередь.
        if signal is not None and signal.kind == "auto_reply":
            находка = {"адреса": [], "постановки": []}
            try:
                from sender.avtootvet import разобрать_автоответ
                свои = {m.mailbox_id for m in self._config.mailboxes()}
                находка = разобрать_автоответ(
                    self._store, recipient_id=recipient_id,
                    текст=ev.snippet or "", от_кого=getattr(ev, "from_addr", ""),
                    свои=свои)
            except Exception:  # noqa: BLE001 - приём входящих важнее добавки
                logger.exception("автоответ: разбор не удался")
            # Без ветки лид тоже нужен. Здесь стояло «and ev.thread_id», и
            # автоответ письма, у которого почтовик срезал References, не
            # показывался никому. Ключ склейки push_warm_lead возьмёт по
            # адресу — сам умеет.
            if self._reply_desk:
                recipient = self._store.get_recipient(recipient_id)
                if recipient:
                    метка = "[автоответ]"
                    if находка["адреса"]:
                        метка += (" новый адрес: " + ", ".join(находка["адреса"]))
                        if находка["постановки"]:
                            метка += " — копия письма поставлена в очередь"
                    with suppress(Exception):
                        self._lid(recipient, ev.thread_id,
                                  f"{метка} {ev.snippet or ''}"[:900],
                                  getattr(ev, "from_addr", None))
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
                # и фактический адрес доставки (оператор мог сменить/вписать
                # контакт в панели) — иначе отписка закрывает не тот адрес.
                # getattr: у мок-suppression в юнитах метода может не быть.
                _aliases = getattr(self._suppression, "add_delivery_aliases", None)
                if callable(_aliases):
                    _aliases(recipient, "unsubscribe", source="reply_text",
                             campaign_id=campaign_id)
                if hasattr(self._store, "log_consent"):
                    try:
                        self._store.log_consent(
                            email=recipient.email, action="unsubscribe",
                            recipient_id=recipient_id, source="reply_text",
                            campaign_id=campaign_id)
                    except Exception:  # noqa: BLE001
                        logger.exception("log_consent failed for reply unsub")
            return  # отказ — не лид

        # ВЕЖЛИВЫЙ ОТКАЗ ТОЖЕ ИДЁТ В ЛЕНТУ. Здесь стоял return, и карточка не
        # заводилась вовсе. Владелец 24.08: «только вручную отказы надо
        # ставить, в ленту общих должны попасть», и следом — «я их не вижу и
        # в отказах».
        #
        # Отказ несёт факты, которых больше взять негде. 24.08 «Сталь
        # Технологии» ответили «у нас компрессоры Берг стоят, КИТАЙ НЕ
        # ИНТЕРЕСЕН СОВСЕМ»: это и конкурент, и причина отказа, и позиция по
        # происхождению техники — продавцу такое видеть надо. Пометку «отказ»
        # несёт тег в сниппете, решение по карточке принимает человек.
        #
        # Черновик ответа отказу НЕ готовим: тому, кто сказал «не интересно»,
        # автоматический ответ слать нельзя. Цепочка ему уже остановлена
        # событием skip выше, повторных писем не будет.
        _otkaz = signal is not None and signal.kind == "not_interested"

        if self._reply_desk and recipient_id:
            recipient = self._store.get_recipient(recipient_id)
            # ВЕТКА НЕ ОБЯЗАТЕЛЬНА. Здесь стояло «and ev.thread_id»: ответ без
            # References (корпоративные почтовики их режут) не заводил
            # карточку вовсе. Сверка 25.08: 129 ответов клиентов против 112
            # карточек — пятнадцать потерянных, среди них живой интерес
            # «Сафита» («с удовольствием рассмотрим»). Ключ склейки без ветки
            # push_warm_lead берёт по адресу.
            if recipient:
                snippet = ev.snippet
                if signal is not None:
                    tags = [signal.kind] + ([f"тел {signal.phone}"] if signal.phone else [])
                    snippet = f"[{', '.join(tags)}] {snippet}"
                self._lid(recipient, ev.thread_id, snippet,
                          getattr(ev, "from_addr", None))

        # Ручной ответ: готовим ЧЕРНОВИК в confirm-очередь (оператор жмёт
        # «Отправить»). Только для «отвечабельных» классов: unsub отсеян выше
        # возвратом, отказ — флагом _otkaz (карточку он получает, черновик нет). Сбой генерации/провайдера НЕ роняет приём входящих.
        if (self._reply_pipeline is not None and recipient_id
                and signal is not None and not _otkaz):
            recipient = self._store.get_recipient(recipient_id)
            if recipient is not None:
                try:
                    self._reply_pipeline.draft_for_incoming(recipient, signal, ev)
                except Exception:  # noqa: BLE001
                    logger.exception("reply draft failed recipient_id=%s", recipient_id)

    def _handle_dsn(self, recipient_id: Optional[int], campaign_id: Optional[int],
                    ev: InboundEvent, orig_msg=None) -> None:
        """Действия по отчёту о недоставке. Событие уже записано вызывающим.

        Вердикт даёт sender.dsn; регулярки по телу остаются запасным путём для
        писем, разобрать которые не удалось (и для юнитов со своими DTO).

        * hard   — адрес мёртв: в стоп-лист уходит ИМЕННО отбившийся адрес.
        * soft   — временный отказ: перепостановка (при soft_bounce_max_retries>0).
        * policy — отказ по политике/контенту (5.7.x, «message rejected»,
          антивирус): ящик ЖИВОЙ, стоп-лист НЕ трогаем. Событие 'bounce' уже
          записано — гейты репутации его увидят, а лид не теряем.
        """
        verdict = (ev.dsn or {}).get("verdict") or "unknown"
        if verdict == "unknown":
            if self._is_hard_bounce(ev.snippet, ev.raw_headers):
                verdict = "hard"
            elif self._is_soft_bounce(ev.snippet, ev.raw_headers):
                verdict = "soft"

        if verdict == "policy":
            logger.info("DSN policy-отказ (%s): адрес не суппрессим, "
                        "recipient_id=%s", (ev.dsn or {}).get("reason", ""),
                        recipient_id)
            return

        if not recipient_id:
            if verdict == "hard":
                logger.warning("DSN hard без привязки к получателю: %s",
                               (ev.dsn or {}).get("failed") or ev.from_addr)
            return

        if verdict == "hard" and self._auto_suppress_bounce:
            recipient = self._store.get_recipient(recipient_id)
            if recipient:
                targets = self._bounce_targets(recipient, ev)
                if not targets:
                    # Отбился ЧУЖОЙ адрес: письмо переслали внутри конторы
                    # получателя (алиас/редирект), и упало уже на их перегоне.
                    # Наш адрес живой — суппрессить его нельзя.
                    logger.info("DSN hard на посторонний адрес %s "
                                "(наш получатель %s) — стоп-лист не трогаем",
                                (ev.dsn or {}).get("failed"), recipient.email)
                    return
                for addr in targets:
                    self._suppression.add_email(
                        addr, reason="bounce_hard", source="imap_dsn",
                        campaign_id=campaign_id)
                self._prigovor_v_bazy(targets, ev)
                suppress_event = EventIn(
                    dedup_key=f"{ev.dedup_key}:suppress",
                    event_type="suppress",
                    event_ts=datetime.now(timezone.utc),
                    recipient_id=recipient_id,
                    campaign_id=campaign_id,
                    detail={"reason": "bounce_hard", "addresses": targets}
                )
                self._store.append_event(suppress_event)
            return

        # 4.x.x (greylist/полный ящик/временный отказ) — ретрай, НЕ suppress.
        if verdict == "soft":
            self._schedule_soft_retry(recipient_id, campaign_id, ev, orig_msg)

    def _prigovor_v_bazy(self, targets: list, ev: InboundEvent) -> None:
        """Разнести приговор доставки по трём базам, а не только в стоп-лист.

        Стоп-лист держит адрес от повторной отправки — и на этом всё:
        проба продолжает считать его живым, обогащение отдаёт его в отбор
        кандидатов, база обзвона о нём не знает. 18.08 работник проб поставил
        kk@vebfabrika.ru «есть» (код 250 от домена-catch-all) поверх нашего
        «нет ящика», и адрес вернулся в работу.

        Сбой этой записи не отменяет стоп-лист: он уже сработал выше.
        """
        try:
            from sender.otbivka_v_bazy import zapisat
            диаг = str((ev.dsn or {}).get("diagnostic") or ev.snippet or "")
            итог = zapisat(
                targets, диаг,
                db_path=str(getattr(self._store, "_db_path", "")
                            or self._config.get("service.db_path", "") or ""),
                config=self._config)
            logger.info("DSN hard: вердикт разнесён по базам %s", итог)
        except Exception:  # noqa: BLE001 - стоп-лист уже сработал
            logger.exception("DSN hard: вердикт не разнёсся по базам")

    def _bounce_targets(self, recipient, ev: InboundEvent) -> list[str]:
        """Какие адреса гасить по жёсткой отбивке.

        Отчёт называет адрес, который не дошёл. Он может отличаться от
        `recipients.email`: оператор подменил контакт в панели (тогда это наш
        доставочный алиас — гасим именно его, база остаётся жить) либо получатель
        переслал письмо внутрь своей конторы (чужой адрес — не наше дело).
        Отчёт без адреса = старое поведение: базовый адрес плюс его алиасы.
        """
        base = (getattr(recipient, "email", "") or "").lower()
        failed = [a.lower() for a in ((ev.dsn or {}).get("failed") or []) if a]

        aliases: set[str] = set()
        getter = getattr(self._store, "delivery_emails_for_recipient", None)
        if callable(getter):
            try:
                aliases = {a.lower() for a in (getter(recipient.id) or []) if a}
            except Exception:  # noqa: BLE001 - старый store/мок
                aliases = set()

        if not failed:
            return [base] + sorted(aliases) if base else sorted(aliases)
        own = [a for a in failed if a == base or a in aliases]
        return own

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
                # жалоба пришла с адреса доставки — закрываем и его (ФЗ-38)
                _aliases = getattr(self._suppression, "add_delivery_aliases", None)
                if callable(_aliases):
                    _aliases(recipient, "complaint", source="imap_complaint",
                             campaign_id=campaign_id)
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
        # Канон распознавания живёт в sender.dsn (там же список формулировок
        # шлюзов: «Non-Delivery Report», «Undeliverable», «не доставлено»…).
        if looks_like_dsn is not None:
            return looks_like_dsn(msg, subject, body)
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

    def _lid(self, recipient, thread_id, snippet, otvetil) -> None:
        """Завести лид, передав адрес ответившего, но не ломаясь о старую
        реализацию лид-деска, которая такого параметра не знает.

        Адрес ответившего важен: письмо уходит на приёмную, там его
        пересылают внутрь, и отвечает человек со своего адреса — карточка
        должна показывать ЕГО, иначе продавец ответит в приёмную.
        """
        try:
            self._reply_desk.push_warm_lead(recipient, thread_id, snippet,
                                            otvetil=otvetil)
        except TypeError:
            self._reply_desk.push_warm_lead(recipient, thread_id, snippet)

    def _ot_mayaka(self, from_addr: str) -> bool:
        """Адрес отправителя — наш маяк? Список живёт в конфиге."""
        try:
            from sender.mayaki import eto_mayak
            return eto_mayak(from_addr, self._config)
        except Exception:  # noqa: BLE001 - нет модуля/конфига: ведём как прежде
            return False

    # Ящики служб жалоб: письмо от них — жалоба независимо от текста.
    _ЯЩИКИ_ЖАЛОБ = frozenset({"abuse", "fbl", "complaints", "feedback",
                              "abuse-report", "spam-report"})

    def _is_complaint(self, msg: EmailMessage, subject: str, body: str) -> bool:
        """Жалоба на спам — это ОТЧЁТ (ARF), а не слово «спам» в тексте.

        Раньше здесь стоял поиск подстрок abuse|spam|complaint|feedback-type
        по теме и телу, и этого хватало, чтобы похоронить живую компанию:
        26.08 ПАО «Лукойл» написало «данный вопрос не относится к
        компетенции службы технической поддержки» и перечислило ТРИ других
        своих адреса, а в тексте их корпоративного баннера нашлось слово
        «спам». Письмо ушло в жалобы, adress автоматом лёг в стоп-лист
        (imap.auto_suppress_on_complaint), карточка лида не завелась - и
        компании с выручкой в триллионы мы больше не пишем никогда.

        Признаём жалобой только машинные признаки: формат ARF, заголовок
        отчёта или письмо со служебного ящика жалоб. Человек, написавший
        слово «спам», жалобы не подавал.
        """
        if msg.get_content_type() == "message/feedback-report":
            return True
        try:
            for часть in msg.walk():
                if часть.get_content_type() == "message/feedback-report":
                    return True
        except Exception:  # noqa: BLE001 - кривой MIME не должен ронять приём
            pass
        if msg.get("Feedback-Type") or msg.get("X-Abuse-Report"):
            return True
        петля = str(msg.get("X-Loop", "") or "").strip().lower()
        if петля.startswith("abuse"):
            return True
        отправитель = self._extract_email(msg.get("From", "") or "")
        if отправитель.split("@", 1)[0] in self._ЯЩИКИ_ЖАЛОБ:
            return True
        # Машинная часть ARF, приехавшая текстом.
        return "feedback-type:" in (body or "").lower()

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

    @staticmethod
    def _decode_part(part) -> str:
        """Тело части в его РЕАЛЬНОЙ кодировке (ревью №31): жёсткое utf-8
        превращало письмо в windows-1251 в пустую строку и убивало
        классификацию. Берём charset из заголовка, при провале — типовые
        для рунета cp1251/koi8-r, в конце — utf-8 с игнором."""
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = (part.get_content_charset() or "").lower()
        tries = [charset] if charset else []
        tries += ["utf-8", "cp1251", "koi8-r", "iso-8859-5"]
        for enc in tries:
            if not enc:
                continue
            try:
                return payload.decode(enc)
            except (LookupError, UnicodeDecodeError):
                continue
        return payload.decode("utf-8", errors="ignore")

    def _extract_body(self, msg: EmailMessage) -> str:
        """Текст входящего. HTML разбираем, а не отдаём разметкой.

        Две дыры, обе видны на живой почте (владелец 18.08 — «почему до сих
        пор так выглядит письмо?»):
          * письмо ИЗ ОДНОЙ ЧАСТИ в HTML приезжало сырым, и оператор видел в
            карточке лида «<div style="background-color:rgb(255,255,255)">»
            вместо ответа клиента;
          * письмо из нескольких частей, где текстовой части НЕТ вообще (а
            так шлёт добрая половина почтовых клиентов), давало пустую
            строку: и «Потребность» пустая, и классификатор ответа слеп.

        Разбор один на всю панель — sender/pismo_v_tekst.py. Обычный текст он
        не трогает, поэтому отчёты о недоставке (а они plain) проходят
        как раньше, и разбор DSN этой правки не замечает.
        """
        from sender.pismo_v_tekst import v_tekst
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    txt = self._decode_part(part)
                    if txt:
                        return txt
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    txt = v_tekst(self._decode_part(part))
                    if txt:
                        return txt
        else:
            return v_tekst(self._decode_part(msg))
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
