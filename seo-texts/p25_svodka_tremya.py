# -*- coding: utf-8 -*-
"""Сводка тремя колонками, как требует старт: личный / городской с именем / общий без имени.

ПОЧЕМУ ИМЕННО ТРИ КОЛОНКИ, А НЕ ОДНО ЧИСЛО «КОНТАКТОВ». Правило владельца: разделять, а не
отсеивать. Личный мобильный это главная мера; городской, к которому привязано имя, — путь к
человеку через коммутатор; общий номер без имени — вход на предприятие. Всё три хранится,
но смешивать их в один счётчик значит выдать второе и третье за первое.

Считается по обоим моим потокам сразу и по каждому отдельно, потому что каналы разные:
именной ищет ЧЕЛОВЕКА и приносит в основном должности, обратный ищет НОМЕР по уже известному
имени и приносит личные мобильные. Замер должен показывать, какой канал чем платит.
"""
import collections
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH  # noqa: E402

POTOKI = (('именной канал', r'C:\sender\_ops\p25-imena.jsonl'),
          ('обратный ход', r'C:\sender\_ops\p25-obratnyy.jsonl'))
BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
KRUG1 = re.compile(r'главн\w*\s+(?:инженер|механик|энергетик)|техническ\w+\s+директор', re.I)
KRUG2 = re.compile(r'начальник\w*\s+(?:производств|цеха)|главн\w+\s+технолог|АСУ|КИПиА', re.I)


def vid(nomer):
    c = re.sub(r'\D', '', nomer or '')
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    if len(c) == 11 and c.startswith('79'):
        return 'личный мобильный'
    if c.startswith('7800'):
        return 'общий: линия 8-800'
    return 'городской' if len(c) in (10, 11) else ''


def sayty():
    import csv
    d = {}
    for p in (r'C:\sender\_ops\3s_p25_sayty_2s.csv',
              r'C:\sender\_ops\3s_p25_sayty_iz_potokov.csv',
              r'C:\sender\_ops\3s_p25_sayty.csv'):
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            v = r.get('ves')
            if v and v.isdigit() and int(v) < 2:
                continue
            if r.get('inn') and r.get('sayt'):
                d.setdefault(r['inn'], r['sayt'])
    return d


def main():
    b = sqlite3.connect(BAZA, uri=True)
    imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
    st = sayty()
    itog = {}
    obshchee = collections.Counter()
    vse_inn, inn_s_lyudmi = set(), set()
    lyudi_vsego = 0
    zakryto = set()
    for imya, put in POTOKI:
        if not os.path.exists(put):
            itog[imya] = 'потока нет'
            continue
        s = collections.Counter()
        for ln in open(put, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            inn = z.get('inn')
            vse_inn.add(inn)
            if z.get('err'):
                s['сбоев'] += 1
                continue
            # Именной канал: человек с должностью, номер иногда в цитате.
            for l in z.get('lyudi') or []:
                if l.get('krug') == 'ИСТОЧНИК ЗАПРЕЩЁН':
                    s['запрещённый источник'] += 1
                    continue
                s['людей'] += 1
                inn_s_lyudmi.add(inn)
                m = TEL.search(l.get('citata') or '')
                if not m:
                    continue
                v = vid(m.group(0))
                imya_est = bool(l.get('fio'))
                kl = (v if v == 'личный мобильный'
                      else ('городской с именем' if imya_est else 'общий без имени'))
                s[kl] += 1
                obshchee[kl] += 1
            # Обратный ход: контакт с уже известным именем.
            for k in z.get('kontakty') or []:
                if k.get('tip') != 'телефон':
                    s['почт'] += 1
                    obshchee['почта'] += 1
                    continue
                v = vid(str(k.get('znachenie') or ''))
                if not v:
                    s['номер неразборчив'] += 1
                    continue
                kl = v if v == 'личный мобильный' else (
                    'городской с именем' if z.get('fio') else 'общий без имени')
                s[kl] += 1
                obshchee[kl] += 1
                if v == 'личный мобильный':
                    d = z.get('dolzhnost') or ''
                    est, _ = CH.stranica_podtverzhdaet(
                        k.get('ssylka', ''), st.get(inn, ''),
                        z.get('predpriyatie', '') or imena.get(inn, ''), '', strogo=True)
                    if (KRUG1.search(d) or KRUG2.search(d)) and est:
                        zakryto.add(inn)
        itog[imya] = dict(s.most_common())
        lyudi_vsego += s['людей']

    itog['ТРИ КОЛОНКИ, оба канала'] = {
        'личный мобильный': obshchee['личный мобильный'],
        'городской с именем': obshchee['городской с именем'],
        'общий без имени': obshchee['общий без имени'],
        'почта': obshchee['почта'],
    }
    itog['предприятий пройдено из 491'] = len(vse_inn)
    itog['предприятий, где нашёлся хоть один человек'] = len(inn_s_lyudmi)
    itog['людей на пройденное предприятие'] = round(
        lyudi_vsego / max(1, len(vse_inn)), 2)
    itog['ЗАКРЫТО (техкруг + личный мобильный + первоисточник)'] = len(zakryto)
    itog['сайтов известно'] = len(st)
    print('ИТОГ ' + json.dumps(itog, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
