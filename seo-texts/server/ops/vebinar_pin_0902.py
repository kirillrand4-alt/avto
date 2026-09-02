# -*- coding: utf-8 -*-
"""Только чтение: как одобрение рождает письмо и можно ли закрепить ящик."""
import inspect
import io
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")

print("=== store.py 1855-1905 ===")
т = io.open(r"C:\sender\sender\store.py", encoding="utf-8", errors="replace").read().splitlines()
for i in range(1854, 1905):
    print("  %4d| %s" % (i + 1, т[i]))

print("\n=== pick_mailbox: сигнатура и первые строки ===")
try:
    from sender.sender import Sender
    ф = getattr(Sender, "pick_mailbox", None) or getattr(Sender, "_pick_mailbox", None)
    if ф is None:
        import sender.sender as SS
        ф = getattr(SS, "pick_mailbox", None)
    if ф:
        print("  %s" % str(inspect.signature(ф))[:200])
        исх = inspect.getsource(ф).splitlines()
        for л in исх[:22]:
            print("  " + л)
except Exception as ex:
    print("  ошибка: %s" % str(ex)[:160])

print("\n=== кто пишет messages.mailbox_id ===")
import os
for корень in (r"C:\sender\sender", r"C:\sender\server"):
    for дп, _, фс in os.walk(корень):
        for ф2 in фс:
            if not ф2.endswith(".py"):
                continue
            п = os.path.join(дп, ф2)
            try:
                s = io.open(п, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for м in re.finditer(r"mailbox_id\s*=\s*\?|SET mailbox_id|mailbox_id=mailbox|"
                                 r"pin_mailbox|zakrepit", s):
                print("  %s:%d %s" % (os.path.relpath(п, r"C:\sender"),
                                      s[:м.start()].count("\n") + 1, м.group(0)[:40]))

print("\n=== ПРИМЕР panel_json ===")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
р = c.execute("SELECT panel_json FROM confirm_reviews WHERE status='pending'"
              " ORDER BY id DESC LIMIT 1").fetchone()
if р and р[0]:
    d = json.loads(р[0])
    print("  ключи: %s" % ", ".join(sorted(d.keys())))
    print("  " + json.dumps(d, ensure_ascii=False)[:900])
