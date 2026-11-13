# -*- coding: utf-8 -*-
"""Работает ли вход в ящики (после смены тарифа владельцем 13.11): SMTP-логин и IMAP-логин паролем из
C:\\sender\\panel.env (читаем в процесс, НЕ печатаем). Письма не шлёт. По умолчанию — первый ящик КЦ и первый Meyer;
--vse — все ящики.   proverka_vhoda_yashchikov.py [--vse]"""
import imaplib, io, smtplib, ssl, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
env = {}
for с in io.open(r"C:\sender\panel.env", encoding="utf-8-sig"):
    if "=" in с and not с.lstrip().startswith("#"):
        к, v = с.split("=", 1); env[к.strip()] = v.strip().strip('"')
ящ = Config.load(r"C:\sender\sender.yaml").mailboxes()
if "--vse" not in sys.argv:
    ящ = [next(m for m in ящ if m.division == "kc"), next(m for m in ящ if m.division == "meyer")]
ок = 0
for m in ящ:
    пw = env.get(m.password_env)
    if not пw: print("%-42s нет пароля в panel.env" % m.mailbox_id); continue
    рез = []
    try:
        if m.smtp_port == 465: s = smtplib.SMTP_SSL(m.smtp_host, 465, timeout=30)
        else: s = smtplib.SMTP(m.smtp_host, m.smtp_port, timeout=30); s.starttls()
        s.login(m.login, пw); s.quit(); рез.append("SMTP ок")
    except Exception as ex: рез.append("SMTP ОШИБКА: %s" % str(ex)[:120])
    try:
        i = imaplib.IMAP4_SSL(m.imap_host, m.imap_port, timeout=30); i.login(m.login, пw); i.logout(); рез.append("IMAP ок")
    except Exception as ex: рез.append("IMAP ОШИБКА: %s" % str(ex)[:120])
    ок += all("ок" in x for x in рез)
    print("%-42s %-6s %s" % (m.mailbox_id, m.division, " | ".join(рез)))
print("итого: %d из %d ящиков входят" % (ок, len(ящ)))
