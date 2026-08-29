# -*- coding: utf-8 -*-
r"""Вытяжка почт, ролей и телефонов из сырых страниц Зенки, лежащих на D:.

Владелец 29.08: «а потом будем вытягивать адреса, их роли со страниц (если в базе
они ещё не известны) ну и номера телефонов сразу» и «можем разбирать те что уже
пришли файлы параллельно? а то опять упустим что то».

ЗАЧЕМ. В razobrano 136 ГБ сырья, которое считалось отработанным. Проверка 29.08:
из ста компаний у 68 в сыром HTML нашлись адреса, которых в базе нет — 169 новых
на 175 найденных. Страницы разбирались ради паспортов сайта, а контакты с них
системно не снимались.

ОДИН ПРОХОД. Перечитывать 136 ГБ второй раз — расточительство, поэтому за проход
берём всё сразу: адреса во всех вариациях написания, роль ящика, телефоны и
контекст ±80 символов вокруг адреса. Контекст нужен, чтобы потом доставать
фамилию и должность провайдером, НЕ перечитывая страницы.

ПАРАЛЛЕЛЬНО С ПЕРЕНОСОМ — можно. Берём только те файлы, у которых близнец на C:
уже удалён: perenos_razobrano.py удаляет исходник лишь после того, как копия
совпала по размеру, поэтому «исходника нет» = «копия целая». Файл, который прямо
сейчас копируется, мы не трогаем.

НЕ ТРОГАЕМ enrich.db. Ночные сверки держат его по четверти часа, и 887 тысяч
файлов на такой замок ставить нельзя. Пишем в отдельную базу-накопитель на D:
(никакой конкуренции), а в enrich.db переливает потом отдельный тихий слив
(slit_nahodki.py) — тем же приёмом окон, что уже отработал на копилках.

РЕЗЮМИРУЕМОСТЬ по компаниям: таблица sdelano в той же базе на D:. Рестарт
песочницы, перезагрузка сервера, падение процесса — продолжаем с места.

ДВА ИСТОЧНИКА. Сырьё Зенки на D: — полные страницы, как их отдал сайт. Кэш
конвейера (pagecache) — то же самое, но урезанное (страница до 300 тысяч знаков,
компания до 2,5 МБ) и зато ПОЛНОЕ по охвату: туда попадает каждая скачанная
страница, чем бы её ни брали — Зенкой в любом режиме или питоновским краулером.
Владелец 29.08: «чтобы всегда и везде брались и почты и телефоны», поэтому
разбираем оба, и кэш перечитываем, когда он пополнился (следим за mtime).

    python razbor_stranic.py                     посчитать объём работы
    python razbor_stranic.py --delat             разбирать сырьё (8 процессов)
    python razbor_stranic.py --delat --kesh      разбирать кэш конвейера
    python razbor_stranic.py --delat --procesov 12 --minut 240
"""
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
if DIR not in sys.path:
    sys.path.insert(0, DIR)

ИСТОЧНИК = os.environ.get('RAZBOR_DIR', r'D:\zenno-razobrano')
ИСХОДНЫЙ_C = os.environ.get('RAZBOR_DIR_C', r'C:\seostat\drop\zenno\razobrano')
КЭШ = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
БАЗА = os.environ.get('RAZBOR_DB', r'D:\razbor-nahodki.db')
ЖУРНАЛ = os.environ.get('RAZBOR_LOG', r'D:\razbor-nahodki.jsonl')
ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ПРЕДЕЛ_СТРАНИЦЫ = 5 * 2**20          # страницы крупнее — пропускаем
ОТЧЁТ_КАЖДЫЕ = 500                   # компаний между записями в журнал

# Домены и адреса, которые почтой компании не являются: чужие сервисы, примеры,
# служебные адреса движков. Без этого в находки лезет мусор вроде no-reply@wix.
МУСОР_ДОМЕН = re.compile(
    r'@(?:example|test|domain|mail|email|site|company|your|sentry\.io|wixpress|'
    r'w3\.org|schema\.org|sentry|jquery|googlemail|localhost|yourdomain|'
    r'company\.com|mysite|bitrix|1gb\.ru|nic\.ru|reg\.ru)\b', re.I)
МУСОР_ЛОКАЛ = re.compile(r'^(?:no-?reply|noreply|donotreply|postmaster|abuse|'
                         r'webmaster|hostmaster|root|admin@localhost)', re.I)
