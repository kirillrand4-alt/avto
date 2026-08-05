# -*- coding: utf-8 -*-
"""Именной поиск ЛЮДЕЙ там, где домен предприятия ИЗВЕСТЕН, а имён нет.

ПОЧЕМУ КАНАЛ БЕРЁТ ТОЛЬКО ПРЕДПРИЯТИЯ С ДОМЕНОМ. Замер по уже пройденному: подтверждённый
человек стоит ~21 запрос, когда домен известен, и ~250, когда домена нет. Разница в
ДВЕНАДЦАТЬ РАЗ, и она не случайная: без домена запрос «"предприятие" "главный инженер"»
уходит в общую сеть, где имя предприятия чаще всего называют агрегаторы выписок, а строгая
приёмка их не засчитывает — то есть большинство ответов оплачено и выброшено заслоном. С
доменом запрос сразу адресован первоисточнику: страница, которую вернул `site:<домен>`, почти
всегда проходит `stranica_podtverzhdaet` по первому же условию «хост совпадает с сайтом
предприятия». Пул общий на три сессии, значит выбор цели есть распределение чужой работы:
предприятия без домена этот канал НЕ берёт вовсе, их место — в канале, который сперва
добывает домен.

ЧТО ЗНАЧИТ «ИМЁН НЕТ». Цель берётся, только если ни в одной выкладке дропа по её ИНН нет
человека и ни один поток канала её ещё не закрыл. Иначе канал перепахивает добытое: за смену
это уже случалось, и стоило оно не денег, а места в общем пуле.

ФОРМА ЗАПРОСА РЕШАЕТ, ЧТО ПОКАЖЕТ СНИМОК. Снимок выдачи следует за запросом: в снимке видно
то, что стоит рядом со словами запроса. Поэтому спрашиваются подряд «главный инженер»,
«главный энергетик» и «руководство контакты» — первая же форма, давшая ПОДТВЕРЖДЁННОГО
страницей человека, останавливает перебор. Неподтверждённый человек удачей не считается:
иначе перебор останавливается на первой попавшейся странице, а следующая форма, которая дала
бы имя с первоисточника, не спрашивается никогда.

ФИЛЬТР НАДО ДОКАЗЫВАТЬ, А НЕ ПРЕДПОЛАГАТЬ. Отдельный счётчик считает документы, пришедшие НЕ
с запрошенного домена вопреки `site:`. Это ровно та ошибка, что стоила 2 399 карточек на
площадке: непустая выдача была принята за доказательство работающего фильтра. Здесь признак
живого фильтра измеряется числом и печатается, а `--proba` требует РАЗЛИЧЕНИЯ: два разных
домена дают разное, бессмыслица даёт ноль, битый вход даёт падение.

ЛОЖНЫЙ НОЛЬ. «Заняты все доступные вам каналы» это `err`, а не пустая выдача. Запись с `err`
цель НЕ закрывает и будет переспрошена следующим запуском — очередь держится в потоке jsonl,
задание раннера умирает на 1700 с, и длинный прогон режется `--lim`.

Запуск (на сервере, через zapusk_na_servere.py):
    python3 p25_imena_po_domenam.py --proba
    python3 p25_imena_po_domenam.py --lim 120 --potokov 6
    python3 p25_imena_po_domenam.py --vylozhit
"""
import collections
import csv
import glob
import importlib.util
import io
import json
import os
import re
import sqlite3
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH  # noqa: E402

POTOK = r'C:\sender\_ops\p25-imena-po-domenam.jsonl'
BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
SAYTY_GLOB = r'C:\sender\_ops\3s_p25_sayty_*.csv'
VYKLADKI_GLOB = r'C:\seostat\drop\drop-storage\*.csv'
# Потоки, где люди уже добыты другими каналами: их предприятия второй раз не спрашиваем.
# путь, имя списка внутри записи, поле имени, поле подтверждения. Имена списков и полей взяты
# из приборного снимка потоков, а не по памяти: в `p25-imena.jsonl` список зовётся `lyudi`, а в
# `p25-obratnyy.jsonl` человек лежит НА ВЕРХНЕМ УРОВНЕ, и список там называется `kontakty`.
POTOKI_S_LYUDMI = ((r'C:\sender\_ops\p25-imena.jsonl', 'lyudi', 'fio', 'podtverzhdena'),
                   (r'C:\sender\_ops\p25-obratnyy.jsonl', '', 'fio', ''))
KANDIDATY_SERP = (r'C:\sender\_ops\3s_lpr_obratnyy.py', r'C:\sender\_ops\_3s_lpr_obratnyy.py')
FORMY = ('site:%s "главный инженер"',
         'site:%s "главный энергетик"',
         'site:%s руководство контакты')
VYHOD = (('P25-IMENA-PO-DOMENAM-3S.csv', 'подтверждено страницей, должность есть'),
         ('P25-IMENA-PO-DOMENAM-3S-bez-dolzhnosti.csv', 'подтверждено страницей, должности нет'),
         ('P25-IMENA-PO-DOMENAM-3S-ne-podtverzhdeno.csv', 'страница заслон не прошла'))
POLYA = ('inn', 'predpriyatie', 'mesto_po_summe', 'sayt', 'fio', 'kak_napisano', 'dolzhnost',
         'dolzhnost_otkuda', 'krug', 'znakov_do_imeni', 'poryadok', 'nomer_imeni_na_stranice',
         'dolzhnosti_ryadom', 'podtverzhdena', 'pochemu_stranica', 'domen_iz_vydachi',
         'zapros', 'citata', 'istochniki', 'istochnikov', 'chelovek_est_i_u_inn')
csv.field_size_limit(10 ** 8)

