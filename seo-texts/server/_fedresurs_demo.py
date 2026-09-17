# -*- coding: utf-8 -*-
"""Живой показ: что Федресурс отдаёт по нашим же компаниям."""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_tmp')
import collector_fedresurs as F  # noqa: E402

# Берём компании из нашей базы: крупные, с сайтом, из целевых отраслей.
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
инны = [r[0] for r in c.execute(
    "select inn from companies where coalesce(site,'')<>'' "
    "and coalesce(division,'') in ('kc','meyer') "
    "order by rowid desc limit 25").fetchall()]
имена = dict(c.execute(
    "select inn, coalesce(name,'') from companies where inn in (%s)"
    % ','.join('?' * len(инны)), инны).fetchall())
c.close()

o = {'спрошено_ИНН': len(инны)}
try:
    items = F.col_fedresurs(days=365, max_items=60, inns=инны)
except TypeError:
    items = F.col_fedresurs(days=365, max_items=60)
except Exception as e:
    items = []
    o['ОШИБКА'] = repr(e)[:200]

o['сообщений'] = len(items)
o['по_типам'] = {}
for it in items:
    k = it.get('msg_type') or it.get('type') or '?'
    o['по_типам'][k] = o['по_типам'].get(k, 0) + 1
o['карточки'] = [{
    'компания': (it.get('company_name') or имена.get(it.get('inn'), ''))[:45],
    'инн': it.get('inn'),
    'тип': it.get('msg_type'),
    'дата': str(it.get('pubDate'))[:10],
    'предмет': str(it.get('what') or it.get('title') or '')[:150],
    'сумма': it.get('sum') or '',
} for it in items[:12]]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str))
