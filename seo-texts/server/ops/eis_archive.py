# -*- coding: utf-8 -*-
r"""АРХИВНЫЙ проход по ЕИС: контакты снабженцев из ЗАКРЫТЫХ закупок за годы.

Решение владельца 23.07, до сих пор не реализованное: нам нужен КОНТАКТ
снабженца, а не активный тендер. Снабженец работает в компании и после того,
как закупка закрылась, поэтому архив даёт в разы больше ФИО на компанию, чем
одни только актуальные процедуры.

РАЗВЕДКА (пробы 1 и 2, 29.07) — что выяснено про ЕИС и на чём стоит механика:
  * `<pubDate>` есть у КАЖДОЙ позиции RSS -> дату закупки берём из выдачи и не
    платим за открытие карточки только ради даты;
  * `pageNumber` в RSS НЕ РАБОТАЕТ: вторая страница отдаёт те же 50 позиций
    (проверено на четырёх компаниях, пересечение 50 из 50). Значит вглубь
    ходим не постранично, а ОКНАМИ ДАТ;
  * `publishDateFrom`/`publishDateTo` работают и режут ровно по годам —
    это и есть рабочий ход в архив;
  * разбор `_eis_people` на карточках 2023-2024 годов живой: ФИО, телефон и
    почта читаются той же функцией, что и на свежих.

СТРАХОВКИ ВЛАДЕЛЬЦА (без них способ запрещён):
  1. у каждого контакта дата закупки и флаг свежести: до 2 лет — fresh,
     2-3 года — stale (берём, но помечаем), старше 3 лет — НЕ БЕРЁМ ВОВСЕ;
  2. дедуп по человеку (почта/телефон/ФИО): один снабженец ведёт десятки
     закупок, схлопываем в одну запись;
  3. приоритет свежих: самая свежая закупка становится source_url, предыдущая
     остаётся запасной ссылкой;
  4. горячий флаг, если предмет закупки — наш профиль (компрессор,
     воздуходувка, фильтр, азот, кислород, МКС).

ПРИВЯЗКА ЗАКРЫТА ПО УМОЛЧАНИЮ: карточка принимается, только если НАШ ИНН
стоит на странице ДО контактного блока. Поиск в ЕИС идёт свободным текстом, и
ИНН умеет случайно попасть в номер контракта (ловушка из find_zakupki_supplier),
а контакт под чужим блоком — это чужой человек в нашей базе.

DURABLE: enrich.db (своя таблица eis_arch + people + phone_contacts + emails +
signals + stage_log) И поток C:\seostat\drop\eis_archive_stream.jsonl с fsync.
Резюмируемо: сделанные ИНН берутся из stage_log, прогон переживает рестарт.

Запуск:
    python eis_archive.py [--apply] [--limit N] [--budget SEC] [--cards N]
                          [--inns 1,2,3]
Без --apply — сухой прогон: считает и пишет поток, но базу не трогает.
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB      # noqa: E402
import enrich_contacts as EC  # noqa: E402

ПОТОК = r'C:\seostat\drop\eis_archive_stream.jsonl'
СТАДИЯ_СУХО = 'eis_archive_dry'
СТАДИЯ_БОЙ = 'eis_archive'

# --------------------------------------------------------------- аргументы
арг = sys.argv[1:]


def _знач(имя, по_умолч):
    if имя in арг:
        return арг[арг.index(имя) + 1]
    return по_умолч


ПРИМЕНЯТЬ = '--apply' in арг
ЛИМИТ = int(_знач('--limit', 25))
БЮДЖЕТ = float(_знач('--budget', 300))
КАРТ_АРХИВ = int(_знач('--cards', 10))     # сколько архивных карточек открывать
КАРТ_АКТУАЛ = 4                            # сколько актуальных (для сравнения)
ИНН_СПИСОК = [x.strip() for x in _знач('--inns', '').split(',') if x.strip()]
ПОТОКИ = 4
НАЧАЛО = time.time()
СЕГОДНЯ = datetime.now(timezone.utc).date()

# --------------------------------------------------------------- регулярки
# Горячий предмет — список владельца. `_ЗАКУПКА_НАШ_ПРОФИЛЬ` из enrich_contacts
# не знает ни фильтров, ни МКС, поэтому расширяем здесь, а не правим общий файл
# (его правит и вторая сессия — см. ловушку 6.6 передачи).
ГОРЯЧО = re.compile(
    r'компрессор|воздуходув|осушител|сжат\w*\s+воздух|пневмо|воздухоразделит'
    r'|генератор\w*\s+(?:азот|кислород)|азотн\w+\s+станц|кислородн\w+\s+станц'
    r'|фильтр|азот|кислород|\bМКС\b|малая\s+кислородн\w+\s+станц', re.I)
# ГРАНИЦА ПРЕДМЕТА. Дефект боевого кода (см. отчёт): в find_zakupki_contacts
# предмет берётся как `(.{6,220})` без границы поля, и в него уезжает соседняя
# колонка — «Поставка изделий из полиэтилена (прайс) Заказчик ГОСУДАРСТВЕННОЕ
# УНИТАРНОЕ ПРЕДПРИЯТИЕ...». Для горячего флага это прямая ложь: название
# заказчика вроде «Казанькомпрессормаш» сделало бы горячей закупку туалетной
# бумаги. Режем по следующей подписи поля.
_ГРАНИЦА = re.compile(
    r'\s(?:Заказчик|Способ\s+(?:размещения|определения|закупки)|Наименование\s+заказчика'
    r'|Начальн\w+\s*\(максимальн\w+\)?\s*цена|Контактн\w+\s+(?:информац|лиц)'
    r'|Этап\s+закупки|Дата\s+размещен|Валюта|Общая\s+информац|Размещение\s+осуществляет'
    r'|Организатор|Сведения\s+о\s+заказчик)', re.I)
_ПРЕДМЕТ = re.compile(
    r'(?:Наименование|Предмет|Объект)\s+(?:закуп\w+|договор\w+|контракт\w+)'
    r'\s*[:\-]?\s*(.{6,300})', re.I | re.S)

БАЗА_URL = ('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='
            '{inn}&fz44=on&fz223=on&recordsPerPage=_50')


def _этапы(архив):
    """af — подача заявок, ca — работа комиссии (это и есть АКТУАЛЬНЫЕ),
    pc — закупка завершена, pa — отменена (это архив)."""
    return ('&af=on&ca=on&pc=on&pa=on' if архив else '&af=on&ca=on')


# --------------------------------------------------------------- утилиты
def дата_позиции(it):
    m = re.search(r'<pubDate>\s*(.*?)\s*</pubDate>', it, re.S)
    if not m:
        return None
    try:
        return parsedate_to_datetime(m.group(1)).astimezone(timezone.utc).date()
    except Exception:  # noqa: BLE001
        return None


def свежесть(d):
    """fresh — до 2 лет, stale — 2-3 года, None — старше трёх (не берём)."""
    if not d:
        return None
    возраст = (СЕГОДНЯ - d).days
    if возраст < 0:
        возраст = 0
    if возраст <= 730:
        return 'fresh'
    if возраст <= 1095:
        return 'stale'
    return None


def _rss(url):
    try:
        r = EC._eis_get(url)
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}: {str(ex)[:60]}'
    if not re.search(r'<(?:rss|channel)\b', r or '', re.I):
        return None, 'ответ не похож на RSS (заглушка/лимит)'
    return re.findall(r'<item>(.*?)</item>', r, re.S), ''


def позиции(url):
    """[(ссылка, дата, заголовок)] из RSS."""
    items, err = _rss(url)
    if items is None:
        return None, err
    из = []
    for it in items:
        lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
        if not lm:
            continue
        u = lm.group(1)
        # в RSS контрактов ссылка ОТНОСИТЕЛЬНАЯ (ловушка 6.5 передачи)
        if u.startswith('/'):
            u = 'https://zakupki.gov.ru' + u
        tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        из.append((u, дата_позиции(it),
                   re.sub(r'\s+', ' ', tm.group(1))[:140] if tm else ''))
    return из, ''


def _окно(inn, с, по, архив=True):
    return (БАЗА_URL.format(inn=inn) + _этапы(архив)
            + '&publishDateFrom=' + с.strftime('%d.%m.%Y')
            + '&publishDateTo=' + по.strftime('%d.%m.%Y'))


def нормтел(s):
    """+7XXXXXXXXXX (плюс «доб.») из строки телефона ЕИС.

    ПОЧЕМУ НЕ ПРОСТО ЦИФРЫ. Сухой прогон записал «7 495 7109333 3042» и
    «84951221888 3683»: на карточке номер и добавочный стоят через пробел без
    подписи «доб.», и склейка выглядит как рабочий номер из 14 цифр. Это
    ловушка 4.7 передачи в чистом виде — продажник наберёт и не дозвонится, а
    номер при этом выглядит здоровым. Отделяем добавочный явно.
    """
    ц = re.sub(r'\D', '', s or '')
    доб = ''
    if len(ц) > 11:
        # 11 цифр начиная с 7/8 — это база (в т.ч. 8-800), остальное добавочный
        if ц[0] in '78':
            ц, доб = ц[:11], ц[11:]
        elif len(ц) > 10:
            ц, доб = ц[:10], ц[10:]
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    if len(ц) != 10:
        return (s or '').strip()[:60]
    return '+7' + ц + (' доб. ' + доб if доб else '')


def тел_ключ(s):
    """База номера без добавочного — для дедупа. С добавочным один и тот же
    человек в двух закупках дал бы две записи."""
    t = нормтел(s)
    return t.split(' доб.')[0] if t.startswith('+7') else ''


def ключ_фио(фио):
    """«Бабенко Я.Ю.» и «Бабенко Яна Юрьевна» — один ключ: фамилия + инициалы."""
    ч = [x for x in re.split(r'[\s.]+', (фио or '').strip()) if x]
    if not ч:
        return ''
    return (ч[0].lower() + ' ' + ' '.join(x[0].lower() for x in ч[1:]))


def почисти_фио(фио):
    """Вернуть точку инициалам: `_eis_value` срезает её финальным strip('.'),
    и в базу уезжает «Алушкина Н.И» вместо «Алушкина Н.И.»."""
    s = re.sub(r'\s+', ' ', (фио or '')).strip()
    if re.search(r'\b[А-ЯЁ]$', s):
        s += '.'
    return s


def предмет_со_страницы(txt):
    m = _ПРЕДМЕТ.search(txt or '')
    if not m:
        return ''
    зн = m.group(1)
    гр = _ГРАНИЦА.search(зн)
    if гр:
        зн = зн[:гр.start()]
    return re.sub(r'\s+', ' ', зн).strip(' .,;:-')[:200]


# ------------------------------------------------------- разбор карточки
def карточка(url, inn):
    """{'ok':bool, 'people':[...], 'subject':str, 'reason':str}"""
    try:
        h = EC._eis_get(url)
    except Exception as ex:  # noqa: BLE001
        return {'ok': False, 'reason': f'{type(ex).__name__}: {str(ex)[:50]}'}
    txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(
        r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)))
    # ДОКАЗАТЕЛЬСТВО ПРИВЯЗКИ: наш ИНН обязан стоять на странице, и именно
    # ДО контактного блока — иначе контакт может принадлежать уполномоченному
    # органу или площадке, а «ИНН где-то на странице» умеет оказаться куском
    # номера контракта.
    if inn not in txt:
        return {'ok': False, 'reason': 'нет ИНН на странице'}
    кб = re.search(r'Контактн\w+\s+(?:информаци\w+|лиц\w+)', txt, re.I)
    поз = кб.start() if кб else len(txt)
    if inn not in txt[max(0, поз - 3000):поз]:
        return {'ok': False, 'reason': 'ИНН не перед контактным блоком'}
    люди = EC._eis_people(txt)
    return {'ok': True, 'people': люди, 'subject': предмет_со_страницы(txt)}


# ------------------------------------------------------- дедуп по человеку
class Союз:
    """Мини-union-find: склеиваем записи, если совпала почта, или ФИО, или
    телефон при непротиворечивых именах.

    Ключ ТОЛЬКО по телефону опасен: на карточках одной компании у Карасева и
    Стойкова стоит один и тот же номер коммутатора +7 (499) 390-34-34 — по
    телефону два разных снабженца схлопнулись бы в одного.
    """

    def __init__(self):
        self.p = {}

    def найти(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def слить(self, a, b):
        ra, rb = self.найти(a), self.найти(b)
        if ra != rb:
            self.p[rb] = ra


def схлопнуть(записи):
    """[запись] -> [человек]. Свежая закупка побеждает, прошлая идёт запасной."""
    с = Союз()
    по_почте, по_фио = {}, {}
    for i, з in enumerate(записи):
        с.найти(i)
        e = (з.get('email') or '').lower()
        f = ключ_фио(з.get('person'))
        if e:
            с.слить(по_почте.setdefault(e, i), i)
        if f:
            с.слить(по_фио.setdefault(f, i), i)
    # телефон склеивает только тех, у кого имена не противоречат
    по_тел = {}
    for i, з in enumerate(записи):
        t = тел_ключ(з.get('phone'))
        if not t:
            continue
        j = по_тел.get(t)
        if j is None:
            по_тел[t] = i
            continue
        fi, fj = ключ_фио(записи[i].get('person')), ключ_фио(записи[j].get('person'))
        if not fi or not fj or fi == fj:
            с.слить(j, i)
    группы = {}
    for i in range(len(записи)):
        группы.setdefault(с.найти(i), []).append(записи[i])
    люди = []
    for гр in группы.values():
        гр.sort(key=lambda z: z['date'], reverse=True)
        гл = гр[0]
        # ФИО/должность/почту берём у самой свежей записи, где они есть
        имя = next((z['person'] for z in гр if z.get('person')), '')
        пост = next((z['post'] for z in гр if z.get('post')), '')
        почта = next((z['email'] for z in гр if z.get('email')), '')
        тел = next((z['phone'] for z in гр if z.get('phone')), '')
        горячие = [z for z in гр if z.get('hot')]
        люди.append({
            'person': почисти_фио(имя), 'post': пост,
            'phone': нормтел(тел), 'email': почта,
            'date': гл['date'], 'freshness': свежесть(
                datetime.strptime(гл['date'], '%Y-%m-%d').date()),
            'subject': гл.get('subject', ''),
            'source_url': гл['url'],
            'alt_url': (гр[1]['url'] if len(гр) > 1 else ''),
            'alt_date': (гр[1]['date'] if len(гр) > 1 else ''),
            'n_procs': len(гр),
            'hot': 1 if горячие else 0,
            'hot_url': (горячие[0]['url'] if горячие else ''),
            'hot_subject': (горячие[0].get('subject', '') if горячие else ''),
            'from_archive': 0 if any(z.get('actual') for z in гр) else 1,
        })
    return люди


# ------------------------------------------------------- один ИНН
def обработать(inn):
    r = {'inn': inn, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
    актуальные, err = позиции(БАЗА_URL.format(inn=inn) + _этапы(False))
    if актуальные is None:
        r['error'] = 'актуальные: ' + err
        актуальные = []
    r['актуальных_позиций'] = len(актуальные)
    # окна: [0..1г], [1..2г], [2..3г]. Три запроса по 50 вместо одного по 50 —
    # ровно потому, что pageNumber в RSS не работает (проба 1).
    архив = []
    for k in (1, 2, 3):
        с = СЕГОДНЯ - timedelta(days=365 * k)
        по = СЕГОДНЯ - timedelta(days=365 * (k - 1) + (1 if k > 1 else 0))
        поз, e2 = позиции(_окно(inn, с, по, архив=True))
        if поз is None:
            r.setdefault('окна_ошибки', []).append(f'{k}г: {e2}')
            continue
        архив += поз
        time.sleep(0.4)
    # ТОЧНЫЙ ПРЕЖНИЙ ПОДХОД, а не его пересказ: боевой find_zakupki_contacts
    # шлёт ровно этот адрес и открывает первые max_cards позиций (в sales_eis и
    # core_eis стоит max_cards=4). Спрашиваем его отдельным запросом, чтобы
    # сравнение «архив против того, что есть» держалось на фактах.
    прод_поз, _e3 = позиции(БАЗА_URL.format(inn=inn) + _этапы(True)
                            + '&sortBy=UPDATE_DATE')
    прод_поз = прод_поз or []
    прежние = {u for u, _d, _t in прод_поз[:4]}
    r['прежний_подход_карточек'] = len(прежние)
    r['прежний_подход_старше_3_лет'] = sum(
        1 for u, d, _t in прод_поз[:4] if d and свежесть(d) is None)
    акт_ссылки = {u for u, _d, _t in актуальные}
    # весь пул карточек, старше трёх лет отсекаем СРАЗУ (условие владельца)
    пул, старых = {}, 0
    for u, d, t in (актуальные + архив + прод_поз[:4]):
        if not d:
            continue
        if свежесть(d) is None:
            старых += 1
            continue
        пред = пул.get(u)
        if пред is None or d > пред[0]:
            пул[u] = (d, t, u in акт_ссылки)
    r['архивных_позиций'] = len(архив)
    r['отброшено_старше_3_лет'] = старых
    r['карточек_всего'] = len(пул)
    r['карточек_архивных'] = sum(1 for v in пул.values() if not v[2])

    отсорт = sorted(пул.items(), key=lambda kv: kv[1][0], reverse=True)
    # карточки прежнего подхода открываем ВСЕГДА — иначе базу сравнения нечем
    # заполнить, и «архив дал больше» повиснет без второй половины
    прод_список = [x for x in отсорт if x[0] in прежние]
    акт_список = [x for x in отсорт
                  if x[1][2] and x[0] not in прежние][:КАРТ_АКТУАЛ]
    арх_список = [x for x in отсорт if not x[1][2] and x[0] not in прежние]
    # архив берём РАЗМАЗАННО по трём годам: подряд идущие закупки одной недели
    # ведёт один и тот же человек, и десять таких карточек дадут одного ФИО.
    if len(арх_список) > КАРТ_АРХИВ:
        шаг = len(арх_список) / float(КАРТ_АРХИВ)
        арх_список = [арх_список[int(i * шаг)] for i in range(КАРТ_АРХИВ)]
    брать = прод_список + акт_список + арх_список

    записи, ошибок, отказов = [], 0, 0
    причины = {}
    for u, (d, t, акт) in брать:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            r['прерван_по_бюджету'] = True
            break
        c = карточка(u, inn)
        time.sleep(0.6)
        if not c.get('ok'):
            прич = c.get('reason', '?')
            причины[прич] = причины.get(прич, 0) + 1
            if 'ИНН' in прич:
                отказов += 1
            else:
                ошибок += 1
            continue
        предмет = c.get('subject') or ''
        горяч = bool(ГОРЯЧО.search(предмет))
        for ч in (c.get('people') or []):
            if not (ч.get('person') or ч.get('phone') or ч.get('email')):
                continue
            записи.append({'person': ч.get('person', ''), 'post': ч.get('post', ''),
                           'phone': ч.get('phone', ''), 'email': ч.get('email', ''),
                           'url': u, 'date': d.isoformat(), 'subject': предмет,
                           'hot': горяч, 'actual': bool(акт)})
    r['открыто_карточек'] = len(брать) - ошибок - отказов
    r['карточек_ошибка'] = ошибок
    r['карточек_отклонено_привязкой'] = отказов
    if причины:
        r['причины'] = причины
    r['сырых_записей'] = len(записи)
    люди = схлопнуть(записи)
    r['людей'] = len(люди)
    # СРАВНЕНИЕ: сколько людей дали бы одни актуальные процедуры
    только_акт = схлопнуть([z for z in записи if z.get('actual')])
    r['людей_из_актуальных'] = len(только_акт)
    r['людей_добавил_архив'] = len(люди) - len(только_акт)
    # и сколько дал бы ПРЕЖНИЙ подход (первые 4 карточки ленты)
    r['людей_прежний_подход'] = len(схлопнуть(
        [z for z in записи if z['url'] in прежние]))
    r['fresh'] = sum(1 for ч in люди if ч['freshness'] == 'fresh')
    r['stale'] = sum(1 for ч in люди if ч['freshness'] == 'stale')
    r['горячих'] = sum(1 for ч in люди if ч['hot'])
    r['люди'] = люди
    return r


# ------------------------------------------------------- запись в базу
def записать(db, e, inn, люди):
    """Возврат: (новых_людей, новых_телефонов, новых_почт, техролей)."""
    нл = нт = нп = тех = 0
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    for ч in люди:
        роль = EDB.EnrichDB._canon_role(ч.get('post') or 'закупки')
        if роль in EDB.EnrichDB.TECH_ROLES:
            тех += 1
        if ч.get('person'):
            было = e.execute(
                'SELECT 1 FROM people WHERE inn=? AND person=? AND post=?',
                (inn, ч['person'][:120], (ч.get('post') or '')[:160])).fetchone()
            db.add_person(inn, ч['person'], post=ч.get('post') or 'закупки',
                          phone=ч.get('phone', ''), email=ч.get('email', ''),
                          source='zakupki:eis-archive',
                          source_url=ч['source_url'], observed_at=ч['date'])
            if not было:
                нл += 1
        тел = ч.get('phone') or ''
        if тел:
            было = e.execute(
                'SELECT 1 FROM phone_contacts WHERE inn=? AND phone=?',
                (inn, тел)).fetchone()
            # 7 значений позиционно — ровно как в схеме phone_contacts.
            # Колонки в неё НЕ ДОБАВЛЯТЬ: sales_eis.py и core_eis.py пишут
            # позиционным INSERT ... VALUES(?,?,?,?,?,?,?) и сломались бы.
            e.execute('INSERT OR REPLACE INTO phone_contacts VALUES (?,?,?,?,?,?,?)',
                      (inn, тел, ч.get('person', ''), роль,
                       'zakupki:eis-archive(%s,%s)' % (ч['freshness'], ч['date']),
                       ч['source_url'], ts))
            if not было:
                нт += 1
        if ч.get('email'):
            было = e.execute('SELECT 1 FROM emails WHERE inn=? AND email=?',
                             (inn, ч['email'].lower())).fetchone()
            db.add_email(inn, ч['email'], role=ч.get('post') or 'закупки',
                         person=ч.get('person', ''), source='zakupki:eis-archive',
                         source_url=ч['source_url'])
            if not было:
                нп += 1
        if ч.get('hot'):
            db.add_signal(inn, 'zakupki:eis-archive', event_type='закупка профиля',
                          what=(ч.get('hot_subject') or ч.get('subject') or '')[:400],
                          source_url=ч.get('hot_url') or ч['source_url'],
                          hotness=1, ts=ч['date'])
        # ДАТА И СВЕЖЕСТЬ — в своей таблице: в phone_contacts колонки для них
        # нет, а добавлять её нельзя (см. выше про позиционный INSERT).
        e.execute(
            'INSERT OR REPLACE INTO eis_arch(inn,pkey,person,post,role,phone,'
            'email,subject,proc_date,freshness,hot,n_procs,from_archive,'
            'source_url,alt_url,alt_date,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            # ключ человека БЕЗ добавочного: с ним одна и та же запись при
            # повторном прогоне уехала бы во вторую строку
            (inn, (ч.get('email') or тел_ключ(ч.get('phone'))
                   or ключ_фио(ч.get('person'))),
             ч.get('person', ''), ч.get('post', ''), роль, ч.get('phone', ''),
             ч.get('email', ''), ч.get('subject', ''), ч['date'], ч['freshness'],
             ч['hot'], ч['n_procs'], ч['from_archive'], ч['source_url'],
             ч.get('alt_url', ''), ч.get('alt_date', ''), ts))
    e.commit()
    return нл, нт, нп, тех


# ------------------------------------------------------- главное
def main():
    db = EDB.EnrichDB()
    e = db.cx
    e.execute("""CREATE TABLE IF NOT EXISTS eis_arch(
        inn TEXT, pkey TEXT, person TEXT, post TEXT, role TEXT, phone TEXT,
        email TEXT, subject TEXT, proc_date TEXT, freshness TEXT,
        hot INTEGER, n_procs INTEGER, from_archive INTEGER,
        source_url TEXT, alt_url TEXT, alt_date TEXT, updated_at TEXT,
        PRIMARY KEY (inn, pkey))""")
    e.execute("""CREATE TABLE IF NOT EXISTS phone_contacts(
        inn TEXT, phone TEXT, person TEXT, role TEXT,
        source TEXT, source_url TEXT, updated_at TEXT,
        PRIMARY KEY (inn, phone, source_url))""")
    e.commit()

    стадия = СТАДИЯ_БОЙ if ПРИМЕНЯТЬ else СТАДИЯ_СУХО
    if ИНН_СПИСОК:
        инны = ИНН_СПИСОК
    else:
        try:
            строки = e.execute(
                'SELECT inn FROM companies WHERE COALESCE(is_competitor,0)=0 '
                'ORDER BY CAST(COALESCE(revenue_rub,0) AS REAL) DESC').fetchall()
        except Exception:  # noqa: BLE001  колонки revenue_rub может не быть
            строки = e.execute('SELECT inn FROM companies').fetchall()
        порядок = [str(x[0]) for x in строки if x[0]]
        сделано = {r[0] for r in e.execute(
            'SELECT inn FROM stage_log WHERE stage=?', (стадия,))}
        инны = [i for i in порядок if i not in сделано][:ЛИМИТ]

    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    замок = threading.Lock()
    итог = {'режим': ('БОЙ' if ПРИМЕНЯТЬ else 'сухой'), 'компаний_в_плане': len(инны),
            'обработано': 0, 'ошибок': 0,
            'карточек_актуальных': 0, 'карточек_архивных': 0,
            'карточек_открыто': 0, 'карточек_отклонено_привязкой': 0,
            'отброшено_старше_3_лет': 0,
            'людей_всего': 0, 'людей_из_актуальных': 0, 'людей_добавил_архив': 0,
            'людей_прежний_подход': 0, 'прежний_подход_карточек': 0,
            'прежний_подход_старше_3_лет': 0,
            'fresh': 0, 'stale': 0, 'горячих_людей': 0,
            'новых_людей_в_базу': 0, 'новых_телефонов': 0, 'новых_почт': 0,
            'техролей': 0, 'компаний_с_людьми': 0, 'примеры': []}
    print('СТАРТ ' + json.dumps(
        {'режим': итог['режим'], 'план': len(инны), 'бюджет': БЮДЖЕТ,
         'карт_архив': КАРТ_АРХИВ}, ensure_ascii=False), flush=True)

    def работа(inn):
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            return
        try:
            r = обработать(inn)
        except Exception as ex:  # noqa: BLE001
            r = {'inn': inn, 'error': f'{type(ex).__name__}: {str(ex)[:90]}'}
        with замок:
            # 1) durable-поток с fsync — переживает рестарт песочницы и сервера
            ф.write(json.dumps(r, ensure_ascii=False) + '\n')
            ф.flush()
            try:
                os.fsync(ф.fileno())
            except Exception:  # noqa: BLE001
                pass
            итог['обработано'] += 1
            if r.get('error'):
                итог['ошибок'] += 1
                return
            for k_из, k_в in (('актуальных_позиций', 'карточек_актуальных'),
                              ('карточек_архивных', 'карточек_архивных'),
                              ('открыто_карточек', 'карточек_открыто'),
                              ('карточек_отклонено_привязкой',
                               'карточек_отклонено_привязкой'),
                              ('отброшено_старше_3_лет', 'отброшено_старше_3_лет'),
                              ('людей', 'людей_всего'),
                              ('людей_из_актуальных', 'людей_из_актуальных'),
                              ('людей_добавил_архив', 'людей_добавил_архив'),
                              ('людей_прежний_подход', 'людей_прежний_подход'),
                              ('прежний_подход_карточек', 'прежний_подход_карточек'),
                              ('прежний_подход_старше_3_лет',
                               'прежний_подход_старше_3_лет'),
                              ('fresh', 'fresh'), ('stale', 'stale'),
                              ('горячих', 'горячих_людей')):
                итог[k_в] += int(r.get(k_из) or 0)
            люди = r.get('люди') or []
            if люди:
                итог['компаний_с_людьми'] += 1
            if ПРИМЕНЯТЬ and люди:
                нл, нт, нп, тех = записать(db, e, inn, люди)
                итог['новых_людей_в_базу'] += нл
                итог['новых_телефонов'] += нт
                итог['новых_почт'] += нп
                итог['техролей'] += тех
            for ч in люди[:2]:
                if len(итог['примеры']) < 10:
                    итог['примеры'].append(
                        {'инн': inn, 'кто': ч.get('person'), 'долж': ч.get('post'),
                         'тел': ч.get('phone'), 'почта': ч.get('email'),
                         'дата': ч['date'], 'св': ч['freshness'],
                         'закупок': ч['n_procs'], 'горяч': ч['hot'],
                         'url': ч['source_url']})
            db.mark_stage(inn, стадия,
                          'люди=%d арх=+%d' % (r.get('людей') or 0,
                                               r.get('людей_добавил_архив') or 0))

    with ThreadPoolExecutor(max_workers=ПОТОКИ) as пул:
        list(пул.map(работа, инны))
    ф.close()
    итог['секунд'] = round(time.time() - НАЧАЛО, 1)
    итог['осталось_в_плане'] = len(инны) - итог['обработано']
    # печатаем ДВАЖДЫ: раннер отдаёт stdout хвостом
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False, indent=1)[:4000], flush=True)


if __name__ == '__main__':
    main()
