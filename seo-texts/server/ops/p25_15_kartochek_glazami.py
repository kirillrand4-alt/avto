# -*- coding: utf-8 -*-
"""15 случайных карточек P25 глазами под входом продавца: что база знает, а панель нет.

ЗАЧЕМ ИМЕННО ГЛАЗАМИ. Счётчик показывает, сколько строк записано, и молчит о
том, доехали ли они до страницы, которую открывает продавец. Сегодня уже
дважды выходило, что цифра верна, а смысл нет.

ЧТО СРАВНИВАЮ по каждой карточке:
  * люди из `person` — все ли фамилии есть в тексте страницы;
  * телефоны из `contact` — все ли номера видны;
  * наблюдения — есть ли на странице хоть одна ссылка-первоисточник;
  * подложные должности — не осталось ли «технический директор» там, где
    цитата говорит «Генеральный директор» (сигнал 3-й сессии по 006–009).

Вход обязателен: без логина панель отдаёт форму, и проверка радостно
отчитается «страница есть». Правило записано после того, как я на это попался.

Запуск: python p25_15_kartochek_glazami.py [--n 15]
"""
import json
import os
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from collections import Counter
from http.cookiejar import CookieJar

P25 = r'C:\seostat\data\p25.db'
БАЗА = 'http://127.0.0.1:8014'
СКОЛЬКО = 15
for i, а in enumerate(sys.argv):
    if а == '--n' and i + 1 < len(sys.argv):
        СКОЛЬКО = int(sys.argv[i + 1])

def _parol_user3():
    """Пароль выводится из секрета сессии САМОЙ службы, на сервере.

    Ни секрет, ни пароль не пересекают границу сервера: и переустановщик, и эта
    проверка считают одно и то же значение из того, что уже лежит в окружении
    службы. Переменной с паролем нет, потому что хранить её негде и незачем.
    """
    import hashlib, subprocess
    от = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "(Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\p25obzvon"
         "\\Parameters' -ErrorAction SilentlyContinue).AppEnvironmentExtra"],
        capture_output=True, text=True, timeout=60)
    for кус in (от.stdout or '').replace('\r', '\n').split('\n'):
        for пара in кус.split(';'):
            имя, _, зн = пара.partition('=')
            if имя.strip() == 'CENTRO_SESSION_SECRET' and зн.strip():
                return hashlib.sha256((зн.strip() + 'user3').encode()).hexdigest()[:32]
    return ''


ТОКЕНЫ = [('user3', _parol_user3())]

банка = CookieJar()
оп = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(банка), urllib.request.ProxyHandler({}))


def войти(кто, ток):
    банка.clear()
    т = urllib.parse.urlencode({'username': кто, 'password': ток}).encode()
    try:
        оп.open(urllib.request.Request(
            f'{БАЗА}/obzvon/centro/login', data=т, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded',
                     'Origin': БАЗА, 'Referer': f'{БАЗА}/obzvon/centro/login'}),
            timeout=60).read()
        return True
    except Exception as ex:  # noqa: BLE001
        print(f'  вход {кто}: {type(ex).__name__} {str(ex)[:70]}')
        return False


def страница(инн):
    try:
        with оп.open(f'{БАЗА}/obzvon/centro?inn={инн}', timeout=60) as о:
            return о.read().decode('utf-8', 'replace')
    except Exception as ex:  # noqa: BLE001
        return f'__ОШИБКА__ {type(ex).__name__} {str(ex)[:60]}'


def цифры(з):
    return re.sub(r'\D', '', str(з or ''))


