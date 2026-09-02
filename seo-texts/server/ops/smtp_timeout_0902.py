# -*- coding: utf-8 -*-
"""Только чтение: есть ли таймаут у SMTP и на ком залип цикл."""
import inspect
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
import sender.sender as S         # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
print("=== ТАЙМАУТЫ В КОНФИГЕ ===")
for к in ("smtp.timeout", "smtp_timeout", "service.smtp_timeout",
          "send.timeout", "smtp.timeout_sec"):
    print("  %-24s %s" % (к, cfg.get(к, "нет ключа")))

исх = inspect.getsource(S)
print("\n=== SMTP В КОДЕ ОТПРАВЩИКА ===")
лн = исх.splitlines()
for м in re.finditer(r"(SMTP\(|SMTP_SSL\(|timeout|starttls|\.send_message)", исх):
    н = исх[:м.start()].count("\n")
    с = лн[н].strip()
    if с.startswith("#") or len(с) < 6:
        continue
    print("  %s" % с[:104])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\n=== КОМУ АДРЕСОВАНЫ ЗАВИСШИЕ ===")
for р in c.execute("SELECT m.id, r.email, r.mx_provider, m.claimed_at FROM messages m"
                   " JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.status='sending' ORDER BY m.claimed_at"):
    print("  msg#%-6s %-34s mx=%-8s взято %s"
          % (р["id"], р["email"][:34], р["mx_provider"], str(р["claimed_at"])[11:19]))
