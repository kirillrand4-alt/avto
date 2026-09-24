# -*- coding: utf-8 -*-
"""Доступы к ящику: сервер, логин, где лежит пароль и его значение.

Владелец просит логин и пароль от ящика, с которого писалось письмо, —
чтобы зайти в почту руками. Печатаем только по явному запросу владельца.
"""
import os
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402

ЯЩИК = sys.argv[1] if len(sys.argv) > 1 else "a.miroshnichenko@optic-sort.ru"
cfg = Config.load(r"C:\sender\sender.yaml")

м = next((x for x in cfg.mailboxes() if x.mailbox_id == ЯЩИК), None)
if not м:
    raise SystemExit("ящика %s в конфиге нет" % ЯЩИК)

print("--- ящик %s ---" % ЯЩИК)
for поле in ("mailbox_id", "login", "from_name", "provider", "smtp_host",
             "smtp_port", "imap_host", "imap_port", "password_env", "division",
             "pool"):
    з = getattr(м, поле, None)
    if з not in (None, ""):
        print("   %-14s %s" % (поле, з))

ключ = getattr(м, "password_env", "") or ""
пароль = os.environ.get(ключ, "")
print("")
print("--- пароль ---")
print("   переменная окружения: %s" % (ключ or "не задана"))
if пароль:
    print("   значение: %s" % пароль)
else:
    print("   в окружении ЭТОГО процесса пусто — ищем там, где живёт служба")
    for п in (r"C:\sender\runner-secrets.env", r"C:\sender\server\runner-secrets.env",
              r"C:\sender\.env", r"C:\sender\secrets.env", r"C:\sender\boxes.env"):
        if not os.path.exists(п):
            continue
        for с in open(п, encoding="utf-8", errors="replace"):
            if с.strip().startswith(ключ + "="):
                print("   %s → %s" % (п, с.split("=", 1)[1].strip()))
print("")
print("=" * 74)
print("=== ДОСТУП К ЯЩИКУ ===")