# Признаки того, что адрес спрятан от глаз — это спам-ловушка, письмо туда бьёт
# по репутации домена. Смотрим 300 символов ДО адреса в сыром HTML.
СКРЫТ = re.compile(r'display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|'
                   r'opacity\s*:\s*0|text-indent\s*:\s*-\d{3}', re.I)


def _база(путь=None):
    c = sqlite3.connect(путь or БАЗА, timeout=60)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    c.executescript("""
    create table if not exists sdelano(
      inn text primary key, ts text, stranic int, pocht int, telefonov int,
      novyh_pocht int, novyh_telefonov int);
    -- кэш конвейера пополняется и после разбора: у файла меняется mtime, и
    -- компанию надо перечитать. Поэтому отдельная таблица со свежестью, а не
    -- отметка «сделано навсегда».
    create table if not exists sdelano_kesh(
      inn text primary key, ts text, mtime real, stranic int, pocht int,
      telefonov int, novyh_pocht int, novyh_telefonov int);
    create table if not exists nahodki_pochta(
      inn text, email text, role text, role_src text, ctx text, src text,
      source_url text, skryt int, novyy int, ts text,
      primary key(inn, email));
    create table if not exists nahodki_telefon(
      inn text, phone text, source_url text, novyy int, ts text,
      primary key(inn, phone));
    -- ИНН, найденный на самой странице, подтверждает принадлежность контакта
    -- сильнее любого совпадения доменов (владелец 29.08: «особенно если знаем
    -- инн на странице»). Считается отдельным дешёвым проходом: поиск подстроки,
    -- а не разбор.
    create table if not exists inn_na_stranicah(
      inn text primary key, ts text, stranic int, s_innom int, adresa_url text);
    """)
    for таблица in ('nahodki_pochta', 'nahodki_telefon'):
        try:
            c.execute('alter table %s add column inn_na_str int' % таблица)
        except sqlite3.OperationalError:
            pass
    return c


