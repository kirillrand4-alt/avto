# -*- coding: utf-8 -*-
"""После перезапуска: жива ли панель и что отдаёт карточка лида с контактами."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
итог = {}
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "(Get-Service SenderPanel).Status"],
                   capture_output=True, text=True, timeout=120)
итог['служба'] = (p.stdout or '').strip()[:20]
r = subprocess.run(['curl', '-s', 'http://127.0.0.1:8091/api/openapi.json'],
                   capture_output=True, text=True, timeout=90)
try:
    схема = json.loads(r.stdout or '{}')
    итог['ручек'] = len((схема.get('paths') or {}))
except Exception as e:  # noqa: BLE001
    итог['схема'] = str(e)[:80]
# зовём тот же код, что и ручка карточки
import importlib
м = importlib.import_module('sender.api.app')
итог['помощник_контактов_в_коде'] = '_kontakty_kompanii' in open(
    r'C:\sender\sender\api\app.py', encoding='utf-8', errors='replace').read()
# данные для двух лидов
import sqlite3
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
лиды = [dict(zip(('id', 'nm', 'inn'), x)) for x in s.execute(
    "select id, coalesce(company_name,''), coalesce(inn,'') from leads "
    "where coalesce(inn,'')<>'' order by id desc limit 2")]
s.close()
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
для = []
for л in лиды:
    цифры = ''.join(ch for ch in л['inn'] if ch.isdigit())
    почты = [dict(x) for x in c.execute(
        "select email, coalesce(role,'') role, coalesce(source_url,'') url "
        'from emails where inn=? limit 3', (цифры,))]
    для.append({'лид': л['id'], 'компания': л['nm'][:22], 'почты': почты})
c.close()
итог['пример_данных'] = для
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2200])
