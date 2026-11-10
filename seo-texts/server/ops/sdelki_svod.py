# -*- coding: utf-8 -*-
"""Свод таблицы sdelki_napr: сколько ИНН с активной сделкой по направлениям, дата выгрузки. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
print(c.execute("SELECT count(*), sum(meyer>0), sum(kc>0), sum(sc>0), min(ts), max(ts) FROM sdelki_napr").fetchone())
