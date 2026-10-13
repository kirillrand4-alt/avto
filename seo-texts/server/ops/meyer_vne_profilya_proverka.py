# -*- coding: utf-8 -*-
"""READ-ONLY: почему meyer-карточка получила строку «НЕ ТО НАПРАВЛЕНИЕ».

Для каждого rid: okved, activity из enrich.db, срабатывание
vne_profilya_meyer боевого ai_letter и какое слово/код его включило.

    meyer_vne_profilya_proverka.py RID [RID ...]
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as A  # noqa: E402

s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
табл = [r[0] for r in e.execute("SELECT name FROM sqlite_master WHERE type='table'")]
комп = next((т for т in табл if т in ('companies', 'company')), None)
кол = [r[1] for r in e.execute('PRAGMA table_info("%s")' % комп)] if комп else []
print('enrich таблица:', комп, [к for к in кол if к in ('inn', 'activity', 'okved', 'site_facts')])
if sys.argv[1:2] == ['seg']:
    from collections import Counter
    сч = Counter()
    прим = {}
    for инн, okved, seg in s.execute(
            "SELECT inn, okved, segment FROM recipients WHERE extra_json LIKE '%meyer%'"):
        q = e.execute('SELECT activity FROM "%s" WHERE inn=? LIMIT 1' % комп, (инн,)).fetchone()
        act = (q[0] if q else '') or ''
        if not A.vne_profilya_meyer(okved, act, None):
            continue
        м = A._NAPITKI_СЛОВА.search('%s %s' % (okved, act))
        ключ = (seg or '?')[:22], ('код ' + str(okved)[:5]) if A._NAPITKI_RE.match(str(okved or '')) \
            else ('слово ' + (м.group(0) if м else '?'))
        сч[ключ] += 1
        прим.setdefault(ключ, инн)
    for к, v in сч.most_common(30):
        print(v, к, прим[к])
    print('ВСЕГО ВНЕ:', sum(сч.values()))
    sys.exit(0)
for rid in sys.argv[1:]:
    r = s.execute('SELECT inn, okved, segment, company_name FROM recipients WHERE id=?',
                  (int(rid),)).fetchone()
    if not r:
        continue
    инн, okved, seg, имя = r
    act, sf = '', None
    if комп and 'inn' in кол:
        q = e.execute('SELECT * FROM "%s" WHERE inn=? LIMIT 1' % комп, (инн,)).fetchone()
        if q:
            d = dict(zip(кол, q))
            act = d.get('activity') or ''
            try:
                sf = json.loads(d.get('site_facts') or 'null')
            except Exception:
                sf = None
    вне = A.vne_profilya_meyer(okved, act, sf)
    код_нап = bool(A._NAPITKI_RE.match(str(okved or '')))
    м = A._NAPITKI_СЛОВА.search('%s %s' % (okved, act))
    print('rid=%s %s okved=%s seg=%s' % (rid, (имя or '')[:30], okved, (seg or '')[:20]))
    print('   activity: %s' % str(act)[:200])
    print('   ВНЕ: %s | код_напитков=%s слово=%r' % (
        'ДА' if вне else 'нет', код_нап, м.group(0) if м else None))