# ФИО ТОЛЬКО ПОЛНОЕ, С ОТЧЕСТВОМ. «Иванов И.И.» и «Сергей Иванов» в канал не идут: по ним
# нельзя ни спросить обратный ход, ни отличить однофамильца, а в выкладке они выглядят
# находкой ровно так же, как настоящая. Два порядка написания, потому что страница руководства
# пишет «Иванов Иван Иванович», а новость завода — «Иван Иванович Иванов».
#
# ОСНОВА ОТЧЕСТВА — `{2,}`, А НЕ `{3,}`, И ЭТО ПРАВКА ПО ЗАМЕРУ, А НЕ ПО ВКУСУ. Шаблон
# соседнего именного канала требует трёх букв до окончания, и на этом теряет самые ходовые
# отчества: «Юрьевич», «Юрьевна», «Львович» — в них между заглавной и окончанием ровно две
# буквы. Проверено прямым прогоном разбора: строка «Технический директор Эдуард Юрьевич
# Еремеев» давала НОЛЬ людей, притом что ровно этот пример стоит в комментарии соседнего
# модуля как разбираемый. Ноль без сбоя выглядит пустой страницей, поэтому такая потеря не
# видна никогда, пока её не спросишь прибором.
FIO = re.compile(
    r'\b([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]{2,})?)\s+([А-ЯЁ][а-яё]{2,})\s+'
    r'([А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична))\b')
FIO_OBR = re.compile(
    r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична))\s+'
    r'([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]{2,})?)\b')
# Слово с большой буквы перед именем — ещё не фамилия. Список перенесён из именного канала
# целиком: каждое слово в нём однажды уехало в выкладку как фамилия ЛПР.
NE_FAMILIYA = re.compile(
    r'^(?:главн|начальн|заместител|директор|инженер|механик|энергетик|технич|исполняющ|'
    r'руководител|специалист|ведущ|старш|представител|контакт|телефон|адрес|общест|'
    r'акционерн|компани|организац|предприят|управлен|отдел|служб|цех|участок|'
    r'уважаем|многоуважаем|дорог|глубокоуважаем|'
    r'сейчас|теперь|ранее|также|кроме|однако|поэтому|затем|тогда|здесь|далее)', re.I)

# ДОЛЖНОСТИ В ТЕКСТЕ. Порядок важен: «заместитель главного инженера» ловится тем же шаблоном,
# что и «главный инженер», поэтому приставка проверяется отдельно и НЕ отменяет запись, а
# меняет круг — заместитель это тоже вход на предприятие, просто другой.
DOLZH_TEKST = (
    ('главный инженер', re.compile(r'главн\w*[\s\-]+инженер\w*', re.I), '1 круг'),
    ('главный энергетик', re.compile(r'главн\w*[\s\-]+энергетик\w*', re.I), '1 круг'),
    ('главный механик', re.compile(r'главн\w*[\s\-]+механик\w*', re.I), '1 круг'),
    ('технический директор', re.compile(r'техническ\w+[\s\-]+директор\w*', re.I), '1 круг'),
    ('главный технолог', re.compile(r'главн\w*[\s\-]+технолог\w*', re.I), '2 круг'),
    ('начальник производства', re.compile(r'начальник\w*[\s\-]+производств\w*', re.I), '2 круг'),
    ('начальник цеха', re.compile(r'начальник\w*[\s\-]+цеха', re.I), '2 круг'),
    ('главный метролог', re.compile(r'главн\w*[\s\-]+метролог\w*', re.I), '2 круг'),
    ('начальник отдела снабжения',
     re.compile(r'начальник\w*[\s\-]+отдела[\s\-]+(?:снабжен|материально)\w*', re.I), '3 круг'),
    ('генеральный директор', re.compile(r'генеральн\w+[\s\-]+директор\w*', re.I), 'руководитель'),
    ('исполнительный директор',
     re.compile(r'исполнительн\w+[\s\-]+директор\w*', re.I), 'руководитель'),
)
PRISTAVKA = re.compile(r'(?:заместител\w*|зам\.?|и\.\s?о\.|исполняющ\w+\s+обязанност\w*|'
                       r'помощник\w*|советник\w*)\s*$', re.I)
# ЛЮБОЕ ДОЛЖНОСТНОЕ СЛОВО, даже не из нашего списка. Нужно для одного решения: брать ли
# должность из адреса страницы. Если в полосе человека уже названа КАКАЯ-ТО должность, а наша
# в ней не нашлась, значит человек занимает другую, и подпись адреса ему не принадлежит.
LYUBAYA_DOLZH = re.compile(
    r'секретар|помощник|референт|начальник|директор|инженер|механик|энергетик|технолог|'
    r'мастер|специалист|руководител|бухгалтер|менеджер|заместител|диспетчер|кладовщик', re.I)
# Слова, отменяющие технический круг: должность совпала, а зона не наша.
NE_NASH_KRUG = re.compile(r'по\s+эколог|эколог|охран\w+\s+труд|промышленн\w+\s+безопасн|'
                          r'по\s+кадр|по\s+персонал|по\s+социальн|по\s+режим|'
                          r'по\s+граждан\w+\s+оборон|по\s+связям', re.I)
