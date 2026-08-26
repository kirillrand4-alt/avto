# -*- coding: utf-8 -*-
"""Для сравнения: как выглядят «домен на много компаний» в НАШЕЙ базе (там, где
сайты добывались поиском) — чтобы честно сопоставить с каталогами."""
import io
import json
import sys
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
O = {}
try:
    O['domeny_mnogo_kompaniy_топ'] = cx.execute(
        "SELECT domen, kompaniy FROM domeny_mnogo_kompaniy ORDER BY kompaniy DESC LIMIT 10"
    ).fetchall()
    O['всего_таких_доменов'] = cx.execute(
        "SELECT COUNT(*) FROM domeny_mnogo_kompaniy").fetchone()[0]
except Exception as e:
    O['err'] = str(e)[:80]
try:
    O['источники_сайта'] = cx.execute(
        "SELECT COALESCE(site_source,'(пусто)'), COUNT(*) FROM companies "
        "WHERE COALESCE(site,'')!='' GROUP BY 1 ORDER BY 2 DESC LIMIT 10").fetchall()
except Exception as e:
    O['err2'] = str(e)[:80]
try:
    O['verified_срез'] = cx.execute(
        "SELECT COALESCE(verified,'(пусто)'), COUNT(*) FROM companies "
        "WHERE COALESCE(site,'')!='' GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall()
except Exception as e:
    O['err3'] = str(e)[:80]
cx.close()
print(json.dumps(O, ensure_ascii=False)[:3000])
