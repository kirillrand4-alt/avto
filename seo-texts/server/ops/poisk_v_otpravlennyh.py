# -*- coding: utf-8 -*-
"""Писали ли мы на адреса (в т.ч. руками из веб-почты): поиск TO/CC в папке
«Отправленные» всех ящиков. Только чтение.
    poisk_v_otpravlennyh.py a@b.ru,c@d.ru [dney=60]"""
import imaplib, os, re, sys, time
sys.path.insert(0, r"C:\sender")
for с in open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in с and not с.strip().startswith("#"):
        к, з = с.split("=", 1); os.environ.setdefault(к.strip(), з.strip().strip('"'))
from sender.config import Config
адреса = [a.strip().lower() for a in sys.argv[1].split(",") if a.strip()]
им = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
SINCE = time.strftime("%d-%b-%Y", time.localtime(time.time() - int(им.get("dney", "60")) * 86400))
нашли = {a: [] for a in адреса}
for mb in Config.load(r"C:\sender\sender.yaml").mailboxes():
    пароль = os.getenv(mb.password_env, "")
    if not пароль: continue
    try:
        im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25); im.login(mb.login, пароль)
    except Exception as ex:
        print("вход не вышел:", mb.mailbox_id, str(ex)[:50]); continue
    папки = []
    for стр in im.list()[1] or []:
        s = стр.decode("utf-8", "replace") if isinstance(стр, bytes) else str(стр)
        м = re.search(r'"([^"]+)"$', s) or re.search(r'\s(\S+)$', s)
        if м and ("\\Sent" in s or re.search(r"(?i)sent|&BB4EQgQ", м.group(1))):
            папки.append(м.group(1))
    if mb.mailbox_id in ("d.ivanov@sorting-systems.ru", "o.boyarkin@optical-sort.ru"): print("папки", mb.mailbox_id, папки)
    for п in папки:
        try:
            if im.select('"%s"' % п, readonly=True)[0] != "OK": continue
            for a in адреса:
                for поле in ("TO", "CC"):
                    u = (im.uid("SEARCH", None, "SINCE", SINCE, поле, a)[1][0] or b"").split()
                    if u: нашли[a].append("%s:%s %d" % (mb.mailbox_id, поле, len(u)))
        except Exception as ex:
            print("папка", mb.mailbox_id, п, str(ex)[:50])
    try: im.logout()
    except Exception: pass
for a, x in нашли.items():
    print(("ПИСАЛИ  " if x else "НЕ ПИСАЛИ ") + a, "|", "; ".join(x))