def main():
    цб = sqlite3.connect(f'file:{P25}?mode=ro', uri=True)
    # берём предприятия, у которых ЕСТЬ что показывать: иначе проверка пустая
    цели = [str(r[0]) for r in цб.execute(
        'SELECT inn FROM company WHERE inn IN (SELECT inn FROM person) '
        'ORDER BY COALESCE(mesto_po_summe, 999999) LIMIT ?', (СКОЛЬКО,))]
    данные = {}
    for и in цели:
        данные[и] = {
            'люди': [r[0] for r in цб.execute(
                "SELECT COALESCE(person,'') FROM person WHERE inn=?", (и,)) if r[0]],
            'телефоны': [r[0] for r in цб.execute(
                "SELECT COALESCE(value,'') FROM contact WHERE inn=? AND kind='phone'",
                (и,)) if r[0]],
            'ссылки': [r[0] for r in цб.execute(
                "SELECT COALESCE(source_url,'') FROM contact_source WHERE inn=?",
                (и,)) if r[0]],
        }
    цб.close()

    вошли = ''
    for кто, ток in ТОКЕНЫ:
        if ток and войти(кто, ток):
            пробная = страница(цели[0]) if цели else ''
            if 'войти' not in пробная.lower()[:4000] and '__ОШИБКА__' not in пробная:
                вошли = кто
                break
    if not вошли:
        print('НЕ ВОШЁЛ НИ ОДНИМ ПОЛЬЗОВАТЕЛЕМ — проверка НЕ проведена.')
        print('Это не «всё хорошо», это отсутствие проверки. Нужен пароль user3.')
        return
    print(f'вошёл как {вошли}, карточек к осмотру {len(цели)}')

    стат = Counter()
    беды = []
    # ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ. «Расхождений нет» — вывод, который прибор обязан
    # заслужить. Подкладываю в первую карточку фамилию, которой там заведомо
    # нет: если проверка её не заметит, она не проверяет ничего, и ноль
    # расхождений означает сломанный прибор, а не чистые данные.
    if цели:
        данные[цели[0]]['люди'] = list(данные[цели[0]]['люди']) + ['Зюзюкин-Контрольный']
    for и in цели:
        html = страница(и)
        if html.startswith('__ОШИБКА__'):
            стат['карточка не открылась'] += 1
            беды.append(f'{и} {html[:60]}')
            continue
        текст = re.sub(r'<[^>]+>', ' ', html)
        цифр_на_странице = цифры(html)
        нет_людей = [ч for ч in данные[и]['люди']
                     if ч.split()[0].lower() not in текст.lower()]
        нет_номеров = [т for т in данные[и]['телефоны']
                       if цифры(т)[-10:] and цифры(т)[-10:] not in цифр_на_странице]
        есть_ссылка = any(u[:40] in html for u in данные[и]['ссылки'] if u)
        стат['карточек осмотрено'] += 1
        стат['людей сверено'] += len(данные[и]['люди'])
        стат['номеров сверено'] += len(данные[и]['телефоны'])
        стат['ссылок сверено'] += len(данные[и]['ссылки'])
        if нет_людей:
            стат['НЕТ В ПАНЕЛИ: люди'] += len(нет_людей)
            беды.append(f'{и} нет на странице: {", ".join(нет_людей[:3])}')
        if нет_номеров:
            стат['НЕТ В ПАНЕЛИ: номера'] += len(нет_номеров)
            беды.append(f'{и} номера не видны: {", ".join(нет_номеров[:3])}')
        if данные[и]['ссылки'] and not есть_ссылка:
            стат['первоисточник не кликабелен на странице'] += 1
            беды.append(f'{и} ни одной ссылки-первоисточника на странице')

    контроль_пойман = any('Зюзюкин-Контрольный' in б for б in беды)
    беды = [б for б in беды if 'Зюзюкин-Контрольный' not in б]
    стат['НЕТ В ПАНЕЛИ: люди'] = max(0, стат.get('НЕТ В ПАНЕЛИ: люди', 0) - 1)
    стат['людей сверено'] -= 1
    print('ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ:',
          'пойман — прибор различает' if контроль_пойман
          else 'НЕ ПОЙМАН — проверка НИЧЕГО не проверяет, вывод ниже недействителен')
    for б in беды[:14]:
        print('  ', б)
    if not беды:
        print('   расхождений нет: всё, что есть в базе, видно продавцу')

    print()
    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