def _журнал(запись):
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(запись, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def целевые_инн():
    """ИНН, у которых на D: лежит .urls.txt — по нему знаем порядок страниц."""
    инн = []
    with os.scandir(ИСТОЧНИК) as это:
        for з in это:
            if з.name.endswith('.urls.txt'):
                инн.append(з.name[:-9])
    return инн


def _страницы(inn):
    """[(url, html)] компании — только из файлов, чей близнец на C: уже удалён."""
    пу = os.path.join(ИСТОЧНИК, '%s.urls.txt' % inn)
    try:
        with open(пу, encoding='utf-8-sig', errors='replace') as f:
            urls = [s.strip().lstrip('\ufeff') for s in f if s.strip()]
    except OSError:
        return [], 0
    страницы, недоехало = [], 0
    for i, u in enumerate(urls):
        имя = '%s_%d.html' % (inn, i)
        пд = os.path.join(ИСТОЧНИК, имя)
        if not os.path.exists(пд):
            continue
        if os.path.exists(os.path.join(ИСХОДНЫЙ_C, имя)):
            недоехало += 1          # файл ещё копируется — не трогаем
            continue
        try:
            if os.path.getsize(пд) > ПРЕДЕЛ_СТРАНИЦЫ:
                continue
            with open(пд, encoding='utf-8', errors='replace') as f:
                h = f.read()
        except OSError:
            continue
        if h.strip():
            страницы.append((u, h))
    return страницы, недоехало


def целевые_кэш(c):
    """ИНН из кэша конвейера, которые ещё не разбирали или которые пополнились.

    Владелец 29.08: «чтобы всегда и везде брались и почты и телефоны». Кэш —
    единственное место, куда попадает КАЖДАЯ скачанная страница, чем бы её ни
    брали: и Зенкой в режиме фактов, и питоновским краулером. Поэтому контакты
    снимаем отсюда, а не только с сырья Зенки.
    """
    было = {str(i): (m or 0) for i, m in c.execute(
        'select inn, coalesce(mtime,0) from sdelano_kesh')}
    цели = []
    try:
        with os.scandir(КЭШ) as это:
            for з in это:
                if not з.name.endswith('.json.gz'):
                    continue
                inn = з.name[:-8]
                try:
                    m = з.stat().st_mtime
                except OSError:
                    continue
                if m > было.get(inn, -1) + 1:
                    цели.append(inn)
    except OSError:
        pass
    return цели


def _страницы_кэша(inn):
    """[(url, html)] из кэша конвейера."""
    import gzip
    п = os.path.join(КЭШ, '%s.json.gz' % inn)
    try:
        with gzip.open(п, 'rb') as f:
            д = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return []
    страницы = []
    for с in (д.get('pages') or []):
        h = с.get('html') or ''
        if h.strip():
            страницы.append((с.get('url') or д.get('site') or '', h))
    return страницы


def _собрать(inn, страницы):
    """Страницы одной компании -> адреса с ролью и контекстом + телефоны."""
    import contact_extract as CE
    почта, телефоны = {}, {}
    for url, html in страницы:
        try:
            д = CE.extract(html)
        except Exception:  # noqa: BLE001
            continue
        низ = html.lower()
        for р in д['emails']:
            e = (р.get('email') or '').lower()
            if not e or МУСОР_ДОМЕН.search(e) or МУСОР_ЛОКАЛ.match(e):
                continue
            поз = низ.find(e)
            скрыт = 1 if (поз > 0 and СКРЫТ.search(html[max(0, поз - 300):поз])) else 0
            было = почта.get(e)
            if было and (было.get('role') or not р.get('role')):
                if скрыт and not было.get('skryt'):
                    было['skryt'] = 1
                continue
            почта[e] = {'email': e, 'role': р.get('role'),
                        'role_src': р.get('role_src'), 'ctx': (р.get('ctx') or '')[:300],
                        'src': р.get('src'), 'source_url': url, 'skryt': скрыт}
        for т in д['phones']:
            т = re.sub(r'\D', '', т or '')
            if len(т) == 11 and т.startswith('8'):
                т = '7' + т[1:]
            if len(т) == 10:
                т = '7' + т
            if len(т) != 11 or not т.startswith('7'):
                continue
            телефоны.setdefault(т, url)
    return {'inn': inn, 'stranic': len(страницы),
            'pochta': list(почта.values()),
            'telefony': [{'phone': p, 'source_url': u} for p, u in телефоны.items()]}


def разобрать(inn):
    """Сырьё Зенки: один ИНН со своими файлами на D:."""
    страницы, недоехало = _страницы(inn)
    if недоехало:
        return {'inn': inn, 'отложен': недоехало}
    if not страницы:
        return {'inn': inn, 'stranic': 0, 'pochta': [], 'telefony': []}
    return _собрать(inn, страницы)


def разобрать_кэш(inn):
    """Кэш конвейера: один ИНН, вместе с отметкой свежести файла."""
    п = os.path.join(КЭШ, '%s.json.gz' % inn)
    try:
        m = os.path.getmtime(п)
    except OSError:
        return {'inn': inn, 'stranic': 0, 'pochta': [], 'telefony': [], 'mtime': 0}
    страницы = _страницы_кэша(inn)
    р = _собрать(inn, страницы) if страницы else {
        'inn': inn, 'stranic': 0, 'pochta': [], 'telefony': []}
    р['mtime'] = m
    return р


def _любые_страницы(inn):
    """Страницы компании откуда угодно: сырьё на D:, сырьё на C:, кэш конвейера."""
    страницы, _ = _страницы(inn)
    if страницы:
        return страницы
    прежний = globals()['ИСТОЧНИК']
    try:                                   # свежие сутки остались на рабочем диске
        globals()['ИСТОЧНИК'] = ИСХОДНЫЙ_C
        страницы, _ = _страницы(inn)
    finally:
        globals()['ИСТОЧНИК'] = прежний
    return страницы or _страницы_кэша(inn)


def инн_на_страницах(inn):
    """Есть ли ИНН компании на её же страницах и на каких именно.

    Ищем и слитно, и с любыми разделителями внутри: «ИНН 7701 234567» и
    «ИНН: 7701234567» — одно и то же число, а различие ломало бы весь смысл
    проверки. Сравниваем по цифрам страницы, а не по её разметке.
    """
    страницы = _любые_страницы(inn)
    if not страницы:
        return {'inn': inn, 'stranic': 0, 's_innom': 0, 'urls': []}
    цифры = re.sub(r'\D', '', str(inn))
    urls = []
    for url, html in страницы:
        текст = re.sub(r'<[^>]+>', ' ', html)
        if цифры in текст or цифры in re.sub(r'[\s\-.]', '', текст):
            urls.append(url)
    return {'inn': inn, 'stranic': len(страницы), 's_innom': len(urls),
            'urls': urls[:20]}


def прогон_инн(процессов=6, предел=0):
    """Проставить признак «ИНН найден на странице» у накопленных находок."""
    t0 = time.time()
    c = _база()
    было = set(str(r[0]) for r in c.execute('select inn from inn_na_stranicah'))
    цели = [str(r[0]) for r in c.execute(
        'select distinct inn from nahodki_pochta '
        'union select distinct inn from nahodki_telefon') if str(r[0]) not in было]
    if предел:
        цели = цели[:предел]
    итог = {'целей': len(цели), 'проверено': 0, 'с_инном': 0, 'без_страниц': 0}
    if not цели:
        итог['итог'] = 'проверять нечего'
        c.close()
        return итог
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    сделано = 0
    with ProcessPoolExecutor(max_workers=процессов) as пул:
        for р in пул.map(инн_на_страницах, цели, chunksize=8):
            inn = р['inn']
            if not р['stranic']:
                итог['без_страниц'] += 1
            c.execute('insert or replace into inn_na_stranicah(inn,ts,stranic,'
                      's_innom,adresa_url) values(?,?,?,?,?)',
                      (inn, сейчас, р['stranic'], р['s_innom'],
                       json.dumps(р['urls'], ensure_ascii=False)))
            if р['s_innom']:
                итог['с_инном'] += 1
                места = set(р['urls'])
                for таблица in ('nahodki_pochta', 'nahodki_telefon'):
                    c.execute('update %s set inn_na_str=1 where inn=? '
                              'and source_url in (%s)'
                              % (таблица, ','.join('?' * len(места))),
                              [inn] + sorted(места))
            итог['проверено'] += 1
            сделано += 1
            if сделано % 500 == 0:
                c.commit()
                _журнал({'ts': time.strftime('%H:%M:%S'), 'инн_проверено': сделано,
                         'с_инном': итог['с_инном'],
                         'секунд': round(time.time() - t0)})
    c.commit()
    итог['секунд'] = round(time.time() - t0)
    if итог['секунд']:
        итог['компаний_в_час'] = round(итог['проверено'] / итог['секунд'] * 3600)
    c.close()
    _журнал({'ts': time.strftime('%H:%M:%S'), 'ИТОГ_ИНН': итог})
    return итог


def _известное():
    """Что уже есть в enrich.db — чтобы сразу помечать находки как новые."""
    почта, телефоны = set(), set()
    try:
        c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True,
                            timeout=30)
        for i, e in c.execute("select inn, lower(email) from emails "
                              "where coalesce(email,'')<>''"):
            почта.add((str(i), e))
        try:
            for i, p in c.execute("select inn, phone from phone_contacts "
                                  "where coalesce(phone,'')<>''"):
                телефоны.add((str(i), re.sub(r'\D', '', p or '')))
        except sqlite3.Error:
            pass
        c.close()
    except sqlite3.Error:
        pass
    return почта, телефоны


