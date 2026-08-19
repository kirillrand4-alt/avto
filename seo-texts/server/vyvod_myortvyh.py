# -*- coding: utf-8 -*-
r"""Вывести из партии адреса, признанные мёртвыми проверкой на VPS.

Мёртвый = вердикт работника «нет ящика» (сервер прямо сказал, что такого
пользователя нет) или «нет MX» (у домена вовсе нет почтового сервера). Прочие
вердикты не трогаем: «отказ пробе» и «неясно» — это про нашу пробу, а не про
адрес, а «принимает всё» ничего не отрицает.

Выводим МЯГКО: снимаем тег группы, саму строку получателя и её родную партию не
трогаем — она законно живёт в своей рассылке, и решение по ней принимать не нам.
След остаётся в extra_json.gruppy_ubrano с причиной и вердиктом.

    python vyvod_myortvyh.py "Партия 935"            посчитать
    python vyvod_myortvyh.py "Партия 935" --primenit вывести
"""
import json
import sqlite3
import sys
import time

БД = r'C:\sender\sender.db'
МЁРТВЫЕ = ('нет ящика', 'нет MX')


def разбор(группа, применять=False):
    s = sqlite3.connect(БД, timeout=90)
    s.row_factory = sqlite3.Row
    верд = {str(r[0]).lower(): (r[1], r[2], r[3]) for r in s.execute(
        "select email, verdict, coalesce(code,''), coalesce(answer,'') from addr_probe")}
    цели, примеры = [], []
    осталось = 0
    for r in s.execute("select id, coalesce(inn,'') inn, lower(coalesce(email,'')) em, "
                       "coalesce(company_name,'') nm, coalesce(extra_json,'') ex "
                       'from recipients where extra_json like ?',
                       ('%' + группа + '%',)):
        try:
            d = json.loads(r['ex']) if r['ex'].strip() else {}
        except Exception:  # noqa: BLE001
            continue
        if группа not in [str(g) for g in (d.get('gruppy') or [])]:
            continue
        в = верд.get(r['em'])
        if not в or в[0] not in МЁРТВЫЕ:
            осталось += 1
            continue
        цели.append((r['id'], r['em'], d, в[0]))
        if len(примеры) < 6:
            примеры.append({'инн': r['inn'], 'имя': r['nm'][:32], 'адрес': r['em'],
                            'вердикт': в[0], 'ответ': str(в[2])[:60]})
    итог = {'группа': группа, 'мёртвых': len(цели), 'останется': осталось,
            'по_вердиктам': {}, 'примеры': примеры}
    for _i, _em, _d, в in цели:
        итог['по_вердиктам'][в] = итог['по_вердиктам'].get(в, 0) + 1
    if применять and цели:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        with s:
            for rid, _em, d, в in цели:
                d['gruppy'] = [g for g in (d.get('gruppy') or []) if g != группа]
                d.setdefault('gruppy_ubrano', []).append(
                    {'gruppa': группа, 'ts': ts,
                     'prichina': 'проверка VPS: %s' % в})
                s.execute('update recipients set extra_json=?, updated_at=? '
                          'where id=?', (json.dumps(d, ensure_ascii=False), ts, rid))
        итог['выведено'] = len(цели)
        # их письма в очереди подтверждения: снимать их — отдельное решение,
        # но молчать о них нельзя, иначе оператор наткнётся на них руками
        адреса = [em for _i, em, _d, _в in цели]
        итог['их_писем_в_очереди'] = s.execute(
            "select count(*) from confirm_reviews where status='pending' "
            "and lower(coalesce(email,'')) in (%s)" % ','.join('?' * len(адреса)),
            адреса).fetchone()[0]
    s.close()
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    доводы = [a for a in sys.argv[1:] if not a.startswith('--')]
    группа = доводы[0] if доводы else 'Партия 935'
    и = разбор(группа, '--primenit' in sys.argv)
    прим = и.pop('примеры', [])
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
