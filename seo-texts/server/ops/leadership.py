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
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import celi_obshchie as ЦЕЛИ  # noqa: E402
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 600.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 6
ТОЛЬКО = (sys.argv[sys.argv.index('--only') + 1]
          if '--only' in sys.argv else 'sales')
ОДИН = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv else '')
# Лимит на круг: без него `--iz-paneli` даст 981 цель в один прогон,
# а задание раннера живёт 1800 секунд. Резюмируемость есть (ПОТОК),
# поэтому круги просто повторяют.
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]
           if '--limit' in sys.argv else 300)
# поиск через xmlriver стоит канала и квоты — можно отключить
БЕЗ_ПОИСКА = '--no-search' in sys.argv
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


# ОБЩЕЕ СОСТОЯНИЕ ПРОГОНА. Этих трёх строк в файле НЕ БЫЛО: ни замка, ни
# счётчиков, ни файла резюма, хотя воркер пользуется всеми тремя. То есть оп
# падал с NameError на первой же обработанной компании — и падал молча, потому
# что его после перевода на общий выбор целей ни разу не запускали. Канал,
# который в отчётах числился «главным источником ФИО с должностью», не работал
# вовсе. Пишем их обратно и печатаем итог, чтобы «прогнали» и «получили» опять
# не разошлись.
замок = threading.Lock()
out = {'обработано': 0, 'страниц': 0, 'филиалов': 0, 'людей': 0,
       'с_телефоном': 0, 'техЛПР': 0, 'из_поиска': 0, 'ошибок': 0,
       'без_сайта': 0, 'усечено_страниц': 0, 'примеры': []}
ф = open(ПОТОК, 'a', encoding='utf-8')


def цели():
    """Цели прогона. Раньше здесь был ЗАШИТ `sales_base.json` — 555 предприятий
    базы продажников, при том что в панели их 1573. То есть канал молча ходил
    по трети базы, а прогон при этом завершался успешно.

    Теперь список задаётся снаружи и печатается: `--inn`, `--targets ФАЙЛ`,
    `--iz-paneli [--vse]`. Без аргументов поведение прежнее — менять умолчание
    молча нельзя, по нему запускают руками.
    """
    цели_, откуда = ЦЕЛИ.выбрать(журнал=ПОТОК, лимит=ЛИМИТ)
    print(f'цели прогона: {откуда}, к обходу {len(цели_)}')
    sys.stdout.flush()
    return цели_


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


def сайт_по_инн(inn):
    """Домен предприятия: сначала база панели, потом enrich.db.

    Прежний `todo` был списком пар (ИНН, сайт) из sales_base.json, и после
    перевода на общий выбор целей воркер стал получать голый ИНН и падать на
    распаковке. Сайт теперь ищется сам — иначе канал работает только по тому
    файлу, из-за которого его и переводили.
    """
    for запрос, путь in (
            ("SELECT sayt FROM company WHERE inn=?",
             os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'),):
        try:
            cx = sqlite3.connect(f'file:{путь}?mode=ro', uri=True, timeout=20)
            р = cx.execute(запрос, (inn,)).fetchone()
            cx.close()
            if р and (р[0] or '').strip():
                return str(р[0]).strip().split()[0].split('|')[0]
        except Exception:  # noqa: BLE001
            pass
    try:
        д = EDB.EnrichDB()
        р = д.cx.execute(
            "SELECT site FROM companies WHERE inn=? AND COALESCE(site,'')<>''",
            (inn,)).fetchone()
        if р:
            return str(р[0]).strip()
    except Exception:  # noqa: BLE001
        pass
    return ''


def работа(t):
    if isinstance(t, str):
        inn, сайт = t, сайт_по_инн(t)
        if not сайт:
            with замок:
                out['обработано'] += 1
                out.setdefault('без_сайта', 0)
                out['без_сайта'] += 1
                ф.write(json.dumps({'inn': inn, 'err': 'сайт неизвестен'},
                                   ensure_ascii=False) + '\n')
                ф.flush()
                os.fsync(ф.fileno())
            return
    else:
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
        # А ЕЩЁ страницы из ПОИСКОВОГО ИНДЕКСА: блок руководства часто лежит на
        # странице, не слинкованной с главной, и обходом её не найти вовсе
        # (наводка владельца 29.07). Домен фильтруется, годность решает разбор.
        из_поиска = []
        if not БЕЗ_ПОИСКА:
            try:
                имя_к = (e.execute('SELECT name FROM companies WHERE inn=?',
                                   (inn,)).fetchone() or [''])[0]
                из_поиска = EC.find_leadership_via_search(
                    {'name': имя_к}, dom, max_urls=4)
                if из_поиска:
                    with замок:
                        out['из_поиска'] = out.get('из_поиска', 0) + len(из_поиска)
            except Exception:  # noqa: BLE001
                из_поиска = []
        план = list(dict.fromkeys(рук + доп + из_поиска))[:14]
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


# СПИСОК БЕРЁТСЯ ИЗ `цели()`, а не из переменной `todo`. `todo` осталась от
# прежней версии с зашитым sales_base.json и после перевода на общий выбор
# целей просто перестала существовать: оп падал с NameError на первом же
# запуске. Это цена того, что канал перевели на новый выбор целей и НИ РАЗУ
# не запустили — «переведён» и «работает» разные вещи.
_цели = цели()
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, _цели))
ф.close()
print(json.dumps(out, ensure_ascii=False, indent=1))
sys.stdout.flush()
os._exit(0)
