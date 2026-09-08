# -*- coding: utf-8 -*-
"""ПЕРЕЧЕНЬ ОБЪЕКТОВ ОПО предприятия ПО ОДНОМУ ИНН — из реестра заключений ЭПБ Ростехнадзора.

ЗАЧЕМ. Наименование ОПО прямо называет машину: «Площадка компрессорной станции», «Площадка
воздухоразделительной установки», «Сеть газопотребления», «Площадка производства …». Это
доказательство силы 1: надзорная запись про объект В ЭКСПЛУАТАЦИИ, а не намерение купить.

ОТКУДА БЕРЁМ (и почему не откуда-то ещё; проверено 09.08.2026, не додумано):
  * `centrifugal-core-opo.csv` и `checko-opo-*.csv` на дропе — это ФЛАГ «ОПО есть» (колонка
    rtn_opo = True), собранный `_opo_worker` из `enrich_contacts.py` со страницы лицензий
    checko.ru. Перечня объектов там нет и быть не может: страница про лицензию, не про реестр.
  * `find_opo_signal` (там же) — не реестр, а ЭВРИСТИКА: SERP-запрос в xmlriver «<компания>
    опасный производственный объект компрессорная станция реестр Ростехнадзор» и поиск типа
    объекта в сниппете. Сам автор пометил её «НЕ авторитетно». Как источник перечня не годится.
  * `e-ecolog.ru` (агрегатор реестра ОПО) на все адреса отвечает антибот-страницей
    «Sorry, your request has been denied» — код 200, данных ноль. Оболочка с кодом 200 данными
    не считается.
  * `gosnadzor.gov.ru` с нашего адреса недоступен (403 / нет соединения).
  * РАБОЧИЙ канал: `monitor-pb.ru` — публикация реестра ЗЭПБ Ростехнадзора. В записи реестра
    ОПО назван ДВАЖДЫ: отдельным полем карточки «Наименование ОПО» / «Регистрационный № ОПО»
    и внутри текста объекта экспертизы («… Наименование ОПО Сеть газопотребления АО «БелЗАН»
    Рег №ОПО/ класс опасности А41-00239-0003/III класс опасности»). Ссылка на запись есть у
    каждой строки, то есть каждое наше утверждение перепроверяемо.

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ `mpb_po_inn.py`. Тот собирает ЗАКЛЮЧЕНИЯ (машина + срок ЭПБ). Здесь из
тех же записей вынимается ДРУГАЯ сущность — сам опасный производственный объект: его
наименование, рег-номер и класс опасности, со схлопыванием повторов. У предприятия сотни
заключений, но объектов ОПО единицы; на выходе нужен перечень объектов, а не список бумаг.

ДВА КАНАЛА ИЗВЛЕЧЕНИЯ, оба из одного и того же текста реестра:
  1) СПИСОК `/conclusions?exploiter=<ИНН>` — в атрибуте `title` у кнопки лежит ПОЛНЫЙ текст
     объекта, часто вместе с «Наименование ОПО …», рег-номером и классом. Это даром: одна
     страница на 25 записей.
  2) КАРТОЧКА `/conclusion/<код>` — отдельные поля «Наименование ОПО» и «Регистрационный
     № ОПО». Они бывают заполнены ТАМ, ГДЕ В ТЕКСТЕ ИХ НЕТ (проверено: 41-ТУ-31942-2022 у
     БелЗАН — в списке только «Компрессор 4ВМ10-100/8…», в карточке поле «Площадка
     производства АО «БелЗАН»»). Обратное тоже верно: у АО «ПОЛИЭФ» поле пустое, а имя ОПО
     стоит в скобках внутри текста. Поэтому каналы дополняют друг друга, и ни один нельзя
     выкинуть. Карточка стоит запроса на запись, поэтому берётся выборкой с шагом и бюджетом.

Использование:
    python3 park_opo_po_inn.py 0255010527
    python3 park_opo_po_inn.py --spisok inns.txt --out park-opo.jsonl
    python3 park_opo_po_inn.py --csv engineers-lens/PARK-FAKTY-2S-EPB.csv --skolko 20

Выход — jsonl, по строке на ОБЪЕКТ ОПО:
    {inn, naimenovanie_obekta, klass_opasnosti, ssylka, citata, data, ...}
`ssylka` — запись реестра, из которой взято наименование. Строк без ссылки не бывает.
"""
import argparse
import csv
import html
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:  # noqa: BLE001
    pass

