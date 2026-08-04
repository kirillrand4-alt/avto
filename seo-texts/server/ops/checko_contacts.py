# -*- coding: utf-8 -*-
"""Слой «Контактная информация» чеко для ОБЕИХ баз (продажники 555 + ядро 396):
страница /contacts карточки — блок «Телефоны» (форматированные номера) и
«Электронная почта». Каждый контакт с URL этой страницы. Жёсткий валидатор.
Резюмируемо: checko_contacts2_stream.jsonl. 50 потоков, socks5:3001.
Запуск: python checko_contacts.py [бюджет_сек]"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 480.0
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\checko_contacts2_stream.jsonl'

db = EDB.EnrichDB()
e = db.cx

# Домены, которые НЕ являются сайтом предприятия. Список не из головы: замер
# по живой базе показал в этом поле vk.ru, globas.credinform.ru и портал
# госуслуг вместо заводского сайта.
_ЧУЖОЙ_ДОМЕН = re.compile(
    r'(?:^|\.)(?:vk\.(?:com|ru)|ok\.ru|facebook|instagram|t\.me|telegram|'
    r'youtube|rutube|dzen\.ru)|checko|credinform|rusprofile|list-org|sbis\.ru|'
    r'zachestnyibiznes|audit-it|companium|inndex|star-pro|ofcheck|'
    r'gosuslugi\.ru|gosweb|\.gov\.ru|zakupki\.gov|mail\.ru|yandex\.|gmail|'
    r'googleapis|gstatic|cloudflare|jquery|bootstrap', re.I)

d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    os.environ.get('DROP_URL', '').rstrip('/') + '/dolphin-proxies.txt',
    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
PX = []
for l in d.open(req, timeout=30).read().decode('utf-8', 'replace').splitlines():
    l = l.strip()
    m = re.match(r'(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', l) if l and not l.startswith('#') else None
    if m:
        u, p, h, _ = m.groups()
        PX.append('socks5://%s:%s@%s:3001' % (u, p, h))

# СПИСОК ЦЕЛЕЙ. Раньше он был жёстко зашит в две базы (продажники 555 плюс
# ядро 396), и прогнать оп по любой другой выборке было нельзя. Тот же класс
# правки уже получили core_sites, lpr_serp и dept_directory: список целей —
# это параметр, а не константа.
_ЦЕЛЕВОЙ = (sys.argv[sys.argv.index('--targets') + 1]
            if '--targets' in sys.argv else '')
инны = []
if _ЦЕЛЕВОЙ:
    for ln in io.open(_ЦЕЛЕВОЙ, encoding='utf-8-sig', errors='replace'):
        m = re.search(r'\b(\d{10}|\d{12})\b', ln)
        if m and m.group(1) not in инны:
            инны.append(m.group(1))
    print('файл целей:', _ЦЕЛЕВОЙ, 'ИНН:', len(инны), flush=True)
else:
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in инны:
                инны.append(i)
    for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                      encoding='utf-8', errors='replace'):
        m = re.search(r'\b(\d{10}|\d{12})\b', ln)
        if m and m.group(1) not in инны:
            инны.append(m.group(1))

сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            сделано.add(str(json.loads(ln)['inn']))
        except Exception:  # noqa: BLE001
            continue
# ЗАНОВО. Отметка «сделано» значит «разобрано ПРЕЖНИМ парсером», а не «с этой
# карточки взято всё». Когда парсер учится новому полю (сегодня — сайт), старая
# отметка обязана перестать блокировать перечитывание: иначе улучшение молча
# достаётся только новым целям, а по уже пройденным поле остаётся пустым
# навсегда. Замер, на котором это вскрылось: из 223 предприятий без сайта 183
# чеко УЖЕ спрашивали.
_ЗАНОВО = '--zanovo' in sys.argv
todo = list(инны) if _ЗАНОВО else [i for i in инны if i not in сделано]
if _ЗАНОВО:
    print(f'перечитываю ЗАНОВО: {len(todo)} целей, отметка «сделано» не применяется',
          flush=True)

ogrn = {}
for i, o in e.execute("SELECT inn, ogrn FROM companies WHERE COALESCE(ogrn,'')<>''"):
    ogrn[str(i)] = str(o)
try:
    ix = __import__('sqlite3').connect(r'C:\sender\obzvon-index.db')
    for i, o in ix.execute("SELECT inn, ogrn FROM obzvon WHERE COALESCE(ogrn,'')<>''"):
        ogrn.setdefault(str(i), str(o))
except Exception:  # noqa: BLE001
    pass

ТЕЛ_ФОРМ = re.compile(r'\+7[\s\u00a0]?\(?\d{3}\)?[\s\u00a0]?\d{3}[-\s\u00a0]\d{2}[-\s\u00a0]\d{2}')
ПОЧТА = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,10}')


def валиден(s):
    """Правило «в хвосте больше одной разной цифры» убрано: оно выбрасывало
    8-800-555-55-55 и 495-777-77-77 — номера крупных компаний."""
    ц = re.sub(r'\D', '', s)
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return (len(ц) == 10 and ц[0] != '0' and ц[:3] != '000'
            and len(set(ц)) > 1
            and ц not in ('0000000000', '1234567890', '9999999999'))


замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
# руководители — отдельным durable-потоком: колонок под них в companies может
# не быть, а терять разобранное нельзя
ф_рук = io.open(r'C:\seostat\drop\checko_heads.jsonl', 'a', encoding='utf-8')
_есть_колонки = {r[1] for r in e.execute('pragma table_info(companies)')} >= {
    'director', 'director_post'}
if not _есть_колонки:
    for кол in ('director', 'director_post'):
        try:
            e.execute(f'ALTER TABLE companies ADD COLUMN {кол} TEXT')
        except Exception:  # noqa: BLE001
            pass
    e.commit()
    _есть_колонки = {r[1] for r in e.execute('pragma table_info(companies)')} >= {
        'director', 'director_post'}
_есть_сайт = 'site' in {r[1] for r in e.execute('pragma table_info(companies)')}
out = {'целей': len(todo), 'обработано': 0, 'тел': 0, 'почт': 0, 'ошибок': 0,
       'без_карточки': 0, 'руководителей': 0, 'сайтов': 0}


def работа(t):
    idx, inn = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    px = PX[idx % len(PX)]
    ог = ogrn.get(inn)
    urls = []
    if ог:
        urls.append('https://checko.ru/company/%s/contacts' % ог)
    urls.append('https://checko.ru/search?query=%s' % inn)
    html, фин = '', ''
    for u in urls:
        try:
            r = requests.get(u, proxies={'http': px, 'https': px},
                             headers={'User-Agent': 'Mozilla/5.0'}, timeout=25,
                             allow_redirects=True)
            if r.status_code != 200 or '/company/' not in str(r.url):
                continue
            фин = str(r.url)
            if not фин.rstrip('/').endswith('/contacts'):
                # с поиска попали на карточку - дотягиваем /contacts
                база = фин.split('?')[0].rstrip('/')
                r2 = requests.get(база + '/contacts',
                                  proxies={'http': px, 'https': px},
                                  headers={'User-Agent': 'Mozilla/5.0'},
                                  timeout=25)
                if r2.status_code == 200:
                    фин = база + '/contacts'
                    html = r2.text
                    break
            html = r.text
            break
        except Exception:  # noqa: BLE001
            continue
    with замок:
        out['обработано'] += 1
        if not html:
            out['без_карточки'] += 1
            ф.write(json.dumps({'inn': inn, 'err': 'нет карточки'},
                               ensure_ascii=False) + '\n')
            ф.flush()
            return
        # блок «Контактная информация»: телефоны только форматированные
        чистый = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html,
                        flags=re.S | re.I)
        # Обрезаем подвал (реклама/др. компании) по маркеру формы правки.
        # Ищем ПОСЛЕДНЕЕ вхождение: нежадный поиск резал по маркеру, который
        # мог встретиться в шапке или в тексте кнопки, и тогда блок контактов
        # оставался за срезом — компания получала ноль контактов, а в резюм
        # писался успех.
        поз = -1
        for маркер in ('Нашли ошибку в контактах', 'Предложить исправление',
                       'Похожие компании', 'Портал «Чекко»', 'Портал «Чекко»'):
            i = чистый.rfind(маркер)
            if i > поз:
                поз = i
        основа = чистый[:поз] if поз > 2000 else чистый
        # телефоны берём из блока «Телефоны», почты из «Электронная почта»
        текст = re.sub(r'<[^>]+>', ' ', основа)
        телефоны = [т for т in dict.fromkeys(ТЕЛ_ФОРМ.findall(текст))
                    if валиден(т)][:30]
        # почты: только href mailto ИЛИ явные адреса из блока (без чужих
        # доменов площадки)
        mail_href = re.findall(r'mailto:([\w.+-]+@[\w.-]+)', основа)
        почты_все = list(dict.fromkeys(
            [p.lower() for p in mail_href]
            + [p.lower() for p in ПОЧТА.findall(текст)]))
        почты = [p for p in почты_все
                 if 'checko' not in p and not p.endswith('.png')
                 and not p.endswith('.jpg')][:30]
        # Руководитель с ДОЛЖНОСТЬЮ — единственное ФИО, доступное по каждой
        # компании; страница уже скачана, разбор стоит ноль запросов. Нужен и
        # для персонализации письма, и чтобы при звонке было кого спросить.
        # САЙТ. Владелец: «сессия сайты найти не может по 491 из чеко». Он и
        # правда там есть — на ЭТОЙ ЖЕ странице контактов, рядом с телефонами,
        # то есть разбор стоит ноль лишних запросов. Раньше оп его просто не
        # читал, и материал пропадал.
        # Берём из href, а не из текста: чеко печатает домен ссылкой, а в
        # тексте рядом попадаются чужие адреса (соцсети, сам чеко, госпорталы).
        сайт = ''
        for м in re.finditer(r'href="(https?://[^"]+)"', основа):
            д = re.sub(r'^https?://(?:www\.)?', '', м.group(1)).split('/')[0].lower()
            if not re.match(r'^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$', д):
                continue
            if _ЧУЖОЙ_ДОМЕН.search(д):
                continue
            сайт = д
            break

        рук_фио, рук_долж = '', ''
        rm = re.search(
            r'Руководител\w*[^А-Яа-яЁё]{0,40}([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'
            r'(?:\s+[А-ЯЁ][а-яё]+)?)', текст)
        if rm:
            рук_фио = rm.group(1)
            dm = re.search(
                r'((?:Генеральн\w+|Исполнительн\w+|Техническ\w+|Управляющ\w+)?\s*'
                r'(?:директор\w*|президент\w*|начальник\w*|управляющ\w*|'
                r'председател\w*[^,;.]{0,30}))',
                текст[max(0, rm.start() - 120):rm.start()], re.I)
            рук_долж = re.sub(r'\s+', ' ', dm.group(1)).strip() if dm else 'руководитель'

        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        for т in телефоны:
            # РОЛЬ «общий», а не «контакты компании (чеко)». Прежняя строка
            # была ПОДПИСЬЮ ИСТОЧНИКА, записанной не в ту графу: провенанс и
            # так лежит в колонке source. Цена ошибки — любой отчёт с условием
            # role NOT IN ('','общий') считал все 2805 таких телефонов
            # «имеющими осмысленную роль», хотя роли у них нет вовсе.
            e.execute('INSERT OR REPLACE INTO phone_contacts VALUES (?,?,?,?,?,?,?)',
                      (inn, т, '', 'общий',
                       'checko:contacts', фин, ts))
            out['тел'] += 1
        if рук_фио:
            e.execute("UPDATE companies SET director=?, director_post=? WHERE inn=?"
                      if _есть_колонки else
                      "UPDATE companies SET name=name WHERE inn=?",
                      ((рук_фио, рук_долж, inn) if _есть_колонки else (inn,)))
            out['руководителей'] = out.get('руководителей', 0) + 1
            ф_рук.write(json.dumps({'inn': inn, 'фио': рук_фио,
                                    'должность': рук_долж, 'url': фин},
                                   ensure_ascii=False) + '\n')
            ф_рук.flush()
        if сайт and _есть_сайт:
            # Только в ПУСТУЮ клетку: занятую мог заполнить первоисточник.
            e.execute("UPDATE companies SET site=? WHERE inn=? "
                      "AND COALESCE(site,'')=''", (сайт, inn))
            out['сайтов'] = out.get('сайтов', 0) + 1
        for п in почты:
            e.execute("INSERT OR IGNORE INTO emails(inn,email,role,person,"
                      "source,source_url,updated_at) VALUES(?,?,?,?,?,?,?)",
                      (inn, п, '', '', 'checko:contacts', фин, ts))
            out['почт'] += 1
        e.commit()
        ф.write(json.dumps({'inn': inn, 'тел': len(телефоны),
                            'почт': len(почты)}, ensure_ascii=False) + '\n')
        ф.flush()


with ThreadPoolExecutor(max_workers=50) as пул:
    list(пул.map(работа, enumerate(todo)))
ф.close()
ф_рук.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
