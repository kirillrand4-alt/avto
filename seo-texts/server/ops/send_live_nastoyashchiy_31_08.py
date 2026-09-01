# -*- coding: utf-8 -*-
"""Только чтение: обе _send_live и чем реально отправляется письмо."""
import io
import re

стр = io.open(r"C:\sender\sender\confirm.py", encoding="utf-8",
              errors="replace").read().splitlines()
print("=== ОБЁРТКА 889-913 ===")
for j in range(888, 913):
    print("  %4d  %s" % (j + 1, стр[j][:110]))

print("\n=== ИТОГ: НАСТОЯЩАЯ _send_live с 914, ключевые строки ===")
i = 913
отступ = len(стр[i]) - len(стр[i].lstrip())
к = len(стр)
for j in range(i + 1, len(стр)):
    x = стр[j]
    if x.strip() and (len(x) - len(x.lstrip())) <= отступ and x.lstrip().startswith("def "):
        к = j
        break
тело = стр[i:к]
print("  тело: %d..%d (%d строк)" % (i + 1, к, len(тело)))
for j, x in enumerate(тело):
    if re.search(r"self\.(_sender|_store)\.\w+\(|send_message|smtp|increment_sent|"
                 r"append_event|mark_sent", x):
        print("  %4d  %s" % (i + j + 1, x.strip()[:104]))
print("\n  записи состояния/события в теле:")
for к2 in ("increment_sent", "append_event", "mark_sent", "mailbox_state"):
    есть = [i + j + 1 for j, x in enumerate(тело) if к2 in x]
    print("    %-18s %s" % (к2, есть if есть else "НЕТ"))
