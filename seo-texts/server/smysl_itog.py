# -*- coding: utf-8 -*-
r"""Свести замер смысла к числам по всей базе паспортов.

Судья спрашивается ТОЛЬКО там, где нет жёсткой улики (ИНН/ОГРН на странице), —
иначе это трата денег на очевидное. Поэтому доля «чужих» считается от той части,
где привязка не доказана, а на всю базу переносится через размер этой части.

    python smysl_itog.py            числа
    python smysl_itog.py --chuzhie  список «чужих» с причинами (для глаз)
"""
import json
import os
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import sverka_smysla as SS         # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def числа():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    всего = c.execute("select count(*) from site_facts where coalesce(facts_json,'')<>'' "
                      'and coalesce(format,0)>=2').fetchone()[0]
    в_карантине = c.execute("select count(*) from site_facts "
                            "where coalesce(otkloneno_json,'')<>''").fetchone()[0]
    c.close()
    ответы = []
    if os.path.exists(SS.ОТВЕТЫ):
        with open(SS.ОТВЕТЫ, encoding='utf-8') as f:
            for s in f:
                try:
                    ответы.append(json.loads(s))
                except Exception:  # noqa: BLE001
                    pass
    судимых_всего = len(SS.задачи()) + len(ответы)      # оставшиеся плюс уже отсуженные
    годных = [о for о in ответы if о.get('verdikt') in ('свой', 'расходится', 'чужой')]
    чужих = sum(1 for о in годных if о['verdikt'] == 'чужой')
    доля = чужих / len(годных) if годных else 0
    return {'паспортов_нового_формата': всего,
            'в_карантине_уже': в_карантине,
            'без_жёсткой_улики_всего': судимых_всего,
            'отсужено': len(годных),
            'из_них_чужой': чужих,
            'доля_чужих_в_этой_части': round(доля, 3),
            'оценка_чужих_по_всей_базе': int(round(доля * судимых_всего)),
            'по_вердиктам': {в: sum(1 for о in ответы if о.get('verdikt') == в)
                             for в in ('свой', 'расходится', 'чужой', 'сбой')}}


def чужие(предел=25):
    из = []
    if not os.path.exists(SS.ОТВЕТЫ):
        return из
    with open(SS.ОТВЕТЫ, encoding='utf-8') as f:
        for s in f:
            try:
                о = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if о.get('verdikt') == 'чужой':
                из.append({'инн': о['inn'], 'имя': о['name'][:45], 'сайт': о['site'],
                           'улики': о.get('ulики', ''), 'уверенность': о.get('uverennost', ''),
                           'оквэд': о.get('okved', '')[:45],
                           'на_сайте': о.get('produkciya', '')[:70],
                           'причина': (о.get('prichina') or '')[:100]})
    return из[:предел]


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if '--chuzhie' in sys.argv:
        print(json.dumps(чужие(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(числа(), ensure_ascii=False, indent=1))
