# -*- coding: utf-8 -*-
"""Штатный импорт догруза + сверка поля в поле и проверка на дубли по ИНН."""
import csv
import io
import json
import random
import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
CSV_PATH = r'C:\sender\_tmp\partiya-935-dogruz.csv'
p = subprocess.run([sys.executable, '-m', 'sender', '--config',
                    r'C:\sender\sender.yaml', 'import', CSV_PATH],
                   cwd=r'C:\sender', capture_output=True, text=True, timeout=1200)
итог = {'импорт_rc': p.returncode, 'импорт': (p.stdout or '')[-300:],
        'ошибки': (p.stderr or '')[-300:]}
s = sqlite3.connect(r'C:\sender\sender.db', timeout=90)
s.row_factory = sqlite3.Row
# импортированные строки надо ещё подключить к группе — source им проставлен,
# но выпадашка панели читает extra_json.gruppy
import time
ts = time.strftime('%Y-%m-%dT%H:%M:%S')
доб = 0
with s:
    for r in s.execute("select id, coalesce(extra_json,'') ex from recipients "
                       "where source='партия-935'"):
        try:
            d = json.loads(r['ex']) if (r['ex'] or '').strip() else {}
            if not isinstance(d, dict):
                d = {}
        except Exception:  # noqa: BLE001
            d = {}
        гр = [g for g in (d.get('gruppy') or []) if str(g).strip()]
        if 'Партия 935' in гр:
            continue
        d['gruppy'] = гр + ['Партия 935']
        s.execute('update recipients set extra_json=?, updated_at=? where id=?',
                  (json.dumps(d, ensure_ascii=False), ts, r['id']))
        доб += 1
итог['догружено_в_группу_тегом'] = доб
# итоговый состав группы
в_группе = [dict(r) for r in s.execute(
    "select coalesce(inn,'') inn, lower(coalesce(email,'')) em from recipients "
    "where extra_json like '%Партия 935%'")]
итог['получателей_в_группе'] = len(в_группе)
итог['компаний_в_группе'] = len({r['inn'] for r in в_группе if r['inn']})
счёт = {}
for r in в_группе:
    if r['inn']:
        счёт[r['inn']] = счёт.get(r['inn'], 0) + 1
дубли = {k: v for k, v in счёт.items() if v > 1}
итог['компаний_с_двумя_и_более_адресами'] = len(дубли)
итог['всего_лишних_строк'] = sum(v - 1 for v in дубли.values())
# сверка CSV -> база
with io.open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
    строки = list(csv.DictReader(f, delimiter=';'))
random.seed(42)
расх = []
for р in random.sample(строки, min(8, len(строки))):
    rec = s.execute('select * from recipients where email=?',
                    (р['email'].lower(),)).fetchone()
    if not rec:
        расх.append({'email': р['email'], 'беда': 'нет в recipients'})
        continue
    for п in ('inn', 'company_name', 'okved', 'segment', 'region', 'source'):
        ож, ест = р.get(п) or '', str(rec[п] or '')
        if ож and ож != ест:
            расх.append({'email': р['email'], 'поле': п, 'csv': ож[:50],
                         'база': ест[:50]})
    for п in ('pxr', 'priority_total', 'priority_max'):
        ож = р.get(п) or ''
        if ож and (rec[п] is None or abs(float(ож) - float(rec[п])) > 0.01):
            расх.append({'email': р['email'], 'поле': п, 'csv': ож, 'база': rec[п]})
s.close()
итог['сверено'] = min(8, len(строки))
итог['расхождения'] = расх
print(json.dumps(итог, ensure_ascii=False, indent=1))
