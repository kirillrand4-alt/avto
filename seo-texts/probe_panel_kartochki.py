# -*- coding: utf-8 -*-
"""Смотрим карточки панели глазами: что видит человек, а не что лежит в базе.

ПОЧЕМУ ЭТО НЕ ЗАМЕНЯЕТСЯ ЗАПРОСОМ К БАЗЕ. В базе проверяется наличие данных. Владелец
спросил другое: правильно ли они показаны, нет ли мусора и не выкинуто ли лишнее. Поле,
заполненное в базе и не выведенное в карточке, по запросу выглядит хорошо, а на экране его
нет. И наоборот: строка-мусор в базе неотличима от данных, пока не увидишь её в карточке
рядом с подписью «Источник».

Первая же открытая карточка показала, зачем смотреть: у предприятия все реквизиты — прочерки,
а в «Источниках проверки компании» стоит `ZHURNAL-2 (ветка claude read-intro-section-hrstzj)`,
то есть имя ветки чужого журнала попало в источники как доказательство.
"""
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request

BAZA = 'http://127.0.0.1:8012'
PREF = '/obzvon/centro'
LOGIN, PAROL = sys.argv[1], sys.argv[2]
SKOLKO = int(sys.argv[3]) if len(sys.argv) > 3 else 6
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def vzyat(put, dannye=None):
    u = put if put.startswith('http') else BAZA + put
    d = urllib.parse.urlencode(dannye).encode() if dannye else None
    try:
        with op.open(urllib.request.Request(u, data=d), timeout=60) as r:
            return r.status, r.read().decode('utf-8', 'replace'), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), u


def vidno(h):
    # ФИЛЬТРЫ И ШАПКУ ВЫРЕЗАЕМ. Выпадающий список регионов — это 90 строк подряд, и в них
    # тонет вся карточка: первый прогон напечатал два экрана названий областей и ни одного
    # поля предприятия. Смотреть надо то, что относится к компании, а не к оснастке.
    h = re.sub(r'(?is)<select[^>]*>.*?</select>', ' [фильтр] ', h)
    h = re.sub(r'(?is)<(nav|header|form)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?i)</(tr|div|p|li|h\d|table|section)>', '\n', h)
    h = re.sub(r'(?i)</t[dh]>', ' | ', h)
    h = re.sub(r'<[^>]+>', '', h)
    for a, b in (('&nbsp;', ' '), ('&laquo;', '«'), ('&raquo;', '»'), ('&quot;', '"'),
                 ('&amp;', '&'), ('&#34;', '"'), ('&#39;', "'")):
        h = h.replace(a, b)
    h = re.sub(r'[ \t]{2,}', ' ', h)
    return re.sub(r'\n\s*\n+', '\n', h).strip()


st, h, _ = vzyat(PREF + '/login')
polya = re.findall(r'<input[^>]*name="([^"]+)"', h)
st, h, u = vzyat(PREF + '/login', {polya[0]: LOGIN, polya[1]: PAROL})
if st != 200 or 'Вход в рабочую базу' in h:
    print('ВОЙТИ НЕ УДАЛОСЬ', st)
    sys.exit(1)

# Ссылки на карточки со списка. Берём разные: первые в списке — это верх приоритета, и по
# ним видно, что панель считает лучшим, а значит что увидит продавец.
# ССЫЛКИ БЕРЁМ ИЗ РАЗМЕТКИ, А НЕ ИЗ ДОГАДКИ О МАРШРУТЕ. Шаблон `/company/<ИНН>` дал ноль —
# значит маршрут другой, и подставлять свой значит проверять несуществующее.
inny = []
for m in re.finditer(r'href="[^"]*?\?inn=(\d{10,12})', h):
    if m.group(1) not in inny:
        inny.append(m.group(1))
print(f'в очереди на странице карточек: {len(inny)}')
if len(sys.argv) > 4:
    inny = sys.argv[4].split(',') + [i for i in inny if i not in sys.argv[4].split(',')]
for inn in inny[:SKOLKO]:
    st, hh, _ = vzyat(f'{PREF}?inn={inn}')
    t = vidno(hh)
    print('\n' + '=' * 96)
    print(f'КАРТОЧКА {inn}  (HTTP {st}, знаков {len(t)})')
    print('=' * 96)
    # Печатаем ХВОСТ карточки тоже: люди и телефоны идут после списка фактов, а в первом
    # прогоне их срезало ограничение в 4 200 знаков — и вывод «контактов не видно» был бы
    # не про панель, а про мою обрезку.
    if len(t) > 5200:
        print(t[:2600])
        print(f'\n… [пропущено {len(t) - 5200} знаков середины] …\n')
        print(t[-2600:])
    else:
        print(t)
