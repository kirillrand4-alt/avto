# -*- coding: utf-8 -*-
"""Через что уходит почта: свой сервер или SMTP провайдеров (это решает,
изменится ли доставляемость при переезде)."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                   # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
хосты = {}
пулы = {}
for м in cfg.mailboxes():
    х = getattr(м, "smtp_host", None) or getattr(м, "host", None) or "?"
    хосты[str(х)] = хосты.get(str(х), 0) + 1
    п = getattr(м, "pool", "?")
    пулы[str(п)] = пулы.get(str(п), 0) + 1
print("SMTP-хосты ящиков:")
for х, n in sorted(хосты.items(), key=lambda x: -x[1]):
    print("   %-34s %d" % (х, n))
print("\nпулы:")
for п, n in sorted(пулы.items(), key=lambda x: -x[1]):
    print("   %-20s %d" % (п, n))
м = cfg.mailboxes()[0]
print("\nполя ящика: %s" % [p for p in dir(м) if not p.startswith("_")][:24])
print("\nIMAP-хосты:")
и = {}
for м in cfg.mailboxes():
    х = getattr(м, "imap_host", None) or "?"
    и[str(х)] = и.get(str(х), 0) + 1
for х, n in sorted(и.items(), key=lambda x: -x[1]):
    print("   %-34s %d" % (х, n))
