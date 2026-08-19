# -*- coding: utf-8 -*-
"""Что реально вернёт лента: зовём тот же код, что и ручка /leads."""
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.leaddesk import LeadDesk      # noqa: E402

config = Config.load(r'C:\sender\sender.yaml', env=__import__('os').environ)
store = Store(r'C:\sender\sender.db')
desk = LeadDesk(config, store)
лиды = desk.queue(limit=8)
отв = store.poslednie_otvety(inns=[getattr(l, 'inn', None) for l in лиды],
                             emails=[getattr(l, 'email', None) for l in лиды])
строки = []
for l in лиды:
    инн = ''.join(c for c in str(getattr(l, 'inn', '') or '') if c.isdigit())
    em = str(getattr(l, 'email', '') or '').lower()
    строки.append({'компания': (getattr(l, 'company_name', '') or '')[:24],
                   'статус': getattr(l, 'status', ''),
                   'приоритет': getattr(l, 'reply_kind', ''),
                   'otvet': отв.get(em) or отв.get(инн)})
print(json.dumps({'лидов': len(лиды), 'строки': строки}, ensure_ascii=False,
                 indent=1)[:2600])
