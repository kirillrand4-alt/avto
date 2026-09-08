# -*- coding: utf-8 -*-
"""Только чтение: где dialog_thread_company теряет второе письмо."""
import io

т = io.open(r"C:\sender\sender\store.py", encoding="utf-8",
            errors="ignore").read()
i = т.find("def dialog_thread_company")
j = т.find("seen_rfc: set", i)
print(т[j:j + 2600])
