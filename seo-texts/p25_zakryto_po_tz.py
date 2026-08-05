# -*- coding: utf-8 -*-
"""Сколько предприятий из 491 закрыто по БУКВЕ ТЗ — по всем источникам сразу.

Мера ТЗ состоит из трёх условий, и каждое должно быть доказано ОТДЕЛЬНО:

    1) человек технического круга (1-2);
    2) ЛИЧНЫЙ мобильный (код 9xx), а не городской и не линия;
    3) первоисточник — страница предприятия, карточка закупки, реестр.

СЛОЖЕНИЕ ДОКАЗАННОГО С НЕДОКАЗАННЫМ ДАЁТ НЕДОКАЗАННОЕ. На этом я едва не объявила
первое закрытие смены: человек был подтверждён страницей А, а номер добыт со страницы
Б, чей источник приёмку не проходил. Поэтому здесь три условия проверяются по ОДНОЙ
строке, а не собираются из разных.

Считаю по выкладкам на дропе, а не по потокам: выкладка — то, что прошло приёмку и
дошло до владельца. Что не выложено — того для меры нет.
"""
import collections
import csv
import glob
import json
import os
import re
import sqlite3

D = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 8)

KRUG12 = re.compile(
    r'главн\w+\s+(?:инженер|механик|энергетик|технолог|сварщик|метролог|конструктор)|'
    r'техническ\w+\s+директор|начальник\w*\s+(?:цеха|производств|участка|службы|'
    r'ремонт\w*|энерго\w*)|механик|энергетик|технолог|инженер|КИПиА|АСУ', re.I)
# Слова, при которых «инженер» не про наш круг: инженер по кадрам, по закупкам и т. п.
NE_NASH = re.compile(r'персонал|кадр|закупк|снабж|бухгалт|юрист|секретар|маркетинг|'
                     r'продаж|устойчив\w+\s+развити|реклам|пресс', re.I)


# Положительная приёмка — дословные формулы, которыми её пишут мои же каналы.
# Формулы сняты прибором p25_formuly_priemki.py с живых выкладок, а не сочинены:
# 49 различных у годных, 41 у отклонённых.
PRIEMKA = re.compile(
    r'страница на сайте предприятия|на сайте холдинга|карточка закупки самого предприятия|'
    r'документ раскрытия|официальн\w+ реестр|заказчик написал|реестр ЭПБ|'
    r'tender\.pro, карточка закупки|контактное лицо заказчика назван', re.I)
# Отказ. Если он есть в строке — строка не годна, чем бы ещё она ни хвалилась.
OTKAZ_V_TEKSTE = re.compile(
    r'не первоисточник|не сайт предприятия|новостн\w+, выставочн\w+|социальн\w+ домен|'
    r'агрегатор|карточка ОРГАНИЗАЦИИ|мошенн|запрещ[её]н|не проходит', re.I)


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

zakryto, strogie = {}, {}
sch = collections.Counter()
KOL_TEL = ('LICHNYY_MOBILNYY', 'telefon', 'znachenie', 'nomer', 'telefon_kak_napisan')
# ДВА ЧТЕНИЯ МЕРЫ, И РАЗЛИЧАТЬ ИХ ПОТРЕБОВАЛА 1-Я СЕССИЯ — справедливо. Формулировка
# ТЗ («технический ЛПР») допускает оба, и подменять её удобным нельзя ни в одну сторону.
#   СТРОГОЕ: должность НАЗВАНА в тексте («главный энергетик», «механик»).
#   ШИРОКОЕ: заказчик поставил человека под меткой «по техническим вопросам», но кем
#            он работает, не написал. Метка говорит, К КОМУ ИДТИ, а не кем человек
#            работает: снабженец, ведущий эту закупку, стоит под той же меткой.
# Печатаю оба числа. Решать, какое считать мерой, — владельцу, а не мне.
KOL_DOLZH_STROGO = ('dolzhnost', 'dolzhnost_v_tekste')
KOL_DOLZH_SHIROKO = ('dolzhnost', 'dolzhnost_v_tekste', 'rol_po_kartochke',
                     'tehnicheskiy_krug', 'chem_dokazan_krug')
KOL_IST = ('pervoistochnik', 'ssylka', 'ssylki', 'chem_podtverzhdena', 'ssylka_na_kartochku',
           'osnovanie', 'chem_dokazana_rol')

