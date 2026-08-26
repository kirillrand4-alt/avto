# -*- coding: utf-8 -*-
"""Как выглядит привязка получателя в БОЕВОМ imap_watcher."""
import io
т = io.open(r"C:\sender\sender\imap_watcher.py", encoding="utf-8",
            errors="replace").read()
i = т.find("recipient_id = None")
print(т[i - 200:i + 2600] if i > 0 else "не нашёл")
print("")
print("=== есть ли уже наши правки ===")
for м in ("_recipient_by_domain", "ОБЩИЕ_ДОМЕНЫ", "_rfc_kandidaty",
          "def _process_event"):
    print("   %-24s %s" % (м, т.count(м)))
