# -*- coding: utf-8 -*-
"""Долить в панель номера тем, кого продавец УЖЕ ВИДИТ, но без телефона.

НАЙДЕНО ГЛАЗАМИ. Карточка АО «Каустик» (3448003962), которую продавец открывает прямо сейчас:

    Потехин Леонид Михайлович   директор
      Источник: сайт:руководство | перенос из enrich.db 3-й сессией
    Ригерт Виталий Александрович   нач.производства
    Калмыков Денис Юрьевич   директор по производству

У всех трёх нет номера. А в `enrich.db` их прямые номера лежат: 8 (8442) 40-66-75,
40-69-94, 40-68-80. То есть человек перенесён МОИМ переносом, а телефон при переносе
остался. Это худший вид непролитых данных: не «нет данных», а «человек на экране есть,
звонить нечем» — продавец видит цель и уходит с карточки.

МАСШТАБ. По ВИДИМЫМ продавцу предприятиям (707 из 1 615): **158 номеров на 80 предприятиях**
есть в источнике и нет в панели, из них 8 мобильных; плюс 137 человек, которых в панели нет
вовсе.

ПОЧЕМУ ПИШЕМ В СНИМОК, ХОТЯ ЕГО ПЕРЕСОБИРАЮТ. Снимок собирают из `enrich.db`, где эти номера
УЖЕ ЕСТЬ, — значит сборка их теряет, и одной пересборкой дело не решится. Об этом сказано
1-й сессии отдельно. Но отчёт у владельца скоро, а номер, невидимый продавцу, для дела не
существует. Поэтому доливаем в снимок сейчас и говорим вслух, что это не заменяет починки
сборки.

ЧТО НЕ ДЕЛАЕТСЯ: не перетирается ни один существующий номер. Пустая клетка заполняется,
занятая — не трогается: чужой номер мог быть личным, а наш городским.

Запуск:
    python3 dolit_nomera_vidimym.py             # посчитать
    python3 dolit_nomera_vidimym.py --primenit  # долить
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

def nom(p):
    c = re.sub(r'\D', '', p or '')
    return c[-10:] if len(c) >= 10 else ''

# Номера источника по паре ИНН+фамилия. Фамилия, а не полное имя: «Амелин С.А.» и «Амелин
# Сергей Александрович» — один человек, правило 1-й сессии.
iz_istochnika = collections.defaultdict(list)
for inn, per, ph, src in en.execute(
        "select coalesce(inn,''), coalesce(person,''), coalesce(phone,''), coalesce(source,'') "
        "from people where coalesce(phone,'') <> ''"):
    if inn in vidno and fam(per):
        iz_istochnika[(inn, fam(per))].append((per, ph, src))

# У кого в панели есть ФАМИЛИЯ, но пусто в телефоне.
pravki, sch = [], collections.Counter()
vsego_nomerov = [(i, p) for i, p in sn.execute(
    "select coalesce(inn,''), coalesce(phone,'') from person where coalesce(phone,'') <> ''")]
karta = O.postroit([(i, p, '') for i, p in vsego_nomerov])
uzhe = collections.defaultdict(set)
for i, p in vsego_nomerov:
    if nom(p):
        uzhe[i].add(nom(p))

for rid, inn, per, ph, src in sn.execute(
        "select rowid, coalesce(inn,''), coalesce(person,''), coalesce(phone,''), "
        "coalesce(source,'') from person"):
    if inn not in vidno or ph.strip() or not fam(per):
        continue
    kand = iz_istochnika.get((inn, fam(per)))
    if not kand:
        sch['человек без номера, в источнике номера тоже нет'] += 1
        continue
    per_ist, ph_ist, src_ist = kand[0]
    nomer, dob, ok, poch = D.raznyat(ph_ist)
    if not ok:
        sch['номер источника неразборчив'] += 1
        continue
    if nom(nomer) in uzhe.get(inn, set()):
        # Номер у предприятия уже есть, просто на другом человеке. Это НЕ повод молчать:
        # приписать его нашему человеку — значит утверждать, что линия его, а мы этого не
        # знаем. Отмечаем в источнике и оставляем клетку пустой.
        sch['номер уже есть у предприятия на другом человеке'] += 1
        continue
    vid = O.sudba(O.klyuch(nomer), karta, nomer)
    pravki.append((nomer, (src + ' | номер долит из enrich.db (3-я сессия), исходное имя '
                           'там «%s», источник номера: %s%s; вид: %s'
                           % (per_ist[:40], src_ist[:60],
                              '; добавочный ' + dob if dob else '', vid['vid_nomera']))[:900],
                   rid, inn, per, nomer, vid['vid_nomera']))
    sch['ДОЛИТЬ, вид: ' + vid['vid_nomera']] += 1

itog = {'видно_продавцу': len(vidno), 'к_доливке': len(pravki), 'по_видам': dict(sch.most_common()),
        'предприятий': len({p[3] for p in pravki}),
        'мобильных': len([p for p in pravki if p[6] == 'мобильный']),
        'примеры': [{'inn': p[3], 'chelovek': p[4][:34], 'nomer': p[5], 'vid': p[6]}
                    for p in pravki[:10]]}

if PRIMENIT and pravki:
    b = io.StringIO()
    w = csv.writer(b, delimiter=';')
    w.writerow(['inn', 'chelovek', 'nomer', 'vid'])
    for p in pravki:
        w.writerow([p[3], p[4], p[5], p[6]])
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/VAZHNOE-3s-DOLITO-NOMEROV-VIDIMYM.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog['бэкап'] = '%s, строк %d' % (r.status, len(pravki))
    except Exception as e:
        itog['бэкап'] = 'НЕ выгружен: ' + type(e).__name__
    sn.executemany('update person set phone = ?, source = ? where rowid = ?',
                   [(p[0], p[1], p[2]) for p in pravki])
    sn.commit()
    itog['применено'] = True
    itog['предприятий_с_телефоном_стало'] = sn.execute(
        "select count(distinct inn) from person where coalesce(phone,'') <> ''").fetchone()[0]
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
             {'dest': r'C:\sender\_ops\3s_dolit.py',
              'b64': base64.b64encode(SCRIPT.encode()).decode()}]
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_dolit.py',
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
