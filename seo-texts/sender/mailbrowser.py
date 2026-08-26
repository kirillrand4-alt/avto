"""Почтовый браузер поверх IMAP: читать ВСЕ письма любого из ящиков панели.

⛔ READ-ONLY: select(readonly=True), BODY.PEEK (флаг \\Seen не трогаем),
никаких store/expunge/delete. Приём холд не нарушает — только чтение.
Отличие от imap_watcher: тот берёт лишь UNSEEN и классифицирует; здесь —
оператор листает ВСЕ письма (входящие/отправленные, прочитанные и нет) и
цепочки, как в веб-почте. Живой IMAP — работает на боевом сервере
(из сессии порт 993 закрыт; тесты на фейковом опенере).

Пути API строятся тонким слоем в api/app.py. Опенер IMAP инжектируется
(imap_opener) — для тестов подменяется фейком.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Optional

logger = logging.getLogger("sender.mailbrowser")

_RE_PREFIX = re.compile(r"^\s*(re|fwd|fw|отв|пересл)\s*:\s*", re.IGNORECASE)


class MailBrowserError(Exception):
    """Ошибка обращения к IMAP-браузеру (недоступен/логин/папка)."""


def _decode(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:  # noqa: BLE001
        return raw


def _norm_subject(subj: str) -> str:
    s = subj or ""
    while True:
        s2 = _RE_PREFIX.sub("", s)
        if s2 == s:
            return s.strip().lower()
        s = s2


def _imap_utf7_decode(name: str) -> str:
    """Имя папки IMAP (modified UTF-7, RFC 3501 §5.1.3) -> юникод.

    mail.ru отдаёт русские папки как «&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-»;
    без декода оператор видел кракозябры, а роль «отправленные» не
    распознавалась (#58). Битое имя возвращаем как есть — хуже не делаем."""
    try:
        out, i = [], 0
        while i < len(name):
            c = name[i]
            if c != '&':
                out.append(c)
                i += 1
                continue
            j = name.index('-', i)          # '&-' — экранированный амперсанд
            chunk = name[i + 1:j]
            if not chunk:
                out.append('&')
            else:
                b64 = chunk.replace(',', '/')
                b64 += '=' * (-len(b64) % 4)
                import base64 as _b64
                out.append(_b64.b64decode(b64).decode('utf-16-be'))
            i = j + 1
        return ''.join(out)
    except Exception:  # noqa: BLE001
        return name


def _folder_role(flags: str, name: str) -> str:
    """Роль папки по SPECIAL-USE флагу или имени (inbox|sent|drafts|junk|other).
    Имя сверяем и в декодированном виде — у mail.ru оно в modified UTF-7."""
    f = (flags or "").lower()
    n = (name or "").lower() + " " + _imap_utf7_decode(name or "").lower()
    if "\\sent" in f or "sent" in n or "отправ" in n:
        return "sent"
    if name.upper() == "INBOX" or "входящ" in n:
        return "inbox"
    if "\\junk" in f or "spam" in n or "спам" in n:
        return "junk"
    if "\\drafts" in f or "draft" in n or "чернов" in n:
        return "drafts"
    if "\\trash" in f or "trash" in n or "корзин" in n:
        return "trash"
    return "other"


class MailBrowser:
    def __init__(self, config: Any, *, imap_opener=None):
        self._config = config
        self._map = {mb.mailbox_id: mb for mb in config.mailboxes()}
        self._opener = imap_opener or self._default_opener
        self._timeout = float(config.get("imap.connect_timeout_sec", 20) or 20)

    def _default_opener(self, mb):
        import os
        pw = os.environ.get(mb.password_env, "")
        if not pw:
            raise MailBrowserError(f"нет пароля в env {mb.password_env}")
        imap = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=self._timeout)
        imap.login(mb.login, pw)
        return imap

    def _mb(self, mailbox_id: str):
        mb = self._map.get(mailbox_id)
        if mb is None:
            raise MailBrowserError(f"неизвестный ящик {mailbox_id!r}")
        return mb

    # -- список ящиков панели ---------------------------------------------- #
    def mailboxes(self) -> list[dict]:
        out = []
        for mb in self._config.mailboxes():
            out.append({"mailbox_id": mb.mailbox_id,
                        "from_name": getattr(mb, "from_name", ""),
                        "provider": getattr(mb, "provider", ""),
                        "division": getattr(mb, "division", None)})
        return out

    # -- папки ящика ------------------------------------------------------- #
    def folders(self, mailbox_id: str) -> list[dict]:
        mb = self._mb(mailbox_id)
        imap = self._opener(mb)
        try:
            typ, data = imap.list()
            if typ != "OK":
                return [{"name": "INBOX", "role": "inbox"}]
            folders = []
            for row in data or []:
                line = row.decode("utf-8", "replace") if isinstance(row, bytes) else str(row)
                # (\HasNoChildren \Sent) "/" "Sent"
                m = re.match(r'\((?P<flags>[^)]*)\)\s+"[^"]*"\s+(?P<name>.+)$', line)
                if not m:
                    continue
                name = m.group("name").strip().strip('"')
                folders.append({"name": name,
                                "title": _imap_utf7_decode(name),
                                "role": _folder_role(m.group("flags"), name)})
            # INBOX гарантированно первым
            folders.sort(key=lambda f: (f["role"] != "inbox", f["role"] != "sent",
                                        f["name"]))
            return folders or [{"name": "INBOX", "role": "inbox"}]
        finally:
            self._safe_logout(imap)

    # -- список писем папки (ВСЕ, не только непрочитанные) ------------------ #
    def messages(self, mailbox_id: str, *, folder: str = "INBOX",
                 limit: int = 50, offset: int = 0,
                 search: Optional[str] = None) -> dict:
        mb = self._mb(mailbox_id)
        imap = self._opener(mb)
        try:
            typ, _ = imap.select(self._enc_folder(folder), readonly=True)
            if typ != "OK":
                raise MailBrowserError(f"папка {folder!r} недоступна")
            crit = ["ALL"]
            if search:
                # ищем по адресу/теме (FROM/TO/SUBJECT) — по подстроке
                s = search.replace('"', "")
                crit = ["OR", "OR", "FROM", f'"{s}"', "TO", f'"{s}"',
                        "SUBJECT", f'"{s}"']
            typ, data = imap.search(None, *crit)
            if typ != "OK":
                return {"total": 0, "messages": []}
            uids = data[0].split()
            uids.sort(key=lambda b: int(b) if b.isdigit() else 0, reverse=True)
            total = len(uids)
            page = uids[offset:offset + limit]
            msgs = []
            for uid in page:
                hdr = self._fetch_headers(imap, uid)
                if hdr:
                    msgs.append(hdr)
            return {"total": total, "messages": msgs}
        finally:
            self._safe_logout(imap)

    # -- одно письмо целиком (тело) ---------------------------------------- #
    def message(self, mailbox_id: str, *, folder: str, uid: str) -> dict:
        mb = self._mb(mailbox_id)
        imap = self._opener(mb)
        try:
            typ, _ = imap.select(self._enc_folder(folder), readonly=True)
            if typ != "OK":
                raise MailBrowserError(f"папка {folder!r} недоступна")
            typ, msg_data = imap.fetch(uid.encode(), "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                raise MailBrowserError(f"письмо uid={uid} не найдено")
            raw = msg_data[0][1]
            m = email.message_from_bytes(raw)
            return self._parse_full(uid, m)
        finally:
            self._safe_logout(imap)

    # -- цепочка (тред) по письму ------------------------------------------ #
    def thread(self, mailbox_id: str, *, folder: str, uid: str) -> list[dict]:
        """Письма той же цепочки в папке: по общей теме (без Re:/Fwd:) и
        пересечению Message-ID/References. Отсортированы по дате (старые сверху)."""
        base = self.message(mailbox_id, folder=folder, uid=uid)
        base_subj = _norm_subject(base.get("subject", ""))
        ids = set(filter(None, [base.get("message_id")]
                         + (base.get("references") or [])
                         + [base.get("in_reply_to")]))
        mb = self._mb(mailbox_id)
        imap = self._opener(mb)
        out = []
        try:
            imap.select(self._enc_folder(folder), readonly=True)
            typ, data = imap.search(None, "ALL")
            uids = data[0].split() if typ == "OK" else []
            for u in uids:
                h = self._fetch_headers(imap, u)
                if not h:
                    continue
                same_subj = _norm_subject(h.get("subject", "")) == base_subj and base_subj
                refset = set(filter(None, [h.get("message_id"), h.get("in_reply_to")]
                                    + (h.get("references") or [])))
                if same_subj or (ids & refset):
                    out.append(h)
        finally:
            self._safe_logout(imap)
        out.sort(key=lambda x: str(x.get("date_iso") or ""))
        return out

    # -- внутреннее -------------------------------------------------------- #
    def _fetch_headers(self, imap, uid) -> Optional[dict]:
        typ, data = imap.fetch(
            uid, "(FLAGS BODY.PEEK[HEADER.FIELDS "
            "(FROM TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])")
        if typ != "OK" or not data or not data[0]:
            return None
        flags = ""
        raw = None
        for part in data:
            if isinstance(part, tuple):
                raw = part[1]
                meta = part[0].decode("utf-8", "replace") if isinstance(part[0], bytes) else str(part[0])
                if "\\Seen" in meta:
                    flags = "seen"
        if raw is None:
            return None
        m = email.message_from_bytes(raw)
        return self._parse_headers(uid, m, seen=(flags == "seen"))

    def _parse_headers(self, uid, m, *, seen: bool) -> dict:
        from_name, from_addr = parseaddr(m.get("From", ""))
        _, to_addr = parseaddr(m.get("To", ""))
        date_iso = ""
        with_suppress = m.get("Date", "")
        try:
            if with_suppress:
                date_iso = parsedate_to_datetime(with_suppress).isoformat()
        except Exception:  # noqa: BLE001
            date_iso = ""
        refs = [r for r in re.split(r"\s+", m.get("References", "") or "") if r]
        return {
            "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
            "seen": seen,
            "from_name": _decode(from_name), "from_addr": from_addr.lower(),
            "to_addr": to_addr.lower(),
            "subject": _decode(m.get("Subject", "")),
            "date": _decode(m.get("Date", "")), "date_iso": date_iso,
            "message_id": (m.get("Message-ID", "") or "").strip(),
            "in_reply_to": (m.get("In-Reply-To", "") or "").strip(),
            "references": refs,
        }

    def _parse_full(self, uid, m) -> dict:
        """Письмо целиком. Тело всегда ТЕКСТ, даже если письмо пришло HTML-ом.

        Экран почты печатает тело как обычный текст, поэтому HTML в нём виден
        буквально — тегами и кусками CSS (владелец 18.08 про ленту лидов).
        Голая замена тегов на пробел этого не решала: сущности («&nbsp;»,
        «&lt;адрес&gt;») оставались как есть, переносы строк пропадали, а
        содержимое <style> вываливалось в текст письма.
        """
        from sender.pismo_v_tekst import luchshee_telo, v_tekst
        head = self._parse_headers(uid, m, seen=True)
        body = ""
        if m.is_multipart():
            # Обе части, и выбор между ними: таблица в plain у Outlook
            # рассыпается на отдельные слова, в HTML она цела.
            plain = html = ""
            for part in m.walk():
                тип = part.get_content_type()
                вложение = "attachment" in str(part.get("Content-Disposition", ""))
                if вложение:
                    continue
                if тип == "text/plain" and not plain:
                    plain = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
                elif тип == "text/html" and not html:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
            body = luchshee_telo(plain, html)
        else:
            # Письмо из одной части бывает и HTML-ом — тогда раньше сюда
            # приезжал сырой исходник: ветка снятия тегов до неё не доходила.
            body = v_tekst((m.get_payload(decode=True) or b"").decode(
                m.get_content_charset() or "utf-8", "replace"))
        head["body"] = body.strip()
        return head

    @staticmethod
    def _enc_folder(folder: str):
        # imaplib принимает имя в кавычках; UTF-7 имена уже приходят как строки
        return f'"{folder}"'

    @staticmethod
    def _safe_logout(imap) -> None:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
