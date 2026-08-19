# -*- coding: utf-8 -*-
r"""Снять из очереди письма на мёртвых и «неясных» адресах (решение владельца 19.08).

Мёртвые — «нет ящика» и «нет MX»: сервер прямо отказал. «Неясно» — проба не
получила внятного ответа (серый список, обрыв связи); адрес может быть живым,
поэтому в стоп-лист их НЕ отправляем и компанию не хороним: снимается только
письмо, адрес остаётся в базе и вернётся в работу, когда проба его подтвердит.

Берём оба состояния очереди: подтверждённые (ждут автоотправки) и ждущие
решения оператора.

    python skip_riskovyh.py            посчитать
    python skip_riskovyh.py --primenit снять
"""
import json
import sqlite3
import sys
import time

БД = r'C:\sender\sender.db'
СНИМАЕМ = {'нет ящика': 'проба: ящика не существует',
           'нет MX': 'проба: у домена нет почтового сервера',
           'неясно': 'проба не подтвердила адрес (серый список/обрыв связи)'}
ПОДПИСЬ = 'проба адресов 19.08 (команда владельца)'


def разбор(применять=False):
    s = sqlite3.connect(БД, timeout=90)
    s.row_factory = sqlite3.Row
    верд = {str(r[0]).lower(): r[1] for r in s.execute(
        'select email, verdict from addr_probe')}
    цели = []
    for r in s.execute("select id, lower(coalesce(email,'')) em, status, "
                       "coalesce(inn,'') inn, coalesce(subject,'') тема "
                       "from confirm_reviews where status in ('approved','pending')"):
        в = верд.get(r['em'])
        if в in СНИМАЕМ:
            цели.append((r['id'], r['em'], r['status'], в, r['inn'], r['тема']))
    итог = {'к_снятию': len(цели), 'по_вердиктам': {}, 'по_состоянию': {}}
    for _i, _e, ст, в, _inn, _t in цели:
        итог['по_вердиктам'][в] = итог['по_вердиктам'].get(в, 0) + 1
        итог['по_состоянию'][ст] = итог['по_состоянию'].get(ст, 0) + 1
    итог['примеры'] = [{'адрес': e, 'состояние': ст, 'вердикт': в, 'инн': inn,
                        'тема': t[:45]} for _i, e, ст, в, inn, t in цели[:6]]
    if применять and цели:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        with s:
            for rid, _em, _ст, в, _inn, _t in цели:
                s.execute("update confirm_reviews set status='skipped', reason=?, "
                          'decided_by=?, decided_at=?, updated_at=? where id=?',
                          (СНИМАЕМ[в], ПОДПИСЬ, ts, ts, rid))
        итог['снято'] = len(цели)
        итог['осталось_в_очереди'] = dict(s.execute(
            "select status, count(*) from confirm_reviews "
            "where status in ('approved','pending') group by 1").fetchall())
    s.close()
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    и = разбор('--primenit' in sys.argv)
    прим = и.pop('примеры', [])
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
