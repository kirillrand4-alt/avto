# -*- coding: utf-8 -*-
"""Страницы «Руководство» и обход филиалов группы (способы А1–А3).

Почему это главный источник (по разбору engineers-lens, проверено на живой
группе «Россети Волга»): страница руководства даёт полное ФИО с отчеством,
ТЕКУЩУЮ должность, прямой телефон и почту одним GET, тогда как протокол закупки
даёт инициалы и роль на дату документа. Семь главных инженеров сняты примерно
за 12 запросов.

Три входа, по убыванию отдачи:
  А1 страница руководства компании;
  А2 отдельная страница блока главного инженера («Контакты подразделений»,
     «Структура») — там у замов ПРЯМЫЕ номера, а не коммутатор;
  А3 список филиалов на сайте головной компании -> страница руководства каждого
     филиала. Для холдинга это цикл, а не один GET, и без него мы берём одну
     страницу вместо десятка.

Разбор — ПО РАЗМЕТКЕ (people_from_html), а не по плоскому тексту: должность и
телефон лежат в одной ячейке таблицы, ФИО в соседней, и парсер по порядку
текста смещает привязку на одного человека (ловушка В2).

Пишем в people (человек с должностью — ДАЖЕ БЕЗ КОНТАКТОВ), а телефоны и почты
дополнительно в phone_contacts/emails со ссылкой на страницу-источник.
Резюмируемо: leadership_stream.jsonl, строки с ошибкой в резюм не попадают.

Запуск: python leadership.py [бюджет_сек] [потоков] [--only sales] [--inn ИНН]
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 600.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 6
ТОЛЬКО = (sys.argv[sys.argv.index('--only') + 1]
          if '--only' in sys.argv else 'sales')
ОДИН = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv else '')
НАЧАЛО = time.time()
# --stream ИМЯ: свой файл резюма. Нужен, когда меняется РАЗБОР: старый
# чекпоинт отметил компании пройденными, и переразбор не пошёл бы вовсе.
_имя = (sys.argv[sys.argv.index('--stream') + 1]
        if '--stream' in sys.argv else 'leadership_stream.jsonl')
ПОТОК = r'C:\seostat\drop' + '\\' + _имя
КЭШ = r'C:\seostat\drop\pagecache'

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS phone_contacts(
    inn TEXT, phone TEXT, person TEXT, role TEXT,
    source TEXT, source_url TEXT, updated_at TEXT,
    PRIMARY KEY (inn, phone, source_url))""")
e.commit()

# страницы руководства: сперва они, потом филиалы (у филиала своя страница)
_РУК = ('rukovodstvo', 'руководств', 'menedzhment', 'менеджмент', 'management',
        'apparat', 'аппарат', 'administrac', 'администрац', 'struktura',
        'структур', 'komanda', 'team', 'staff', 'sotrudniki', 'сотрудник',
        'podrazdelen', 'подразделен', 'kontakty-podrazdelen')
_ФИЛ = ('filial', 'филиал', 'branch', 'otdelen', 'отделен', 'predstavit',
        'представит', 'region', 'регион')


def цели():
    из = []
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    было = set()
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append(i)
    if ТОЛЬКО != 'sales':
        for ln in io.open(r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt',
                          encoding='utf-8', errors='replace'):
            m = re.search(r'\b(\d{10}|\d{12})\b', ln)
            if m and m.group(1) not in было:
                было.add(m.group(1))
                из.append(m.group(1))
    сайты = {r[0]: r[1] for r in e.execute(
        "select inn, site from companies where coalesce(site,'')<>''")}
    return [(i, сайты[i]) for i in из if сайты.get(i)]


сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            j = json.loads(ln)
            if not j.get('err'):
                сделано.add(str(j['inn']))
        except Exception:  # noqa: BLE001
            continue

todo = [(i, s) for i, s in цели() if i not in сделано]
if ОДИН:
    todo = [(i, s) for i, s in цели() if i == ОДИН]

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'целей': len(todo), 'обработано': 0, 'ошибок': 0, 'страниц': 0,
       'филиалов': 0, 'людей': 0, 'с_телефоном': 0, 'техЛПР': 0,
       'усечено_страниц': 0, 'примеры': []}


def _страницы_из_кэша(inn):
    """Уже скачанные страницы компании: сеть не трогаем вовсе."""
    p = os.path.join(КЭШ, f'{inn}.json.gz')
    if not os.path.exists(p):
        return []
    try:
        import gzip
        with gzip.open(p, 'rb') as f:
            d = json.loads(f.read().decode('utf-8', 'replace'))
        with замок:
            out['усечено_страниц'] += sum(
                1 for x in (d.get('pages') or []) if x.get('html_truncated'))
        return [(x.get('url') or '', x.get('html') or '')
                for x in (d.get('pages') or []) if x.get('html')]
    except Exception:  # noqa: BLE001
        return []