def прогон(процессов=8, минут=0, предел=0, источник='razobrano'):
    t0 = time.time()
    c = _база()
    кэш = (источник == 'kesh')
    if кэш:
        цели = целевые_кэш(c)
        уже = c.execute('select count(*) from sdelano_kesh').fetchone()[0]
        дело = разобрать_кэш
    else:
        было = set(r[0] for r in c.execute('select inn from sdelano'))
        цели = [i for i in целевые_инн() if i not in было]
        уже = len(было)
        дело = разобрать
    if предел:
        цели = цели[:предел]
    известн_п, известн_т = _известное()
    итог = {'источник': источник, 'целей': len(цели), 'уже_было': уже,
            'разобрано': 0, 'страниц': 0, 'почт': 0, 'новых_почт': 0,
            'телефонов': 0, 'новых_телефонов': 0, 'отложено': 0, 'скрытых': 0,
            'ошибок': 0}
    if not цели:
        итог['итог'] = 'разбирать нечего'
        c.close()
        return итог
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    с_прошлой_записи = 0
    with ProcessPoolExecutor(max_workers=процессов) as пул:
        for р in пул.map(дело, цели, chunksize=8):
            if минут and time.time() - t0 > минут * 60:
                итог['итог'] = 'остановлен по времени, остальное — в следующий раз'
                break
            if not р:
                итог['ошибок'] += 1
                continue
            if р.get('отложен'):
                итог['отложено'] += 1
                continue
            inn = р['inn']
            нп = нт = 0
            for п in р['pochta']:
                новый = 1 if (inn, п['email']) not in известн_п else 0
                нп += новый
                итог['скрытых'] += п['skryt']
                c.execute(
                    'insert or ignore into nahodki_pochta(inn,email,role,role_src,'
                    'ctx,src,source_url,skryt,novyy,ts) values(?,?,?,?,?,?,?,?,?,?)',
                    (inn, п['email'], п['role'], п['role_src'], п['ctx'], п['src'],
                     п['source_url'], п['skryt'], новый, сейчас))
            for т in р['telefony']:
                новый = 1 if (inn, т['phone']) not in известн_т else 0
                нт += новый
                c.execute('insert or ignore into nahodki_telefon(inn,phone,'
                          'source_url,novyy,ts) values(?,?,?,?,?)',
                          (inn, т['phone'], т['source_url'], новый, сейчас))
            if кэш:
                c.execute('insert or replace into sdelano_kesh(inn,ts,mtime,'
                          'stranic,pocht,telefonov,novyh_pocht,novyh_telefonov) '
                          'values(?,?,?,?,?,?,?,?)',
                          (inn, сейчас, р.get('mtime') or 0, р['stranic'],
                           len(р['pochta']), len(р['telefony']), нп, нт))
            else:
                c.execute('insert or replace into sdelano(inn,ts,stranic,pocht,'
                          'telefonov,novyh_pocht,novyh_telefonov) '
                          'values(?,?,?,?,?,?,?)',
                          (inn, сейчас, р['stranic'], len(р['pochta']),
                           len(р['telefony']), нп, нт))
            итог['разобрано'] += 1
            итог['страниц'] += р['stranic']
            итог['почт'] += len(р['pochta'])
            итог['новых_почт'] += нп
            итог['телефонов'] += len(р['telefony'])
            итог['новых_телефонов'] += нт
            с_прошлой_записи += 1
            if с_прошлой_записи >= ОТЧЁТ_КАЖДЫЕ:
                c.commit()
                с_прошлой_записи = 0
                _журнал({'ts': time.strftime('%H:%M:%S'),
                         'разобрано': итог['разобрано'], 'страниц': итог['страниц'],
                         'новых_почт': итог['новых_почт'],
                         'новых_телефонов': итог['новых_телефонов'],
                         'секунд': round(time.time() - t0)})
    c.commit()
    итог['секунд'] = round(time.time() - t0)
    if итог['секунд'] > 0:
        итог['компаний_в_час'] = round(итог['разобрано'] / итог['секунд'] * 3600)
    c.close()
    _журнал({'ts': time.strftime('%H:%M:%S'), 'ИТОГ': итог})
    return итог


