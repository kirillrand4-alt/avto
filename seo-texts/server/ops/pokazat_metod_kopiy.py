# -*- coding: utf-8 -*-
"""Текст боевого kopii_avtootveta — чтобы править хирургически."""
import io

s = io.open(r"C:\sender\sender\store.py", encoding="utf-8").read()
i = s.find("def kopii_avtootveta")
print(s[i - 60:i + 2100] if i > 0 else "метода нет")
