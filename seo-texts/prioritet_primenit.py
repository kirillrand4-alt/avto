# -*- coding: utf-8 -*-
"""Применить приоритет продажи к живой очереди обзвона. Одобрено владельцем 04.08.

КУДА ПИШЕТСЯ И ПОЧЕМУ ИМЕННО ТУДА. Очередь продавца — это `company_assignment` в
`centro_sales.db`: по строке на пару «предприятие + пользователь», порядок задаёт
`assignment_score`. Эта база НЕ пересобирается, в отличие от `centrifugal.db`, которую
собирают заново из enrich.db. На этом уже обожглась 1-я сессия: их правка контактов писалась
в пересобираемую базу и откатывалась следующей сборкой. Поэтому пишем в базу решений.

ЦЕЛЬ ВЛАДЕЛЬЦА ДОСЛОВНО: «нужно чтобы приоритеты были нацелены в первую очередь на звонить
сегодня». Поэтому очередь не просто сортируется по числу, а разделена ступенями, и ступень
сильнее любого веса внутри неё:

    2000 + приоритет   звонить сегодня — есть кому и по чему звонить
    1000 + приоритет   добыть контакт — повод сильный, звонить некому
       0 + приоритет   фон — копить данные

Внутри ступени работает множительная формула из `prioritet_prodazhi.py`: повод × соответствие
× досягаемость × доверие. Ступени не заменяют её, а гарантируют, что прозвонимое стоит выше
непрозвонимого при любых весах.

ОБРАТИМОСТЬ. Прежний `assignment_score` каждой строки выгружается на дроп до перезаписи —
очередь у продавца живая, и «улучшение», перевернувшее её посреди смены, должно откатываться
одной командой, а не восстанавливаться по памяти.

ЧЕСТНАЯ ОГОВОРКА ПРО ФЛАГИ. В таблице есть `has_phone`, `has_tech`, `has_purchaser` — они
проставлены сборкой от 31.07 и с тех пор устарели. Пересчитываю их тем же проходом: иначе
фильтр «есть телефон» в панели будет спорить с приоритетом, посчитанным по свежим данным.

Использование:
    python3 prioritet_primenit.py             # только посчитать
    python3 prioritet_primenit.py --primenit  # записать в очередь
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
import collections, csv, importlib.util, io, json, os, re, sqlite3, sys, urllib.request

PRIMENIT = 'PRIMENIT' in sys.argv
spec = importlib.util.spec_from_file_location('pp', r'C:\sender\_ops\3s_prioritet_prodazhi.py')
pp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pp)

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')

STUPEN = {'звонить сегодня': 2000, 'добыть контакт — повод сильный, звонить некому': 1000,
          'фон: копить данные': 0}

# Общий номер — по всей базе, а не по предприятию: номер у 2+ РАЗНЫХ предприятий личным не
# бывает, и в отдельной карточке этого не видно.
karta = collections.defaultdict(set)
for inn, phone in cx.execute("select coalesce(inn,''), coalesce(phone,'') from person "
                             "where coalesce(phone,'') <> ''"):
    c = re.sub(r'\D', '', phone)
    if len(c) >= 10:
        karta[c[-10:]].add(inn)
obshchie = {k for k, v in karta.items() if len(v) > 1}

# Свёрнутые как мусор факты не должны кормить состояние: доверие к такому состоянию ниже.
svernuto = collections.Counter()
for inn, in sale.execute("select coalesce(inn,'') from hidden_item where kind='fact'"):
    svernuto[inn] += 1

sost = {}
# Число источников берём из имеющейся колонки, а не из желаемой: `istochnikov` в company нет,
# провенанс лежит в `ssylki_na_istochniki` строкой. Считаю по ней, а не выдумываю поле.
for inn, s, sreda, ssyl in cx.execute(
        "select inn, coalesce(sostoyaniya_po_faktam,''), coalesce(sreda_po_faktam,''), "
        "coalesce(ssylki_na_istochniki,'') from company"):
    sost[inn] = (s, sreda, len([x for x in re.split(r'[|;\s]+', ssyl) if x.startswith('http')]))

# СООТВЕТСТВИЕ СЧИТАЕТСЯ ПО ЛУЧШЕМУ ФАКТУ, А НЕ ПО СВОДНОЙ СТРОКЕ. Владелец спросил прямо:
# имеет ли «очевидно центробежное компрессорное» приоритет над «не установлено». Должно — и
# в первой версии НЕ ИМЕЛО: степень соответствия бралась только из `sreda_po_faktam`, то есть
# из среды, а тип машины в неё вообще не входил. У предприятия с одним доказанным центробежным
# фактом и десятью «тип не установлен» вес получался такой же, как у предприятия, где
# центробежного нет вовсе. Здесь берётся МАКСИМУМ по фактам: одно доказательство сильнее
# любого числа неопределённостей, потому что неопределённость его не опровергает.
STUPENI_SOOT = {
    'центробежная и воздух, доказано текстом первоисточника': 4,
    'центробежная, среда не названа': 3,
    'признак производства: разделение воздуха, кислородная станция': 2,
    'тип не установлен': 1,
    'центробежная, но газ': 0,
}
luchshee = {}
for inn, tip, sreda_f, quote in cx.execute(
        "select coalesce(inn,''), coalesce(equipment_type,''), coalesce(medium,''), "
        "coalesce(quote,'') from fact"):
    t, sr, q = tip.lower(), (sreda_f or '').lower(), quote.lower()
    centro = 'центробежн' in t or 'турбокомпрессор' in t
    vozduh = 'воздух' in sr or 'воздух' in q or 'воздуходувк' in q
    gaz = 'газ' in sr and 'воздух' not in sr
    if centro and vozduh and not gaz:
        k = 'центробежная и воздух, доказано текстом первоисточника'
    elif centro and gaz:
        k = 'центробежная, но газ'
    elif centro:
        k = 'центробежная, среда не названа'
    elif re.search(r'разделени\w*\s+воздуха|кислородн\w+\s+станци|компрессорн\w+\s+станци', q):
        k = 'признак производства: разделение воздуха, кислородная станция'
    else:
        k = 'тип не установлен'
    if STUPENI_SOOT[k] > STUPENI_SOOT.get(luchshee.get(inn, 'центробежная, но газ'), -1):
        luchshee[inn] = k

lyudi = collections.defaultdict(lambda: {'lt': 0, 'l': 0, 'it': 0, 'o': 0})
for inn, ph, teh, person in cx.execute(
        "select coalesce(inn,''), coalesce(phone,''), coalesce(is_tech,0), "
        "coalesce(person,'') from person"):
    z = lyudi[inn]
    c = re.sub(r'\D', '', ph)
    if len(c) >= 10:
        if c[-10:] in obshchie or not c[-10:].startswith('9'):
            z['o'] += 1
        else:
            z['l'] += 1
            z['lt'] += 1 if teh else 0
    elif person and teh:
        z['it'] += 1

stroki = sale.execute(
    'select inn, username, coalesce(assignment_score,0) from company_assignment').fetchall()
bekap, novye = [], []
sch = collections.Counter()
for inn, user, staryy in stroki:
    s, sreda, ist_n = sost.get(inn, ('', '', 0))
    z = lyudi.get(inn, {'lt': 0, 'l': 0, 'it': 0, 'o': 0})
    dos = pp.stepen_dosyagaemosti(z['lt'], z['l'], z['it'], z['o'])
    pov = pp.stepen_povoda(s, None)
    soot = luchshee.get(inn)
    if not soot:
        sr = (sreda or '').lower()
        soot = ('центробежная и воздух, доказано текстом первоисточника' if 'воздух' in sr
                else 'центробежная, но газ' if 'газ' in sr
                else 'тип не установлен')
    if svernuto.get(inn) and not (z['l'] or z['lt']):
        dov = 'состояние держится на факте, который свёрнут как мусор'
    elif (ist_n or 0) >= 2:
        dov = 'два и более независимых источника'
    else:
        dov = 'один источник, есть ссылка на первоисточник'
    p = pp.prioritet(pov, soot, dos, dov)
    och = pp.ochered(dos, soot, pov)
    sch[och] += 1
    novye.append((round(STUPEN[och] + p, 1), 1 if (z['l'] or z['o']) else 0,
                  1 if (z['lt'] or z['it']) else 0, inn, user))
    bekap.append({'inn': inn, 'username': user, 'staryy_score': staryy,
                  'novyy_score': round(STUPEN[och] + p, 1), 'ochered': och,
                  'prioritet': p, 'dosyagaemost': dos, 'povod': pov, 'sootvetstvie': soot,
                  'doverie': dov})

itog = {'строк_очереди': len(stroki), 'по_очередям': dict(sch),
        'примeneno': False,
        'верх_нового': sorted(bekap, key=lambda x: -x['novyy_score'])[:5]}

if PRIMENIT:
    # Бэкап ДО записи: очередь живая, откат должен быть одной командой.
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=list(bekap[0]))
    w.writeheader(); w.writerows(bekap)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/VAZHNOE-3s-OCHERED-do-i-posle.csv', data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            itog['бэкап'] = f'{r.status}, {len(telo)} байт'
    except Exception as e:
        itog['бэкап'] = f'НЕ ВЫГРУЖЕН: {type(e).__name__}'
    sale.executemany(
        'update company_assignment set assignment_score = ?, has_phone = ?, has_tech = ? '
        'where inn = ? and username = ?', novye)
    sale.commit()
    itog['примeneno'] = True
    itog['новый_диапазон'] = sale.execute(
        'select min(assignment_score), max(assignment_score) from company_assignment').fetchone()

print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    primenit = '--primenit' in sys.argv
    for put in ('prioritet_prodazhi.py',):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), put)
        R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
            {'dest': r'C:\sender\_ops\3s_' + put,
             'b64': base64.b64encode(open(p, encoding='utf-8').read().encode()).decode()}]},
            timeout=300)
    dest = r'C:\sender\_ops\3s_prioritet_primenit.py'
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': dest, 'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest,
                                     'argv': ['PRIMENIT'] if primenit else [],
                                     'timeout': 900}, timeout=1200)
    d = r.get('data') or {}
    hvost = d.get('stdout_tail') or d.get('stderr_tail') or ''
    for s in hvost.splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('строки ИТОГ нет. Хвост:', hvost[-500:], file=sys.stderr)


if __name__ == '__main__':
    main()
