# -*- coding: utf-8 -*-
"""Исправить причину у 19 снятых дублей адреса в кампании 22 «КЦ газ 11.11» (старая версия dubli_kartochek.py
записала причину от 29.10). Меняется только текст reason."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with c:
    n = c.execute("UPDATE confirm_reviews SET reason='дубль адреса в кампании КЦ газ (общий ящик двух ИНН)' WHERE campaign_id=22 "
                  "AND status='skipped' AND reason='дубль карточки (двойной запуск починки 29.10)'").rowcount
print("исправлено:", n)