def посмотреть():
    c = _база()
    д = {'база': БАЗА,
         'сделано_компаний': c.execute('select count(*) from sdelano').fetchone()[0],
         'найдено_почт': c.execute('select count(*) from nahodki_pochta').fetchone()[0],
         'из_них_новых': c.execute(
             'select count(*) from nahodki_pochta where novyy=1').fetchone()[0],
         'скрытых_подозрений': c.execute(
             'select count(*) from nahodki_pochta where skryt=1').fetchone()[0],
         'найдено_телефонов': c.execute(
             'select count(*) from nahodki_telefon').fetchone()[0],
         'новых_телефонов': c.execute(
             'select count(*) from nahodki_telefon where novyy=1').fetchone()[0],
         'роли': c.execute('select coalesce(role,"без роли"), count(*) '
                           'from nahodki_pochta group by 1 order by 2 desc').fetchall(),
         'сделано_из_кэша': c.execute(
             'select count(*) from sdelano_kesh').fetchone()[0]}
    д['осталось_в_кэше'] = len(целевые_кэш(c))
    c.close()
    д['целей_сырья'] = len(целевые_инн())
    return д


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]

    def чис(ключ, умолч):
        if ключ in a:
            try:
                return int(a[a.index(ключ) + 1])
            except Exception:  # noqa: BLE001
                pass
        return умолч

    if '--posmotret' in a:
        print(json.dumps(посмотреть(), ensure_ascii=False, indent=1))
        return 0
    источник = 'kesh' if '--kesh' in a else 'razobrano'
    if '--inn' in a:
        print(json.dumps(прогон_инн(чис('--procesov', 6), чис('--predel', 0)),
                         ensure_ascii=False, indent=1))
        return 0
    if '--delat' not in a:
        c = _база()
        уже = c.execute('select count(*) from sdelano').fetchone()[0]
        осталось_кэш = len(целевые_кэш(c))
        уже_кэш = c.execute('select count(*) from sdelano_kesh').fetchone()[0]
        c.close()
        цели = целевые_инн()
        print(json.dumps({'сырьё_на_D': len(цели), 'сырьё_разобрано': уже,
                          'сырьё_осталось': len(цели) - уже,
                          'кэш_разобран': уже_кэш, 'кэш_осталось': осталось_кэш,
                          'база': БАЗА}, ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(прогон(чис('--procesov', 8), чис('--minut', 0),
                            чис('--predel', 0), источник),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
