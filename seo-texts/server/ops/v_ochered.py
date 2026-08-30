# -*- coding: utf-8 -*-
"""Положить письма агентов в очередь подтверждения. ДАЛЬШЕ ХОЛД.

Идём тем же путём, что боевой прогон (ai_quota.py, строка ~1866):
    mid, _step, why = aq._ensure_message(campaign_id, recipient_id)
    store.confirm_submit(..., message_id=mid, status='pending')

Заслоны очереди (90 дней на контакт, потолок 2 адреса на компанию, стоп-лист)
стоят ВНУТРИ _ensure_message и confirm_submit - мы их не обходим: если письмо
отклонено, так и записываем.

  v_ochered.py proba  — показать, что будет сделано, ничего не писать
  v_ochered.py boy    — записать в sender.db
"""
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')

REZHIM = sys.argv[1] if len(sys.argv) > 1 else 'proba'
ISH = sys.argv[2] if len(sys.argv) > 2 else 'PISMA-GOTOVYE.json'
KAMPANIYA = int(sys.argv[3]) if len(sys.argv) > 3 else 10
ZHURNAL = r'C:\sender\_ops\zhurnal-agenty-50m.jsonl'
URL, TOK = os.environ['DROP_URL'].rstrip('/'), os.environ['DROP_TOKEN']

rq = urllib.request.Request(f'{URL}/{ISH}', headers={'X-Drop-Token': TOK})
with urllib.request.urlopen(rq, timeout=180) as r:
    dannye = json.loads(r.read().decode())
pisma = dannye['pisma']

from sender.config import Config              # noqa: E402
from sender.store import Store                # noqa: E402
from sender.ai_quota import build_ai_quota    # noqa: E402

cfg = Config.load(r'C:\sender\sender.yaml', env=os.environ)
try:
    db_path = cfg.get('service.db_path', r'C:\sender\sender.db') or r'C:\sender\sender.db'
except Exception:                              # noqa: BLE001
    db_path = r'C:\sender\sender.db'
store = Store(db_path)
aq = build_ai_quota(store, cfg)

itogi = []
for z in pisma:
    itog = {'nomer': z['nomer'], 'rid': z['rid'], 'email': z['email'],
            'inn': z.get('inn'), 'subject': z['subject'],
            'slov': len(z['body'].split())}
    if REZHIM != 'boy':
        itog['deystvie'] = 'холостой прогон, ничего не записано'
        itogi.append(itog)
        continue
    try:
        mid, _step, why = aq._ensure_message(KAMPANIYA, z['rid'])
        itog['message_id'] = mid
        if mid is None:
            itog['otkaz'] = f'очередь не завела message: {why}'
        else:
            rid_review, novyy = store.confirm_submit(
                email=z['email'], subject=z['subject'], body=z['body'],
                inn=z.get('inn'), campaign_id=KAMPANIYA, recipient_id=z['rid'],
                message_id=mid, status='pending')
            itog['review_id'] = rid_review
            itog['novaya_zapis'] = bool(novyy)
    except Exception as e:                     # noqa: BLE001
        itog['oshibka'] = f'{type(e).__name__}: {e}'[:300]
    itogi.append(itog)

if REZHIM == 'boy':
    try:
        with open(ZHURNAL, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'kampaniya': KAMPANIYA, 'itogi': itogi},
                               ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:                     # noqa: BLE001
        itogi.append({'zhurnal_oshibka': str(e)[:200]})

import sqlite3                                 # noqa: E402
s = sqlite3.connect(db_path)
v_ocheredi = s.execute(
    'select count(*) from confirm_reviews where campaign_id=? and status="pending"',
    (KAMPANIYA,)).fetchone()[0]

print(json.dumps({'rezhim': REZHIM, 'pisem': len(pisma),
                  'postavleno': sum(1 for i in itogi if i.get('review_id')),
                  'otkazov': sum(1 for i in itogi if i.get('otkaz') or i.get('oshibka')),
                  'pending_v_kampanii': v_ocheredi, 'itogi': itogi},
                 ensure_ascii=False, indent=1))
