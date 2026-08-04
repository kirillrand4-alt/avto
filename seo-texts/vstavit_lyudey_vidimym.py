# -*- coding: utf-8 -*-
"""Вставить в панель людей, которых у меня есть, а у продавца нет — по ВИДИМЫМ предприятиям.

ПОЧЕМУ ЭТО ОТДЕЛЬНО ОТ ДОЛИВКИ НОМЕРОВ. Доливка чинит клетку у человека, который на карточке
уже есть. Здесь человека НЕТ ВОВСЕ: продавец открывает карточку и не знает, что у нас есть
имя, должность и номер. Это не «данные с ошибкой», это непролитые данные — прямо пункт 2
задания владельца.

ЗАМЕР ПО ВИДИМЫМ (707 предприятий из 1 615): **96 человек на 43 предприятиях**, из них
85 с телефоном (3 мобильных). Немного, и это честное «немного»: основная масса источника уже
в панели. Но каждый из 85 — это готовый вход, которого продавец сегодня не видит.

ЧТО НЕ ПЕРЕНОСИТСЯ И ПОЧЕМУ
  * без фамилии — по имени-отчеству человека не спросить у секретаря;
  * если фамилия у этого ИНН в панели уже есть — не вставляем: это либо тот же человек в
    другом написании, либо однофамилец, и решать это вставкой нельзя (правило 1-й сессии:
    две записи с одной фамилией у одного ИНН не сшивать, а помечать);
  * номер прогоняется через отрезание добавочного и через общий заслон — вид пишется явно,
    чтобы линию приёмной никто не посчитал личной.

Запуск:
    python3 vstavit_lyudey_vidimym.py             # посчитать
    python3 vstavit_lyudey_vidimym.py --primenit  # вставить
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, csv, io, json, os, re, sqlite3, sys, urllib.request
sys.path.insert(0, r'C:\sender\_ops')
import _3s_nomer_dobavochnyy as D
import _3s_nomer_obshchiy as O

PRIMENIT = 'PRIMENIT' in sys.argv
sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sn = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
en = sqlite3.connect(r'C:\sender\enrich.db')

skryto = {v or i for i, v in sale.execute(
    "select coalesce(inn,''), coalesce(value,'') from hidden_item where kind='company'")}
vidno = {i for (i,) in sale.execute('select distinct inn from company_assignment')} - skryto

def fam(v):
    ch = re.split(r'[\s.,]+', (v or '').strip())
    return ch[0].lower().replace('ё', 'е') if ch and ch[0] else ''

OTCH = re.compile(r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)$', re.I)

est = {(i, fam(p)) for i, p in sn.execute(
    "select coalesce(inn,''), coalesce(person,'') from person")}
karta = O.postroit([(i, p, q) for i, p, q in sn.execute(
    "select coalesce(inn,''), coalesce(phone,''), coalesce(person,'') from person "
    "where coalesce(phone,'') <> ''")])

kol = [r[1] for r in sn.execute('pragma table_info(person)')]
novye, sch = [], collections.Counter()
for inn, per, post, ph, src, url in en.execute(
        "select coalesce(inn,''), coalesce(person,''), coalesce(post,''), coalesce(phone,''), "
        "coalesce(source,''), coalesce(source_url,'') from people"):
    if inn not in vidno or not fam(per):
        continue
    ch = per.split()
    if len(ch) == 2 and OTCH.search(ch[1]) and not OTCH.search(ch[0]):
        sch['имя-отчество без фамилии — не вставляю'] += 1
        continue
    if (inn, fam(per)) in est:
        continue
    est.add((inn, fam(per)))
    nomer, dob, ok, poch = D.raznyat(ph)
    vid = ''
    if ph.strip() and not ok:
        sch['номер неразборчив, человек вставлен без номера'] += 1
        nomer = ''
    elif nomer:
        vid = O.sudba(O.klyuch(nomer), karta, nomer)['vid_nomera']
    sch['вставить, номер: ' + (vid or 'нет')] += 1
    novye.append({'inn': inn, 'person': per.strip(), 'position': post[:120],
                  'phone': nomer,
                  'source': ('перенос из enrich.db (3-я сессия), пункт «вливаем данные»; '
                             'исходный источник: %s%s%s' % (
                                 src[:90], '; вид номера: ' + vid if vid else '',
                                 '; добавочный ' + dob if dob else ''))[:900],
                  'source_url': url[:300]})

itog = {'видно_продавцу': len(vidno), 'к_вставке': len(novye),
        'предприятий': len({n['inn'] for n in novye}), 'по_видам': dict(sch.most_common()),
        'с_телефоном': len([n for n in novye if n['phone']])}

if PRIMENIT and novye:
    polya = [k for k in ('inn', 'person', 'position', 'phone', 'source', 'source_url')
             if k in kol]
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=list(novye[0]), extrasaction='ignore')
    w.writeheader(); w.writerows(novye)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/VAZHNOE-3s-VSTAVLENO-LYUDEY-VIDIMYM.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog['бэкап'] = '%s, строк %d' % (r.status, len(novye))
    except Exception as e:
        itog['бэкап'] = 'НЕ выгружен: ' + type(e).__name__
    sn.executemany('insert into person (%s) values (%s)'
                   % (','.join(polya), ','.join('?' * len(polya))),
                   [tuple(n[k] for k in polya) for n in novye])
    sn.commit()
    itog['применено'] = True
    itog['людей_в_панели_стало'] = sn.execute('select count(*) from person').fetchone()[0]
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    tut = os.path.dirname(os.path.abspath(__file__))
    fajly = [{'dest': r'C:\sender\_ops\_3s_nomer_dobavochnyy.py',
              'b64': base64.b64encode(open(os.path.join(tut, 'nomer_dobavochnyy.py'),
                                           encoding='utf-8').read().encode()).decode()},
             {'dest': r'C:\sender\_ops\_3s_nomer_obshchiy.py',
              'b64': base64.b64encode(open(os.path.join(tut, 'nomer_obshchiy.py'),
                                           encoding='utf-8').read().encode()).decode()},
             {'dest': r'C:\sender\_ops\3s_vstavit.py',
              'b64': base64.b64encode(SCRIPT.encode()).decode()}]
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_vstavit.py',
                  'argv': ['PRIMENIT'] if '--primenit' in sys.argv else [], 'timeout': 900},
                 timeout=1200)
    d = r.get('data') or {}
    for s in (d.get('stdout_tail') or '').splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('пусто:', (d.get('stderr_tail') or '')[-900:], file=sys.stderr)


if __name__ == '__main__':
    main()
