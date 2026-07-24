"""IMAP-браузер панели (read-only) на фейковом IMAP.

Проверяем: список ящиков из конфига; папки с ролями; ВСЕ письма папки
(не только непрочитанные), новые сверху; поиск по адресу/теме; полное тело;
цепочка по теме/References; read-only (никаких store/expunge)."""
import email
import os
import sys
from email.message import EmailMessage

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.config import Config  # noqa: E402
from sender.mailbrowser import MailBrowser, _norm_subject  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402


def _raw(frm, to, subj, date, mid, body="Текст письма.",
         in_reply_to=None, refs=None):
    m = EmailMessage()
    m["From"] = frm
    m["To"] = to
    m["Subject"] = subj
    m["Date"] = date
    m["Message-ID"] = mid
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
    if refs:
        m["References"] = refs
    m.set_content(body)
    return m.as_bytes()


# письма INBOX: два в одной цепочке + одно отдельное
_MSGS = {
    b"1": _raw("Клиент <k@zavod.ru>", "i.lyapin@box.ru", "Запрос цены",
              "Mon, 21 Jul 2026 10:00:00 +0300", "<a@zavod.ru>"),
    b"2": _raw("i.lyapin@box.ru", "k@zavod.ru", "Re: Запрос цены",
              "Mon, 21 Jul 2026 11:00:00 +0300", "<b@box.ru>",
              in_reply_to="<a@zavod.ru>", refs="<a@zavod.ru>"),
    b"3": _raw("Другой <x@other.ru>", "i.lyapin@box.ru", "Реклама",
              "Sun, 20 Jul 2026 09:00:00 +0300", "<c@other.ru>"),
}
_SEEN = {b"1"}  # письмо 1 прочитано, 2 и 3 — нет


class _FakeIMAP:
    """Фейковый IMAP4: только read-методы. store/expunge/delete запрещены."""

    def __init__(self):
        self.selected_readonly = None
        self.mutations = []  # сюда попадёт любая мутация → тест это ловит

    def list(self):
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Sent) "/" "Sent"',
            b'(\\HasNoChildren \\Junk) "/" "Spam"',
        ]

    def select(self, folder, readonly=False):
        self.selected_readonly = readonly
        return "OK", [b"3"]

    def search(self, charset, *criteria):
        if criteria and criteria[0] == "ALL":
            return "OK", [b" ".join(_MSGS.keys())]
        # поиск по подстроке в FROM/TO/SUBJECT
        joined = " ".join(str(c) for c in criteria).lower()
        term = None
        for c in criteria:
            if c not in ("OR", "FROM", "TO", "SUBJECT") and '"' in str(c):
                term = str(c).strip('"').lower()
        hits = []
        for uid, raw in _MSGS.items():
            if term and term in raw.decode("utf-8", "replace").lower():
                hits.append(uid)
        return "OK", [b" ".join(hits)]

    def fetch(self, uid, spec):
        uid = uid if isinstance(uid, bytes) else str(uid).encode()
        raw = _MSGS.get(uid)
        if raw is None:
            return "NO", [None]
        if "HEADER.FIELDS" in spec:
            m = email.message_from_bytes(raw)
            hdr_keys = ["From", "To", "Subject", "Date", "Message-ID",
                        "In-Reply-To", "References"]
            hdr = "".join(f"{k}: {m[k]}\r\n" for k in hdr_keys if m[k]).encode()
            flags = b"\\Seen" if uid in _SEEN else b""
            return "OK", [(b"%s (FLAGS (%s) BODY[HEADER])" % (uid, flags), hdr)]
        return "OK", [(b"%s (BODY[])" % uid, raw)]

    # мутации — если браузер их вызовет, тест упадёт
    def store(self, *a, **k):
        self.mutations.append(("store", a))
        return "OK", []

    def expunge(self):
        self.mutations.append(("expunge", ()))
        return "OK", []

    def logout(self):
        return "OK", []


@pytest.fixture
def browser(tmp_path):
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    (tmp_path / "c.yaml").write_text(
        BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db")),
        encoding="utf-8")
    cfg = Config.load(str(tmp_path / "c.yaml"))
    fake = _FakeIMAP()
    br = MailBrowser(cfg, imap_opener=lambda mb: fake)
    return br, cfg, fake


def test_mailboxes_from_config(browser):
    br, cfg, _ = browser
    boxes = br.mailboxes()
    assert len(boxes) == len(cfg.mailboxes())
    assert all("mailbox_id" in b and "provider" in b for b in boxes)


def test_folders_roles(browser):
    br, cfg, _ = browser
    mbid = cfg.mailboxes()[0].mailbox_id
    folders = br.folders(mbid)
    roles = {f["role"]: f["name"] for f in folders}
    assert roles.get("inbox") == "INBOX"
    assert "sent" in roles and "junk" in roles
    assert folders[0]["role"] == "inbox"  # INBOX первым


def test_messages_all_not_only_unseen(browser):
    br, cfg, _ = browser
    mbid = cfg.mailboxes()[0].mailbox_id
    res = br.messages(mbid, folder="INBOX", limit=50)
    assert res["total"] == 3                      # ВСЕ письма, не только UNSEEN
    uids = [m["uid"] for m in res["messages"]]
    assert uids == ["3", "2", "1"]                # новые сверху (uid desc)
    m1 = next(m for m in res["messages"] if m["uid"] == "1")
    assert m1["seen"] is True                     # прочитанное помечено
    assert m1["from_addr"] == "k@zavod.ru"
    assert m1["subject"] == "Запрос цены"


def test_readonly_no_mutations(browser):
    br, cfg, fake = browser
    mbid = cfg.mailboxes()[0].mailbox_id
    br.messages(mbid, folder="INBOX", limit=50)
    br.message(mbid, folder="INBOX", uid="1")
    assert fake.selected_readonly is True         # select(readonly=True)
    assert fake.mutations == []                   # \Seen/expunge НЕ трогали


def test_search_by_address(browser):
    br, cfg, _ = browser
    mbid = cfg.mailboxes()[0].mailbox_id
    res = br.messages(mbid, folder="INBOX", search="zavod.ru")
    addrs = {m["from_addr"] for m in res["messages"]}
    assert "k@zavod.ru" in addrs
    assert "x@other.ru" not in addrs              # чужой адрес отфильтрован


def test_full_message_body(browser):
    br, cfg, _ = browser
    mbid = cfg.mailboxes()[0].mailbox_id
    full = br.message(mbid, folder="INBOX", uid="2")
    assert "Текст письма." in full["body"]
    assert full["in_reply_to"] == "<a@zavod.ru>"
    assert full["subject"] == "Re: Запрос цены"


def test_thread_groups_conversation(browser):
    br, cfg, _ = browser
    mbid = cfg.mailboxes()[0].mailbox_id
    thread = br.thread(mbid, folder="INBOX", uid="1")
    uids = [m["uid"] for m in thread]
    assert "1" in uids and "2" in uids            # оба письма цепочки
    assert "3" not in uids                        # чужое письмо не в треде
    # старые сверху (по дате)
    assert uids.index("1") < uids.index("2")


def test_norm_subject():
    assert _norm_subject("Re: Запрос") == "запрос"
    assert _norm_subject("Fwd: Re: Тест") == "тест"
    assert _norm_subject("Обычная") == "обычная"
