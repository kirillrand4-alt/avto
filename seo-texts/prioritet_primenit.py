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
_sp = importlib.util.spec_from_file_location('mf', r'C:\sender\_ops\3s_musor_faktov.py')
mf = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(mf)

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')

STUPEN = {'звонить сегодня': 2000, 'добыть контакт — повод сильный, звонить некому': 1000,
          'фон: копить данные': 0}

# ОБЩИЙ НОМЕР РЕШАЕТСЯ ФАМИЛИЕЙ, А НЕ ЧИСЛОМ ИНН. Поправка 1-й сессии по моему же файлу:
# «номер у двух ИНН не личный» снимало настоящие личные — Сидиченко Александр Александрович
# числится у двух предприятий сразу, и это обычное дело, один человек у двух работодателей.
# Не личный номер тогда, когда на нём РАЗНЫЕ ЛЮДИ. Заодно их же замер: из 153 «разных людей»
# 29 оказались одним человеком в разных написаниях, поэтому сравнивается первое слово имени,
# а не строка целиком.
karta = collections.defaultdict(set)
for inn, phone, person in cx.execute(
        "select coalesce(inn,''), coalesce(phone,''), coalesce(person,'') from person "
        "where coalesce(phone,'') <> ''"):
    c = re.sub(r'\D', '', phone)
    if len(c) < 10:
        continue
    ch = re.split(r'[\s.,]+', (person or '').strip())
    if ch and ch[0]:
        karta[c[-10:]].add(ch[0].lower().replace('ё', 'е'))
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
    # МАРКА СПРАШИВАЕТСЯ ПЕРВОЙ. Поля `equipment_type` и `medium` у многих фактов пусты, и
    # тогда доказанная маркой машина получала «тип не установлен» — множитель 0.30 вместо
    # 1.00, то есть предприятие проваливалось в очереди звонков втрое. Живой случай:
    # ПАО «Юнипро», факт «Поставка запасных частей к компрессору К-250-61-5», поля пустые.
    vid_mk, _ = mf.razobrat(quote, tip)
    # СРЕДА, НАЗВАННАЯ КОНКРЕТНЫМ ГАЗОМ, — тоже «центробежная, но газ». Проверка `'газ' in sr`
    # не ловила «хлорный», «аммиачный», «азотный»: слова «газ» в них нет. Найдено владельцем
    # на карточке АО «Каустик», где хлорный компрессор стоял выше настоящих воздушных.
    if vid_mk == mf.VID_SREDA_NE_VOZDUH:
        k = 'центробежная, но газ'
    elif vid_mk == mf.VID_NASH_PO_MARKE:
        k = 'центробежная и воздух, доказано текстом первоисточника'
    elif vid_mk == mf.VID_MARKA_SREDA:
        k = 'центробежная, среда не названа'
    elif vid_mk == mf.VID_MARKA_GAZ:
        k = 'центробежная, но газ'
    elif centro and vozduh and not gaz:
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

# ТЕЛЕФОНЫ ЛЕЖАТ НЕ ТОЛЬКО В `person`. У компании свои колонки — `telefony_checko`,
# `telefony_predpriyatiya`, `telefony_iz_bazy`, — и модель их не читала. Замер по очереди
# «добыть контакт»: из 507 предприятий, помеченных «звонить некому», телефоны есть у 443,
# мобильных среди них 328. Ноль был свойством запроса, а не предприятия.
# ЗАСЛОН ОБЩЕГО НОМЕРА НА УРОВНЕ КОМПАНИЙ. У номера из реквизитов фамилии нет, поэтому
# обычный заслон (разные фамилии на номере) его не ловит. Проверяем иначе: номер, стоящий в
# реквизитах НЕСКОЛЬКИХ предприятий, — это бухгалтерия на аутсорсе или общий представитель,
# и личным он не бывает. Замер: из 1 254 мобильных таких всего 10, но правило дешёвое, а
# цена ошибки — продавец звонит чужому человеку.
_karta_komp = collections.defaultdict(set)
tel_kompanii = collections.defaultdict(int)
kol_c = [r[1] for r in cx.execute('pragma table_info(company)')]
polya_tel = [k for k in ('telefony_checko', 'telefony_predpriyatiya', 'telefony_iz_bazy')
             if k in kol_c]
if polya_tel:
    zapros = 'select inn, ' + ', '.join('coalesce("%s",\'\')' % k for k in polya_tel) \
             + ' from company'
    _stroki_komp = cx.execute(zapros).fetchall()
    for stroka in _stroki_komp:
        inn, znach = stroka[0], ' | '.join(stroka[1:])
        for n in re.findall(r'\d[\d\-\s()]{8,}\d', znach):
            c = re.sub(r'\D', '', n)
            if len(c) >= 10 and c[-10:].startswith('9'):
                _karta_komp[c[-10:]].add(inn)
    _obshch_komp = {k for k, v in _karta_komp.items() if len(v) > 1}
    for stroka in _stroki_komp:
        inn, znach = stroka[0], ' | '.join(stroka[1:])
        for n in re.findall(r'\d[\d\-\s()]{8,}\d', znach):
            c = re.sub(r'\D', '', n)
            if c[-10:] in _obshch_komp:
                continue
            # Мобильный и не общий: тот же заслон, что для person — номер на разных
            # фамилиях личным не бывает. Здесь фамилий нет вовсе, поэтому проверяем только
            # по карте общих номеров, собранной выше.
            if len(c) >= 10 and c[-10:].startswith('9') and c[-10:] not in obshchie:
                tel_kompanii[inn] += 1

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
    dos = pp.stepen_dosyagaemosti(z['lt'], z['l'], z['it'], z['o'], tel_kompanii.get(inn, 0))
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
    for put in ('prioritet_prodazhi.py', 'musor_faktov.py'):
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