# СУДИТ СТРОКА, А НЕ ИМЯ ФАЙЛА. Сперва я мела все файлы подряд и считала закрытиями то,
# что сама отложила как недоказанное (13 -> 30, половина прибавки из отказов). Потом
# отбросила файлы отказов целиком — и упала до 6. Оба раза неверно, и прочтение
# фактических формулировок показало почему:
#
#   в файлах ГОДНЫХ лежат 14 строк с «домен «…» не первоисточник»;
#   в файлах ОТКЛОНЁННЫХ лежат 799 строк с «карточка закупки самого предприятия» —
#   они отклонены по ДРУГОЙ причине (номер не личный, привязка спорная).
#
# Значит имя файла не признак годности источника. Признак — что написано в самой
# строке, и он проверяется в обе стороны: есть положительная формула приёмки И нет
# формулы отказа. Прочие условия ТЗ (личный номер, бесспорная привязка) проверяются
# рядом своими полями, как и раньше.
for p in sorted(glob.glob(os.path.join(D, 'P25-*3S*.csv'))):
    try:
        rows = list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'))
    except Exception:  # noqa: BLE001
        continue
    for r in rows:
        inn = (r.get('inn') or '').strip()
        if inn not in nashi:
            continue
        # 1) круг — в двух чтениях сразу
        d_strogo = ' '.join(str(r.get(k) or '') for k in KOL_DOLZH_STROGO)
        d_shiroko = ' '.join(str(r.get(k) or '') for k in KOL_DOLZH_SHIROKO)
        strogo = bool(KRUG12.search(d_strogo)) and not NE_NASH.search(d_strogo)
        shiroko = strogo or (
            (r.get('tehnicheskiy_krug') == 'да'
             or bool(KRUG12.search(d_shiroko))) and not NE_NASH.search(d_shiroko))
        if not shiroko:
            continue
        dolzh = d_strogo if strogo else (r.get('rol_po_kartochke') or d_shiroko)
        # 2) личный мобильный В ЭТОЙ ЖЕ СТРОКЕ
        nomer = next((str(r.get(k)) for k in KOL_TEL if lichnyy(r.get(k))), '')
        if not nomer:
            continue
        # 3) первоисточник В ЭТОЙ ЖЕ СТРОКЕ
        # ИСТОЧНИК ДОКАЗЫВАЕТСЯ ПОЛОЖИТЕЛЬНО, А НЕ НАЛИЧИЕМ БУКВ. Прежний шаблон ловил
        # слово «карточка» ВНУТРИ ОТРИЦАНИЯ «не сайт предприятия, не карточка», а
        # `https?://` есть в каждой строке и не доказывает ничего. Так в меру попали
        # «ИСО» (домен ggpk31 прямо помечен «не первоисточник») и «СЛК ЦЕМЕНТ»
        # (новостной домен gov74). Поле, которое говорит НЕТ, читалось как ДА.
        ist = ' '.join(str(r.get(k) or '') for k in KOL_IST)
        if OTKAZ_V_TEKSTE.search(ist):
            sch['источник в строке прямо помечен как непринятый'] += 1
            continue
        # Колонка `pervoistochnik` со значением «да» — тоже приёмка, её ставят каналы,
        # где формула лежит в соседнем поле.
        if not (PRIEMKA.search(ist)
                or (r.get('pervoistochnik') or '').strip().lower() == 'да'):
            sch['круг и мобильный есть, первоисточника в строке нет'] += 1
            continue
        # заслон: спорная привязка и общие номера в меру не идут
        if 'спорн' in (r.get('uverennost_privyazki') or '').lower():
            sch['спорная привязка — в меру не идёт'] += 1
            continue
        if 'ОБЩИЙ' in (r.get('vid') or '') or 'ЛИНИЯ' in (r.get('vid') or ''):
            sch['номер общий или линия — в меру не идёт'] += 1
            continue
        chel = (r.get('chelovek') or r.get('fio') or '').strip()
        zakryto.setdefault(inn, []).append(
            (chel, nomer, dolzh.strip()[:40], os.path.basename(p)))
        sch['строк по ШИРОКОМУ чтению'] += 1
        if strogo:
            strogie.setdefault(inn, []).append((chel, nomer, dolzh.strip()[:40]))
            sch['строк по СТРОГОМУ чтению (должность названа)'] += 1

po_mestu = sorted(zakryto.items(), key=lambda x: mesta.get(x[0], 9999))
for inn, lyudi in po_mestu:
    kto = collections.OrderedDict((l[0], l) for l in lyudi)
    print('  место %4s  %-34s  %d чел: %s' % (
        mesta.get(inn, '—'), (nashi.get(inn) or '')[:34], len(kto),
        ', '.join('%s (%s)' % (k[:22], v[1]) for k, v in list(kto.items())[:3])))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('\nСТРОГОЕ ЧТЕНИЕ — должность названа в тексте:')
for inn, lyudi in sorted(strogie.items(), key=lambda x: mesta.get(x[0], 9999)):
    kto = collections.OrderedDict((l[0], l) for l in lyudi)
    for k, v in kto.items():
        print('   место %4s  %-30s %-28s %-18s %s' % (
            mesta.get(inn, '—'), (nashi.get(inn) or '')[:30], k[:28], v[1], v[2][:26]))
print('ИТОГ ' + json.dumps({
    'ЗАКРЫТО СТРОГО (должность названа)': len(strogie),
    'ЗАКРЫТО ШИРОКО (метка заказчика)': len(zakryto),
    'человек строго': len({(i, l[0]) for i, ls in strogie.items() for l in ls}),
    'человек широко': len({(i, l[0]) for i, ls in zakryto.items() for l in ls}),
    'строго из первой сотни': len([i for i in strogie if mesta.get(i, 9999) <= 100]),
}, ensure_ascii=False))