BAZA = 'https://monitor-pb.ru'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
PAUZA = float(os.environ.get('PARK_OPO_PAUZA', '0.7'))

TR = re.compile(r'<tr>(.*?)</tr>', re.S)
NOMER = re.compile(r'href="/conclusion/([^"]+)"')
DATA = re.compile(r'tabular-nums[^>]*>([\d.]{8,10})<')
TITLE = re.compile(r'<button[^>]*title="([^"]{20,})"')
VSEGO = re.compile(r'из <span[^>]*>(\d[\d\s ]*)</span>')
# Поля КАРТОЧКИ. Разметка списка и карточки разные — это уже стоило прогона с нулём автору
# mpb_po_inn.py, повторять не будем: карточка разбирается своими шаблонами.
K_NAIM = re.compile(r'>Наименование ОПО</div><div class="[^"]*">(.*?)</div>')
K_REG = re.compile(r'>Регистрационн\w+ № ОПО</div><div class="[^"]*">(.*?)</div>')

# ТИПЫ ОПО из перечня к 116-ФЗ: с этих слов начинается наименование объекта в реестре.
# Список закрытый НАМЕРЕННО. Без него в «наименование ОПО» уезжает половина текста
# заключения: «Компрессор 4ВМ10-100/8, установленный в помещении компрессорной станции» —
# это МАШИНА на объекте, а не объект. Разница в том, с чего строка НАЧИНАЕТСЯ.
TIP = (r'(?:Площадк\w+|Участок|Участк\w+|Цех\b|Цеха\b|Сеть\s+газо\w+|Систем\w+\s+газо\w+|'
       r'Сети\s+газо\w+|Склад\w*|Станци\w+|Установк\w+|Котельн\w+|Групп\w+\s+котельн\w+|'
       r'Карьер\b|Карьер[аы]\b|Рудник\w*|Шахт\w+|Транспортн\w+\s+участок|Комплекс\w*|'
       r'База\b|Пункт\b|Полигон\w*|Резервуарн\w+\s+парк|'
       r'Аммиачно[- ]холодильн\w+|Элеватор\w*|Мельниц\w+|Пристань|Причал\w*|'
       r'Сеть\s+теплоснабжен\w+)')
# «Корпус 101 (инв. № 0000546) цеха №2…», «Отделение…», «Производство ТКФ мощностью 230 тыс.т…»
# и «Территория…» из TIP тоже убраны: на прогоне 20 ИНН они дали здания и куски проектных
# названий вместо объектов реестра. Площадка/цех/установка эти же случаи ловят правильно.
# НЕ типы ОПО, а объекты экспертизы: «газопровод среднего давления от эстакады…»,
# «технологический трубопровод…», «печь…». Реестр называет ОПО «Сеть газопотребления», а
# газопровод — это сооружение НА объекте. Держать их в TIP значило пускать в перечень
# объектов детали оборудования (проверено на прогоне: у АО «БелЗАН» так пролезла строка
# «газопровод среднего давления от эстакады по крыше главного корпуса»).
NACH_TIP = re.compile(r'^\s*' + TIP, re.I)
# Начала имени ОПО в тексте записи. КАНАЛ 1 — явное поле: пишут и «Наименование ОПО:», и
# «Наименование ОПОСеть …» (без пробела — так реестр склеивает ячейки таблицы), и
# «Наименование ОПО «…»». КАНАЛ 2 — «на опасном производственном объекте: <имя>».
POLE = re.compile(r'Наименовани\w*\s*ОПО\s*[:\-–]?\s*[«"]?\s*', re.I)
POSLE_OBEKTE = re.compile(r'производственн\w+\s+объект\w*\s*[:\-–№]?\s*[«"]?\s*', re.I)
# Канал 3: имя ОПО в скобках рядом с машиной — «(Площадка производства АО «ПОЛИЭФ», корпус 830)»
V_SKOBKAH = re.compile(r'\(\s*(' + TIP + r'[^()]{3,180})\)')
# ГДЕ ИМЯ КОНЧАЕТСЯ. Режем по ЦЕЛОМУ маркеру-хвосту, а не «до первой кавычки»: у АО «БМК»
# запись выглядит как `объекте "Площадка производства АО "БМК" IY класса опасности` — ленивый
# разбор «до кавычки» обрывал имя на «Площадка производства АО». Класс опасности в маркер
# входит вместе с цифрой, иначе он же и обрежет имя на слове «класс».
RIMSK = r'(?:[IVХXУY]{1,4}|[1-4])'
STOP = re.compile(r'\s*' + RIMSK + r'\s*(?:[-–]?\s*(?:го|ый|ой|й))?\s*класс\w*\s*опаснос'
                  r'|\s*[Рр]ег\.?\s*№|\s*Регистрационн|\s*Адрес\s+ОПО|\s*Эксплуатирующ\w*\s'
                  r'|\s*находящ|\s*располож|\s*по\s+адресу|\s*Объект\s+экспертиз|\s*\|'
                  r'|\s*\(\s*(?:рег|№|А\s?-?\s?\d{2}\s?-\s?\d{5})', re.I)
