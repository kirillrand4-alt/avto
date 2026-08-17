# -*- coding: utf-8 -*-
r"""Пересверка партии-935 после чистки мульти-ИНН доменов.

Партия набиралась по признаку «чистая почта С САЙТА + паспорт с продукцией».
Чистка снимает чужие сайты и карантинит их паспорта — у части компаний партии
основание исчезает: их почта снята с ЧУЖОГО сайта, паспорт описывает чужой
завод. Таких выводим из группы (убираем «Партия 935» из extra_json.gruppy),
чтобы кампании 10/11 не сгенерировали письмо по чужим фактам.

    python _935_peresverka.py            посчитать
    python _935_peresverka.py --primenit вывести из группы
"""
import json
import sqlite3
import sys

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'
ГРУППА = 'Партия 935'

САЙТОВЫЕ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТЫЕ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
          "and coalesce(e.pometka,'') not like '%скрыт%' "
          "and coalesce(e.pometka,'') not like '%не использовать%'")


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    применять = '--primenit' in sys.argv
    e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    отбор = {str(r[0]) for r in e.execute(
        "select k.inn from companies k "
        "where exists (select 1 from emails x where x.inn=k.inn and %s and %s) "
        "and exists (select 1 from site_facts f where f.inn=k.inn "
        " and coalesce(f.format,0)>=2 and f.facts_json like '%%\"продукция\": [\"%%')"
        % (САЙТОВЫЕ.replace('e.', 'x.'), ЧИСТЫЕ.replace('e.', 'x.')))}
    чужие_вердиктом = {str(r[0]) for r in e.execute(
        "select inn from prigovor_domenov where verdikt='чужой'")} \
        if e.execute("select 1 from sqlite_master where name='prigovor_domenov'"
                     ).fetchone() else set()
    e.close()

    s = sqlite3.connect(SENDER, timeout=90)
    s.row_factory = sqlite3.Row
    выводим, остаются = [], 0
    for r in s.execute("select id, coalesce(inn,'') inn, email, "
                       "coalesce(extra_json,'') ex from recipients "
                       "where extra_json like '%%%s%%'" % ГРУППА):
        инн = ''.join(c for c in r['inn'] if c.isdigit())
        if инн in отбор and инн not in чужие_вердиктом:
            остаются += 1
            continue
        причина = ('сайт признан чужим' if инн in чужие_вердиктом
                   else 'основание исчезло после чистки')
        выводим.append((r['id'], инн, r['email'], r['ex'], причина))
    итог = {'в_группе': остаются + len(выводим), 'остаются': остаются,
            'выводим': len(выводим),
            'из_них_чужой_вердикт': sum(1 for x in выводим if x[4].startswith('сайт')),
            'примеры': [{'инн': и, 'ящик': п, 'почему': ч}
                        for _, и, п, _, ч in выводим[:8]]}
    if применять and выводим:
        import time
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        with s:
            for rid, _и, _п, ex, _ч in выводим:
                try:
                    d = json.loads(ex) if ex.strip() else {}
                except Exception:  # noqa: BLE001
                    d = {}
                гр = [g for g in (d.get('gruppy') or []) if g != ГРУППА]
                d['gruppy'] = гр
                d.setdefault('gruppy_ubrano', []).append(
                    {'gruppa': ГРУППА, 'ts': ts, 'prichina': _ч})
                s.execute('update recipients set extra_json=?, updated_at=? '
                          'where id=?', (json.dumps(d, ensure_ascii=False), ts, rid))
        итог['выведено'] = len(выводим)
        # письма этих компаний, ждущие подтверждения в кампаниях партии
        итог['их_писем_в_очереди'] = s.execute(
            "select count(*) from confirm_reviews where status='pending' "
            'and inn in (%s)' % ','.join('?' * len(выводим)),
            [x[1] for x in выводим]).fetchone()[0]
    s.close()
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
