# -*- coding: utf-8 -*-
r"""Сборка АВТОНОМНОЙ базы центробежных для панели обзвона.

ЗАЧЕМ отдельный файл, а не таблица в seo.db/enrich.db:
  * seo.db — 11 ГБ и общая с SEO-аналитикой: любой наш промах там дорого стоит;
  * enrich.db пишет БОЕВОЕ обогащение, и конкурировать с ним за блокировки
    (панель держит открытое соединение часами) нельзя.
Поэтому результат — одноразово собираемый снимок C:\seostat\data\centrifugal.db,
который панель открывает в режиме read-only. Все ЧТЕНИЯ источников тоже строго
read-only (file:...?mode=ro): скрипт физически не может помешать обогащению.

Запуск на сервере:
    python build_centrifugal_db.py                       # в C:\seostat\data\centrifugal.db
    python build_centrifugal_db.py D:\tmp\centrifugal.db  # в указанный файл

Идемпотентность: таблицы пересоздаются с нуля (DROP+CREATE) внутри ОДНОЙ
транзакции, поэтому повторный запуск даёт тот же результат, а читатель-панель
до самого COMMIT видит прежний снимок и никогда — полупустой.

Источники (все read-only):
    C:\sender\obzvon-index.db          таблица obzvon — реквизиты 161k юрлиц
    C:\sender\enrich.db                companies / phone_contacts / emails / signals
    C:\sender\_ops\sales_base.json     555 ИНН базы продажников -> centro1
    C:\seostat\drop\...\centrifugal-core-inns.txt  396 ИНН ядра -> centro2
    C:\sender\server\core396.json      (необязательно) имена/выручка/сектор ядра

Пути переопределяются переменными окружения CENTRO_OBZVON_DB, CENTRO_ENRICH_DB,
CENTRO_SALES_JSON, CENTRO_CORE_TXT, CENTRO_CORE_JSON, CENTRO_OUT_DB и ключами
командной строки (см. --help) — это же даёт прогнать сборку на копиях источников.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# Пути источников
# --------------------------------------------------------------------------- #
DEF_OBZVON = os.environ.get('CENTRO_OBZVON_DB', r'C:\sender\obzvon-index.db')
DEF_ENRICH = os.environ.get('CENTRO_ENRICH_DB', r'C:\sender\enrich.db')
DEF_SALES = os.environ.get('CENTRO_SALES_JSON', r'C:\sender\_ops\sales_base.json')
DEF_CORE_TXT = os.environ.get(
    'CENTRO_CORE_TXT', r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt')
DEF_CORE_JSON = os.environ.get('CENTRO_CORE_JSON', r'C:\sender\server\core396.json')
DEF_OUT = os.environ.get('CENTRO_OUT_DB', r'C:\seostat\data\centrifugal.db')

BASES = {'centro1': 'Центробежные 1', 'centro2': 'Центробежные 2'}

# --------------------------------------------------------------------------- #
# Схема снимка. Пишется буквально по общему контракту — панель и сборщик
# сверяются по ЭТОМУ тексту, поэтому менять его в одностороннем порядке нельзя.
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE company(
  base TEXT NOT NULL,
  inn TEXT NOT NULL,
  name_short TEXT, name_full TEXT, ogrn TEXT, kpp TEXT,
  status TEXT, reg_date TEXT, address TEXT, region TEXT, opf TEXT,
  director TEXT, director_inn TEXT, founders TEXT,
  okved_main TEXT, okved_all TEXT, equipment TEXT, equipment_all TEXT,
  revenue TEXT, revenue_num REAL, revenue_year TEXT, profit TEXT, staff TEXT,
  site TEXT, activity TEXT,
  priority INTEGER DEFAULT 0, max_hit INTEGER DEFAULT 0,
  rank_metric REAL,
  in_obzvon INTEGER DEFAULT 0,
  n_phones INTEGER DEFAULT 0, n_emails INTEGER DEFAULT 0,
  n_purchaser INTEGER DEFAULT 0,
  n_signals INTEGER DEFAULT 0,
  search_blob TEXT,
  PRIMARY KEY(base, inn));

CREATE TABLE contact(
  id INTEGER PRIMARY KEY,
  base TEXT NOT NULL, inn TEXT NOT NULL,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  person TEXT, role TEXT,
  source TEXT,
  source_url TEXT,
  is_purchaser INTEGER DEFAULT 0,
  in_sales_base INTEGER DEFAULT 0);

CREATE TABLE signal(
  id INTEGER PRIMARY KEY,
  base TEXT NOT NULL, inn TEXT NOT NULL,
  source TEXT, event_type TEXT, what TEXT, hotness INTEGER,
  ts TEXT, source_url TEXT);

CREATE INDEX ix_company_base ON company(base);
CREATE INDEX ix_company_rank ON company(base, rank_metric DESC, revenue_num DESC);
CREATE INDEX ix_contact ON contact(base, inn);
CREATE INDEX ix_signal ON signal(base, inn);
"""

