# -*- coding: utf-8 -*-
r"""Импорт partiya-935-dobor.csv штатной командой и сверка «всё ли долетело».

Канонный путь из PANEL-DEPLOY.md: python -m sender --config C:\sender\sender.yaml
import <csv>. После импорта сверяем recipients с CSV поле в поле: сначала
счётчики заполненности, потом 8 случайных строк дословно.
"""
import csv
import io
import json
import random
import sqlite3
import subprocess
import sys

CSV_PATH = r'C:\sender\_tmp\partiya-935-dobor.csv'
SENDER = r'C:\sender\sender.db'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p = subprocess.run([sys.executable, '-m', 'sender', '--config',
                        r'C:\sender\sender.yaml', 'import', CSV_PATH],
                       cwd=r'C:\sender', capture_output=True, text=True,
                       timeout=1200)
    итог = {'импорт_rc': p.returncode,
            'импорт_вывод': (p.stdout or '')[-900:],
            'импорт_ошибки': (p.stderr or '')[-500:]}
    # что легло в базу
    s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    s.row_factory = sqlite3.Row
    итог['в_группе_стало'] = s.execute(
        "select count(*) from recipients where source='партия-935'").fetchone()[0]
    итог['заполнено_в_группе'] = dict(s.execute(
        "select 'inn', count(nullif(coalesce(inn,''),'')) from recipients where source='партия-935' "
        "union all select 'company_name', count(nullif(coalesce(company_name,''),'')) from recipients where source='партия-935' "
        "union all select 'okved', count(nullif(coalesce(okved,''),'')) from recipients where source='партия-935' "
        "union all select 'segment', count(nullif(coalesce(segment,''),'')) from recipients where source='партия-935' "
        "union all select 'region', count(nullif(coalesce(region,''),'')) from recipients where source='партия-935' "
        "union all select 'tz', count(nullif(coalesce(tz,''),'')) from recipients where source='партия-935' "
        "union all select 'contact_name', count(nullif(coalesce(contact_name,''),'')) from recipients where source='партия-935' "
        "union all select 'pxr', count(pxr) from recipients where source='партия-935' "
        "union all select 'priority_total', count(priority_total) from recipients where source='партия-935' "
        "union all select 'priority_max', count(priority_max) from recipients where source='партия-935'"
    ).fetchall())
    # дословная сверка случайных строк CSV -> recipients
    with io.open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        строки = list(csv.DictReader(f, delimiter=';'))
    random.seed(935)
    расхождения, проверено = [], 0
    for р in random.sample(строки, 8):
        проверено += 1
        rec = s.execute('select * from recipients where email=?',
                        (р['email'].lower(),)).fetchone()
        if not rec:
            расхождения.append({'email': р['email'], 'беда': 'нет в recipients'})
            continue
        for п in ('inn', 'company_name', 'okved', 'segment', 'region',
                  'contact_name'):
            ожид, есть = р.get(п) or '', str(rec[п] or '')
            if ожид and ожид != есть:
                расхождения.append({'email': р['email'], 'поле': п,
                                    'в_csv': ожид[:60], 'в_базе': есть[:60]})
        for п in ('pxr', 'priority_total', 'priority_max'):
            ожид = р.get(п) or ''
            if ожид and (rec[п] is None or
                         abs(float(ожид) - float(rec[п])) > 0.01):
                расхождения.append({'email': р['email'], 'поле': п,
                                    'в_csv': ожид, 'в_базе': rec[п]})
        if р['source'] != (rec['source'] or ''):
            расхождения.append({'email': р['email'], 'поле': 'source',
                                'в_csv': р['source'], 'в_базе': rec['source']})
    итог['сверено_строк'] = проверено
    итог['расхождения'] = расхождения
    s.close()
    print(json.dumps(итог, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
