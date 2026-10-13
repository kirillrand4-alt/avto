# -*- coding: utf-8 -*-
"""Текст свежего письма из ящика по адресу отправителя (только чтение, PEEK).

    pismo_iz_yashchika.py <ящик> <от_кого> [dney=3]
"""
import email
import email.header
import email.policy
import imaplib
import os
import re
import sys
import time
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
ЯЩ, ОТ = sys.argv[1].lower(), sys.argv[2].lower()
им = dict(а.split("=", 1) for а in sys.argv[3:] if "=" in а)
cfg = Config.load(r"C:\sender\sender.yaml")
mb = next(m for m in cfg.mailboxes() if m.mailbox_id.lower() == ЯЩ)
im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
im.login(mb.login, os.getenv(mb.password_env, ""))
SINCE = time.strftime("%d-%b-%Y", time.localtime(time.time() - int(им.get("dney", "3")) * 86400))
папки = []
for стр in (im.list()[1] or []):
    м = re.search(rb'(?:"([^"]+)"|(\S+))$', стр if isinstance(стр, bytes) else b"")
    if м:
        папки.append((м.group(1) or м.group(2)).decode())
пары = []
for п in папки:
    try:
        if im.select('"%s"' % п, readonly=True)[0] != "OK":
            continue
        вс = (im.uid("SEARCH", None, "SINCE", SINCE)[1][0] or b"").split()
        if not вс:
            continue
        for ч in im.uid("FETCH", b",".join(вс), "(UID BODY.PEEK[HEADER.FIELDS (FROM)])")[1] or []:
            if isinstance(ч, tuple) and ОТ.encode() in ч[1].lower():
                мu = re.search(rb"UID (\d+)", ч[0])
                if мu:
                    пары.append((п, мu.group(1)))
    except Exception:  # noqa: BLE001
        continue
print("папки: %s; нашлось: %s" % (папки, [(п, u.decode()) for п, u in пары]))
for п, u in пары:
    im.select('"%s"' % п, readonly=True)
    сыр = next(ч[1] for ч in im.uid("FETCH", u, "(BODY.PEEK[])")[1] if isinstance(ч, tuple))
    м = email.message_from_bytes(сыр, policy=email.policy.default)
    print("--- uid %s | %s | от %s | кому %s | тема %s" % (u.decode(), м["Date"], м["From"], м["To"], м["Subject"]))
    print("In-Reply-To: %s | References: %s" % (str(м["In-Reply-To"])[:80], str(м["References"])[:80]))
    тело = м.get_body(preferencelist=("plain", "html"))
    т = тело.get_content() if тело else ""
    if тело and тело.get_content_subtype() == "html":
        т = re.sub(r"<[^>]+>", " ", т)
    print(re.sub(r"\n\s*\n+", "\n", т).strip()[:1500])
    влож = [ч.get_filename() for ч in м.iter_attachments()]
    if влож:
        print("вложения:", влож)
im.logout()
print("=== ПИСЬМО ИЗ ЯЩИКА ===")
