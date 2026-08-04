# -*- coding: utf-8 -*-
"""Посмотреть панель глазами: войти, открыть карточки и напечатать то, что видит человек.

ЗАЧЕМ НЕ ЗАПРОСОМ К БАЗЕ. В базе можно проверить, что данные ЕСТЬ. Вопрос владельца другой:
правильно ли они ПОКАЗАНЫ и не выкинуто ли лишнее. На это отвечает только отрисованная
страница: поле может быть заполнено в базе и не выводиться в карточке, а скрытая запись
выглядит как отсутствующая.

Браузерный пробник для входа не годится: его `fill` перебирает селекторы как ЗАПАСНЫЕ
варианты и применяет первый сработавший, то есть заполнить логин И пароль одним заданием
нельзя. Поэтому вход делается обычным запросом с кукой, прямо на 127.0.0.1:8012.
"""
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request

BAZA = 'http://127.0.0.1:8012'
LOGIN, PAROL = sys.argv[1], sys.argv[2]
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
    """Текст, как его видит человек: без скриптов, стилей и тегов."""
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?i)</(tr|div|p|li|h\d|table)>', '\n', h)
    h = re.sub(r'(?i)</t[dh]>', ' | ', h)
    h = re.sub(r'<[^>]+>', '', h)
    h = h.replace('&nbsp;', ' ').replace('&laquo;', '«').replace('&raquo;', '»')
    h = h.replace('&quot;', '"').replace('&amp;', '&').replace('&#34;', '"')
    return re.sub(r'[ \t]{2,}', ' ', re.sub(r'\n{3,}', '\n\n', h)).strip()


# Приложение смонтировано под префиксом, а на голом /login отвечает 401 «Нужен логин и
# пароль обзвона» — то есть форму искать надо по тому же пути, что и снаружи.
import base64
PREF = ''
for p in ('/obzvon/centro', ''):
    st, h, _ = vzyat(p + '/login')
    if st == 200 and 'input' in h.lower():
        PREF = p
        break
polya = re.findall(r'<input[^>]*name="([^"]+)"', h)
print(f'префикс {PREF!r}: страница входа {st}, поля формы {polya}')
if polya:
    st, h, u = vzyat(PREF + '/login', {polya[0]: LOGIN,
                                       polya[1] if len(polya) > 1 else 'password': PAROL})
else:
    # Формы нет — значит вход базовый, HTTP Basic. Проверяем и его, чтобы не гадать.
    op.addheaders = [('Authorization', 'Basic ' + base64.b64encode(
        f'{LOGIN}:{PAROL}'.encode()).decode())]
    st, h, u = vzyat(PREF + '/')
print(f'после входа: {st}, адрес {u}, кук {len(cj)}')
if 'Вход в рабочую базу' in h or st == 401:
    print('ВОЙТИ НЕ УДАЛОСЬ. Ответ:', vidno(h)[:300])
    sys.exit(1)
print('=' * 100)
print(vidno(h)[:5000])