def _взять(url):
    try:
        h, _m, mt = EC._fetch_site(url)
        return '' if (not h or mt.get('captcha_type')) else h
    except Exception:  # noqa: BLE001
        return ''


def работа(t):
    inn, сайт = t
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    итог = {'inn': inn}
    try:
        if not сайт.startswith('http'):
            сайт = 'http://' + сайт
        dom = EC._domain(сайт)
        страницы = _страницы_из_кэша(inn)
        главная = страницы[0][1] if страницы else _взять(сайт)
        if not главная:
            итог['err'] = 'главная не открылась'
            raise RuntimeError(итог['err'])
        # 1) страницы руководства с главной + всё, что уже в кэше
        ссылки = EC.branch_links(главная, dom)
        рук = [u for u in ссылки if any(h in u.lower() for h in _РУК)]
        фил = [u for u in ссылки if any(h in u.lower() for h in _ФИЛ)]
        # 2) А3: с каждой страницы филиалов достаём ссылки на их руководство
        доп = []
        for u in фил[:6]:
            h = _взять(u)
            if not h:
                continue
            with замок:
                out['страниц'] += 1
                out['филиалов'] += 1
            доп += [x for x in EC.branch_links(h, dom)
                    if any(k in x.lower() for k in _РУК)]
        план = list(dict.fromkeys(рук + доп))[:12]
        люди = []
        # Разбираем ВСЕ уже скачанные страницы, а не только те, где слово-
        # подсказка попало в АДРЕС. Замер показал, почему это важно: из 404
        # компаний людей дали лишь 41 — остальные отсеивались фильтром по URL,
        # хотя блок руководства часто лежит на /about/ или /company/ без всякого
        # ключевого слова в пути. Кэш уже скачан, разбор его бесплатен.
        for u, h in страницы:
            люди += EC.people_from_html(h, u)
        for u in план:
            if time.time() - НАЧАЛО > БЮДЖЕТ:
                break
            h = _взять(u)
            if not h:
                continue
            with замок:
                out['страниц'] += 1
            люди += EC.people_from_html(h, u)
        # дедуп по ФИО+должность
        свод = {}
        for ч in люди:
            k = (ч['person'].lower(), (ч.get('post') or '').lower())
            вес = sum(1 for п in ('post', 'phone', 'email') if ч.get(п))
            if k not in свод or вес > свод[k][0]:
                свод[k] = (вес, ч)
        люди = [v[1] for v in свод.values()]
        итог['людей'] = len(люди)
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        with замок:
            for ч in люди:
                роль = EDB.EnrichDB._canon_role(ч.get('post') or '')
                db.add_person(inn, ч['person'], post=ч.get('post') or '',
                              phone=ч.get('phone') or '', email=ч.get('email') or '',
                              source='сайт:руководство', source_url=ч.get('url') or '')
                out['людей'] += 1
                if ч.get('phone'):
                    out['с_телефоном'] += 1
                    ключ = re.sub(r'\D', '', ч['phone'])[-10:]
                    если_есть = e.execute(
                        'SELECT rowid, phone FROM phone_contacts WHERE inn=?',
                        (inn,)).fetchall()
                    своя = next((r for r in если_есть
                                 if re.sub(r'\D', '', r[1] or '')[-10:] == ключ), None)
                    if своя:
                        e.execute('UPDATE phone_contacts SET person=?, role=?, '
                                  'source=?, source_url=?, updated_at=? WHERE rowid=?',
                                  (ч['person'], роль or 'руководство',
                                   'сайт:руководство', ч.get('url') or '', ts, своя[0]))
                    else:
                        e.execute('INSERT INTO phone_contacts'
                                  '(inn,phone,person,role,source,source_url,updated_at)'
                                  ' VALUES (?,?,?,?,?,?,?)',
                                  (inn, ч['phone'], ч['person'],
                                   роль or 'руководство', 'сайт:руководство',
                                   ч.get('url') or '', ts))
                if ч.get('email'):
                    db.add_email(inn, ч['email'], role=ч.get('post') or '',
                                 person=ч['person'], source='сайт:руководство',
                                 source_url=ч.get('url') or '')
                if роль in EDB.EnrichDB.TECH_ROLES:
                    out['техЛПР'] += 1
                    if len(out['примеры']) < 15:
                        out['примеры'].append(
                            {'инн': inn, 'фио': ч['person'],
                             'должность': ч.get('post'), 'роль': роль,
                             'тел': ч.get('phone'), 'почта': ч.get('email'),
                             'откуда': (ч.get('url') or '')[:70]})
            e.commit()
    except Exception as ex:  # noqa: BLE001
        итог.setdefault('err', f'{type(ex).__name__}: {str(ex)[:70]}')
        with замок:
            out['ошибок'] += 1
    with замок:
        out['обработано'] += 1
        ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, todo))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
sys.stdout.flush()
os._exit(0)
