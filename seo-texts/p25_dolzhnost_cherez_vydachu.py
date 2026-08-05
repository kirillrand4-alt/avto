# -*- coding: utf-8 -*-
"""Должность человеку, у которого УЖЕ ЕСТЬ мобильный. Второй прицельный ход через xmlriver.

ЗАЧЕМ ИМЕННО ЭТО, а не «ещё немного людей». Считано по выкладке 029 в разрезе каналов:

    канал              людей   мобильных   технических   снабжение
    площадка ЭТП         544          84             0           0
    сайт предприятия     505          59            23          79
    ЕИС                   63           1             0           0

Площадки и ЕИС дали 607 человек и НИ ОДНОЙ должности: карточка закупки несёт имя и телефон,
а кем человек работает — не пишет. Все технические и все снабженцы пришли с сайтов.

Отсюда узкое место меры видно точно. Мера ТЗ — «технический ЛПР с личным мобильным». У меня
есть 22 технических БЕЗ мобильного (за ними ходит `p25_nomer_cherez_vydachu`) и **85 человек
С МОБИЛЬНЫМ, но без должности, на 35 незакрытых предприятиях**. Вторая группа дороже: номер —
самое трудное, он уже добыт и подтверждён как мобильный. Не хватает одного поля.

ЧЕМ ЭТОТ ПОИСК ОТЛИЧАЕТСЯ ОТ ПОИСКА НОМЕРА. Там слово запроса подбиралось так, чтобы номер
попал В СНИМОК выдачи («доб» работает, «телефон» нет). Здесь наоборот: должность в снимок
попадает почти всегда, потому что она стоит рядом с именем в любом перечне людей. Поэтому
формы запроса короче, а вся работа — в разборе окрестности имени.

ЧЕГО МОДУЛЬ НЕ ДЕЛАЕТ. Не решает, техническая должность или нет: он возвращает ДОСЛОВНУЮ
строку и цитату, а роль считает `p25_otdat_lyudey` общим правилом. Две копии правила ролей
разошлись бы молча — это уже было с разбором ФИО.

Использование:
    python3 p25_dolzhnost_cherez_vydachu.py [--predel 40]
"""
import base64
import csv
import glob
import json
import os
import re
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
sys.path.insert(0, os.path.join(BAZA, 'server'))
import run_on_server as R

DEST = r'C:\sender\_ops\2s_dolzhnost_cheloveku.py'
VYHOD = os.path.join(L, 'P25-DOLZHNOSTI-NAYDENNYE.csv')

SERVERNYY = r'''
# -*- coding: utf-8 -*-
import importlib.util, json, re, sys

spec = importlib.util.spec_from_file_location('lpr', r'C:\sender\_ops\3s_lpr_obratnyy.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

CELI = json.loads(sys.argv[sys.argv.index('--celi') + 1]) if '--celi' in sys.argv else []

# Должность опознаётся по НАЧАЛУ: «главный инженер», «начальник отдела ...», «заместитель
# генерального директора по ...». Хвост берём до знака препинания или до конца строки —
# «Начальник отдела закупки технологического оборудования, техники и шин» это одна должность,
# и обрубать её по первой запятой нельзя, поэтому запятая разрешена внутри.
NACHALO = (r'(?:и\.?\s?о\.?\s+)?(?:главн\w+|нач\w+|зам\w*\.?|заведующ\w+|руководител\w+|'
           r'директор\w*|техническ\w+\s+директор|старш\w+|ведущ\w+|начальник\w*|'
           r'управляющ\w+|президент|генеральн\w+\s+директор|исполнительн\w+\s+директор)')
DOLZH = re.compile(NACHALO + r'[^.;|\n\r]{0,90}', re.I)
# Мусорные «должности»: строка, начавшаяся с нужного слова, но продолжившаяся не тем.
NE_DOLZHNOST = re.compile(r'^(?:главн\w+\s+(?:образом|страниц|мен))', re.I)


def familiya(fio):
    ch = [x for x in (fio or '').split() if len(x) > 1]
    # В выкладке бывает и «Фамилия Имя Отчество», и «Имя Отчество Фамилия»: берём самое
    # длинное слово — фамилия почти всегда длиннее имени и отчества по отдельности.
    return max(ch, key=len) if ch else ''


def dolzhnost_ryadom(t, fam):
    """Ищем должность в ОКРЕСТНОСТИ фамилии: сначала перед именем (типовой порядок
    «Начальник отдела — Иванов И. И.»), потом после (порядок «Иванов И. И., начальник»)."""
    i = t.find(fam)
    if i < 0:
        return '', ''
    do = t[max(0, i - 130):i]
    posle = t[i + len(fam):i + len(fam) + 130]
    for kusok in (do, posle):
        for kand in DOLZH.finditer(kusok):
            d = ' '.join(kand.group(0).split())
            if len(d) < 6 or NE_DOLZHNOST.match(d):
                continue
            return d, ' '.join(t[max(0, i - 150):i + 250].split())[:400]
    return '', ''


primery, itog, zaprosov, sboev, bez = [], [], 0, 0, 0
for c in CELI:
    fam = familiya(c['chelovek'])
    pred = (c.get('predpriyatie') or '')[:40]
    formy = []
    if c.get('domen'):
        formy.append('site:%s "%s"' % (c['domen'], fam))
    formy += ['"%s" "%s"' % (c['chelovek'], pred),
              '"%s" %s должность' % (c['chelovek'], pred)]
    nashli = None
    for z in formy:
        if nashli:
            break
        docs, err = m.serp(z)
        zaprosov += 1
        if err:
            sboev += 1
            continue
        for d in (docs or []):
            t = d.get('tekst') or ''
            if fam not in t:
                continue
            dolzh, citata = dolzhnost_ryadom(t, fam)
            if not dolzh:
                continue
            nashli = {'inn': c['inn'], 'chelovek': c['chelovek'], 'telefon': c.get('telefon', ''),
                      'dolzhnost': dolzh, 'zapros': z, 'ssylka': d.get('url', ''),
                      'citata': citata}
            break
    if nashli:
        itog.append(nashli)
        if len(primery) < 10:
            primery.append('%s | %s' % (nashli['chelovek'][:26], nashli['dolzhnost'][:60]))
    else:
        bez += 1

# ПРИМЕРЫ ПЕРВЫМИ, СЧЁТЧИКИ ПОСЛЕДНИМИ: stdout_tail это хвост.
for p in primery:
    print('  ', p)
print('запросов', zaprosov, 'сбоев', sboev, 'без должности', bez)
print('НАЙДЕНО_JSON', json.dumps(itog, ensure_ascii=False))
'''

