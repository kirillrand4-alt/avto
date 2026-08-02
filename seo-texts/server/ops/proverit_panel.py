# -*- coding: utf-8 -*-
"""Проверить, что правка дошла ДО ПРОДАВЦА, а не просто легла в файл.

Прошлая проверка вернула 200 и 554 байта — это страница логина. «Панель
отвечает» и «продавец видит правку» разные вещи, и вторую нельзя вывести из
первой: неверный шаблон за логином отдаёт ровно такой же 200.

Логинимся паролем продавца и ищем признак правки в той странице, которую он
реально получит.

Запуск: python proverit_panel.py <пароль> [признак]
"""
import http.cookiejar
import sys
import urllib.error
import urllib.parse
import urllib.request

БАЗА = 'http://127.0.0.1:8012/obzvon/centro'


def main():
    пароль = sys.argv[1] if len(sys.argv) > 1 else ''
    признак = sys.argv[2] if len(sys.argv) > 2 else 'centro_vid_v1'
    if not пароль:
        print('нужен пароль продавца первым аргументом')
        return
    банка = http.cookiejar.CookieJar()
    от = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(банка))

    # форма логина: посмотреть, как называется поле
    try:
        with от.open(БАЗА + '/login', timeout=25) as о:
            форма = о.read().decode('utf-8', 'replace')
        поля = set()
        import re
        for m in re.finditer(r'name="([^"]+)"', форма):
            поля.add(m.group(1))
        print('поля формы логина:', sorted(поля))
    except Exception as e:  # noqa: BLE001
        print('форму логина не открыть:', str(e)[:150])
        поля = set()

    # У формы ДВА поля: username и password. Первый прогон слал одно и получил
    # 422 «Field required» — «пароль не подошёл» и «форму заполнили не тем
    # набором полей» снаружи выглядят как один отказ логина, а лечатся
    # по-разному. Имя пользователя берём из аргумента или из префикса пароля
    # (U1-…, U2-…, Adm-… — так владелец их и назвал).
    логин = sys.argv[3] if len(sys.argv) > 3 else ''
    if not логин:
        логин = ('admin' if пароль.startswith('Adm')
                 else 'user1' if пароль.startswith('U1')
                 else 'user2' if пароль.startswith('U2') else 'user1')
    print('логинюсь как:', логин)
    тело = urllib.parse.urlencode({'username': логин,
                                   'password': пароль}).encode()
    try:
        with от.open(urllib.request.Request(
                БАЗА + '/login', data=тело,
                headers={'Content-Type':
                         'application/x-www-form-urlencoded'}), timeout=30) as о:
            стр = о.read().decode('utf-8', 'replace')
            print(f'логин: код {о.status}, {len(стр)} байт, '
                  f'куки {[c.name for c in банка]}')
    except urllib.error.HTTPError as e:
        print(f'логин: HTTP {e.code} '
              f'{e.read().decode("utf-8", "replace")[:200]}')
        return
    except Exception as e:  # noqa: BLE001
        print('логин не прошёл:', str(e)[:200])
        return

    try:
        with от.open(БАЗА + '/', timeout=40) as о:
            стр = о.read().decode('utf-8', 'replace')
        есть = признак in стр
        print(f'страница продавца: {о.status}, {len(стр)} байт')
        print(f'ПРИЗНАК ПРАВКИ «{признак}»: '
              f'{"ЕСТЬ, правка дошла" if есть else "НЕТ — продавец её не видит"}')
        # заодно перечислим блоки, которые панель показывает
        import re
        блоки = re.findall(r'<h2[^>]*>(.*?)</h2>', стр, re.S)
        print('блоки на карточке:',
              ' | '.join(б.strip()[:28] for б in блоки[:14]))
    except Exception as e:  # noqa: BLE001
        print('страницу продавца не открыть:', str(e)[:200])


if __name__ == '__main__':
    main()
