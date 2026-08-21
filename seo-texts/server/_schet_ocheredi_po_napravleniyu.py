# -*- coding: utf-8 -*-
r"""Что теперь увидит оператор в очереди КЦ и в очереди Meyer.

К API без пароля не пустят, поэтому считаем тем же предикатом, что стоит в
app.confirm_queue: направление ПИСЬМА (panel.letter_division, иначе лексика),
а при неизвестном — метка компании; письмо без направления видно в обеих.
"""
import json
import sqlite3

МАРКЕРЫ = {
    'kc': ('компрессор', 'азот', 'кислород', ' мкс', 'пневмо', 'воздуходув'),
    'meyer': ('рентген', 'фотосепар', 'фото-сепар', 'инспекц', 'сортировк'),
}
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
таблицы = [r[0] for r in s.execute(
    "select name from sqlite_master where type='table'")]
ТАБ = next((t for t in таблицы if 'review' in t or 'confirm' in t), '')
if not ТАБ:
    raise SystemExit(json.dumps({'нет таблицы очереди': таблицы[:20]},
                                ensure_ascii=False))
ст = {'в_очереди': 0, 'письмо_kc': 0, 'письмо_meyer': 0,
      'по_метке_компании': 0, 'совсем_без_направления': 0}
видно = {'kc': 0, 'meyer': 0}
примеры_meyer = []
КОЛОНКИ = [x[1] for x in s.execute('PRAGMA table_info(%s)' % ТАБ)]
ПАНЕЛЬ = next((k for k in ('panel', 'panel_json', 'extra_json', 'meta_json')
               if k in КОЛОНКИ), '')
for r in s.execute("select * from %s where status='pending'" % ТАБ):
    ст['в_очереди'] += 1
    try:
        panel = json.loads((r[ПАНЕЛЬ] if ПАНЕЛЬ else '') or '{}') or {}
    except Exception:  # noqa: BLE001
        panel = {}
    d = str(panel.get('letter_division') or '').strip().lower()
    if d not in ('kc', 'meyer'):
        письмо = panel.get('letter') or {}
        текст = ' '.join([
            str(r['subject'] or ''), str(r['body'] or ''),
            str(письмо.get('subject') or '') if isinstance(письмо, dict) else '',
            str(письмо.get('body') or '') if isinstance(письмо, dict) else '',
        ]).lower()
        попало = {k for k, ms in МАРКЕРЫ.items() if any(m in текст for m in ms)}
        d = next(iter(попало)) if len(попало) == 1 else ''
        if d:
            ст['письмо_%s' % d] += 1
    else:
        ст['письмо_%s' % d] += 1
    if not d:
        d = str(((panel.get('company') or {}).get('division') or '')).lower()
        if d:
            ст['по_метке_компании'] += 1
        else:
            ст['совсем_без_направления'] += 1
    for напр in ('kc', 'meyer'):
        if (not d) or (напр in d):
            видно[напр] += 1
            if напр == 'meyer' and len(примеры_meyer) < 6:
                примеры_meyer.append({'id': r['id'],
                                      'тема': str(r['subject'] or '')[:60],
                                      'направление': d or '(неизвестно)'})
s.close()
print(json.dumps({'примеры_очереди_meyer': примеры_meyer},
                 ensure_ascii=False, indent=1))
print(json.dumps({'таблица': ТАБ, 'колонка_панели': ПАНЕЛЬ, 'счёт': ст, 'увидит_оператор': видно},
                 ensure_ascii=False, indent=1))