COLS = ['inn', 'chelovek', 'telefon', 'dolzhnost', 'zapros', 'ssylka', 'citata']


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def main():
    predel = dovod('--predel', 60)
    och = {r['inn']: r for r in chitat(os.path.join(L, 'P25-OCHERED.csv'))}
    posl = sorted(glob.glob(os.path.join(L, 'P25-LYUDI-2S-0*.csv')))[-1]
    lyudi = chitat(posl)
    print(f'выкладка: {os.path.basename(posl)}', file=sys.stderr)

    SILA = {'подтверждён': 0, 'название совпало': 1, 'сайт группы': 2}
    luchshie = {}
    for r in chitat(os.path.join(L, 'P25-SAJTY.csv')):
        s = SILA.get(r['itog'])
        if s is None:
            continue
        d = re.sub(r'^https?://', '', r['sayt']).replace('www.', '')
        if r['inn'] not in luchshie or s <= luchshie[r['inn']][0]:
            luchshie[r['inn']] = (s, d)

    uzhe = {(r['inn'], r['chelovek']) for r in chitat(VYHOD)}
    celi = []
    for x in lyudi:
        if x.get('vid_nomera') != 'мобильный' or (x.get('dolzhnost') or '').strip():
            continue
        if (x['inn'], x['chelovek']) in uzhe:
            continue
        celi.append({'inn': x['inn'], 'chelovek': x['chelovek'],
                     'telefon': x.get('telefon', ''),
                     'predpriyatie': och.get(x['inn'], {}).get('predpriyatie', ''),
                     'domen': luchshie.get(x['inn'], (9, ''))[1]})
    # ПОРЯДОК — ПО СУММЕ ПОКУПОК. Единственная сортировка задачи.
    celi.sort(key=lambda c: int(och.get(c['inn'], {}).get('mesto') or 10 ** 9))
    celi = celi[:predel]
    print(f'людей с мобильным и без должности: {len(celi)}, с известным доменом: '
          f'{sum(1 for c in celi if c["domen"])}', file=sys.stderr)
    if not celi:
        return

    R.submit('enrich_contacts',
             {'op': 'panel_file_put',
              'files': [{'dest': DEST,
                         'b64': base64.b64encode(SERVERNYY.encode('utf-8')).decode()}]},
             timeout=300)
    otvet = R.submit('enrich_contacts',
                     {'op': 'panel_py', 'script': DEST,
                      'argv': ['--celi', json.dumps(celi, ensure_ascii=False)],
                      'timeout': 1700}, timeout=1800)
    d = otvet.get('data') or {}
    hvost = d.get('stdout_tail') or ''
    print(f'rc={d.get("rc")}', file=sys.stderr)
    print(hvost[-1500:], file=sys.stderr)
    if d.get('stderr_tail'):
        print('stderr:', str(d['stderr_tail'])[-400:], file=sys.stderr)

    m = re.search(r'НАЙДЕНО_JSON (\[.*?\])\s*$', hvost, re.S)
    if not m:
        print('строки с находками в выводе нет', file=sys.stderr)
        return
    najdeno = json.loads(m.group(1))
    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    with open(VYHOD, 'a', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        if novyy:
            w.writeheader()
        for r in najdeno:
            w.writerow(r)
    print(f'записано должностей {len(najdeno)}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
