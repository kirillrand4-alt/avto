# -*- coding: utf-8 -*-
r"""Мёртвые адреса — в стоп-лист по адресу, чтобы не всплыли в следующей заливке.

Вывод из группы решает задачу один раз: адрес просто теряет тег партии. Но
следующая заливка соберёт его заново — он остаётся лучшим адресом компании в
enrich.db, и правило отбора о вердиктах пробы ничего не знает. Стоп-лист же
проверяется на всех путях: и при отборе кандидатов, и перед самой отправкой.

Берём только прямой отказ сервера: «нет ящика» (такого пользователя нет) и
«нет MX» (у домена вовсе нет почтового сервера). Причина hard_bounce — она уже
используется в панели для того же смысла.

    python stop_myortvyh.py            посчитать
    python stop_myortvyh.py --primenit занести
"""
import json
import sqlite3
import sys
import time

БД = r'C:\sender\sender.db'
МЁРТВЫЕ = ('нет ящика', 'нет MX')


def разбор(применять=False, все=False):
    s = sqlite3.connect(БД, timeout=90)
    s.row_factory = sqlite3.Row
    уже = {str(r[0]).lower() for r in s.execute(
        "select value from suppression where scope='email'")}
    # По умолчанию — только выведенные из партии (владелец просил «эти 166»).
    # --vse заносит ВСЕХ, кого проба когда-либо похоронила: 5229 адресов, они
    # так же всплывут в следующей заливке, но это отдельное решение владельца.
    наши = set()
    if not все:
        for em, ex in s.execute("select lower(coalesce(email,'')), "
                                "coalesce(extra_json,'') from recipients "
                                "where extra_json like '%проверка VPS%'"):
            if em:
                наши.add(em)
    цели = []
    for r in s.execute("select lower(email) em, verdict, coalesce(answer,'') otv "
                       'from addr_probe where verdict in (?,?)', МЁРТВЫЕ):
        if not r['em'] or r['em'] in уже:
            continue
        if все or r['em'] in наши:
            цели.append((r['em'], r['verdict'], r['otv'][:120]))
    всего_мёртвых = s.execute(
        'select count(*) from addr_probe where verdict in (?,?)', МЁРТВЫЕ).fetchone()[0]
    итог = {'мёртвых_всего_в_базе_проб': всего_мёртвых,
            'к_занесению': len(цели), 'уже_в_стопе': len(уже),
            'по_вердиктам': {}}
    for _e, в, _o in цели:
        итог['по_вердиктам'][в] = итог['по_вердиктам'].get(в, 0) + 1
    итог['примеры'] = [{'адрес': e, 'вердикт': в, 'ответ': o[:70]}
                       for e, в, o in цели[:5]]
    if применять and цели:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        with s:
            for адрес, в, отв in цели:
                s.execute('insert into suppression(scope, value, reason, source, '
                          'created_at) values(?,?,?,?,?)',
                          ('email', адрес, 'hard_bounce',
                           'проба VPS 19.08: %s — %s' % (в, отв[:80]), ts))
        итог['занесено'] = len(цели)
    s.close()
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    и = разбор('--primenit' in sys.argv, '--vse' in sys.argv)
    прим = и.pop('примеры', [])
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
