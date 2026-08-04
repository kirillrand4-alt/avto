# -*- coding: utf-8 -*-
"""Имена со страниц контактов: разбор БЛОКАМИ вместо построчного.

ЗАЧЕМ. Владелец показал экраном: в карточке ВОЛТАЙР-ПРОМ 67 контактов и у всех
«Имя не указано», а на сайте `voltyre-prom.ru/contacts/` рядом с теми же
номерами стоят ФИО, должность и почта. Обход брал то, что похоже на телефон, и
выбрасывал соседей по блоку.

Проверено на этой самой странице: блочный разбор дал **19 человек — у всех
телефон, у 18 должность, у 14 почта** — там, где было 67 безымянных номеров.

КАК УСТРОЕН РАЗБОР. Имя, должность, почта и телефоны одного человека лежат в
ОДНОМ узле страницы, и ценно именно соседство. Признак начала блока — ФИО из
трёх слов, где третье кончается отчеством; всё до следующего ФИО принадлежит
ему. Отчество здесь не украшение: без него в улов идут названия отделов и
«Правительства Российской Федерации».

ЧЕГО НЕ ДЕЛАЕМ. Не берём номер из блока, если он встречается у ДВУХ И БОЛЕЕ
разных людей на той же странице: это линия отдела, а не личный номер. Правило
то же, что для общих номеров в панели, и по той же причине.

ДОЛГОВЕЧНОСТЬ. Каждое предприятие пишется строкой в `lica_blokami.jsonl` с
fsync сразу; повторный запуск пропускает уже пройденные.

Запуск: python lica_blokami.py [--lim N] [--potokov N] [--apply]
"""
import json
import os
import re
import sqlite3
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ENR = r'C:\sender\enrich.db'
ПОТОК = r'C:\seostat\drop\lica_blokami.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


ЛИМ = арг('--lim', 120)
ПОТОКОВ = арг('--potokov', 6)

ОТЧ = re.compile(r'(ович|евич|ьич|овна|евна|ична)$', re.I)
ФИО = re.compile(r'\b([А-ЯЁ][а-яё-]{2,})\s+([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,})\b')
ТЕЛ = re.compile(r'(?:\+7|8)?[\s(-]*(\d{3,4})[\s)-]*(\d{2,3})[\s-]*(\d{2})[\s-]*(\d{2})')
ПОЧТА = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
ДОЛЖ = re.compile(
    r'(начальник|руководител|менеджер|директор|главный|заместител|инженер|'
    r'специалист|механик|энергетик|технолог|мастер|диспетчер)[^|]{0,70}', re.I)
СТРАНИЦЫ = ('/contacts/', '/kontakty/', '/contact/', '/about/contacts/',
            '/o-kompanii/kontakty/', '/company/contacts/', '/')
_замок = threading.Lock()


