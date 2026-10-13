# -*- coding: utf-8 -*-
"""READ-ONLY: брак писем Meyer по химии и зерну из журнала gen-rossiya-9000.

    meyer_brak_himiya_zerno.py svod
    meyer_brak_himiya_zerno.py spisok him|zer [с] [сколько] [символов_тела]
    meyer_brak_himiya_zerno.py telo him|zer N        (полное тело N-го брака)
"""
import json
import re
import sqlite3
import sys
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-rossiya-9000.jsonl"
СЕГ = {'him': 'Химия, удобрения', 'zer': 'Зерно, мука, элеваторы, семена'}

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сегмент = {}
for rid, seg in c.execute("SELECT id, segment FROM recipients"):
    сегмент[rid] = seg or ''

if len(sys.argv) > 2 and sys.argv[1] == 'hist':
    rid = int(sys.argv[2])
    with open(ЖУРНАЛ, encoding='utf-8') as f:
        for стр in f:
            if str(rid) not in стр:
                continue
            з = json.loads(стр)
            if з.get('recipient_id') != rid:
                continue
            print({k: (str(v)[:160]) for k, v in з.items()
                   if k not in ('тело_брака', 'inn', 'имя', 'направление')})
    sys.exit(0)
if len(sys.argv) > 2 and sys.argv[1] == 'rid':
    c.row_factory = sqlite3.Row
    r = c.execute('SELECT * FROM recipients WHERE id=?', (int(sys.argv[2]),)).fetchone()
    for k in r.keys():
        print('%s = %s' % (k, str(r[k])[:1800]))
    sys.exit(0)
записи = []
with open(ЖУРНАЛ, encoding='utf-8') as f:
    for стр in f:
        try:
            з = json.loads(стр)
        except Exception:
            continue
        if з.get('этап') != 'итог':
            continue
        з['_seg'] = сегмент.get(з.get('recipient_id'), '?')
        записи.append(з)

режим = sys.argv[1] if len(sys.argv) > 1 else 'svod'


def причина(з):
    б = з.get('брак') or []
    return б[0] if б else ''


if режим == 'svod':
    for ключ, seg in СЕГ.items():
        рр = [з for з in записи if з['_seg'] == seg]
        print('=== %s: итогов %d' % (seg, len(рр)))
        по_дню = Counter()
        for з in рр:
            по_дню[(з.get('день'), str(з.get('направление')),
                    'ок' if з.get('ок') else 'брак')] += 1
        for к, v in sorted(по_дню.items(), key=lambda x: str(x[0])):
            print('  ', к, v)
        пр = Counter()
        for з in рр:
            if not з.get('ок'):
                п = причина(з)
                пр[п.split(':')[0][:60]] += 1
        for к, v in пр.most_common(25):
            print('   [%d] %s' % (v, к))
    print('направления:', Counter(str(з.get('направление')) for з in записи))
    print('дни:', sorted(Counter(str(з.get('день')) for з in записи).items())[-8:])
    print('поля итога:', sorted(записи[-1].keys()) if записи else '-')
elif режим == 'reason':
    под = sys.argv[2]
    n = 0
    по_сег = Counter()
    for з in записи:
        for б in (з.get('брак') or []):
            if под in str(б):
                n += 1
                по_сег[з['_seg']] += 1
                print('%s rid=%s %s | %s' % (з.get('день'), з.get('recipient_id'),
                      з['_seg'][:18], str(б)[:230]))
    print('ВСЕГО', n, dict(по_сег))
    ок = Counter((з['_seg'], bool(з.get('ок'))) for з in записи)
    print('appr:', sum(1 for з in записи if 'очередь: approved' in str(з.get('брак')) and з['_seg'].startswith('Зерно')))
elif режим == 'kart':
    seg = СЕГ[sys.argv[2]]
    тек = sys.argv[3] if len(sys.argv) > 3 else ''
    рр = [з for з in записи if з['_seg'] == seg]
    видел = set()
    for з in рр:
        rid = з.get('recipient_id')
        if rid in видел:
            continue
        видел.add(rid)
        r = c.execute('SELECT extra_json FROM recipients WHERE id=?', (rid,)).fetchone()
        ex = json.loads(r[0] or '{}') if r and r[0] else {}
        sf = ex.get('site_facts') or {}
        if тек:
            j = json.dumps(ex, ensure_ascii=False)
            for k in re.finditer(тек, j):
                print('  rid=%s %s: ...%s...' % (rid, 'ок' if з.get('ок') else 'брак',
                      j[max(0, k.start() - 100):k.end() + 60]))
            continue
        print('rid=%s %s grad=%r otrasl=%r keys=%s' % (
            rid, 'ок' if з.get('ок') else 'брак', ex.get('meyer_gradaciya'),
            ex.get('otrasl'), ','.join(sorted(ex.keys()))[:160]))
        if isinstance(sf, dict):
            print('    сырьё=%s | прод=%s' % (str(sf.get('сырьё'))[:120],
                                           str(sf.get('продукция'))[:100]))
elif режим == 'frag':
    import re
    seg = СЕГ[sys.argv[2]]
    рр = [з for з in записи if з['_seg'] == seg and not з.get('ок')]
    for i, з in enumerate(рр):
        тело = (з.get('тело_брака') or '').replace('\n', ' ')
        for б in (з.get('брак') or []):
            б = str(б)
            if not (б.startswith('редактор') or 'лексика' in б or 'корпоратив' in б
                    or 'регламент' in б or 'линза' in б):
                continue
            м = re.findall(r'«([^«»]{8,})»?\s*$', б)
            фр = м[-1].strip() if м else ''
            print('#%d %s | %s' % (i, (з.get('имя') or '')[:25], б.split(':')[0][:90]))
            print('   правило: %s' % б[:200].split(': «')[0][-140:])
            if фр and тело:
                кл = фр[:25].strip()
                k = тело.find(кл)
                if k >= 0:
                    a = max(тело.rfind('.', 0, k - 1) + 1, k - 260)
                    b = тело.find('.', k + len(кл))
                    b = len(тело) if b < 0 else min(b + 1, k + 360)
                    print('   ПРЕДЛ: %s' % тело[a:b].strip())
                else:
                    print('   ФРАГ(не найден в теле): %s' % фр[:150])
            elif not тело:
                print('   (тела нет) фраг: %s' % фр[:150])
elif режим in ('spisok', 'telo'):
    seg = СЕГ[sys.argv[2]]
    рр = [з for з in записи if з['_seg'] == seg and not з.get('ок')]
    if режим == 'telo':
        з = рр[int(sys.argv[3])]
        print(json.dumps({k: v for k, v in з.items() if k != 'тело_брака'},
                         ensure_ascii=False)[:1500])
        print('ТЕМА:', з.get('тема_брака'))
        print(з.get('тело_брака'))
    else:
        с = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        ch = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        print('всего брака: %d' % len(рр))
        for i, з in enumerate(рр[с:с + n], с):
            print('#%d %s %s %s inn=%s rid=%s' % (
                i, з.get('день'), з.get('направление'), (з.get('имя') or '')[:30],
                з.get('inn'), з.get('recipient_id')))
            for б in (з.get('брак') or []):
                print('   - %s' % str(б)[:400])
            if ch:
                print('   ТЕЛО: %s' % (з.get('тело_брака') or '')[:ch].replace('\n', ' / '))