# --------------------------------------------------------------------------- #
# Разбор значений
# --------------------------------------------------------------------------- #
INN_RE = re.compile(r'\b(\d{10}|\d{12})\b')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
# телефон внутри свободного текста: цифры/пробелы/дефисы/скобки, буквы обрывают
# совпадение — поэтому «+7 342 292-14-60 доб.122» даёт номер без добавочного
PHONE_IN_TEXT_RE = re.compile(r'\+?\d[\d\s\-()]{8,}\d')
# добавочный режем ДО нормализации: иначе валидный номер выглядит как 13-14 цифр
# и улетает в мусор вместе с ОГРН (грабля владельца, см. build_contacts_xlsx.py)
EXT_RE = re.compile(r'(доб|добав|вн\.?|ext|extension|#|,)', re.I)
# «закупщик» по роли/источнику. Латиница нужна обязательно: контакты ЕИС лежат
# с source='zakupki:eis' — на одной кириллице (закуп|снабж|тендер|постав) главный
# признак владельца не сработал бы ровно там, где он важнее всего.
PURCHASER_RE = re.compile(
    r'закуп|снабж|тендер|постав|контрактн|zakup|tender|snab|procure', re.I)

_MULT = {'млрд': 1e9, 'млн': 1e6, 'тыс': 1e3}
_POSTCODE = re.compile(r'^\d{5,6}$')
# мусор, который Checko тащит в колонку «Сайты» (счётчики/CDN/сам checko)
_JUNK_SITE = re.compile(
    r'yastatic\.net|an\.yandex\.|mc\.yandex\.|avatars\.mds\.yandex|ads\.adfox\.'
    r'|chrome\.google\.com|checko\.ru|yandex\.st|google-analytics|googletagmanager',
    re.I)

# метки ЗАПУСКА, которыми обогащение затирает настоящий источник контакта
# (enrich_contacts._persist кладёт в source аргумент прогона). Для таких записей
# честный источник восстанавливаем из source_url — он не затирается.
RUN_LABELS = {'enrich', 'sales-base', 'centrifugal-core', 'core', ''}
HOST_LABEL = {
    'zakupki.gov.ru': 'ЕИС (карточка закупки)',
    'checko.ru': 'checko',
    'list-org.com': 'list-org',
    'rusprofile.ru': 'rusprofile',
    'vk.com': 'VK',
    'hh.ru': 'hh.ru',
}

# Честные (не затёртые) метки конвейера записаны техническими кодами. Панель показывает
# источник продажнику, поэтому переводим ИЗВЕСТНЫЙ закрытый список кодов в
# человеческие подписи. Провенанс при этом не меняется: 'zakupki:eis' и
# «ЕИС (карточка закупки)» — одно и то же место. Незнакомый код проходит как есть.
SOURCE_LABEL = {
    'zakupki': 'ЕИС (карточка закупки)',
    'zakupki:eis': 'ЕИС (карточка закупки)',
    'zakupki.gov': 'ЕИС (карточка закупки)',
    'checko': 'checko',
    'checko:contacts': 'checko (страница контактов)',
    'checko.ru': 'checko',
    'hh': 'hh.ru (вакансии)',
    'hh.ru': 'hh.ru (вакансии)',
    'egrul': 'ЕГРЮЛ',
    'egrul:dadata': 'ЕГРЮЛ (Dadata)',
    'egrul:dadata-releak': 'ЕГРЮЛ (Dadata)',
    'vk-group': 'VK (сообщество)',
    'vk.com': 'VK',
    'maps:yandex': 'Яндекс.Карты',
    'serp-card:yandex': 'Яндекс (карточка организации)',
    'serp': 'поисковая выдача',
    'news': 'новость (СМИ)',
    'directory': 'отраслевой справочник',
    'site': 'сайт компании',
    'crawl': 'сайт компании',
    'staff': 'сайт компании (страница сотрудников)',
    'cache:enrich-db': 'обогащение (кэш)',
}


def norm_inn(raw) -> str:
    """Канон ИНН: только цифры (как в company_card.norm_inn — иначе не сойдёмся
    с ключами obzvon-index.db)."""
    return re.sub(r'\D', '', str(raw or ''))


def norm_phone(raw):
    """Телефон -> 10 цифр или None. Отсекает ОГРН/счета/заглушки."""
    if not raw:
        return None
    s = str(raw)
    m = EXT_RE.search(s)
    if m:                      # отрезаем добавочный и всё после него
        s = s[:m.start()]
    d = re.sub(r'\D', '', s)
    if len(d) == 11 and d[0] in '78':
        d = d[1:]
    if len(d) != 10:
        return None            # ОГРН (13), счёт (20), обрезки — не телефон
    if d[0] in '012':
        return None            # российских кодов на 0/1/2 не бывает (хвосты ОГРН)
    if d[:3] == '000':
        return None
    if len(set(d)) == 1:       # 0000000000 / 9999999999
        return None
    if d[3:] == '0000000':     # +7 (XXX) 000-00-00
        return None
    return d


def fmt_phone(d10: str) -> str:
    return f'+7 ({d10[:3]}) {d10[3:6]}-{d10[6:8]}-{d10[8:]}'


def norm_email(raw):
    if not raw:
        return None
    e = str(raw).strip().lower().strip('.,;')
    return e if EMAIL_RE.fullmatch(e) else None