def прокси():
    import urllib.request
    d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    зпр = urllib.request.Request(
        os.environ.get('DROP_URL', '').rstrip('/') + '/dolphin-proxies.txt',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    из = []
    for l in d.open(зпр, timeout=30).read().decode('utf-8', 'replace').splitlines():
        l = l.strip()
        m = (re.match(r'(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', l)
             if l and not l.startswith('#') else None)
        if m:
            u, pw, h, _ = m.groups()
            из.append('socks5://%s:%s@%s:3001' % (u, pw, h))
    return из


PX = []


def взять(url, i):
    import requests
    for попытка in range(3):
        px = PX[(i * 7 + попытка * 13) % len(PX)] if PX else None
        try:
            r = requests.get(url, proxies=({'http': px, 'https': px} if px else None),
                             timeout=40, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code < 400 and len(r.text) > 400:
                return r.text
        except Exception:  # noqa: BLE001
            continue
    return ''


def люди_из_страницы(html):
    т = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html)
    т = re.sub(r'<[^>]+>', ' | ', т)
    т = re.sub(r'\s+', ' ', т)
    т = re.sub(r'(\s*\|\s*)+', ' | ', т)
    точки = [(м.start(), ' '.join(м.groups())) for м in ФИО.finditer(т)
             if ОТЧ.search(м.group(3))]
    сырые = []
    for н, (поз, имя) in enumerate(точки):
        конец = точки[н + 1][0] if н + 1 < len(точки) else min(len(т), поз + 700)
        блок = т[поз:конец]
        почты = ПОЧТА.findall(блок)
        телы = []
        for м in ТЕЛ.finditer(блок.replace('|', ' ')):
            ц = re.sub(r'\D', '', м.group(0))
            if len(ц) == 10:
                ц = '7' + ц
            if len(ц) == 11 and ц[0] in '78' and ц[1] in '3489':
                телы.append('+7' + ц[1:])
        д = ДОЛЖ.search(блок)
        сырые.append({'chelovek': имя,
                      'dolzhnost': (д.group(0).strip(' |')[:70] if д else ''),
                      'pochta': (почты[0] if почты else ''),
                      'telefony': sorted(set(телы))[:3]})
    # номер, стоящий у 2+ РАЗНЫХ людей на этой же странице — линия отдела
    сколько = Counter()
    for ч in сырые:
        for т_ in set(ч['telefony']):
            сколько[т_] += 1
    for ч in сырые:
        ч['telefony'] = [т_ for т_ in ч['telefony'] if сколько[т_] < 2]
    return сырые


def пройдено():
    было = set()
    if os.path.exists(ПОТОК):
        for стр in open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                было.add(str(json.loads(стр).get('inn') or ''))
            except Exception:  # noqa: BLE001
                continue
    return было


def записать(з):
    with _замок:
        with open(ПОТОК, 'a', encoding='utf-8') as ф:
            ф.write(json.dumps(з, ensure_ascii=False) + '\n')
            ф.flush()
            os.fsync(ф.fileno())


def цели():
    """Видимые предприятия, где есть безымянные номера И известен сайт."""
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    скр = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(inn,'') FROM hidden_item WHERE kind='company'")}
    пр.close()
    безым = Counter()
    for и, ч in цб.execute(
            "SELECT inn, COALESCE(person,'') FROM contact WHERE kind='phone'"):
        if not str(ч).strip():
            безым[str(и)] += 1
    из = []
    for и, сайт, имя in цб.execute(
            "SELECT inn, COALESCE(sayt,''), COALESCE(predpriyatie,'') FROM company"):
        и = str(и)
        if и in скр or not сайт.strip() or безым.get(и, 0) < 3:
            continue
        из.append((и, сайт.strip(), имя, безым[и]))
    цб.close()
    из.sort(key=lambda x: -x[3])
    return из


def main():
    global PX
    PX = прокси()
    было = пройдено()
    сп = [ц for ц in цели() if ц[0] not in было][:ЛИМ]
    print(f'целей в этот заход {len(сп)} (уже пройдено {len(было)}), '
          f'прокси {len(PX)}', flush=True)
    стат = Counter()

    def один(пара):
        i, (инн, сайт, имя, безым) = пара
        база = сайт if сайт.startswith('http') else 'https://' + sayt_чист(сайт)
        лучшие = []
        for путь in СТРАНИЦЫ:
            html = взять(база.rstrip('/') + путь, i)
            if not html:
                continue
            л = [ч for ч in люди_из_страницы(html) if ч['telefony'] or ч['pochta']]
            if len(л) > len(лучшие):
                лучшие = л
            if len(лучшие) >= 5:
                break
        з = {'inn': инн, 'name': имя, 'sayt': база, 'bezymyannyh_bylo': безым,
             'lica': лучшие, 'ts': int(time.time())}
        записать(з)
        return з

    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        for з in пул.map(один, list(enumerate(сп))):
            стат['предприятий пройдено'] += 1
            стат['ЛЮДЕЙ НАЙДЕНО'] += len(з['lica'])
            if з['lica']:
                стат['предприятий с людьми'] += 1
            стат['с телефоном'] += sum(1 for ч in з['lica'] if ч['telefony'])
            стат['с почтой'] += sum(1 for ч in з['lica'] if ч['pochta'])
    print(json.dumps(стат.most_common(), ensure_ascii=False, indent=1))


def sayt_чист(s):
    return re.sub(r'^https?://', '', str(s or '')).strip('/')


if __name__ == '__main__':
    main()
