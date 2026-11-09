# -*- coding: utf-8 -*-
"""Диагностика IMAP «Отправленных» ящика: imap_sent_test.py <ящик>. Только чтение."""
import imaplib, os, re, sys, time
sys.path.insert(0, r"C:\sender")
for с in open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in с and not с.strip().startswith("#"):
        к, з = с.split("=", 1); os.environ.setdefault(к.strip(), з.strip().strip('"'))
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
mb = next(m for m in cfg.mailboxes() if m.mailbox_id == sys.argv[1])
t = time.time(); im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=40); im.login(mb.login, os.getenv(mb.password_env, "")); print("вход %.1fс" % (time.time() - t))
for с in im.list()[1]: print(" ", с.decode("utf-8", "replace")[:100])
for п in ("Sent", '"Sent"', "&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-"):
    try:
        r = im.select(п, readonly=True); print("select", п, r[0], r[1][:1])
        if r[0] == "OK": break
    except Exception as ex: print("select", п, "ОШИБКА", str(ex)[:80])
for к in (("SEARCH", None, "ALL"), ("SEARCH", None, "SINCE", "01-Sep-2026")):
    try: t = time.time(); r = im.uid(*к); print(к, r[0], "найдено", len((r[1][0] or b"").split()), "%.1fс" % (time.time() - t))
    except Exception as ex: print(к, "ОШИБКА", str(ex)[:100])
uids = (im.uid("SEARCH", None, "SINCE", "01-Sep-2026")[1][0] or b"").split()
for n in (1, 5, 25):
    for вид in ("(BODY.PEEK[HEADER.FIELDS (TO DATE)])", "(BODY.PEEK[HEADER.FIELDS (TO CC DATE SUBJECT CONTENT-TYPE)])"):
        try:
            t = time.time(); r = im.uid("FETCH", b",".join(uids[:n]), вид); print("FETCH", n, вид[:40], r[0], len(r[1]), "%.1fс" % (time.time() - t))
        except Exception as ex:
            print("FETCH", n, вид[:40], "ОШИБКА", str(ex)[:80])
            im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=40); im.login(mb.login, os.getenv(mb.password_env, "")); im.select("Sent", readonly=True)
try:
    t = time.time(); r = im.fetch(b"1:25", "(BODY.PEEK[HEADER.FIELDS (TO DATE)])"); print("FETCH по номерам 1:25", r[0], len(r[1]), "%.1fс" % (time.time() - t))
except Exception as ex: print("FETCH по номерам ОШИБКА", str(ex)[:80])