# НЕ ОБЪЕКТ, А БУМАГА. Заключения по техперевооружению названы «Установка массового
# расходомера на трубопроводе…», «Установка обратного клапана…» — по форме это «Установка …»,
# по сути монтаж прибора. Такие имена в перечень объектов пускать нельзя.
NE_OBEKT = re.compile(r'расходомер|клапан|щит\w*|датчик|прибор учёт|прибор учет|'
                      r'самосвал|экскаватор|автокран|бульдозер|'
                      r'замен\w+\s+(?:трубопровод|аппарат|оборудован)|монтаж|демонтаж|'
                      r'техническ\w+\s+перевооружен|реконструкц|проектн\w+\s+документац|'
                      r'мощностью\s+\d', re.I)
KLASS = re.compile(RIMSK + r'\s*[-–]?\s*(?:ый|ой|го|й)?\s*класс\w*\s+опаснос', re.I)
KLASS_OBR = re.compile(r'класс\w*\s+опаснос\w*\s*[:\-–]?\s*' + RIMSK, re.I)
# Рег-номер ОПО пишут и «А41-00239-0003», и «А-41-00238-0009», и с пробелами.
REG = re.compile(r'\bА\s?-?\s?\d{2}\s?-\s?\d{5}\s?-\s?\d{3,4}\b')
REG_KOROTKO = re.compile(r'\bА\s?-?\s?\d{2}\s?-\s?\d{5}\b')
RIM = {'1': 'I', '2': 'II', '3': 'III', '4': 'IV'}
KLASSY = ('I', 'II', 'III', 'IV')


