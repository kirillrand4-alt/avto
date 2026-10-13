# -*- coding: utf-8 -*-
"""Вход по SMTP в каждый ящик — без отправки письма (EHLO, AUTH, QUIT).

Владелец 13.10: «Яндекс отвечает = работает отправка?». Соединение — ещё не
отправка: проверяем, что каждый ящик логинится. Пароли не печатаются.
"""
import os
import smtplib
import ssl
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
ящики = list(cfg.mailboxes())
ок = 0
for м in ящики:
    g = (lambda k: getattr(м, k, None) if not isinstance(м, dict) else м.get(k))
    хост, порт, логин, env = g("smtp_host"), int(g("smtp_port") or 465), g("login"), g("password_env")
    пароль = os.environ.get(str(env or ""))
    if not пароль:
        print("   %-34s %s:%s -> нет пароля в env %s" % (логин, хост, порт, env))
        continue
    t = time.time()
    try:
        if порт == 465:
            s = smtplib.SMTP_SSL(хост, порт, timeout=20, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(хост, порт, timeout=20)
            s.starttls(context=ssl.create_default_context())
        s.login(логин, пароль)
        s.quit()
        ок += 1
        print("   %-34s %s:%s -> ВХОД ОК %.1fс" % (логин, хост, порт, time.time() - t))
    except Exception as е:  # noqa: BLE001
        print("   %-34s %s:%s -> СБОЙ %.1fс: %s" % (логин, хост, порт, time.time() - t,
                                                   str(е)[:120]))
print("=== ВХОД В ЯЩИКИ: %d из %d ===" % (ок, len(ящики)))
