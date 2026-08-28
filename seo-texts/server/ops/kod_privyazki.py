# -*- coding: utf-8 -*-
import io
т = io.open(r"C:\sender\sender\imap_watcher.py", encoding="utf-8").read()
i = т.find("_recipient_by_emails([from_addr])")
print(т[max(0, i - 1500):i + 900])
print("=" * 60)
j = т.find("def _recipient_by_domain")
print(т[j:т.find("\n    def ", j + 10)])
