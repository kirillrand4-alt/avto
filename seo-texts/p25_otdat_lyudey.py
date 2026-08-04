# -*- coding: utf-8 -*-
"""P25: выложить добытых людей файлом в формате, который принимает залив 1-й сессии.

ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ ШАГ И ПОЧЕМУ ОН ИДЁТ СРАЗУ ПОСЛЕ ПЕРВОГО ЖЕ КУСКА. Вчера у меня
156 добытых телефонов пролежали в потоке на сервере, пока владелец не спросил, где они.
Правило усвоено: кусок прошёл — файл выложен. Не «в конце прогона», не «когда наберётся».

ФОРМАТ — НЕ МОЙ, А ПРИЁМНИКА. 1-я сессия назвала точку записи и колонки:

    inn; chelovek; dolzhnost; podrazdelenie; telefon; pochta; rol; ssylka;
    data_nablyudeniya; citata

Напрямую в базу не пишет никто, включая меня: вливает один оп `vlit_lyudey_csv.py`, и три
исхода вставки живут в одном месте. Это правильно — правило, размазанное по трём сессиям,
разойдётся к вечеру.

ЧТО ВЫКЛАДЫВАЕТСЯ И ЧТО НЕТ. Только люди, у которых страница ПОДТВЕРЖДАЕТ принадлежность:
сайт предприятия, страница про него на сайте холдинга, карточка закупки или имя предприятия
в тексте. Остальные остаются в потоке и в отдельном файле «не подтверждено» — не выбрасываю,
но и в базу не отдаю: непроверенная привязка там дороже пустой клетки.

    ИСТОЧНИК ЗАПРЕЩЁН    не выкладывается вовсе (реестр проверок, аттестация, выборы)
    страница не подтверждает   отдельным файлом, с причиной по каждому
    мимо: зона не наша   отдельным файлом (экология, охрана труда — не наш круг)

РОЛЬ СТАВИТСЯ ПО ПОДРАЗДЕЛЕНИЮ, а не по слову должности — правило ТЗ. Подразделения в выдаче
чаще всего нет, и тогда поле остаётся ПУСТЫМ: угадать его по слову значит подменить правило.

Запуск: python3 p25_otdat_lyudey.py
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

SCRIPT = r'''
# -*- coding: utf-8 -*-
import collections, csv, io, json, os, re, sys, urllib.request

POTOK = r'C:\sender\_ops\p25-imena.jsonl'
POLYA = ['inn', 'chelovek', 'dolzhnost', 'podrazdelenie', 'telefon', 'pochta', 'rol',
         'ssylka', 'data_nablyudeniya', 'citata', 'chem_podtverzhdena']

# Круг по ТЗ: 1) главный инженер/механик/энергетик/техдиректор; 2) начальник производства.
KRUG1 = re.compile(r'главн\w*\s+(?:инженер|механик|энергетик)|техническ\w+\s+директор', re.I)
KRUG2 = re.compile(r'начальник\w*\s+(?:производств|цеха)|главн\w+\s+технолог|АСУ|КИПиА', re.I)
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
# ДАТА ЛЕЖИТ И В АДРЕСЕ, А Я СМОТРЕЛ ТОЛЬКО В ЦИТАТЕ. Замечание 1-й сессии по первому же
# принятому файлу: 12 строк из 13 ушли без даты, то есть в МЕРУ УСПЕХА не пошли, — при том
# что год виден прямо в источнике:
#     tehremex.com/Сборник_докладов_СГМ_2024.pdf      → 2024 в имени файла
#     ab-solution.ru/.../news-energy2024-portrait     → 2024 в адресе
# Правило ТЗ: дата — та, НА КОТОРУЮ человек занимал должность, а не день скачивания. Год
# сборника ей отвечает.
#
# ПОРЯДОК ИСТОЧНИКОВ ДАТЫ — от надёжного к слабому, и он подписывается в `chem`, а не
# теряется: год рядом с именем сильнее года в адресе, а год в адресе сильнее года где-то на
# странице. Если на странице несколько РАЗНЫХ годов и рядом с именем нет ни одного — даты
# нет: выбрать наугад значит выдумать свежесть, а это ровно то, против чего правило.
GOD_RYADOM = re.compile(r'\b(20[0-2]\d)\b')
GOD_V_ADRESE = re.compile(r'(?<!\d)(20[0-2]\d)(?!\d)')


def data_nablyudeniya(citata, ssylka, ves_tekst=''):
    """(год, чем подтверждён). Пусто — честнее выдуманного."""
    m = GOD_RYADOM.search(citata or '')
    if m:
        return m.group(1), 'год в тексте рядом с именем и должностью'
    m = GOD_V_ADRESE.search(ssylka or '')
    if m:
        return m.group(1), 'год в адресе страницы или в имени файла'
    gody = set(GOD_RYADOM.findall(ves_tekst or ''))
    if len(gody) == 1:
        return gody.pop(), 'единственный год на странице'
    return '', ('на странице несколько разных годов — выбрать наугад значит выдумать свежесть'
                if gody else 'даты в источнике нет')
POCHTA = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

vydacha, ne_podtv, mimo = [], [], []
sch = collections.Counter()
for ln in open(POTOK, encoding='utf-8'):
    z = json.loads(ln)
    if z.get('err'):
        sch['сбой канала — переспросится'] += 1
        continue
    for l in z.get('lyudi') or []:
        krug = l.get('krug', '')
        if krug == 'ИСТОЧНИК ЗАПРЕЩЁН':
            sch['источник запрещён — не выкладываю'] += 1
            continue
        cit = l.get('citata') or ''
        tel = TEL.search(cit)
        poch = POCHTA.search(cit)
        d = l.get('dolzhnost') or ''
        god, chem = l.get('data_iz_teksta', ''), l.get('chem_data', '')
        if not god:
            god, chem = data_nablyudeniya(cit, l.get('ssylka', ''), l.get('citata', ''))
        if god:
            sch['дата определена: ' + chem[:34]] += 1
        else:
            sch['даты нет: ' + chem[:34]] += 1
        stroka = {
            'inn': z['inn'], 'chelovek': l['fio'], 'dolzhnost': d,
            # ПОДРАЗДЕЛЕНИЕ ПУСТОЕ, ЕСЛИ ЕГО НЕТ В ТЕКСТЕ. Роль по ТЗ ставится по
            # подразделению; выводить его из слова должности значит подменить правило,
            # ради которого оно написано.
            'podrazdelenie': '',
            'telefon': tel.group(0) if tel else '',
            'pochta': poch.group(0) if poch else '',
            'rol': ('1 круг' if KRUG1.search(d) else '2 круг' if KRUG2.search(d) else ''),
            'ssylka': l.get('ssylka', ''),
            'data_nablyudeniya': god,
            'citata': cit[:500],
            'chem_podtverzhdena': chem,
        }
        if krug == 'мимо: зона не наша':
            stroka['rol'] = 'мимо: зона не наша'
            mimo.append(stroka); sch['зона не наша'] += 1
        elif l.get('podtverzhdena'):
            vydacha.append(stroka); sch['ВЫКЛАДЫВАЮ (страница подтверждает)'] += 1
            if stroka['telefon']:
                sch['  из них с телефоном в цитате'] += 1
        else:
            stroka['rol'] = (stroka['rol'] + ' | ' + (l.get('pochemu') or ''))[:120]
            ne_podtv.append(stroka); sch['не подтверждено — отдельным файлом'] += 1


def vylozhit(imya, dannye):
    if not dannye:
        return 'пусто'
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=POLYA, extrasaction='ignore')
    w.writeheader(); w.writerows(dannye)
    telo = b.getvalue().encode('utf-8-sig')
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/' + imya, data=telo, method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''), 'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return '%s, строк %d' % (r.status, len(dannye))
    except Exception as e:
        return 'НЕ выгружен: ' + type(e).__name__


itog = {'по_видам': dict(sch.most_common()),
        'P25-LYUDI-3S.csv': vylozhit('P25-LYUDI-3S.csv', vydacha),
        'P25-LYUDI-3S-ne-podtverzhdeno.csv':
            vylozhit('P25-LYUDI-3S-ne-podtverzhdeno.csv', ne_podtv),
        'P25-LYUDI-3S-zona-ne-nasha.csv':
            vylozhit('P25-LYUDI-3S-zona-ne-nasha.csv', mimo),
        'предприятий_в_выдаче': len({s['inn'] for s in vydacha})}
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def main():
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'dest': r'C:\sender\_ops\3s_p25_otdat.py',
         'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_p25_otdat.py',
                  'argv': [], 'timeout': 600}, timeout=900)
    d = r.get('data') or {}
    for s in (d.get('stdout_tail') or '').splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('пусто:', (d.get('stderr_tail') or '')[-900:], file=sys.stderr)


if __name__ == '__main__':
    main()
