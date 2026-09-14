# -*- coding: utf-8 -*-
"""Что от компрессорных осталось в конфиге и мешает ли это."""
import io
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402

ФАЙЛ = r"C:\sender\sender.yaml"
ДОМЕНЫ = ("kompressor-", "compressor-")
т = io.open(ФАЙЛ, encoding="utf-8").read()
cfg = Config.load(ФАЙЛ)

раздел = ""
print("--- оставшиеся упоминания ---")
n = 0
for с in т.splitlines():
    if re.match(r"^[A-Za-z_]", с):
        раздел = с.split(":")[0]
    if any(д in с for д in ДОМЕНЫ):
        n += 1
        print("   [%s] %s" % (раздел, с.strip()[:100]))
print("   всего: %d" % n)

print("")
print("--- карта обращений (personalization) ---")
вкл = False
к = 0
for с in т.splitlines():
    if с.startswith("personalization:"):
        вкл = True
    elif вкл and re.match(r"^[^\s#]", с):
        break
    if вкл and "@" in с:
        к += 1
print("   строк с ящиками: %d (ждём 19)" % к)

print("")
print("--- ящики, которые панель считает своими ---")
свои = {m.mailbox_id for m in cfg.mailboxes()}
print("   %d штук, компрессорных среди них: %d"
      % (len(свои), sum(1 for x in свои if any(д in x for д in ДОМЕНЫ))))
print("")
print("=" * 74)
print("=== ОСТАТКИ КОМПРЕССОРНЫХ В КОНФИГЕ ===")
