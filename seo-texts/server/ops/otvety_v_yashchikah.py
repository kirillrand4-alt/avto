# -*- coding: utf-8 -*-
"""Ответы, которые лежат в ящиках, но панель их не подхватила (владелец 20.10:
«посмотри такие и подобные в ящиках, если нет в ленте — заведи»).

По IMAP всех ящиков за N дней (по умолч. 14) читаем ЗАГОЛОВКИ писем во
«Входящих» и в «Спаме» (ответ клиента мог лечь в спам нашего ящика). Отсев:
наши домены, отбивки (mailer-daemon/postmaster), автоответы (Auto-Submitted,
«автоответ/out of office»). Остальное сверяем с лентой: адрес ответившего уже
есть в leads или в событиях reply — пропуск. Привязка к компании: адрес или
домен, которому мы писали. Пишет _ops/otvety-v-yashchikah.json; с --zavesti —
лиды через LeadDesk.push_warm_lead (без Битрикса). Тела писем не читаем.

    otvety_v_yashchikah.py [N] [--zavesti]"""
import email
import email.header
import email.utils
import imaplib
import io
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
for с in open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in с and not с.strip().startswith("#"):
        к, з = с.split("=", 1)
        os.environ.setdefault(к.strip(), з.strip().strip('"'))
from sender.config import Config  # noqa: E402

N = int(next((a for a in sys.argv[1:] if a.isdigit()), "14"))
SINCE = time.strftime("%d-%b-%Y", time.localtime(time.time() - N * 86400))
cfg = Config.load(r"C:\sender\sender.yaml")
ящики = list(cfg.mailboxes())
наши = {mb.mailbox_id.split("@")[-1].lower() for mb in ящики} | {"prokompressor.ru", "ruspromgroup.ru"}
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
известно = {str(r[0]).lower() for r in c.execute("SELECT email FROM leads WHERE email IS NOT NULL")}
for r in c.execute("SELECT r.email FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','reply_auto')"):
    известно.add(str(r[0]).lower())
АВТО = re.compile(r"(?i)автоответ|auto.?reply|out of office|автоматическ|отсутств|в отпуске|vacation|undeliver|не доставлен|delivery status")


def дек(s):
    try:
        return str(email.header.make_header(email.header.decode_header(s or "")))
    except Exception:  # noqa: BLE001
        return str(s or "")


нашли = []
сч = {"писем": 0, "наши/отбивки": 0, "автоответ": 0, "уже в ленте": 0}
for mb in ящики:
    пароль = os.getenv(mb.password_env, "")
    if not пароль:
        continue
    try:
        im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
        im.login(mb.login, пароль)
    except Exception as ex:  # noqa: BLE001
        print("вход не вышел:", mb.mailbox_id, str(ex)[:50])
        continue
    папки = ["INBOX"]
    for стр in im.list()[1] or []:
        s = стр.decode("utf-8", "replace") if isinstance(стр, bytes) else str(стр)
        м = re.search(r'"([^"]+)"$', s) or re.search(r"\s(\S+)$", s)
        if м and ("\\Junk" in s or "\\Spam" in s or re.search(r"(?i)spam|junk|&BCEEPwQwBDw", м.group(1))):
            папки.append(м.group(1))
    for п in папки:
        try:
            if im.select('"%s"' % п if п != "INBOX" else п, readonly=True)[0] != "OK":
                continue
            uids = (im.uid("SEARCH", None, "SINCE", SINCE)[1][0] or b"").split()
            for i in range(0, len(uids), 100):
                кус = b",".join(uids[i:i + 100])
                typ, data = im.uid("FETCH", кус, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE AUTO-SUBMITTED IN-REPLY-TO MESSAGE-ID)])")
                for часть in data or []:
                    if not isinstance(часть, tuple):
                        continue
                    сч["писем"] += 1
                    h = email.message_from_bytes(часть[1])
                    имя, адр = email.utils.parseaddr(дек(h.get("From")))
                    адр = адр.lower()
                    тема = дек(h.get("Subject"))
                    if not адр or адр.split("@")[-1] in наши or re.search(r"(?i)mailer-daemon|postmaster|no-?reply|noreply", адр):
                        сч["наши/отбивки"] += 1
                        continue
                    if (h.get("Auto-Submitted") or "").lower() not in ("", "no") or АВТО.search(тема):
                        сч["автоответ"] += 1
                        continue
                    if адр in известно:
                        сч["уже в ленте"] += 1
                        continue
                    нашли.append({"ящик": mb.mailbox_id, "папка": п, "от": адр, "имя": имя, "тема": тема[:90],
                                  "дата": str(h.get("Date") or "")[:31], "ответ_на": bool(h.get("In-Reply-To")),
                                  "msgid": str(h.get("Message-ID") or "").strip()})
        except Exception as ex:  # noqa: BLE001
            print("папка", mb.mailbox_id, п, str(ex)[:60])
    try:
        im.logout()
    except Exception:  # noqa: BLE001
        pass
# привязка к компании
for x in нашли:
    rec = c.execute("SELECT id, company_name, inn FROM recipients WHERE lower(email)=?", (x["от"],)).fetchone()
    if rec is None:
        rec = c.execute("SELECT r.id, r.company_name, r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                        "WHERE m.status='sent' AND r.domain=? ORDER BY m.sent_at DESC LIMIT 1", (x["от"].split("@")[-1],)).fetchone()
    x["rid"], x["компания"], x["inn"] = (rec[0], rec[1], rec[2]) if rec else (None, None, None)
нашли.sort(key=lambda x: (x["rid"] is None, x["ящик"]))
json.dump(нашли, io.open(r"C:\sender\_ops\otvety-v-yashchikah.json", "w", encoding="utf-8"), ensure_ascii=False)
print("за %d дней: %s" % (N, сч))
print("писем от внешних, которых нет в ленте: %d, из них привязаны к нашей компании: %d, в спаме: %d" % (
    len(нашли), sum(1 for x in нашли if x["rid"]), sum(1 for x in нашли if x["папка"] != "INBOX")))
for x in нашли[:60]:
    print("  %s %-34s %-6s от %-32s | %-26s | %s" % (x["дата"][5:22], x["ящик"][:34], "спам" if x["папка"] != "INBOX" else "вход",
                                                  x["от"][:32], str(x["компания"] or "—")[:26], x["тема"][:60]))
if "--zavesti" in sys.argv:
    from sender.leaddesk import LeadDesk  # noqa: E402
    from sender.store import Store  # noqa: E402
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    ld = LeadDesk(cfg, store)
    n = 0
    for x in нашли:
        if not x["rid"]:
            continue
        lid = ld.push_warm_lead(store.get_recipient(int(x["rid"])), x["msgid"] or ("imap:%s" % x["от"]),
                                "[ящик %s, %s] %s" % (x["ящик"], "спам" if x["папка"] != "INBOX" else "входящие", x["тема"]),
                                otvetil=x["от"], v_bitrix=False)
        n += 1
        print("  лид #%s: %s (%s)" % (lid, x["от"], x["компания"]))
    print("заведено в ленту:", n)
