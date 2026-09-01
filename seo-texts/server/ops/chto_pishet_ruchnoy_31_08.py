# -*- coding: utf-8 -*-
"""Только чтение: что вызывает и что записывает ручной путь."""
import io
import re

c = io.open(r"C:\sender\sender\confirm.py", encoding="utf-8",
            errors="replace").read()
стр = c.splitlines()
н = [i for i, x in enumerate(стр) if re.match(r"\s*def _send_live", x)]
print("=== _send_live начинается на строке %s ===" % [i + 1 for i in н])
if н:
    i = н[0]
    # конец функции — следующий def на том же отступе
    отступ = len(стр[i]) - len(стр[i].lstrip())
    к = len(стр)
    for j in range(i + 1, len(стр)):
        x = стр[j]
        if x.strip() and (len(x) - len(x.lstrip())) <= отступ and x.lstrip().startswith("def "):
            к = j
            break
    print("  тело: строки %d..%d" % (i + 1, к))
    тело = стр[i:к]
    print("\n=== ВЫЗОВЫ ВНУТРИ _send_live ===")
    for j, x in enumerate(тело):
        if re.search(r"self\.(_sender|_store)\.\w+\(", x):
            m = re.findall(r"self\.(?:_sender|_store)\.(\w+)\(", x)
            print("  %4d  %-24s %s" % (i + j + 1, ",".join(m), x.strip()[:78]))
    print("\n=== ЕСТЬ ЛИ ЗАПИСЬ СОБЫТИЯ / СОСТОЯНИЯ ===")
    for к2 in ("add_event", "append_event", "event", "mark_sent",
               "upsert_mailbox_state", "mailbox_state", "record_send"):
        есть = [i + j + 1 for j, x in enumerate(тело) if к2 in x]
        print("  %-22s %s" % (к2, есть if есть else "НЕТ"))

print("\n=== ИТОГ: как отправляет sender.py (около строки с event_type=sent) ===")
s = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
            errors="replace").read().splitlines()
н2 = [i for i, x in enumerate(s) if 'event_type="sent"' in x]
for i in н2:
    print("  --- sender.py:%d ---" % (i + 1))
    for j in range(max(0, i - 14), min(i + 8, len(s))):
        print("    %4d  %s" % (j + 1, s[j][:104]))
