# -*- coding: utf-8 -*-
"""Убрать ложные новости из живой очереди рассылки. ЗАПИСЬ в sender.db, с откатом.

Что делаю и почему именно так.

Ложная тут — ПАРА «новость → компания», а не компания. Поэтому я не заношу предприятия в
suppression: это закрыло бы им дорогу и в другие кампании, а владелец просил убрать новости.
Вместо этого:

  1. `recipients.extra_json.news_object` — текст новости, из которого рендерится письмо, —
     переношу в `news_object_snyato` и ставлю причину. Не удаляю: правило владельца
     «разделять, а не отсеивать», данные заново не добываются.
  2. Письма этих получателей в кампании 1 со статусом `pending_review` перевожу в `skipped` —
     тот же статус, которым система уже пользуется. Из очереди подтверждения они уходят.

Прежнее состояние целиком выгружается на дроп файлом `OTKAT-ochered-mismatchi.json` ДО правки,
чтобы откат был механическим, а не по памяти.
"""
import base64
import json
import sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R  # noqa: E402

INN = json.load(open('/home/user/work/mismatch-inn.json'))
PRICHINA = ('ложная привязка новости: подтверждённый мисматч, аудит 3-й сессии 02.08.2026 '
            '(тёзка / родитель-дочка / бывшее предприятие / дайджест)')

SCRIPT = '''# -*- coding: utf-8 -*-
import json, os, sqlite3, urllib.request
INN = %s
PRICHINA = %s
cx = sqlite3.connect('C:/sender/sender.db', timeout=60); cx.row_factory = sqlite3.Row
q = ','.join('?' * len(INN))
poluch = [dict(r) for r in cx.execute(
    'select id,inn,email,segment,source,extra_json from recipients '
    'where inn in (%%s) and segment=?' %% q, INN + ['новостные'])]
ids = [p['id'] for p in poluch]
qi = ','.join('?' * len(ids))
pisma = [dict(r) for r in cx.execute(
    'select id,campaign_id,recipient_id,status,scheduled_at,sent_at from messages '
    'where recipient_id in (%%s)' %% qi, ids)]
otkat = {'poluchateli': poluch, 'pisma': pisma}
U = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
T = os.environ.get('DROP_TOKEN', '')
b = json.dumps(otkat, ensure_ascii=False, default=str).encode('utf-8')
try:
    urllib.request.urlopen(urllib.request.Request(
        U + '/OTKAT-ochered-mismatchi.json', data=b, method='PUT',
        headers={'X-Drop-Token': T}), timeout=180).read()
    vygr = 'ok %%d байт' %% len(b)
except Exception as e:
    vygr = 'СБОЙ: %%s' %% e
if not vygr.startswith('ok'):
    print(json.dumps({'ostanovlen': 'откат не выгружен, правку не делаю', 'prichina': vygr},
                     ensure_ascii=False)); raise SystemExit(0)

snyato_novostey = 0
for p in poluch:
    try: ej = json.loads(p['extra_json'] or '{}')
    except Exception: ej = {}
    if ej.get('news_object'):
        ej['news_object_snyato'] = ej.pop('news_object')
        snyato_novostey += 1
    ej['snyato_prichina'] = PRICHINA
    cx.execute('update recipients set extra_json=?, updated_at=datetime("now") where id=?',
               (json.dumps(ej, ensure_ascii=False), p['id']))
cur = cx.execute('update messages set status="skipped", last_error=?, updated_at=datetime("now") '
                 'where recipient_id in (%%s) and status="pending_review"' %% qi,
                 [PRICHINA] + ids)
snyato_pisem = cur.rowcount
cx.commit()

proverka = {r[0]: r[1] for r in cx.execute(
    'select status, count(*) from messages where recipient_id in (%%s) group by 1' %% qi, ids)}
ostalos = cx.execute('select count(*) from recipients r join messages m on m.recipient_id=r.id '
                     'where r.inn in (%%s) and m.status in ("pending_review","scheduled")' %% q,
                     INN).fetchone()[0]
print(json.dumps({'otkat_vygruzhen': vygr, 'poluchateley_tronuto': len(poluch),
                  'novostey_snyato': snyato_novostey, 'pisem_v_skipped': snyato_pisem,
                  'statusy_posle': proverka, 'ostalos_v_ocheredi_po_etim_inn': ostalos},
                 ensure_ascii=False))
''' % (json.dumps(INN), json.dumps(PRICHINA))

dest = r'C:\sender\ochered_chistka_3s.py'
R.submit('enrich_contacts', {'op': 'panel_file_put',
         'files': [{'dest': dest, 'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'timeout': 600}, timeout=900)
open('/home/user/work/ochered-chistka.json', 'w', encoding='utf-8').write(
    json.dumps(r, ensure_ascii=False, indent=1))
d = r.get('data') or {}
print('rc', d.get('rc'))
print((d.get('stdout_tail') or d.get('stderr_tail') or '')[:2500])
