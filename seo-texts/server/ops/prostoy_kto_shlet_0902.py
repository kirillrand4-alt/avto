# -*- coding: utf-8 -*-
"""Только чтение: как AutoSendLoop выбирает ящик — тот же ли это путь."""
import io
import re

п = r"C:\sender\sender\auto_send.py"
т = io.open(п, encoding="utf-8", errors="replace").read()
лн = т.splitlines()
print("строк в auto_send.py: %d" % len(лн))

print("\n=== ВЫБОР ЯЩИКА И ОТПРАВКА ===")
for м in re.finditer(r"(pick_mailbox|\.send\(|mailbox_id|division)", т):
    н = т[:м.start()].count("\n")
    с = лн[н].strip()
    if с.startswith("#") or not с:
        continue
    print("  %5d| %s" % (н + 1, с[:104]))

print("\n=== ОКРЕСТНОСТЬ pick_mailbox ===")
н = next((i for i, л in enumerate(лн) if "pick_mailbox" in л and not л.strip().startswith("#")), None)
if н is not None:
    for i in range(max(0, н - 14), min(len(лн), н + 12)):
        print("  %5d| %s" % (i + 1, лн[i][:104]))
else:
    print("  pick_mailbox в auto_send.py не встречается")
