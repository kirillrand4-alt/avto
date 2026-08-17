# -*- coding: utf-8 -*-
"""Письмо «Заводским сетям»: чьё оно, что в карточке и откуда синяя фраза.

Владелец показал письмо с выделенной фразой «обслуживание оборудования для
сжатого воздуха». Смотрим: ИНН, карточку (не конкурент ли — сервис сжатого
воздуха!), паспорт сайта и как письмо лежит в очереди (флаги, разметка).
"""
import json
import re
import sqlite3
import sys

SENDER = r'C:\sender\sender.db'
ENRICH = r'C:\sender\enrich.db'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    s.row_factory = sqlite3.Row
    итог = {}
    кол = [r[1] for r in s.execute('pragma table_info(confirm_reviews)')]
    текстовые = [k for k in кол if any(x in k for x in
                 ('subject', 'body', 'text', 'html', 'json'))]
    условие = ' or '.join("%s like '%%Заводских сетях%%'" % k
                          for k in текстовые)
    ряд = None
    for r in s.execute('select * from confirm_reviews where %s '
                       'order by id desc limit 3' % условие):
        ряд = dict(r)
        break
    if not ряд:
        кол2 = [r[1] for r in s.execute('pragma table_info(ai_letter_log)')]
        т2 = [k for k in кол2 if any(x in k for x in ('json', 'body', 'text'))]
        у2 = ' or '.join("%s like '%%Заводск%%'" % k for k in т2)
        for r in s.execute('select * from ai_letter_log where %s '
                           'order by id desc limit 1' % у2):
            ряд = dict(r)
            break
    s.close()
    if not ряд:
        print(json.dumps({'беда': 'письмо не нашлось ни в очереди, ни в логе'},
                         ensure_ascii=False))
        return 0
    итог['таблица_поля'] = sorted(ряд.keys())
    for k in ('id', 'inn', 'recipient_id', 'campaign_id', 'status', 'kind',
              'flags_json', 'checks_json', 'subject'):
        if k in ряд:
            итог[k] = ряд[k]
    # тело: ищем, ЧЕМ выделена фраза (ссылка? подчёркивание? span?)
    тело = ''
    for k in ('body_html', 'body', 'letter_json', 'html'):
        if ряд.get(k):
            тело = str(ряд[k])
            break
    m = re.search(r'.{160}обслуживани[^<]{0,60}', тело)
    итог['кусок_вокруг_фразы'] = m.group(0) if m else тело[:300]
    инн = ''.join(c for c in str(ряд.get('inn') or '') if c.isdigit())
    итог['инн'] = инн
    if инн:
        e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
        e.row_factory = sqlite3.Row
        k = e.execute('select name, is_competitor, activity, okved, site, '
                      'cand_site, division from companies where inn=?',
                      (инн,)).fetchone()
        if k:
            итог['карточка'] = {kk: k[kk] for kk in k.keys()}
        f = e.execute('select facts_json from site_facts where inn=?',
                      (инн,)).fetchone()
        if f and f['facts_json']:
            d = json.loads(f['facts_json'])
            итог['паспорт'] = {kk: d[kk] for kk in
                               ('продукция', 'оборудование_линии', 'энергохозяйство')
                               if d.get(kk)}
        e.close()
    print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:5300])
    return 0


if __name__ == '__main__':
    sys.exit(main())