# ДОЛЖНОСТЬ ИЗ АДРЕСА СТРАНИЦЫ. `kirovets-ptz.com/contacts/sluzhba-glavnogo-inzhenera/` — адрес
# называет должность прямее, чем текст снимка, где её может не быть вовсе. Но адрес говорит про
# СТРАНИЦУ, а не про человека: на странице службы главного инженера названы и подчинённые.
# Поэтому адрес идёт вторым источником, только когда полоса человека молчит, и вид источника
# пишется в выгрузку явно, чтобы человек мог рассудить сам.
DOLZH_URL = (
    ('главный инженер', re.compile(r'glavn\w*[-_]?inzhener|glavnogo[-_]inzhenera|'
                                   r'gl[-_]?inzh|chief[-_]?engineer', re.I), '1 круг'),
    ('главный энергетик', re.compile(r'glavn\w*[-_]?energetik|glavnogo[-_]energetika', re.I),
     '1 круг'),
    ('главный механик', re.compile(r'glavn\w*[-_]?meh?anik|glavnogo[-_]mehanika', re.I), '1 круг'),
    ('технический директор', re.compile(r'teh(?:nicheskiy)?[-_]?direktor|'
                                        r'tech[-_]?director', re.I), '1 круг'),
    ('главный технолог', re.compile(r'glavn\w*[-_]?tehnolog', re.I), '2 круг'),
)
# Должность дальше этого от имени принадлежит другому блоку страницы, а не человеку.
PREDEL_ZNAKOV = 300


def klyuch_cheloveka(v):
    """Сравнение людей идёт по сжатым пробелам и регистру: написание есть свойство страницы."""
    return re.sub(r'\s+', ' ', str(v or '')).strip().lower()


def yadro(u):
    """Ядро домена: `www.sibur.ru/polief/` -> `sibur`. Им сравнивают ПРИНАДЛЕЖНОСТЬ."""
    return CH.yadro_domena(u)


def host(u):
    """Хост целиком: `https://www.kaustik.ru/about/` -> `kaustik.ru`. Им СПРАШИВАЮТ.

    Ядро и хост путать нельзя, и это стоило целого прогона в пробе: в запрос уходило
    `site:kaustik` вместо `site:kaustik.ru`. Оператор `site:` без домена первого уровня не
    адрес, поисковик читает его как обычное слово — фильтр молча выключается, выдача остаётся
    непустой, и ноль людей выглядит свойством предприятия, а не поломкой запроса.
    """
    v = re.sub(r'^\w+://', '', (u or '').strip().lower()).split('/')[0].split('?')[0]
    return re.sub(r'^www\.', '', v).strip('.')


def _serp():
    """serp(zapros) -> (docs, err). Модуль подключается по файлу: на сервере он лежит рядом."""
    for put in KANDIDATY_SERP:
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location('lpr_obr_dom', put)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m.serp
    raise SystemExit('модуля поиска нет ни по одному из путей: %s' % (KANDIDATY_SERP,))


def kolonki(b, tablica):
    """Схема снимается прибором. Шесть угаданных имён полей за смену дали шесть пустых ответов."""
    try:
        return [r[1] for r in b.execute('pragma table_info(%s)' % tablica)]
    except Exception:  # noqa: BLE001
        return []


def domeny():
    """ИНН -> домен. Строки с ves < 2 пропускаются: слабый признак домена хуже отсутствия."""
    d, sch = {}, collections.Counter()
    for p in sorted(glob.glob(SAYTY_GLOB)):
        try:
            with open(p, encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f, delimiter=';'):
                    ves = (r.get('ves') or '').strip()
                    if ves.isdigit() and int(ves) < 2:
                        sch['домен пропущен: ves < 2'] += 1
                        continue
                    inn, sayt = (r.get('inn') or '').strip(), (r.get('sayt') or '').strip()
                    if inn and sayt and inn not in d:
                        d[inn] = sayt
                        sch['домен из %s' % os.path.basename(p)] += 1
        except Exception as e:  # noqa: BLE001
            sch['файл доменов не прочитан: %s' % type(e).__name__] += 1
    return d, sch


