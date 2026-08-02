# -*- coding: utf-8 -*-
"""E2E-проверка удаления: скрыть номер, убедиться что исчез, вернуть обратно.

«Кнопка на странице есть» и «кнопка работает» — разные вещи. Форма может
слать не туда, роут может молча падать на 422, и снаружи это выглядит как
исправная панель. Поэтому проверяем действием, а потом ОБЯЗАТЕЛЬНО возвращаем
всё как было: панель боевая, продавцы работают.
"""
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

БАЗА = 'http://127.0.0.1:8012/obzvon/centro'


def main():
    пароль = sys.argv[1] if len(sys.argv) > 1 else ''
    банка = http.cookiejar.CookieJar()
    от = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(банка))
    от.open(urllib.request.Request(
        БАЗА + '/login',
        data=urllib.parse.urlencode({'username': 'user1',
                                     'password': пароль}).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'}),
        timeout=40).read()

    with от.open(БАЗА + '/', timeout=60) as о:
        стр = о.read().decode('utf-8', 'replace')
    инн = re.search(r'name="inn" value="(\d{8,12})"', стр)
    ном = re.search(r'name="kind" value="phone">\s*<input type="hidden" '
                    r'name="value" value="([^"]+)"', стр)
    if not (инн and ном):
        print('на карточке не нашёл формы скрытия номера — проверять нечего')
        return
    инн, ном = инн.group(1), ном.group(1)
    print(f'проверяю на ИНН {инн}, номер {ном}')
    было = стр.count(ном)

    # скрыть
    r = от.open(urllib.request.Request(
        БАЗА + '/hide',
        data=urllib.parse.urlencode({'inn': инн, 'kind': 'phone',
                                     'value': ном,
                                     'reason': 'проба удаления'}).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded',
                 'Referer': БАЗА + '/'}), timeout=40)
    print('  POST /hide →', r.status)
    with от.open(БАЗА + '/', timeout=60) as о:
        после = о.read().decode('utf-8', 'replace')
    стало = после.count(ном)
    print(f'  упоминаний номера на странице: было {было}, стало {стало}')
    ок = стало < было

    # ВЕРНУТЬ как было — панель боевая
    от.open(urllib.request.Request(
        БАЗА + '/hide',
        data=urllib.parse.urlencode({'inn': инн, 'kind': 'phone',
                                     'value': ном, 'undo': '1'}).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded',
                 'Referer': БАЗА + '/'}), timeout=40)
    with от.open(БАЗА + '/', timeout=60) as о:
        вернул = о.read().decode('utf-8', 'replace').count(ном)
    print(f'  после возврата: {вернул}')
    print()
    print('УДАЛЕНИЕ РАБОТАЕТ' if ок else 'УДАЛЕНИЕ НЕ СРАБОТАЛО')
    print('ВОЗВРАТ РАБОТАЕТ' if вернул >= было else
          f'ВОЗВРАТ НЕ ВОССТАНОВИЛ ({вернул} против {было}) — чинить немедленно')


if __name__ == '__main__':
    main()