def phones_from_text(text):
    """Все телефоны из свободного текста (колонки базы «Телефоны», «Телефоны с
    сайта» — разделитель там непредсказуем). Email вырезаем: их цифры не номера."""
    s = EMAIL_RE.sub(' ', str(text or ''))
    out, seen = [], set()
    for m in PHONE_IN_TEXT_RE.findall(s):
        d = norm_phone(m)
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def emails_from_text(text):
    out, seen = [], set()
    for m in EMAIL_RE.findall(str(text or '')):
        e = norm_email(m)
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def parse_money(text):
    """«55,3 млрд руб.» -> 5.53e10; «114 100 000 000» -> 1.141e11; '' -> None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).replace('\xa0', ' ').replace('\u202f', ' ').strip()
    if not s:
        return None
    m = re.search(r'(-?\d[\d\s]*(?:[.,]\d+)?)', s)
    if not m:
        return None
    try:
        num = float(m.group(1).replace(' ', '').replace(',', '.'))
    except ValueError:
        return None
    for word, k in _MULT.items():
        if word in s:
            return num * k
    return num


def to_int(v, default=0):
    try:
        return int(float(str(v).replace(' ', '').replace(',', '.')))
    except (TypeError, ValueError):
        return default


def first_str(*vals) -> str:
    """Первое непустое строковое значение (порядок = приоритет источника)."""
    for v in vals:
        s = str(v).strip() if v is not None else ''
        if s:
            return s
    return ''


def first_num(*vals):
    """Первое РАСПАРСЕННОЕ число. Отдельно от first_str, потому что 0 — валидная
    выручка, и обычный `or` её бы проглотил."""
    for v in vals:
        n = parse_money(v)
        if n is not None:
            return n
    return None


def clean_sites(raw) -> str:
    """« | »-строка реальных сайтов без счётчиков/CDN."""
    out, seen = [], set()
    for tok in str(raw or '').split('|'):
        u = tok.strip()
        if not u or _JUNK_SITE.search(u):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return ' | '.join(out)


def first_site(raw) -> str:
    s = clean_sites(raw)
    return s.split(' | ')[0] if s else ''


def as_url(site: str) -> str:
    """Домен из базы -> кликабельный http(s)-адрес."""
    s = (site or '').strip()
    if not s:
        return ''
    return s if s.startswith(('http://', 'https://')) else 'http://' + s


def region_from_address(addr) -> str:
    """Регион из адреса Checko: «664043, Иркутская область, г. Иркутск…» ->
    «Иркутская область». Нужен, когда колонка «Регион» в выгрузке пуста."""
    for part in str(addr or '').split(','):
        p = part.strip()
        if not p or _POSTCODE.match(p):
            continue
        return re.sub(r'^(г\.\s*о\.|г\.|город)\s+', '', p).strip()
    return ''


def host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or '').lower().split('@')[-1].split(':')[0]
    except ValueError:
        return ''


def nice_source(source, url, site) -> str:
    """Читаемый источник: своё честное значение, иначе восстановленное из ссылки.
    Панель показывает эту строку рядом с контактом, поэтому 'sales-base' (метка
    запуска, а не источник) там появляться не должен."""
    s = (source or '').strip()
    if s.lower() not in RUN_LABELS:
        return SOURCE_LABEL.get(s.lower(), s)
    host = host_of(url or '')
    if not host:
        # Ссылки нет — восстанавливать источник НЕ ИЗ ЧЕГО, а вернуть сюда сам
        # `s` нельзя: это метка запуска ('sales-base', 'enrich', 'core'), и она
        # уехала бы продажнику в панель как «источник». Такие записи в enrich.db
        # массовые (egrul:dadata пишет source_url=''), поэтому отдаём честное
        # «обогащение» — конвейер, место в котором мы уже не знаем.
        return 'обогащение' if s else '—'
    bare = host[4:] if host.startswith('www.') else host
    for known, label in HOST_LABEL.items():
        if bare == known or bare.endswith('.' + known):
            return label
    base = (site or '').lower().replace('http://', '').replace('https://', '').strip('/')
    base = base.split('/')[0]
    if base.startswith('www.'):
        base = base[4:]
    if base and (bare == base or bare.endswith('.' + base) or base.endswith('.' + bare)):
        return 'сайт компании'
    return bare


def is_purchaser(role, source, url) -> int:
    """Закупщик = роль/источник про закупки-снабжение ИЛИ контакт снят прямо
    с карточки закупки ЕИС (там по определению сидит снабжение)."""
    blob = f'{role or ""} {source or ""}'
    if PURCHASER_RE.search(blob):
        return 1
    return 1 if 'zakupki.gov.ru' in host_of(url or '') else 0


# --------------------------------------------------------------------------- #
# Чтение источников
# --------------------------------------------------------------------------- #
def ro_uri(path: str) -> str:
    """file-URI для read-only соединения. Через прямые слэши и три слэша —
    на Windows 'file:C:\\sender\\x.db' парсится не везде одинаково."""
    p = os.path.abspath(path).replace('\\', '/').lstrip('/')
    p = p.replace('?', '%3f').replace('#', '%23')
    return f'file:///{p}?mode=ro'


def ro_connect(path: str, warn: list):
    """Соединение ТОЛЬКО на чтение. Нет файла — работаем без источника (честно
    сообщаем в отчёте), а не падаем: панель нужна и с частичными данными."""
    if not path or not os.path.exists(path):
        warn.append(f'нет источника: {path}')
        return None
    cx = None
    try:
        cx = sqlite3.connect(ro_uri(path), uri=True, timeout=60)
        cx.execute('PRAGMA busy_timeout=60000')
        # ПРОБНОЕ ЧТЕНИЕ обязательно: sqlite3.connect() сам файл не открывает
        # (ленивое открытие), поэтому битая база, чужая блокировка и WAL без
        # -shm вылезли бы не здесь, а МОЛЧА — table_info вернул бы пусто, и
        # снимок собрался бы без контактов без единого слова в отчёте.
        cx.execute('SELECT count(*) FROM sqlite_master').fetchone()
    except sqlite3.Error as e:
        warn.append(f'не открылся {path}: {e}')
        if cx is not None:
            try:
                cx.close()
            except sqlite3.Error:
                pass
        return None
    return cx


def table_cols(cx, table: str) -> list:
    """Реальные колонки таблицы. Схемы боевых баз правились ALTER'ами мимо
    репозитория (revenue_rub, shared_phone), поэтому состав колонок узнаём у
    самой БД, а не берём из кода — иначе сборка падает на живом сервере."""
    if cx is None:
        return []
    try:
        return [r[1] for r in cx.execute(f'PRAGMA table_info("{table}")')]
    except sqlite3.Error:
        return []


def _chunks(seq, n=400):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def rows_by_inn(cx, table: str, wanted, inns) -> list:
    """Строки таблицы по набору ИНН -> список dict. Берём только существующие
    колонки; отсутствующие возвращаем пустыми, чтобы вызывающий код не гадал."""
    have = table_cols(cx, table)
    if not have or not inns or 'inn' not in have:
        return []
    cols = [c for c in wanted if c in have]
    if 'inn' not in cols:
        cols = ['inn'] + cols
    sel = ', '.join(f'"{c}"' for c in cols)
    missing = {c: '' for c in wanted if c not in have}
    out = []
    for part in _chunks(inns):
        ph = ','.join('?' * len(part))
        sql = f'SELECT {sel} FROM "{table}" WHERE inn IN ({ph})'
        for row in cx.execute(sql, part):
            rec = dict(zip(cols, row))
            rec.update(missing)
            out.append(rec)
    return out


def _as_list(v):
    """phones/emails базы продажников -> список значений.

    Формат файла известен по коду (_ops_recon_bases, build_contacts_xlsx) как
    список, но встречается и одна строка, и ГОЛОЕ ЧИСЛО (Excel съел формат
    телефона). Скаляр итерировать нельзя: list(74951234567) роняет всю сборку
    целиком, а из-за одной кривой ячейки терять базу нельзя.
    """
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


def load_sales(path: str, warn: list):
    """База продажников: список ИНН (порядок файла) + имена + то, что у них УЖЕ
    есть (телефоны по 10 цифрам, email) — для флага in_sales_base."""
    inns, names = [], {}
    phones, emails = set(), set()
    own = {}                      # inn -> {'phones': [...], 'emails': [...]}
    if not os.path.exists(path):
        warn.append(f'нет источника: {path}')
        return inns, names, phones, emails, own
    try:
        data = json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError) as e:
        warn.append(f'не разобрался sales_base.json: {e}')
        return inns, names, phones, emails, own

    items = []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                items.extend(v)
    elif isinstance(data, list):
        items = data

    seen = set()
    for r in items:
        if not isinstance(r, dict):
            continue
        m = INN_RE.search(str(r.get('inn') or ''))
        inn = m.group(1) if m else ''
        if inn and inn not in seen:
            seen.add(inn)
            inns.append(inn)
        nm = str(r.get('name') or '').strip()
        if inn and nm and not names.get(inn):
            names[inn] = nm
        # phones/emails бывают и списком, и одной строкой через разделитель
        raw_p = _as_list(r.get('phones'))
        raw_e = _as_list(r.get('emails'))
        got_p, got_e = [], []
        for p in raw_p:
            found = phones_from_text(p)
            if not found:                      # «84951234567» без разделителей
                one = norm_phone(p)
                found = [one] if one else []
            for d in found:
                phones.add(d)
                got_p.append(d)
        for e in raw_e:
            for v in emails_from_text(e):
                emails.add(v)
                got_e.append(v)
        if inn:
            slot = own.setdefault(inn, {'phones': [], 'emails': []})
            slot['phones'].extend(got_p)
            slot['emails'].extend(got_e)
    return inns, names, phones, emails, own


def load_core(path: str, warn: list):
    """Ядро центробежных: по ИНН в строке."""
    if not os.path.exists(path):
        warn.append(f'нет источника: {path}')
        return []
    out, seen = [], set()
    with open(path, encoding='utf-8', errors='replace') as fh:
        for ln in fh:
            m = INN_RE.search(ln)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                out.append(m.group(1))
    return out


def load_core_json(path: str):
    """core396.json — имя/ОГРН/сектор/выручка ядра. Необязательный источник:
    им закрываем дыры, когда компании нет ни в обзвоне, ни в обогащении."""
    if not path or not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    out = {}
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict) and r.get('inn'):
                out[norm_inn(r['inn'])] = r
    return out


# --------------------------------------------------------------------------- #
# Сборка компаний
# --------------------------------------------------------------------------- #
OBZ_COLS = ['inn', 'base_label', 'ogrn', 'kpp', 'name_short', 'name_full', 'status',
            'reg_date', 'address', 'region', 'opf', 'director', 'dir_inn', 'founders',
            'okved_main', 'okved_all_codes', 'phones_base', 'emails_base', 'sites',
            'phones_site', 'emails_site', 'god_otch', 'revenue', 'profit', 'ssch',
            'priority_total', 'priority_max', 'equip_by_okved', 'equip_categories',
            'calc_comment', 'revenue_rub', 'pxr']
ENR_COLS = ['inn', 'name', 'site', 'region', 'okved', 'activity', 'revenue_rub',
            'phones', 'best_email', 'pxr', 'is_competitor', 'verified']


def build_company(base, inn, obz, enr, core, sales_name):
    """Одна строка company: реквизиты из обзвона, дыры — из обогащения и core396.

    Приоритет источников ЗДЕСЬ важен: база обзвона — это выгрузка Checko с
    расчётом приоритетов владельца, она главная по реквизитам; enrich.db
    главнее по «живым» полям (сайт, вид деятельности), которые конвейер
    подтверждал краулом.
    """
    obz = obz or {}
    enr = enr or {}
    core = core or {}

    address = first_str(obz.get('address'))
    # companies.region в enrich.db фактически хранит ГОРОД (см. _persist),
    # поэтому он идёт последним — как грубая замена, а не как настоящий регион.
    region = first_str(obz.get('region'), region_from_address(address), enr.get('region'))
    site = first_str(first_site(obz.get('sites')), enr.get('site'))
    name_short = first_str(obz.get('name_short'), enr.get('name'), core.get('name'),
                           sales_name)
    name_full = first_str(obz.get('name_full'), core.get('name'), enr.get('name'),
                          name_short)

    revenue_num = first_num(obz.get('revenue_rub'), obz.get('revenue'),
                            enr.get('revenue_rub'), core.get('revenue_rub'))
    priority = to_int(obz.get('priority_total'))
    # «как в базе обзвона»: pxr = приоритет × выручка / 10000. Считаем сами,
    # когда есть оба слагаемых (значение сойдётся с колонкой pxr), иначе берём
    # готовый pxr — он бывает посчитан там, где выручку мы не распарсили.
    if priority and revenue_num:
        rank_metric = priority * revenue_num / 10000.0
    else:
        rank_metric = first_num(obz.get('pxr'), enr.get('pxr'))

    parts = [name_short, name_full, inn, address, first_str(obz.get('director'))]
    search_blob = '|'.join(p for p in parts if p).casefold()

    return {
        'base': base, 'inn': inn,
        'name_short': name_short, 'name_full': name_full,
        'ogrn': first_str(obz.get('ogrn'), core.get('ogrn')),
        'kpp': first_str(obz.get('kpp')),
        'status': first_str(obz.get('status')),
        'reg_date': first_str(obz.get('reg_date')),
        'address': address, 'region': region,
        'opf': first_str(obz.get('opf')),
        'director': first_str(obz.get('director')),
        'director_inn': first_str(obz.get('dir_inn')),
        'founders': first_str(obz.get('founders')),
        'okved_main': first_str(obz.get('okved_main'), enr.get('okved')),
        'okved_all': first_str(obz.get('okved_all_codes')),
        'equipment': first_str(obz.get('equip_by_okved')),
        'equipment_all': first_str(obz.get('equip_categories')),
        'revenue': first_str(obz.get('revenue'), enr.get('revenue_rub'),
                             core.get('revenue_rub')),
        'revenue_num': revenue_num,
        'revenue_year': first_str(obz.get('god_otch')),
        'profit': first_str(obz.get('profit')),
        'staff': first_str(obz.get('ssch')),
        'site': site,
        # calc_comment сюда НЕ кладём: это комментарий расчёта приоритета
        # («ОКВЭД 25.62 → компрессоры, балл 4»), а не вид деятельности
        'activity': first_str(enr.get('activity'), core.get('sector')),
        'priority': priority,
        'max_hit': to_int(obz.get('priority_max')),
        'rank_metric': rank_metric,
        'in_obzvon': 1 if obz else 0,
        'n_phones': 0, 'n_emails': 0, 'n_purchaser': 0, 'n_signals': 0,
        'search_blob': search_blob,
    }


# --------------------------------------------------------------------------- #
# Сборка контактов
# --------------------------------------------------------------------------- #
class ContactBox:
    """Копилка контактов одной базы с дедупом и «дозаписью лучшего».

    ЗАЧЕМ не «первый победил»: один и тот же номер приходит и из ЕИС (с ФИО,
    ролью и ссылкой на карточку закупки), и из реестра (голым). Побеждать
    должна запись со ссылкой и ролью — иначе главное требование владельца
    (кликабельный источник у каждого контакта) теряется на дублях.
    """

    def __init__(self, base, known_phones, known_emails):
        self.base = base
        self.known_phones = known_phones
        self.known_emails = known_emails
        self.items = {}          # (inn, kind, ключ) -> dict
        self.dropped = 0         # мусорных телефонов
        self.merged = 0          # схлопнутых дублей

    def add(self, inn, kind, value, key, person, role, source, url, in_sales):
        rec = {
            'base': self.base, 'inn': inn, 'kind': kind, 'value': value,
            'person': (person or '').strip(), 'role': (role or '').strip(),
            'source': source or '', 'source_url': url or '',
            'is_purchaser': is_purchaser(role, source, url),
            'in_sales_base': 1 if in_sales else 0,
        }
        k = (inn, kind, key)
        old = self.items.get(k)
        if old is None:
            self.items[k] = rec
            return
        self.merged += 1
        # источник и ссылка переносятся ТОЛЬКО парой: подпись «ЕИС» под ссылкой
        # на сайт компании — это враньё в панели, а не «дозапись недостающего»
        if rec['source_url'] and not old['source_url']:
            old['source_url'] = rec['source_url']
            if rec['source']:
                old['source'] = rec['source']
        for f in ('person', 'role'):
            if not old[f] and rec[f]:
                old[f] = rec[f]
        if not old['source'] and rec['source']:
            old['source'] = rec['source']
        old['is_purchaser'] = max(old['is_purchaser'], rec['is_purchaser'])
        old['in_sales_base'] = max(old['in_sales_base'], rec['in_sales_base'])

    def add_phone(self, inn, raw, person, role, source, url):
        d = norm_phone(raw)
        if not d:
            self.dropped += 1
            return
        self.add(inn, 'phone', fmt_phone(d), d, person, role, source, url,
                 d in self.known_phones)

    def add_email(self, inn, raw, person, role, source, url):
        e = norm_email(raw)
        if not e:
            return
        self.add(inn, 'email', e, e, person, role, source, url,
                 e in self.known_emails)

    def rows(self):
        # телефоны раньше email, закупщики выше — панель показывает как есть
        return sorted(self.items.values(),
                      key=lambda r: (r['inn'], 0 if r['kind'] == 'phone' else 1,
                                     -r['is_purchaser'], r['value']))


def collect_contacts(base, inns, companies, ph_rows, em_rows, known_phones,
                     known_emails, obz_by_inn, sales_own, with_base_contacts):
    """Контакты базы: обогащение (главное) + реквизиты выгрузки + то, что уже
    было у продажников. Последние два слоя дают панели полную картину «новый
    контакт против уже был», но помечены своими источниками."""
    box = ContactBox(base, known_phones, known_emails)
    wanted = set(inns)
    site_of = {i: (companies.get(i) or {}).get('site', '') for i in inns}

    # 1) обогащение — здесь живут ФИО, роли и ссылки на страницы-источники
    for r in ph_rows:
        inn = norm_inn(r.get('inn'))
        if inn not in wanted:
            continue
        url = str(r.get('source_url') or '').strip()
        box.add_phone(inn, r.get('phone'), r.get('person'), r.get('role'),
                      nice_source(r.get('source'), url, site_of.get(inn, '')), url)
    for r in em_rows:
        inn = norm_inn(r.get('inn'))
        if inn not in wanted:
            continue
        url = str(r.get('source_url') or '').strip()
        box.add_email(inn, r.get('email'), r.get('person'), r.get('role'),
                      nice_source(r.get('source'), url, site_of.get(inn, '')), url)

    if not with_base_contacts:
        return box

    # 2) реквизиты самой базы обзвона. Источник этих строк — карточка Checko
    #    (выгрузка сделана оттуда), поэтому ссылка на неё честная, а не выдуманная.
    for inn in inns:
        obz = obz_by_inn.get(inn)
        if not obz:
            continue
        ogrn = first_str(obz.get('ogrn'))
        checko = f'https://checko.ru/company/{ogrn or inn}'
        for d in phones_from_text(obz.get('phones_base')):
            box.add(inn, 'phone', fmt_phone(d), d, '', '', 'реестр (Checko)',
                    checko, d in known_phones)
        for e in emails_from_text(obz.get('emails_base')):
            box.add(inn, 'email', e, e, '', '', 'реестр (Checko)',
                    checko, e in known_emails)
        # «с сайта компании» — Checko снял их со страницы фирмы, ссылка = сайт
        site_url = as_url(site_of.get(inn, '') or first_site(obz.get('sites')))
        for d in phones_from_text(obz.get('phones_site')):
            box.add(inn, 'phone', fmt_phone(d), d, '', '', 'сайт компании',
                    site_url, d in known_phones)
        for e in emails_from_text(obz.get('emails_site')):
            box.add(inn, 'email', e, e, '', '', 'сайт компании',
                    site_url, e in known_emails)

    # 3) то, что уже лежало в базе продажников: ссылки нет, но панель обязана
    #    показывать «этот контакт у нас уже был» рядом с новыми.
    for inn in inns:
        own = sales_own.get(inn)
        if not own:
            continue
        for d in own['phones']:
            box.add(inn, 'phone', fmt_phone(d), d, '', '', 'база продажников',
                    '', True)
        for e in own['emails']:
            box.add(inn, 'email', e, e, '', '', 'база продажников', '', True)
    return box


# --------------------------------------------------------------------------- #
# Запись снимка
# --------------------------------------------------------------------------- #
COMPANY_FIELDS = ['base', 'inn', 'name_short', 'name_full', 'ogrn', 'kpp', 'status',
                  'reg_date', 'address', 'region', 'opf', 'director', 'director_inn',
                  'founders', 'okved_main', 'okved_all', 'equipment', 'equipment_all',
                  'revenue', 'revenue_num', 'revenue_year', 'profit', 'staff', 'site',
                  'activity', 'priority', 'max_hit', 'rank_metric', 'in_obzvon',
                  'n_phones', 'n_emails', 'n_purchaser', 'n_signals', 'search_blob']
CONTACT_FIELDS = ['base', 'inn', 'kind', 'value', 'person', 'role', 'source',
                  'source_url', 'is_purchaser', 'in_sales_base']
SIGNAL_FIELDS = ['base', 'inn', 'source', 'event_type', 'what', 'hotness', 'ts',
                 'source_url']


def snapshot_counts(out_path):
    """Что уже лежит в целевом файле: {'company': n, 'contact': n}. Нет файла или
    он ещё без наших таблиц — нули."""
    out = {'company': 0, 'contact': 0}
    if not os.path.exists(out_path):
        return out
    try:
        cx = sqlite3.connect(ro_uri(out_path), uri=True, timeout=30)
    except sqlite3.Error:
        return out
    try:
        for t in out:
            try:
                out[t] = cx.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
            except sqlite3.Error:
                pass
    finally:
        cx.close()
    return out


def write_snapshot(out_path, companies, contacts, signals):
    """DROP+CREATE+INSERT одной транзакцией.

    Транзакция здесь не про «скорость», а про читателя: панель держит открытое
    read-only соединение, и до COMMIT она видит СТАРЫЙ снимок целиком, а не
    пустые таблицы посреди пересборки. Журнал оставляем обычный (не WAL):
    read-only клиент WAL-базы требует доступа к -shm/-wal файлам, а нам нужен
    именно беспроблемный ro-доступ.
    """
    d = os.path.dirname(os.path.abspath(out_path))
    if d:
        os.makedirs(d, exist_ok=True)
    cx = sqlite3.connect(out_path, timeout=120, isolation_level=None)
    try:
        cx.execute('PRAGMA busy_timeout=120000')
        cx.execute('BEGIN IMMEDIATE')
        for t in ('company', 'contact', 'signal'):
            cx.execute(f'DROP TABLE IF EXISTS {t}')
        # индексы уходят вместе с таблицами, но старые сборки могли оставить свои
        for ix in ('ix_company_base', 'ix_company_rank', 'ix_contact', 'ix_signal'):
            cx.execute(f'DROP INDEX IF EXISTS {ix}')
        # по одному оператору, а НЕ executescript: тот делает неявный COMMIT и
        # разорвал бы транзакцию, из-за чего читатель увидел бы пустые таблицы
        for stmt in filter(None, (s.strip() for s in SCHEMA.split(';'))):
            cx.execute(stmt)

        cx.executemany(
            f'INSERT INTO company ({",".join(COMPANY_FIELDS)}) VALUES '
            f'({",".join("?" * len(COMPANY_FIELDS))})',
            [[c.get(f) for f in COMPANY_FIELDS] for c in companies])
        cx.executemany(
            f'INSERT INTO contact ({",".join(CONTACT_FIELDS)}) VALUES '
            f'({",".join("?" * len(CONTACT_FIELDS))})',
            [[c.get(f) for f in CONTACT_FIELDS] for c in contacts])
        cx.executemany(
            f'INSERT INTO signal ({",".join(SIGNAL_FIELDS)}) VALUES '
            f'({",".join("?" * len(SIGNAL_FIELDS))})',
            [[s.get(f) for f in SIGNAL_FIELDS] for s in signals])
        cx.execute('COMMIT')
        # ANALYZE — планировщику панели (1k компаний против 60k контактов), но
        # УЖЕ ПОСЛЕ фиксации и отдельной транзакцией. Свой except обязателен:
        # иначе занятая читателем база валила бы ГОТОВУЮ сборку, да ещё и через
        # ROLLBACK без транзакции — с подменой настоящей причины.
        try:
            cx.execute('ANALYZE')
        except sqlite3.Error:
            pass
    except Exception:
        # ROLLBACK сам падает, если транзакция не открылась (BEGIN не прошёл по
        # блокировке), и своей ошибкой заслоняет исходную — гасим.
        try:
            cx.execute('ROLLBACK')
        except sqlite3.Error:
            pass
        raise
    finally:
        cx.close()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description='Сборка автономной centrifugal.db для панели обзвона.')
    ap.add_argument('out', nargs='?', default=DEF_OUT, help='куда писать centrifugal.db')
    ap.add_argument('--obzvon', default=DEF_OBZVON, help='obzvon-index.db')
    ap.add_argument('--enrich', default=DEF_ENRICH, help='enrich.db')
    ap.add_argument('--sales', default=DEF_SALES, help='sales_base.json (centro1)')
    ap.add_argument('--core', default=DEF_CORE_TXT, help='centrifugal-core-inns.txt (centro2)')
    ap.add_argument('--core-json', default=DEF_CORE_JSON, help='core396.json (необязательно)')
    ap.add_argument('--only-enrich-contacts', action='store_true',
                    help='только контакты обогащения (без реквизитов базы и базы продажников)')
    ap.add_argument('--force', action='store_true',
                    help='перезаписать снимок, даже если новая сборка пустая')
    args = ap.parse_args(argv)

    t0 = time.time()
    warn = []
    sales_inns, sales_names, known_phones, known_emails, sales_own = load_sales(
        args.sales, warn)
    core_inns = load_core(args.core, warn)
    core_json = load_core_json(args.core_json)

    base_inns = {'centro1': sales_inns, 'centro2': core_inns}
    all_inns = sorted(set(sales_inns) | set(core_inns))

    obz_cx = ro_connect(args.obzvon, warn)
    enr_cx = ro_connect(args.enrich, warn)

    # реквизиты
    obz_by_inn = {norm_inn(r['inn']): r
                  for r in rows_by_inn(obz_cx, 'obzvon', OBZ_COLS, all_inns)}
    enr_by_inn = {norm_inn(r['inn']): r
                  for r in rows_by_inn(enr_cx, 'companies', ENR_COLS, all_inns)}
    # контакты и сигналы тянем ОДИН раз на оба списка (15 ИНН общие) и раскладываем
    ph_rows = rows_by_inn(enr_cx, 'phone_contacts',
                          ['inn', 'phone', 'person', 'role', 'source', 'source_url'],
                          all_inns)
    em_rows = rows_by_inn(enr_cx, 'emails',
                          ['inn', 'email', 'person', 'role', 'source', 'source_url'],
                          all_inns)
    # 'sum' тянем, хотя колонки под него в контракте нет: сумма закупки — самый
    # весомый для продажника факт повода, дописываем её в текст (см. ниже).
    sig_rows = rows_by_inn(enr_cx, 'signals',
                           ['inn', 'source', 'event_type', 'what', 'sum', 'hotness',
                            'ts', 'source_url'], all_inns)
    if obz_cx is not None:
        obz_cx.close()
    if enr_cx is not None:
        enr_cx.close()

    companies, contacts, signals = [], [], []
    report = {'выход': os.path.abspath(args.out), 'базы': {}}

    for base in ('centro1', 'centro2'):
        inns = base_inns[base]
        # компании
        by_inn = {}
        for inn in inns:
            rec = build_company(base, inn, obz_by_inn.get(inn), enr_by_inn.get(inn),
                                core_json.get(inn), sales_names.get(inn, ''))
            by_inn[inn] = rec

        box = collect_contacts(base, inns, by_inn, ph_rows, em_rows, known_phones,
                               known_emails, obz_by_inn,
                               {} if args.only_enrich_contacts else sales_own,
                               not args.only_enrich_contacts)
        base_contacts = box.rows()

        # сигналы
        wanted = set(inns)
        base_signals = []
        seen_sig = set()
        for r in sig_rows:
            inn = norm_inn(r.get('inn'))
            if inn not in wanted:
                continue
            k = (inn, r.get('source'), r.get('what'))
            if k in seen_sig:
                continue
            seen_sig.add(k)
            what = first_str(r.get('what'))
            amount = first_str(r.get('sum'))
            # сумма закупки лежит в signals.sum, а колонки под неё в контракте
            # нет — теряться она не должна, поэтому уходит в текст повода
            # (проверяем, что цифр нет уже в самом тексте — иначе дубль)
            if amount and re.search(r'\d', amount) \
                    and re.sub(r'\D', '', amount) not in re.sub(r'\D', '', what):
                what = f'{what}, сумма {amount}'.lstrip(', ')
            # источник повода панель печатает как есть, поэтому технический код
            # ('zakupki:eis') переводим тем же закрытым словарём, что и у
            # контактов; имя издания/донора незнакомо словарю и идёт как есть
            sig_src = first_str(r.get('source'))
            base_signals.append({
                'base': base, 'inn': inn,
                'source': SOURCE_LABEL.get(sig_src.lower(), sig_src),
                'event_type': first_str(r.get('event_type')),
                'what': what,
                'hotness': to_int(r.get('hotness'), 0),
                'ts': first_str(r.get('ts')),
                'source_url': first_str(r.get('source_url')),
            })

        # счётчики в карточке компании (панель не должна считать их запросами)
        for c in base_contacts:
            rec = by_inn.get(c['inn'])
            if not rec:
                continue
            rec['n_phones' if c['kind'] == 'phone' else 'n_emails'] += 1
            rec['n_purchaser'] += c['is_purchaser']
        for s in base_signals:
            rec = by_inn.get(s['inn'])
            if rec:
                rec['n_signals'] += 1

        companies.extend(by_inn.values())
        contacts.extend(base_contacts)
        signals.extend(base_signals)

        with_contacts = sum(1 for r in by_inn.values() if r['n_phones'] or r['n_emails'])
        report['базы'][base] = {
            'название': BASES[base],
            'ИНН_в_списке': len(inns),
            'компаний': len(by_inn),
            'нашлось_в_базе_обзвона': sum(1 for r in by_inn.values() if r['in_obzvon']),
            'с_контактами': with_contacts,
            'телефонов': sum(1 for c in base_contacts if c['kind'] == 'phone'),
            'email': sum(1 for c in base_contacts if c['kind'] == 'email'),
            'из_них_закупщиков': sum(1 for c in base_contacts if c['is_purchaser']),
            'со_ссылкой_источником': sum(1 for c in base_contacts if c['source_url']),
            'новых_против_базы_продажников': sum(
                1 for c in base_contacts if not c['in_sales_base']),
            'сигналов': len(base_signals),
            'компаний_с_сигналами': len({s['inn'] for s in base_signals}),
            'мусорных_телефонов_отброшено': box.dropped,
            'дублей_схлопнуто': box.merged,
        }

    # Предохранитель: запуск с неверными путями (нет C:\sender, опечатка в ключе)
    # собирает пустой снимок и МОЛЧА затирает рабочий — панель остаётся без
    # данных, а причина неочевидна. Пустую сборку поверх непустой не пишем.
    was = snapshot_counts(args.out)
    if not args.force and ((was['company'] and not companies)
                           or (was['contact'] and not contacts)):
        report['ОТКАЗ'] = (
            f'новая сборка пустая (компаний {len(companies)}, контактов {len(contacts)}), '
            f'а в снимке уже есть {was["company"]} компаний и {was["contact"]} контактов. '
            f'Проверьте пути к источникам; перезаписать намеренно — ключ --force.')
        report['предупреждения'] = warn
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    write_snapshot(args.out, companies, contacts, signals)

    report['было_в_снимке'] = was
    report['пересечение_баз'] = len(set(sales_inns) & set(core_inns))
    report['итого'] = {'компаний': len(companies), 'контактов': len(contacts),
                       'сигналов': len(signals)}
    report['контакты'] = ('только обогащение' if args.only_enrich_contacts
                          else 'обогащение + реквизиты базы + база продажников')
    report['секунд'] = round(time.time() - t0, 1)
    if warn:
        report['предупреждения'] = warn
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