def lyudi_uzhe_est():
    """ИНН, у которых человек уже добыт: выкладки дропа и потоки других каналов."""
    est, sch = set(), collections.Counter()
    KOL_CHELOVEKA = ('fio', 'ФИО', 'chelovek', 'imya', 'chelovek_v_kartochke', 'familiya')
    for p in sorted(glob.glob(VYKLADKI_GLOB)):
        try:
            # Файл с полными текстами карточек весит десятки мегабайт и людей по ИНН не несёт;
            # называем пропуск вслух, а не молча, чтобы «ноль» потом не пришлось объяснять.
            if os.path.getsize(p) > 200 * 1024 * 1024:
                sch['выкладка пропущена по размеру: %s' % os.path.basename(p)] += 1
                continue
            with open(p, encoding='utf-8-sig', newline='') as f:
                rd = csv.DictReader(f, delimiter=';')
                polya = rd.fieldnames or []
                kf = [x for x in polya if x and x.strip() in KOL_CHELOVEKA]
                if not kf or 'inn' not in [x.strip() for x in polya if x]:
                    continue
                bylo = len(est)
                for r in rd:
                    inn = (r.get('inn') or '').strip()
                    if inn and any(klyuch_cheloveka(r.get(k)) for k in kf):
                        est.add(inn)
                if len(est) > bylo:
                    sch['людей из %s' % os.path.basename(p)] += len(est) - bylo
        except Exception as e:  # noqa: BLE001
            sch['выкладка не прочитана: %s' % type(e).__name__] += 1
    for put, spisok, pole, pole_podtv in POTOKI_S_LYUDMI:
        if not os.path.exists(put):
            sch['потока нет: %s' % os.path.basename(put)] += 1
            continue
        bylo = len(est)
        for ln in open(put, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            inn = (z.get('inn') or '').strip()
            if not inn:
                continue
            if spisok:
                # НЕПОДТВЕРЖДЁННОЕ ИМЯ ПРЕДПРИЯТИЕ НЕ ЗАКРЫВАЕТ. Именной канал кладёт в поток
                # и то, что страница не подтвердила; считать это «человек уже есть» значит
                # снять цель с обхода из-за записи, которую сами же признали негодной.
                if any(klyuch_cheloveka(x.get(pole)) and (not pole_podtv or x.get(pole_podtv))
                       for x in (z.get(spisok) or [])):
                    est.add(inn)
            elif klyuch_cheloveka(z.get(pole)):
                est.add(inn)
        sch['людей из %s' % os.path.basename(put)] += len(est) - bylo
    return est, sch


def celi():
    """Предприятия p25.db с известным доменом и без единого человека."""
    sch = collections.Counter()
    b = sqlite3.connect(BAZA, uri=True)
    kol = kolonki(b, 'company')
    sch['колонки company: ' + ','.join(kol)] += 1
    nuzhno = [c for c in ('inn', 'predpriyatie', 'sayt', 'mesto_po_summe') if c in kol]
    if 'inn' not in nuzhno:
        raise SystemExit('в company нет колонки inn — читать нечем, схема изменилась')
    firmy = [dict(zip(nuzhno, r)) for r in b.execute('select %s from company' % ','.join(nuzhno))]
    sch['предприятий в p25.db'] += len(firmy)
    # Человек из самой базы это тоже человек. Колонка имени не угадывается: берём ту, что
    # действительно есть в схеме, а если связи по ИНН нет — говорим об этом, а не молчим.
    kol_p = kolonki(b, 'person')
    sch['колонки person: ' + ','.join(kol_p)] += 1
    pole_imeni = next((c for c in ('fio', 'imya', 'name', 'chelovek') if c in kol_p), '')
    est_v_baze = set()
    if 'inn' in kol_p and pole_imeni:
        for (i,) in b.execute("select distinct inn from person where trim(coalesce(%s,''))<>''"
                              % pole_imeni):
            if i:
                est_v_baze.add(str(i).strip())
        sch['ИНН с человеком в p25.db.person'] += len(est_v_baze)
    else:
        sch['p25.db.person по ИНН не связан — не используется'] += 1
    b.close()

    dom, sch_dom = domeny()
    sch.update(sch_dom)
    est, sch_est = lyudi_uzhe_est()
    sch.update(sch_est)
    est |= est_v_baze

    out = []
    for f in firmy:
        inn = str(f.get('inn') or '').strip()
        if not inn:
            continue
        sayt = dom.get(inn) or (f.get('sayt') or '').strip()
        if not sayt:
            sch['мимо: домена нет — цена человека тут ~250 запросов, канал не берёт'] += 1
            continue
        if '.' not in host(sayt) or len(host(sayt)) < 4:
            # Строка вроде «нет сайта» или «см. почту» доменом не является: `site:` от неё
            # превращается в обычное слово, и запрос уходит в общую сеть от имени этого канала.
            sch['мимо: в поле сайта не домен: %s' % sayt[:30]] += 1
            continue
        if inn in est:
            sch['мимо: человек по этому ИНН уже добыт'] += 1
            continue
        out.append({'inn': inn, 'predpriyatie': (f.get('predpriyatie') or '').strip(),
                    'mesto_po_summe': f.get('mesto_po_summe') or '',
                    'sayt': sayt})
        sch['ЦЕЛЬ: домен известен, людей нет'] += 1
    # Порядок обхода по месту в продажах: пул общий, и первые запросы должны уходить туда,
    # где закрытие дороже. Место может прийти пустым или нечисловым — тогда цель уходит в
    # конец очереди, а не роняет отбор целиком.
    def mesto(z):
        try:
            return int(z['mesto_po_summe'])
        except (TypeError, ValueError):
            return 9999
    out.sort(key=mesto)
    return out, sch


def imena(tekst):
    """Люди на странице по порядку: (начало, конец, ФИО в каноне, как написано)."""
    najdeno, zanyato = [], []
    for rx, poryadok in ((FIO, 'фио'), (FIO_OBR, 'иоф')):
        for m in rx.finditer(tekst):
            if any(m.start() < k and m.end() > n for n, k in zanyato):
                continue
            if poryadok == 'фио':
                fam, im, otch = m.group(1), m.group(2), m.group(3)
            else:
                im, otch, fam = m.group(1), m.group(2), m.group(3)
            if NE_FAMILIYA.match(fam) or NE_FAMILIYA.match(im):
                continue
            zanyato.append((m.start(), m.end()))
            najdeno.append((m.start(), m.end(), '%s %s %s' % (fam, im, otch), m.group(0)))
    najdeno.sort()
    return najdeno


def dolzhnosti_v_tekste(tekst):
    """Все вхождения должностей: (позиция, название, круг, приставка)."""
    out = []
    for nazv, rx, krug in DOLZH_TEKST:
        for m in rx.finditer(tekst):
            pr = bool(PRISTAVKA.search(tekst[max(0, m.start() - 40):m.start()]))
            out.append((m.start(), nazv, krug, pr))
    out.sort()
    return out


def dolzhnost_iz_adresa(url):
    for nazv, rx, krug in DOLZH_URL:
        if rx.search(url or ''):
            return nazv, krug
    return '', ''


def privyazat(lyudi, dolzh):
    """Должность -> человек. Одно вхождение принадлежит ровно одному имени.

    ПРАВИЛО, ОПЛАЧЕННОЕ ТРИЖДЫ: близость не доказывает принадлежности, поэтому должность
    ищется В ПОЛОСЕ ЧЕЛОВЕКА — от его имени до следующего имени, а не в окне вокруг. Окно
    ±120 знаков однажды выдало одну должность двум фамилиям сразу.

    Исключение названо прямо, а не спрятано: страница руководства часто пишет должность ПЕРЕД
    именем («Главный инженер — Иванов И. И.»), и по правилу полосы она досталась бы
    предыдущему человеку. Поэтому вхождение отходит ближайшему имени, а при равенстве —
    ПРЕДШЕСТВУЮЩЕМУ, и в выгрузку пишутся и расстояние, и порядок, чтобы видно было, какой
    именно случай сработал.
    """
    privyazka = collections.defaultdict(list)
    for poz, nazv, krug, pr in dolzh:
        luchshiy, luchshee = -1, None
        for i, (n, _k, _fio, _kak) in enumerate(lyudi):
            d = poz - n if poz >= n else n - poz
            # Равенство отдаём предшествующему имени: строгое «<» оставляет первым найденного
            # раньше, а перебор идёт слева направо.
            if luchshee is None or d < luchshee:
                luchshiy, luchshee = i, d
        if luchshiy < 0 or luchshee > PREDEL_ZNAKOV:
            continue
        privyazka[luchshiy].append({
            'dolzhnost': nazv, 'krug': krug, 'pristavka': pr, 'znakov_do_imeni': luchshee,
            'poz': poz,
            'poryadok': 'должность после имени' if poz >= lyudi[luchshiy][0]
                        else 'должность перед именем'})
    for i in privyazka:
        privyazka[i].sort(key=lambda x: x['znakov_do_imeni'])
    return privyazka


def razobrat(docs, cel, zapros):
    """Люди со страницы. Битый вход обязан падать здесь, а не превращаться в пустой ответ."""
    out, sch = [], collections.Counter()
    for d in docs:
        url = (d.get('url') or '').strip()
        # ИМЯ ПОЛЯ НЕ УГАДЫВАЕТСЯ: документ несёт ровно `url` и `tekst`. Берём все строковые
        # поля кроме адреса — тогда переименование поля в источнике канал не сломает молча.
        tekst = ' '.join(v for k, v in d.items() if k != 'url' and isinstance(v, str))
        if not tekst.strip():
            sch['документ без текста'] += 1
            continue
        svoy = yadro(url) == yadro(cel['sayt'])
        if not svoy:
            # ФИЛЬТР ДОКАЗЫВАЕТСЯ СЧЁТОМ. Документ с чужого домена при запросе `site:` значит,
            # что оператор site: не применён, и вся выдача под подозрением.
            sch['выдача вернула ЧУЖОЙ домен вопреки site:'] += 1
        # ЗАСЛОН СПРАШИВАЕТСЯ ВСЕГДА И СО ВСЕМИ АРГУМЕНТАМИ: с пустыми строками он пропускает
        # агрегаторы, то есть заслон, который никто не спрашивает как надо, хуже отсутствия.
        est, poch = CH.stranica_podtverzhdaet(url, cel['sayt'], cel['predpriyatie'], tekst,
                                              strogo=True)
        if not est:
            sch['ЗАСЛОН не пропустил страницу'] += 1
        lyudi = imena(tekst)
        if not lyudi:
            sch['страница без полного ФИО'] += 1
            continue
        privyazka = privyazat(lyudi, dolzhnosti_v_tekste(tekst))
        u_nazv, u_krug = dolzhnost_iz_adresa(url)
        for i, (n, k, fio, kak) in enumerate(lyudi):
            konec = lyudi[i + 1][0] if i + 1 < len(lyudi) else len(tekst)
            # ЦИТАТА ОБЯЗАНА СОДЕРЖАТЬ ДОКАЗАТЕЛЬСТВО. Полоса человека начинается с его имени,
            # а «Главный инженер — Иванов И. И.» ставит должность ПЕРЕД именем: цитата из одной
            # полосы показывала бы имя без должности, то есть проверить запись глазами было бы
            # нечем. Поэтому начало цитаты сдвигается к найденной должности, если она левее.
            nach_cit = n
            nashi = privyazka.get(i) or []
            if nashi and nashi[0]['poz'] < n:
                nach_cit = max(0, nashi[0]['poz'] - 20)
            polosa = tekst[nach_cit:konec]
            if nashi:
                g = nashi[0]
                nazv, krug, otkuda = g['dolzhnost'], g['krug'], 'полоса человека в тексте'
                if g['pristavka']:
                    krug = krug + ', заместитель или и.о.'
                if NE_NASH_KRUG.search(tekst[max(0, n - 120):konec][:400]):
                    krug = 'зона не наша: ' + krug
                zn, por = g['znakov_do_imeni'], g['poryadok']
                ryadom = ', '.join('%s (%d)' % (x['dolzhnost'], x['znakov_do_imeni'])
                                   for x in nashi[1:])
            elif u_nazv and not LYUBAYA_DOLZH.search(tekst[max(0, n - 120):konec][:400]):
                # Адрес страницы называет должность СТРАНИЦЫ, а не человека, поэтому берётся
                # он последним и только когда в полосе НЕ названо никакой другой должности.
                # Проверено разбором: на `…/sluzhba-glavnogo-inzhenera/` первой стоит запись
                # «Секретарь Орлова Мария Ивановна» — и без этой оговорки секретарь уезжает в
                # выкладку главным инженером. Своя должность в полосе отменяет подпись адреса.
                nazv, krug, otkuda = u_nazv, u_krug + ' (по адресу страницы)', 'адрес страницы'
                zn, por, ryadom = '', 'должность взята из адреса, а не из текста', ''
            elif u_nazv:
                nazv, krug, otkuda = '', 'в полосе названа другая должность — подпись адреса ' \
                                         'ему не принадлежит', ''
                zn, por, ryadom = '', '', u_nazv + ' (в адресе страницы)'
            else:
                # НИЧЕГО НЕ ВЫБРАСЫВАЕМ: человек без должности это всё равно имя на
                # первоисточнике, и обратный ход по нему спрашивать можно.
                nazv, krug, otkuda = '', 'должности рядом нет', ''
                zn, por, ryadom = '', '', ''
            out.append({
                'fio': fio, 'kak_napisano': kak, 'dolzhnost': nazv, 'dolzhnost_otkuda': otkuda,
                'krug': krug, 'znakov_do_imeni': zn, 'poryadok': por,
                'nomer_imeni_na_stranice': i + 1, 'dolzhnosti_ryadom': ryadom,
                'ssylka': url, 'podtverzhdena': est, 'pochemu_stranica': poch[:120],
                'domen_iz_vydachi': 'свой' if svoy else 'ЧУЖОЙ вопреки site:',
                'zapros': zapros, 'citata': polosa[:300]})
            sch['человек найден'] += 1
            if est:
                sch['человек на подтверждённой странице'] += 1
    return out, sch


def vylozhit(imya, dannye):
    """PUT на дроп с заголовком X-Drop-Token. CSV с ';' и BOM, как все выкладки сессий."""
    if not dannye:
        return 'пусто'
    b = io.StringIO()
    w = csv.DictWriter(b, delimiter=';', fieldnames=POLYA, extrasaction='ignore')
    w.writeheader()
    w.writerows(dannye)
    telo = b.getvalue().encode('utf-8-sig')
    adres = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
    req = urllib.request.Request(adres + '/' + imya, data=telo, method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''),
                                          'Content-Type': 'text/csv'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return '%s, строк %d, %d байт' % (r.status, len(dannye), len(telo))
    except Exception as e:  # noqa: BLE001
        return 'НЕ выгружено: %s' % type(e).__name__


def svod_iz_potoka():
    """Выгрузка пересобирается из ВСЕГО потока, а не из последнего прогона.

    ИСТОЧНИКИ НАКАПЛИВАЮТСЯ, А НЕ ЗАМЕНЯЮТСЯ. Один человек, найденный тремя формами запроса на
    трёх страницах одного домена, это факт, подтверждённый трижды; складывать его в одну
    ссылку значит стирать разницу между подтверждённым однажды и подтверждённым трижды.
    """
    svod, sch = {}, collections.Counter()
    if not os.path.exists(POTOK):
        return svod, sch
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            sch['строка потока не разобрана'] += 1
            continue
        for ch in (z.get('lyudi') or []):
            k = (z['inn'], klyuch_cheloveka(ch.get('fio')))
            s = svod.get(k)
            if s is None:
                s = {p: '' for p in POLYA}
                s.update({'inn': z['inn'], 'predpriyatie': z.get('predpriyatie', ''),
                          'mesto_po_summe': z.get('mesto_po_summe', ''),
                          'sayt': z.get('sayt', ''), 'istochniki': [], 'zapros': []})
                svod[k] = s
            for p in ('fio', 'kak_napisano', 'dolzhnost', 'dolzhnost_otkuda', 'krug',
                      'znakov_do_imeni', 'poryadok', 'nomer_imeni_na_stranice',
                      'dolzhnosti_ryadom', 'pochemu_stranica', 'domen_iz_vydachi', 'citata'):
                # Первой остаётся запись с ПОДТВЕРЖДЁННОЙ страницы: подтверждённое не должно
                # затираться неподтверждённым только потому, что пришло позже.
                if not s.get(p) or (ch.get('podtverzhdena') and not s.get('podtverzhdena')):
                    s[p] = ch.get(p, '')
            s['podtverzhdena'] = bool(s.get('podtverzhdena')) or bool(ch.get('podtverzhdena'))
            if ch.get('ssylka') and ch['ssylka'] not in s['istochniki']:
                s['istochniki'].append(ch['ssylka'])
            if ch.get('zapros') and ch['zapros'] not in s['zapros']:
                s['zapros'].append(ch['zapros'])
    # ОДИН ЧЕЛОВЕК У ДВУХ ПРЕДПРИЯТИЙ — то же правило, что «номер у двух людей личным не
    # считается», только про имя. Такое бывает и честно (человек сменил завод, страницы обе
    # старые), и от ошибки разбора. Строку не удаляем, а помечаем чужими ИНН: решать должен
    # человек, у которого перед глазами обе ссылки.
    po_imeni = collections.defaultdict(set)
    for inn, fio_k in svod:
        po_imeni[fio_k].add(inn)
    for (inn, fio_k), s in svod.items():
        drugie = sorted(po_imeni[fio_k] - {inn})
        s['chelovek_est_i_u_inn'] = ', '.join(drugie)
        if drugie:
            sch['ОДНО ИМЯ У НЕСКОЛЬКИХ ПРЕДПРИЯТИЙ — проверить глазами'] += 1
    for s in svod.values():
        s['istochnikov'] = len(s['istochniki'])
        s['istochniki'] = ' | '.join(s['istochniki'])
        s['zapros'] = ' | '.join(s['zapros'])
        s['podtverzhdena'] = 'да' if s['podtverzhdena'] else 'нет'
        if s['podtverzhdena'] == 'нет':
            sch['людей: страница не подтвердила'] += 1
        elif s['dolzhnost']:
            sch['ЛЮДЕЙ ПОДТВЕРЖДЕНО С ДОЛЖНОСТЬЮ'] += 1
        else:
            sch['людей подтверждено без должности'] += 1
    return svod, sch


def otdat():
    svod, sch = svod_iz_potoka()
    strok = list(svod.values())
    fajly = {
        VYHOD[0][0]: [s for s in strok if s['podtverzhdena'] == 'да' and s['dolzhnost']],
        VYHOD[1][0]: [s for s in strok if s['podtverzhdena'] == 'да' and not s['dolzhnost']],
        VYHOD[2][0]: [s for s in strok if s['podtverzhdena'] == 'нет'],
    }
    itog = {}
    for imya, dann in fajly.items():
        itog[imya] = vylozhit(imya, dann)
    return itog, sch


def proba():
    """Самопроверка прибора: РАЗЛИЧЕНИЕ, а не непустота.

    Три условия, каждое числом. Непустой ответ ничего не доказывает: фильтр площадки однажды
    отвечал бодрой выдачей, не будучи применён вовсе, и 2 399 карточек уехали не тем.

    Разбор и заслон проверяются БЕЗ СЕТИ и потому проверяются всегда: если поисковый модуль не
    поднялся, три обязательных условия всё равно должны быть названы числом, а про сеть надо
    сказать «не проверено», а не молча выдать её отсутствие за успех.
    """
    # 1. РАЗЛИЧЕНИЕ РАЗБОРА, без сети: два разных набора документов обязаны дать РАЗНЫХ людей.
    cel_a = {'inn': '1', 'predpriyatie': 'АО «Каустик»', 'sayt': 'http://kaustik.ru'}
    cel_b = {'inn': '2', 'predpriyatie': 'ПАО «КАМАЗ»', 'sayt': 'https://kamaz.ru'}
    doc_a = [{'url': 'https://kaustik.ru/about/management/',
              'tekst': 'Руководство. Главный инженер Петров Пётр Петрович. '
                       'Главный энергетик Сидоров Сидор Сидорович.'}]
    doc_b = [{'url': 'https://kamaz.ru/company/structure/',
              'tekst': 'Технический директор Иванов Иван Иванович.'}]
    a, _ = razobrat(doc_a, cel_a, 'проба А')
    b, _ = razobrat(doc_b, cel_b, 'проба Б')
    imena_a = sorted(x['fio'] for x in a)
    imena_b = sorted(x['fio'] for x in b)
    razlichaet = bool(imena_a) and bool(imena_b) and imena_a != imena_b
    print('  А: %s' % json.dumps([(x['fio'], x['dolzhnost'], x['znakov_do_imeni'])
                                  for x in a], ensure_ascii=False))
    print('  Б: %s' % json.dumps([(x['fio'], x['dolzhnost'], x['znakov_do_imeni'])
                                  for x in b], ensure_ascii=False))
    # 2. БЕССМЫСЛИЦА ДАЁТ НОЛЬ: текст без людей и заведомо чужая страница.
    bred, _ = razobrat([{'url': 'https://kaustik.ru/x', 'tekst': 'кастрюлякастрюля 12345 доб.'}],
                       cel_a, 'проба бессмыслица')
    # Заслон обязан ОТКАЗАТЬ агрегатору, иначе он не спрашивается по-настоящему.
    zaslon_agr, poch_agr = CH.stranica_podtverzhdaet('https://checko.ru/company/ao-kaustik-1',
                                                     'http://kaustik.ru', 'АО «Каустик»',
                                                     'АО Каустик выписка', strogo=True)
    zaslon_svoy, _ = CH.stranica_podtverzhdaet('https://kaustik.ru/about/management/',
                                               'http://kaustik.ru', 'АО «Каустик»',
                                               'руководство', strogo=True)
    # 3. БИТЫЙ ВХОД ДАЁТ ПАДЕНИЕ: разбор не имеет права молча вернуть пустой список.
    upalo = False
    try:
        razobrat(None, cel_a, 'проба битая')
    except Exception:  # noqa: BLE001
        upalo = True
    upalo_polya = False
    try:
        # Документ, который не словарь, — это сломанный источник, и он обязан уронить разбор.
        # А вот документ-словарь БЕЗ знакомых полей ронять не должен: текст собирается из всех
        # строковых полей кроме адреса, поэтому переименование поля в источнике канал
        # переживёт, а пустой документ уйдёт в счётчик «документ без текста» и будет виден.
        razobrat(['это не словарь'], cel_a, 'проба битая 2')
    except Exception:  # noqa: BLE001
        upalo_polya = True
    bez_polej, sch_bez = razobrat([{'net_takogo_polya': 1}], cel_a, 'проба без полей')
    # Сетевая часть: жив ли оператор site:. Отказ канала это ЛОЖНЫЙ НОЛЬ, и он называется так.
    seti, nabory = {}, []
    try:
        serp = _serp()
    except SystemExit as e:
        seti['поисковый модуль'] = 'не поднялся: %s' % e
        serp = None
    for c in ((cel_a, cel_b) if serp else ()):
        # Запрос кладётся в отчёт ЦЕЛИКОМ: половина ошибок этого канала видна прямо в его
        # тексте («site:kaustik» без домена первого уровня), и никакой счётчик их не покажет.
        q = FORMY[0] % host(c['sayt'])
        docs, err = serp(q)
        if err:
            seti[q] = 'канал не ответил (ложный ноль): ' + err[:70]
            nabory.append(None)
            continue
        svoih = len([d for d in docs if yadro(d.get('url')) == yadro(c['sayt'])])
        nabory.append(frozenset(d.get('url', '') for d in docs))
        seti[q] = 'документов %d, на своём домене %d' % (len(docs), svoih)
        if docs:
            print('  ключи документа выдачи (не угаданные, снятые): %s'
                  % json.dumps(sorted(docs[0].keys()), ensure_ascii=False))
    if serp:
        docs_b, err_b = serp(FORMY[0] % 'takogo-domena-net-12345.ru')
        seti['бессмысленный домен'] = ('канал не ответил: ' + err_b[:70]) if err_b \
            else 'документов %d (должно быть 0)' % len(docs_b)
    # «Не проверено» это отдельный ответ, а не «да» и не «нет»: канал бывает занят, и молча
    # выдать его молчание за успех значит повторить ложный ноль на самой проверке.
    site_razlichaet = ('не проверено: канал не ответил или модуль поиска не поднялся'
                       if len(nabory) < 2 or any(n is None for n in nabory)
                       else nabory[0] != nabory[1])

    print('REC разбор различает два входа\t%d' % int(razlichaet))
    print('REC бессмыслица даёт людей\t%d' % len(bred))
    print('REC битый вход уронил разбор\t%d' % int(upalo and upalo_polya))
    print('REC заслон отказал агрегатору\t%d' % int(not zaslon_agr))
    print('REC заслон принял свой домен\t%d' % int(zaslon_svoy))
    print('REC документ без знакомых полей: людей %d, счётчик %s'
          % (len(bez_polej), json.dumps(dict(sch_bez), ensure_ascii=False)))
    print('REC сеть: %s' % json.dumps(seti, ensure_ascii=False))
    print('ИТОГ ' + json.dumps({
        'разбор различает два входа': razlichaet,
        'бессмыслица даёт ноль': len(bred) == 0,
        'битый вход даёт падение': upalo and upalo_polya,
        'заслон отказывает агрегатору': not zaslon_agr,
        'причина отказа заслона': poch_agr[:80],
        'оператор site: различает домены': site_razlichaet,
    }, ensure_ascii=False))


def main():
    if '--proba' in sys.argv:
        proba()
        return
    if '--vylozhit' in sys.argv:
        fajly, sch = otdat()
        for k, v in sch.most_common():
            print('REC %s\t%d' % (k, v))
        print('ИТОГ ' + json.dumps({'файлы': fajly}, ensure_ascii=False))
        return

    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 120
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 6
    pot = max(1, min(pot, 8))     # пул общий на три сессии: больше восьми потоков не наши
    serp = _serp()
    vse, sch_otbor = celi()
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            # Запись со сбоем цель НЕ закрывает: иначе занятость канала выглядит как «спросили».
            if not z.get('err'):
                gotovo.add(z['inn'])
    zad = [z for z in vse if z['inn'] not in gotovo][:lim]
    print('целей %d, уже спрошено %d, к обходу %d, потоков %d'
          % (len(vse), len(gotovo), len(zad), pot), file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    itog = collections.Counter()

    def odin(c):
        d = host(c['sayt'])
        lyudi, zaprosy, err, sch = [], [], '', collections.Counter()
        for forma in FORMY:
            q = forma % d
            zaprosy.append(q)
            docs, e = serp(q)
            if e:
                # Признак провала берётся у источника: serp отдаёт непустой err. Проверять
                # «пусто ли docs» нельзя — честный ноль выдачи выглядел бы сбоем и наоборот.
                err = e
                continue
            try:
                nashli, s = razobrat(docs, c, q)
            except Exception as ex:  # noqa: BLE001
                # Падение разбора это тоже сбой цели, а не её закрытие: пишем и переспросим.
                err = 'разбор упал: %s: %s' % (type(ex).__name__, str(ex)[:80])
                continue
            lyudi += nashli
            sch.update(s)
            if any(x['podtverzhdena'] for x in nashli):
                break     # Первая форма с ПОДТВЕРЖДЁННЫМ человеком останавливает перебор.
        return {'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                'mesto_po_summe': c['mesto_po_summe'], 'sayt': c['sayt'], 'domen': d,
                'zaprosy': zaprosy, 'zaprosov': len(zaprosy),
                'err': err if not lyudi else '', 'lyudi': lyudi, 'sch': dict(sch)}

    primerov = 0
    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())      # результат обязан пережить смерть задания по таймауту
                itog.update(r['sch'])
                itog['запросов'] += r['zaprosov']
                if r['err']:
                    itog['СБОЙ (цель не закрыта, будет переспрошена)'] += 1
                elif not r['lyudi']:
                    itog['людей на домене не нашлось — честный ноль'] += 1
                else:
                    itog['предприятий с людьми'] += 1
                # Примеры печатаются ПЕРВЫМИ: раннер отдаёт хвост вывода, и счётчики внизу.
                if primerov < 12 and any(x['podtverzhdena'] and x['dolzhnost']
                                         for x in r['lyudi']):
                    ch = next(x for x in r['lyudi'] if x['podtverzhdena'] and x['dolzhnost'])
                    print('%-34s %-32s %-22s %s знаков, %s | %s'
                          % (r['predpriyatie'][:34], ch['fio'], ch['dolzhnost'],
                             ch['znakov_do_imeni'], ch['dolzhnost_otkuda'], ch['ssylka'][:60]))
                    primerov += 1
    f.close()

    fajly, sch_vyl = otdat()
    for k, v in sch_otbor.most_common(14):
        print('REC отбор: %s\t%d' % (k, v))
    for k, v in itog.most_common():
        print('REC прогон: %s\t%d' % (k, v))
    for k, v in sch_vyl.most_common():
        print('REC выгрузка: %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({
        'спрошено предприятий': len(zad),
        'осталось целей': len(vse) - len(gotovo) - len(zad),
        'запросов': itog['запросов'],
        'людей найдено': itog['человек найден'],
        'людей на подтверждённой странице': itog['человек на подтверждённой странице'],
        'заслон не пропустил страниц': itog['ЗАСЛОН не пропустил страницу'],
        'чужой домен вопреки site:': itog['выдача вернула ЧУЖОЙ домен вопреки site:'],
        'сбоев': itog['СБОЙ (цель не закрыта, будет переспрошена)'],
        'файлы': fajly,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
