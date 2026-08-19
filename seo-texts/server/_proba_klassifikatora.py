# -*- coding: utf-8 -*-
"""Прогнать НОВЫЙ классификатор по сохранённым ответам и сравнить со старым."""
import importlib.util
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')


def грузить(путь, имя):
    сп = importlib.util.spec_from_file_location(имя, путь)
    м = importlib.util.module_from_spec(сп)
    сп.loader.exec_module(м)
    return м


новый = грузить(r'C:\sender\_tmp\reply_classify.py', 'rc_new')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
строки = [dict(r) for r in s.execute(
    "select id, coalesce(company_name,'') nm, coalesce(reply_kind,'') было, "
    "coalesce(need,'') текст from leads where coalesce(need,'')<>'' order by id desc")]
s.close()
итог = {'проверено': len(строки), 'переходы': {}, 'стало': {}, 'примеры': []}
for r in строки:
    з = новый.classify_reply('', r['текст'])
    стало = з.kind
    итог['стало'][стало] = итог['стало'].get(стало, 0) + 1
    ключ = '%s -> %s' % (r['было'] or '(пусто)', стало)
    итог['переходы'][ключ] = итог['переходы'].get(ключ, 0) + 1
    if r['было'] != стало and len(итог['примеры']) < 10:
        итог['примеры'].append({'компания': r['nm'][:24], 'было': r['было'],
                                'стало': стало, 'по_чему': list(з.matched)[:3],
                                'текст': r['текст'][:80].replace('\n', ' ')})
итог['переходы'] = dict(sorted(итог['переходы'].items(), key=lambda kv: -kv[1]))
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4000])