def bez_tegov(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def _vzyat(url, popytok=3):
    for p in range(popytok):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return '__ОШИБКА__ %s: %s' % (type(e).__name__, str(e)[:90])
            time.sleep(1.5 * (p + 1))


def otrezat(hvost):
    """Имя ОПО из куска текста, начинающегося с имени: до первого маркера-хвоста."""
    s = hvost[:220]
    m = STOP.search(s)
    if m and m.start() >= 5:
        s = s[:m.start()]
    return pochistit(s)


def pochistit(s, glubina=3):
    """Убрать обрамление, не съев кавычки внутри имени («Площадка производства АО "БМК"»).

    ЧИСТИТ ПО КРУГУ, пока строка меняется. За один проход не выходит: у АО «БелЗАН» запись
    обрывается как `Сеть газопотребления АО «БелЗАН»» (` — сперва надо снять висячую скобку,
    и только потом видно, что закрывающих кавычек на одну больше. Один проход оставлял
    `…«БелЗАН»»`."""
    ishodnoe = s or ''
    s = re.sub(r'\s+', ' ', html.unescape(s or '')).strip()
    s = s.replace('“', '«').replace('”', '»').replace('„', '«').replace('‟', '»')
    s = s.strip(' \t\'.,;:-–—')
    # непарные кавычки — обрамление, парные — часть имени
    if s.startswith('«') and s.count('«') > s.count('»'):
        s = s[1:]
    while s.endswith('»') and s.count('»') > s.count('«'):
        s = s[:-1]   # «…АО «БелЗАН»» — внешняя кавычка реестра, не часть имени
    if s.count('"') % 2:
        s = s[1:] if s.startswith('"') else (s[:-1] if s.endswith('"') else s)
    if s.count('«') == s.count('»') + 1:
        s += '»'   # «Площадка производства АО «БелЗАН → добиваем закрывающую
    if s.count('(') > s.count(')'):
        s = s[:s.rfind('(')]   # оборванная скобка — хвост чужой мысли, не часть имени
    s = s.strip(' \t.,;:-–—')
    return pochistit(s, glubina - 1) if (glubina > 0 and s != ishodnoe) else s


def klass_iz(txt):
    """Класс опасности римской цифрой. Пусто — значит в записи его нет, а не «нет класса»."""
    m = KLASS.search(txt) or KLASS_OBR.search(txt)
    if not m:
        return ''
    v = re.sub(r'[^IVХXУY1-4]', '', m.group(0).upper())[:4]
    if v in RIM:
        return RIM[v]
    # «IY класса опасности» — латинская Y вместо V, встречается в реестре как опечатка
    v = v.replace('Y', 'V').replace('У', 'V').replace('Х', '').replace('X', '')
    return v if v in KLASSY else ''


def reg_iz(txt):
    m = REG.search(txt) or REG_KOROTKO.search(txt)
    return re.sub(r'\s|(?<=А)-', '', m.group(0)) if m else ''


def imena_iz_teksta(txt):
    """Все наименования ОПО из текста записи реестра. Возврат: [(имя, канал)]."""
    out = []
    for m in POLE.finditer(txt):
        im = otrezat(txt[m.end():])
        if len(im) >= 5:
            out.append((im, 'поле «Наименование ОПО»'))
    if not out:
        for m in POSLE_OBEKTE.finditer(txt):
            im = otrezat(txt[m.end():])
            if len(im) >= 5:
                out.append((im, 'текст «на ОПО: …»'))
    for m in V_SKOBKAH.finditer(txt):
        im = pochistit(m.group(1))
        if len(im) >= 5:
            out.append((im, 'скобки в тексте объекта'))
    if not out and NACH_TIP.search(txt):
        im = otrezat(txt)
        if 5 <= len(im) <= 200:
            out.append((im, 'текст объекта целиком'))
    # оставляем только то, что НАЧИНАЕТСЯ с типа ОПО и не является названием работ:
    # остальное — машина или бумага, а не объект
    return [(i, k) for i, k in out if NACH_TIP.search(i) and not NE_OBEKT.search(i)]


# ЧЕМ ПОДТВЕРЖДЕНО. Каналы неравноценны, и смешивать их в одну кучу нечестно: поле реестра —
# это ответ самого реестра на вопрос «как называется ОПО», а «текст объекта целиком» — догадка
# по началу строки, где имя ОПО не отделено от машины («установка №2, цех №52, завод Мономер
# Конденсатор-холодильник поз. Т-305»). Колонка позволяет отобрать только твёрдое.
SILA = {
    'поле карточки «Наименование ОПО»': 'высокая: отдельное поле записи реестра',
    'поле «Наименование ОПО»': 'высокая: подпись «Наименование ОПО» в тексте записи',
    'текст «на ОПО: …»': 'высокая: «на опасном производственном объекте …»',
    'скобки в тексте объекта': 'средняя: имя ОПО в скобках при машине',
    'текст объекта целиком': 'низкая: имя ОПО не отделено от машины',
}


def klyuch(imya):
    return re.sub(r'[^а-яёa-z0-9]', '', imya.lower())[:70]


def citata_dlya(txt, imya):
    """Кусок исходного текста ВОКРУГ найденного имени: доказательство, а не пересказ."""
    i = txt.find(imya[:40])
    if i < 0:
        return txt[:220]
    return re.sub(r'\s+', ' ', txt[max(0, i - 70):i + len(imya) + 90]).strip()


def stroki_spiska(h):
    """Записи со страницы списка. Пустой список = СБОЙ РАЗБОРА, а не «нет данных»."""
    out = []
    for tr in TR.findall(h):
        n = NOMER.search(tr)
        if not n:
            continue
        t = TITLE.search(tr)
        d = DATA.search(tr)
        out.append({'kod': n.group(1),
                    'data': d.group(1) if d else '',
                    'text': re.sub(r'\s+', ' ', html.unescape(t.group(1))) if t else ''})
    return out


def stranicy_dlya(maks, skolko, podryad):
    """Какие страницы списка качать. По умолчанию — ВРАЗБРОС по всему реестру.

    Почему не первые N подряд: список отсортирован по дате, и первые 150 записей крупного
    завода — это один цех одного года. У ООО «Газпром нефтехим Салават» 20 870 заключений;
    шесть первых страниц покажут объекты последнего месяца и создадут ложное «у завода один
    ОПО». Равномерный разброс по всей пагинации за те же шесть запросов достаёт объекты
    разных лет и разных производств."""
    if maks <= 1:
        return [1]
    if podryad or skolko >= maks:
        return list(range(1, min(maks, skolko) + 1))
    shag = (maks - 1) / float(skolko - 1) if skolko > 1 else 0
    return sorted(set(int(round(1 + i * shag)) for i in range(skolko)))


def po_inn(inn, stranic=6, kart=20, stop_posle=10, podryad=False):
    """Перечень объектов ОПО одного ИНН. Возврат: (объекты, справка, ошибка)."""
    zapisi, seen_kod = [], set()
    vsego_v_reestre = 0
    # число страниц — из САМИХ ссылок пагинации. Угадывать нельзя: на непонятный параметр
    # реестр отдаёт ту же первую страницу, и цикл ушёл бы в вечность.
    h = _vzyat('%s/conclusions?exploiter=%s' % (BAZA, inn))
    if h.startswith('__ОШИБКА__'):
        return [], {}, h
    stranicy = [int(x) for x in re.findall(
        r'href="/conclusions\?[^"]*exploiter=%s[^"]*page=(\d+)' % inn, h)]
    maks = max(stranicy) if stranicy else 1
    v = VSEGO.search(h)
    if v:
        vsego_v_reestre = int(re.sub(r'\D', '', v.group(1)))
    spisok_stranic = stranicy_dlya(maks, stranic, podryad)
    for st in spisok_stranic:
        if st > 1:
            h = _vzyat('%s/conclusions?exploiter=%s&page=%d' % (BAZA, inn, st))
            if h.startswith('__ОШИБКА__'):
                return [], {}, h
            time.sleep(PAUZA)
        rows = stroki_spiska(h)
        if not rows:
            continue
        for r in rows:
            if r['kod'] in seen_kod:
                continue
            seen_kod.add(r['kod'])
            zapisi.append(r)

    obekty = {}

    def dobavit(imya, kanal, txt, kod, data):
        """Один объект — одна строка. Одно и то же ОПО разные эксперты пишут по-разному
        («Сеть газопотребления АО «БелЗАН»» и «…АО «Белзан» (А41-00239-0003»), поэтому
        совпадением считается и ВЛОЖЕНИЕ ключа: иначе перечень объектов раздувается
        вариантами написания одного объекта."""
        k = klyuch(imya)
        if not k:
            return False
        for k2, ob in list(obekty.items()):
            if k == k2 or k.startswith(k2) or k2.startswith(k):
                if not ob['klass_opasnosti'] and klass_iz(txt):
                    ob['klass_opasnosti'] = klass_iz(txt)
                if not ob['reg_nomer_opo'] and reg_iz(txt):
                    ob['reg_nomer_opo'] = reg_iz(txt)
                if len(imya) > len(ob['naimenovanie_obekta']):
                    ob['naimenovanie_obekta'] = imya
                    ob['ssylka'] = '%s/conclusion/%s' % (BAZA, kod)
                    ob['citata'] = citata_dlya(txt, imya)
                    ob['data'] = data
                    ob['otkuda'] = kanal
                    ob['dostovernost'] = SILA.get(kanal, '')
                    ob['zaklyuchenie'] = urllib.parse.unquote(kod)
                return False
        obekty[k] = {
            'inn': inn,
            'naimenovanie_obekta': imya,
            'klass_opasnosti': klass_iz(txt),
            'reg_nomer_opo': reg_iz(txt),
            'ssylka': '%s/conclusion/%s' % (BAZA, kod),
            'citata': citata_dlya(txt, imya),
            'data': data,
            'otkuda': kanal,
            'dostovernost': SILA.get(kanal, ''),
            'zaklyuchenie': urllib.parse.unquote(kod),
        }
        return True

    # КАНАЛ 1 — даром, из уже скачанных страниц списка.
    bez_imeni = []
    for r in zapisi:
        nashli = False
        for imya, kanal in imena_iz_teksta(r['text']):
            dobavit(imya, kanal, r['text'], r['kod'], r['data'])
            nashli = True
        if not nashli:
            bez_imeni.append(r)

    # КАНАЛ 2 — карточки, выборкой с шагом по ВСЕМУ списку (а не первые N подряд: подряд идут
    # заключения одного цеха одного года, и выборка «сверху» показала бы один объект из пяти).
    #
    # ПУСТАЯ КАРТОЧКА — НЕ ПРИЗНАК НАСЫЩЕНИЯ. Первая версия обрывала добор после `stop_posle`
    # карточек подряд без имени, и это дало ЛОЖНЫЙ НОЛЬ: у АО «Мелеузовские минеральные
    # удобрения» (0263009557) прибор вернул «объектов ОПО 0», а ручная проверка 12 случайных
    # карточек нашла поле заполненным у трёх — там «Площадка компрессорного участка
    # организации». Поле в реестре заполнено примерно у четверти записей, десять пустых подряд
    # при такой доле — норма, а не конец данных. Поэтому расход ограничен ТОЛЬКО бюджетом
    # карточек, а досрочный выход — лишь по насыщению (имена перестали быть новыми).
    kart_sdelano = 0
    bez_novogo = 0
    kart_pustyh = 0
    if kart > 0 and bez_imeni:
        shag = max(1, len(bez_imeni) // kart)
        for r in bez_imeni[::shag][:kart]:
            ch = _vzyat('%s/conclusion/%s' % (BAZA, r['kod']))
            kart_sdelano += 1
            time.sleep(PAUZA)
            if ch.startswith('__ОШИБКА__'):
                continue
            n = K_NAIM.search(ch)
            g = K_REG.search(ch)
            imya = pochistit(bez_tegov(n.group(1))) if n else ''
            if not imya:
                kart_pustyh += 1
                continue
            txt = imya + ((' Рег № ОПО ' + bez_tegov(g.group(1))) if g else '') + ' | ' + r['text']
            if dobavit(imya, 'поле карточки «Наименование ОПО»', txt, r['kod'], r['data']):
                bez_novogo = 0
            else:
                bez_novogo += 1
                if len(obekty) >= 2 and bez_novogo >= stop_posle:
                    break   # насыщение: имена идут, но все уже известные

    spravka = {'zaklyucheniy_v_reestre': vsego_v_reestre, 'stranic_vzyato': len(spisok_stranic),
               'stranic_vsego': maks, 'zapisey_prosmotreno': len(zapisi),
               'bez_imeni_v_tekste': len(bez_imeni), 'kartochek_skachano': kart_sdelano,
               'kartochek_bez_polya': kart_pustyh}
    return list(obekty.values()), spravka, ''


def samoproverka():
    """КОНТРОЛЬ ПРИБОРА. Ноль объектов на прогоне обязан означать «в реестре их нет»,
    а не «разбор сломался». Поэтому разбор гоняется по эталонам ДО сети, на каждом запуске."""
    obr = [
        ('ЗАКЛЮЧЕНИЕ … Объект экспертизы: Газопровод к термоагрегату «Ipsen» Адрес ОПО: 452002, '
         'РБ, г. Белебей Наименование ОПОСеть газопотребления АО «БелЗАН» Рег №ОПО/ класс '
         'опасности А41-00239-0003/III класс опасности Эксплуатирующая организация: АО «БелЗАН»',
         'Сеть газопотребления АО «БелЗАН»', 'III', 'А41-00239-0003'),
        ('сооружение Резервуар для хранения уксусной кислоты поз. Е23/1, зав.№У-07-6254, '
         'рег. №105 (Площадка производства АО «ПОЛИЭФ», корпус 830)',
         'Площадка производства АО «ПОЛИЭФ», корпус 830', '', ''),
        ('Компрессор 4ВМ10-100/8, зав.№342, установленный в помещении компрессорной станции',
         None, '', ''),   # это МАШИНА, а не объект: имени ОПО тут нет
        ('Кран мостовой, прокатный цех АО БМК», применяемый на опасном производственном '
         'объекте "Площадка производства АО "БМК" IY класса опасности рег.№А-41-00238-0009, '
         'находящийся по адресу:453500, Республика Башкортостан',
         'Площадка производства АО "БМК"', 'IV', 'А41-00238-0009'),
    ]
    ok = True
    for txt, zhdem, kl, rg in obr:
        got = imena_iz_teksta(txt)
        imya = got[0][0] if got else None
        if zhdem is None:
            horosho = not got
        else:
            horosho = bool(imya) and klyuch(imya) == klyuch(zhdem)
        horosho = horosho and klass_iz(txt) == kl and reg_iz(txt) == rg
        ok = ok and horosho
        print('   КОНТРОЛЬ %s: %s | класс «%s» рег «%s»'
              % ('OK ' if horosho else 'СБОЙ', imya, klass_iz(txt), reg_iz(txt)))
    return ok


def inn_iz_csv(put, kolonka='inn', skolko=0):
    with io.open(put, 'r', encoding='utf-8-sig', errors='replace', newline='') as f:
        head = f.readline()
        delim = ';' if head.count(';') >= head.count(',') else ','
        f.seek(0)
        rd = csv.DictReader(f, delimiter=delim)
        out, s = [], set()
        for r in rd:
            v = re.sub(r'\D', '', (r.get(kolonka) or ''))
            if v and v not in s:
                s.add(v)
                out.append(v)
                if skolko and len(out) >= skolko:
                    break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inn', nargs='*')
    ap.add_argument('--spisok', help='файл со списком ИНН, по одному в строке')
    ap.add_argument('--csv', help='CSV с колонкой ИНН')
    ap.add_argument('--kolonka', default='inn')
    ap.add_argument('--skolko', type=int, default=0, help='взять первые N ИНН')
    ap.add_argument('--out', default='park-opo.jsonl')
    ap.add_argument('--stranic', type=int, default=6, help='страниц списка на ИНН (25 записей)')
    ap.add_argument('--kart', type=int, default=25, help='бюджет карточек на ИНН')
    ap.add_argument('--stop-posle', type=int, default=12, dest='stop_posle',
                    help='выход по насыщению: столько карточек подряд БЕЗ НОВОГО имени')
    ap.add_argument('--podryad', action='store_true',
                    help='страницы списка подряд с первой, а не вразброс по всему реестру')
    ap.add_argument('--zanovo', action='store_true', help='не пропускать уже сделанные ИНН')
    a = ap.parse_args()

    print('Самопроверка разбора:')
    if not samoproverka():
        print('РАЗБОР СЛОМАН — прогон остановлен, чтобы не выдать ложный ноль.')
        return 2

    inns = list(a.inn)
    if a.spisok:
        inns += [re.sub(r'\D', '', l) for l in io.open(a.spisok, encoding='utf-8-sig') if l.strip()]
    if a.csv:
        inns += inn_iz_csv(a.csv, a.kolonka, a.skolko)
    inns = [i for i in dict.fromkeys(inns) if i]
    if a.skolko:
        inns = inns[:a.skolko]
    if not inns:
        print('не задан ни один ИНН'); return 1

    gotovo_put = a.out + '.gotovo'
    sdelano = set()
    if not a.zanovo and os.path.exists(gotovo_put):
        sdelano = set(l.strip() for l in io.open(gotovo_put, encoding='utf-8') if l.strip())

    itogo = 0
    with io.open(a.out, 'a', encoding='utf-8') as f, \
            io.open(gotovo_put, 'a', encoding='utf-8') as g:
        for n, inn in enumerate(inns, 1):
            if inn in sdelano:
                print('%2d/%d %s — уже сделан, пропуск' % (n, len(inns), inn))
                continue
            t0 = time.time()
            ob, sp, err = po_inn(inn, a.stranic, a.kart, a.stop_posle, a.podryad)
            if err:
                print('%2d/%d %s — ОШИБКА СЕТИ: %s (ИНН не помечен сделанным)'
                      % (n, len(inns), inn, err))
                continue
            for o in ob:
                f.write(json.dumps(o, ensure_ascii=False) + '\n')
            f.flush()
            g.write(inn + '\n'); g.flush()
            itogo += len(ob)
            print('%2d/%d %s — объектов ОПО %d | заключений в реестре %s, страниц %d из %d, '
                  'записей %d, карточек %d | %.0f c'
                  % (n, len(inns), inn, len(ob), sp.get('zaklyucheniy_v_reestre', '?'),
                     sp.get('stranic_vzyato', 0), sp.get('stranic_vsego', 0),
                     sp.get('zapisey_prosmotreno', 0), sp.get('kartochek_skachano', 0),
                     time.time() - t0))
            for o in ob[:4]:
                print('       · %s%s' % (o['naimenovanie_obekta'][:95],
                                         (' [' + o['klass_opasnosti'] + ' класс]')
                                         if o['klass_opasnosti'] else ''))
    print('\nВСЕГО объектов ОПО записано: %d → %s' % (itogo, a.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
