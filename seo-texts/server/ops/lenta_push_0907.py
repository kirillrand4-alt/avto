# -*- coding: utf-8 -*-
"""Только чтение: push_warm_lead целиком."""
import io

т = io.open(r"C:\sender\sender\leaddesk.py", encoding="utf-8",
            errors="ignore").read()
i = т.find("def push_warm_lead")
print(т[i:i + 4200] if i > 0 else "push_warm_lead не найден")
