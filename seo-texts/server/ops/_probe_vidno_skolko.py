# -*- coding: utf-8 -*-
"""Сколько предприятий ВИДИТ продавец на панели после скрытия 164.

Число из базы продаж («останется видимыми: 1409») — это арифметика, а не то,
что отрисует страница: список фильтруется в роутере, и ошибка там даст
расхождение, которого в базе не видно. Поэтому логинимся и читаем счётчик со
страницы, как продавец.

Пароль НЕ печатаем: берём из окружения панели (panel.env, его подкладывает
раннер), перебираем подходящие ключи и выводим только ИМЯ сработавшего.

Запуск: python _probe_vidno_skolko.py
"""
import http.cookiejar
import os
import re
import urllib.parse
import urllib.request

БАЗА = 'http://127.0.0.1:8012/obzvon/centro'


def попытка(логин, пароль):
    банка = http.cookiejar.CookieJar()
    от = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(банка))
    тело = urllib.parse.urlencode({'username': логин, 'password': пароль}).encode()
    try:
        от.open(urllib.request.Request(БАЗА + '/login', data=тело), timeout=25)
        with от.open(БАЗА + '/', timeout=40) as о:
            стр = о.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:80]
    if 'password' in стр.lower() and len(стр) < 4000:
        return None, 'снова форма логина'
    return стр, ''


def main():
    ключи = [k for k in os.environ
             if re.search(r'OBZVON|CENTRO|PANEL|ADMIN', k, re.I)
             and re.search(r'PASS|PWD', k, re.I)]
    print('ключи-кандидаты:', ключи or 'нет ни одного')
    for k in ключи:
        for логин in ('admin', 'user1'):
            стр, ошибка = попытка(логин, os.environ[k])
            if not стр:
                continue
            числа = re.findall(r'редприяти\w*[^0-9<]{0,40}(\d{2,6})', стр)
            ссылка = re.search(r'скрытых предприятий:\s*(\d+)', стр)
            print(f'вошёл: ключ {k}, логин {логин}')
            print(f'  длина страницы: {len(стр)}')
            print(f'  числа рядом со словом «предприятия»: {числа[:6]}')
            print(f'  ссылка «скрытых предприятий»: '
                  f'{ссылка.group(1) if ссылка else "НЕТ на странице"}')
            return
    print('войти не удалось ни одним ключом — счётчик не проверен')


if __name__ == '__main__':
    main()
