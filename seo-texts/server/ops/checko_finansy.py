# -*- coding: utf-8 -*-
"""Добрать финансы с чеко: выручка, чистая прибыль, ССЧ — и ГОД отчётности.

ЗАЧЕМ. После заливки реквизитов официальные поля закрыты почти полностью
(адрес 1571, директор 1559, статус 1572), а денежные остались редкими:
выручка 266, прибыль 98, ССЧ 54. DaData на бесплатном тарифе финансы не отдаёт.
Владелец: «чеко отдаёт эту инфу» — проверено, отдаёт: страница компании по ОГРН
открывается с наших socks5-прокси кодом 200 и содержит все три показателя.

ГОД ОБЯЗАТЕЛЕН, и это не педантизм. Разведка по трём компаниям дала отчётность
за 2025, 2021 и 2018 годы — то есть у части предприятий свежих данных нет
вовсе. «Выручка 5,4 млрд» без года выглядит одинаково убедительно и для
прошлого года, и для позапрошлой пятилетки, а продавец на её основании решает,
крупный ли это клиент СЕГОДНЯ. Пишем год рядом и показываем его в карточке.

ФОРМАТ ЧИСЕЛ. Чеко пишет «11,9 млрд руб.», «49,4 млн руб.», «773 человека».
Переводим в рубли целыми: 11,9 млрд -> 11900000000. Множитель обязателен —
без него «11,9» уедет в базу как одиннадцать рублей.

ПРОКСИ. socks5 из dolphin-proxies.txt (78 штук), по кругу. Именно socks5:
http-схема к ним не подключается вовсе (проверено — ConnectionError на всех).

DURABILITY: пишем в enrich.db.requisites (upsert) + журнал с fsync, прогон
резюмируемый по журналу.

Запуск: python checko_finansy.py [--lim N] [--potok N] [--vse]
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402
import requests  # noqa: E402

ЖУРНАЛ = r'C:\sender\server\checko_finansy.jsonl'
ВСЕ = '--vse' in sys.argv
БЕЗ_БАЗЫ = '--bez-bazy' in sys.argv or '--tolko-zhurnal' in sys.argv
# МОБИЛЬНЫЕ С РОТАЦИЕЙ (владелец 01.09: «мобильные ротируются»). Пул из 78
# статичных socks5 Чеко закрыл наглухо: замер дал 429 на всех сорока
# запросах подряд, начиная с первого, и это держится часами. Мобильный
# адрес живёт 30-45 запросов, но потом МЕНЯЕТСЯ, и лимит приходит чистым.
# Замер ротации 01.09, десять минут наблюдения: 77.51.189.183 меняет адрес
# раз в полторы-две минуты, 194.143.150.98 — раз в шесть, bproxy.site за
# десять минут не сменил. При двух запросах на компанию это 700-1000
# компаний в час, зато бесконечно.
МОБИЛЬНЫЕ = '--mobilnye' in sys.argv
ФАЙЛ_МОБИЛЬНЫХ = r'C:\sender\proxies-mobile.txt'
_замок = threading.Lock()
_стат = Counter()
_остыв = {}
_МНОЖ = {'трлн': 10 ** 12, 'млрд': 10 ** 9, 'млн': 10 ** 6,
         'тыс': 10 ** 3, 'руб': 1}


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


_ip_прокси = {}
_ждут = {}


def мобильные_прокси():
    """Мобильные из файла, без дублей. Их мало, но у них меняется адрес."""
    из, видели = [], set()
    if not os.path.exists(ФАЙЛ_МОБИЛЬНЫХ):
        return из
    with open(ФАЙЛ_МОБИЛЬНЫХ, encoding='utf-8', errors='replace') as ф:
        строки = ф.read().splitlines()
    for l in строки:
        l = l.strip()
        if l and not l.startswith('#') and l not in видели:
            видели.add(l)
            из.append(l if '://' in l else 'socks5://' + l)
    return из


def внешний_ip(px, таймаут=15):
    try:
        r = requests.get('https://api.ipify.org', proxies={'http': px,
                                                           'https': px},
                         timeout=таймаут)
        return r.text.strip() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def ждать_смены_ip(px, предел=480):
    """Ждать, пока у прокси сменится адрес. True — сменился.

    Спать вслепую бесполезно: лимит Чеко привязан к АДРЕСУ, и он снимется
    ровно тогда, когда мобильный оператор выдаст новый. Поэтому опрашиваем
    внешний адрес, а не таймер. Один ждущий на прокси — остальные потоки
    просто идут к другим выходам.
    """
    with _замок:
        if _ждут.get(px):
            return False
        _ждут[px] = True
    try:
        было = _ip_прокси.get(px) or внешний_ip(px)
        _ip_прокси[px] = было
        до = time.time() + предел
        while time.time() < до:
            time.sleep(12)
            стало = внешний_ip(px)
            if стало and стало != было:
                _ip_прокси[px] = стало
                with _замок:
                    _стат['ротаций дождались'] += 1
                return True
        with _замок:
            _стат['ротации не дождались'] += 1
        return False
    finally:
        with _замок:
            _ждут[px] = False


def прокси():
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


def в_рубли(число, единица):
    """«11,9» + «млрд» -> 11900000000. Без множителя не возвращаем ничего."""
    try:
        ч = float(str(число).replace(',', '.').replace(' ', ''))
    except ValueError:
        return None
    м = _МНОЖ.get(str(единица or '').strip().lower()[:4].rstrip('.'))
    if м is None:
        return None
    return int(round(ч * м))


# ОКВЭДы с расшифровкой: секция «ОКВЭД-2 42.21 Строительство… 43.3 Работы…»
# и заканчивается «Все виды деятельности компании (65)». Код может быть
# двух-, трёх- и четырёхуровневым (42.21, 43.99.2), название — до следующего
# кода. Забираем ВСЕ, а не только основной: владелец просил доп. виды с
# расшифровкой деятельности.
_ОКВЭД_СЕКЦИЯ = re.compile(
    r'ОКВЭД-2\s*(.{20,6000}?)(?:Все виды деятельности компании|'
    r'Финансовая отчетность|Финансовая \(бухгалтерская\))', re.S)
_ОКВЭД_ПАРА = re.compile(
    r'(\d{2}(?:\.\d{1,2}){0,2})\s+([А-ЯЁA-Z][^\d]{3,160}?)'
    r'(?=\s+\d{2}(?:\.\d{1,2}){0,2}\s+[А-ЯЁA-Z]|\s*$)')
_ВСЕГО_ВИДОВ = re.compile(r'Все виды деятельности компании \((\d+)\)')
# Контакты берём со страницы /contacts: на главной длинный список обрезается
# (поправка владельца). Телефонов и почт там может быть несколько.
_ТЕЛЕФОН = re.compile(r'\+7[\d\s\-()]{9,18}')
_ПОЧТА = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_САЙТ = re.compile(r'Веб-сайт\s+([A-Za-z0-9.\-]+\.[A-Za-z]{2,})')

_ГОД = re.compile(r'Финансовые показатели за (\d{4}) год')
_ВЫРУЧКА = re.compile(
    r'Выручка[^\d]{0,40}?([\d  ,\.]+)\s*(трлн|млрд|млн|тыс|руб)', re.I)
_ПРИБЫЛЬ = re.compile(
    r'Чистая прибыль[^\d]{0,40}?([\d  ,\.]+)\s*(трлн|млрд|млн|тыс|руб)', re.I)
_УБЫТОК = re.compile(r'Чистый убыток[^\d]{0,40}?([\d  ,\.]+)\s*'
                     r'(трлн|млрд|млн|тыс|руб)', re.I)
_ССЧ = re.compile(r'Среднесписочная численность работников[^\d]{0,60}?'
                  r'(\d[\d  ]*)\s*человек', re.I)
_ССЧ_ГОД = re.compile(r'Среднесписочная численность работников за (\d{4})', re.I)


def разобрать(html):
    т = re.sub(r'<[^>]+>', ' ', html)
    т = re.sub(r'&nbsp;|&thinsp;|&#\d+;', ' ', т)
    т = re.sub(r'\s+', ' ', т)
    из = {}
    м = _ГОД.search(т)
    if м:
        из['fin_god'] = м.group(1)
    м = _ВЫРУЧКА.search(т)
    if м:
        в = в_рубли(м.group(1), м.group(2))
        if в is not None:
            из['revenue_rub'] = в
    м = _ПРИБЫЛЬ.search(т)
    if м:
        п = в_рубли(м.group(1), м.group(2))
        if п is not None:
            из['profit_rub'] = п
    else:
        м = _УБЫТОК.search(т)
        if м:
            п = в_рубли(м.group(1), м.group(2))
            if п is not None:
                из['profit_rub'] = -п   # убыток пишем отрицательным, а не теряем
    м = _ССЧ.search(т)
    if м:
        из['ssch'] = int(re.sub(r'\D', '', м.group(1)) or 0)
    м = _ССЧ_ГОД.search(т)
    if м:
        из['ssch_god'] = м.group(1)
    # ОКВЭДы с расшифровкой
    м = _ОКВЭД_СЕКЦИЯ.search(т)
    if м:
        пары = []
        for код, назв in _ОКВЭД_ПАРА.findall(м.group(1)):
            н = назв.strip(' .,;')
            if len(н) > 3:
                пары.append(f'{код} {н}')
        if пары:
            из['okved_all_checko'] = ' | '.join(пары)
            из['okved_main_checko'] = пары[0]
    м = _ВСЕГО_ВИДОВ.search(т)
    if м:
        из['okved_count'] = м.group(1)
    return из


def разобрать_контакты(html):
    """Со страницы /contacts: ВСЕ телефоны и почты, а не первый попавшийся."""
    т = re.sub(r'<script.*?</script>', ' ', html, flags=re.S | re.I)
    т = re.sub(r'<[^>]+>', ' ', т)
    т = re.sub(r'&nbsp;|&thinsp;|&#\d+;', ' ', т)
    т = re.sub(r'\s+', ' ', т)
    # обрезаем подвал сайта: там лежат телефоны и почты САМОГО чеко
    гр = т.find('Нашли ошибку в контактах')
    ядро = т[:гр] if гр > 0 else т
    тел, почт = [], []
    for x in _ТЕЛЕФОН.findall(ядро):
        ц = re.sub(r'\D', '', x)
        # Российский номер: 11 цифр, начинается с 7, а КОД региона/оператора —
        # с 3, 4, 8 или 9. Проверка не косметическая: в разведке из склеенного
        # текста вылез «+76478661124» (код 647 не существует). Ложный номер
        # стоит впустую потраченного звонка, а пустое поле не стоит ничего.
        if len(ц) == 11 and ц[0] == '7' and ц[1] in '3489' and ц not in тел:
            тел.append(ц)
    for x in _ПОЧТА.findall(ядро):
        а = x.lower().strip('.')
        if 'checko' in а or a_мусор(а) or а in почт:
            continue
        почт.append(а)
    из = {}
    if тел:
        из['phones_checko'] = ' | '.join('+' + t for t in тел[:12])
    if почт:
        из['emails_checko'] = ' | '.join(почт[:12])
    м = _САЙТ.search(ядро)
    if м:
        из['site_checko'] = м.group(1)
    return из


def a_мусор(адрес):
    return any(x in адрес for x in ('example.', 'sentry.', '.png', '.jpg',
                                    'yandex.ru/support', 'noreply@'))


def сделанные():
    из = set()
    if os.path.exists(ЖУРНАЛ):
        for стр in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            # СБОЙ — ЭТО НЕ «СДЕЛАНО» (01.09). Здесь ИНН заносился в
            # «уже спрошено» по одному факту записи в журнале, а строка
            # сбоя пишется туда же, что и удача. Прогон 01.09 не достучался
            # до 6358 компаний (Чеко перестал отдавать страницы после
            # четырёх тысяч), и все они были бы молча пропущены следующим
            # прогоном — навсегда, потому что вторая попытка к ним уже
            # никогда бы не пришла.
            if з.get('сбой'):
                continue
            if з.get('inn'):
                из.add(str(з['inn']))
    return из


def main():
    ЛИМ, ПОТОК = арг('--lim', 1600), арг('--potok', 8)
    PX = мобильные_прокси() if МОБИЛЬНЫЕ else прокси()
    if not PX:
        raise SystemExit('нет прокси в dolphin-proxies.txt')
    db = EDB.EnrichDB()
    for стлб in ('revenue_rub', 'profit_rub', 'ssch', 'fin_god', 'ssch_god',
                 'okved_all_checko', 'okved_main_checko', 'okved_count',
                 'phones_checko', 'emails_checko', 'site_checko'):
        try:
            db.cx.execute(f'ALTER TABLE requisites ADD COLUMN {стлб} TEXT')
        except Exception:  # noqa: BLE001
            pass
    db.cx.commit()
    ряды = db.cx.execute(
        "SELECT inn, ogrn FROM requisites WHERE COALESCE(ogrn,'')<>''").fetchall()
    было = сделанные()
    цели = [(и, о) for и, о in ряды if ВСЕ or str(и) not in было][:ЛИМ]
    print(f'с ОГРН в базе: {len(ряды)}; уже спрошено: {len(было)}; '
          f'в этот прогон: {len(цели)}; прокси: {len(PX)}')
    sys.stdout.flush()
    if not цели:
        return
    ж = open(ЖУРНАЛ, 'a', encoding='utf-8')
    поля = ('revenue_rub', 'profit_rub', 'ssch', 'fin_god', 'ssch_god',
             'okved_all_checko', 'okved_main_checko', 'okved_count',
             'phones_checko', 'emails_checko', 'site_checko')

    def взять(url, i):
        """Запрос с ротацией прокси и ОСТЫВАНИЕМ на 429.

        Владелец: «на 50 компании начинаются 429». Это лимит НА АДРЕС, поэтому
        лечится не паузой всего прогона, а сменой выхода: получивший 429 прокси
        уходит в остывание, запрос немедленно повторяется с другого. Прокси у
        нас 78 — это больше выходов, чем дал бы Дельфин (3 мобильных профиля),
        и ротация здесь дешевле подъёма профиля на каждую компанию.
        """
        for попытка in range(6):
            with _замок:
                годные = [p for p in PX if _остыв.get(p, 0) < time.time()]
                px = (годные or PX)[(i * 7 + попытка * 13) % len(годные or PX)]
            try:
                r = requests.get(
                    url, proxies={'http': px, 'https': px},
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; '
                                           'Win64; x64) AppleWebKit/537.36'},
                    timeout=30)
            except Exception:  # noqa: BLE001
                with _замок:
                    _стат['сбой связи'] += 1
                continue
            if r.status_code == 429:
                with _замок:
                    _стат['429'] += 1
                if МОБИЛЬНЫЕ:
                    # Ждём НОВЫЙ АДРЕС, а не отсидки: у мобильного лимит
                    # снимается сменой IP, а не временем.
                    ждать_смены_ip(px)
                else:
                    with _замок:
                        _остыв[px] = time.time() + 90
                    time.sleep(0.5)
                continue
            if r.status_code != 200:
                with _замок:
                    _стат[f'код {r.status_code}'] += 1
                continue
            return r.text
        return None

    def один(п):
        i, (инн, огрн) = п
        for _раз in (1,):
            тело = взять(f'https://checko.ru/company/{огрн}', i)
            if тело is None:
                continue
            з = разобрать(тело)
            # контакты — со СТРАНИЦЫ КОНТАКТОВ (поправка владельца: на главной
            # длинный список обрезается и часть телефонов не видна)
            тк = взять(f'https://checko.ru/company/{огрн}/contacts', i + 3)
            if тк:
                з.update(разобрать_контакты(тк))
            with _замок:
                _стат['страниц ок'] += 1
                for к in поля:
                    if з.get(к) not in (None, ''):
                        _стат['есть ' + к] += 1
                # БЕЗ БАЗЫ — ТОЛЬКО ЖУРНАЛ (01.09). Запись сюда идёт под
                # общим замком потоков, а соединение ждёт занятую базу до
                # тридцати секунд — и все восемь потоков стоят за одной
                # неудачной записью. При трёх писцах разом (часовая сверка
                # приговоров, заливка и сама ходилка) прогон выродился в
                # четыре компании за четыре минуты. Журнал ниже пишется
                # независимо от базы, поэтому ничего не теряется:
                # добытое переносит ops/dolit_iz_zhurnala_hodilki.py.
                if з and not БЕЗ_БАЗЫ:
                    try:
                        db.cx.execute(
                            'UPDATE requisites SET ' +
                            ', '.join(f'{к}=?' for к in поля) +
                            ', updated_at=? WHERE inn=?',
                            [str(з.get(к, '') or '') for к in поля] +
                            [time.strftime('%Y-%m-%dT%H:%M:%S'), инн])
                    except Exception as e:  # noqa: BLE001
                        _стат['запись не легла'] += 1
                        if _стат['запись не легла'] < 3:
                            print('  запись:', str(e)[:110])
                ж.write(json.dumps({'inn': инн, 'ogrn': огрн, **з},
                                   ensure_ascii=False) + '\n')
            return
        with _замок:
            _стат['не достучались'] += 1
            ж.write(json.dumps({'inn': инн, 'ogrn': огрн, 'сбой': True},
                               ensure_ascii=False) + '\n')

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=ПОТОК) as п:
        for n, _ in enumerate(п.map(один, list(enumerate(цели))), 1):
            # СБРОС КАЖДЫЕ ДЕСЯТЬ, А НЕ СТО (01.09). В мобильном режиме
            # прогон идёт со скоростью ротации адресов — десятки компаний в
            # час, а не тысячи. При шаге в сто первые девяносто девять
            # записей не видны в журнале вовсе и теряются из буфера, если
            # процесс снять. Десять — и прогресс виден, и терять почти
            # нечего.
            if n % 10 == 0:
                with _замок:
                    if not БЕЗ_БАЗЫ:
                        db.cx.commit()
                    ж.flush()
                    os.fsync(ж.fileno())
                print(f'  {n}/{len(цели)}, {int(time.time()-t0)} с, '
                      f'ок {_стат["страниц ок"]}, выручек {_стат["есть revenue_rub"]}'
                      f', 429 {_стат["429"]}, ротаций {_стат["ротаций дождались"]}',
                      flush=True)
                sys.stdout.flush()
    db.cx.commit()
    ж.flush()
    os.fsync(ж.fileno())
    ж.close()
    с_выр = db.cx.execute(
        "SELECT COUNT(*) FROM requisites WHERE COALESCE(revenue_rub,'') NOT IN ('','0')"
    ).fetchone()[0]
    с_ссч = db.cx.execute(
        "SELECT COUNT(*) FROM requisites WHERE COALESCE(ssch,'') NOT IN ('','0')"
    ).fetchone()[0]
    print(json.dumps({'итог': dict(_стат), 'в_requisites_с_выручкой': с_выр,
                      'с_ССЧ': с_ссч, 'секунд': int(time.time() - t0)},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
