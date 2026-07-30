# -*- coding: utf-8 -*-
"""Патч fetch_url: методы POST и произвольные заголовки.

ЗАЧЕМ. `fetch_url` умеет только GET, и на этом встали сразу три задачи:

- **Сбербанк-АСТ**: выдача уходит POST-ом, GET на `/Main/SearchQuery/…` отдаёт 200 и ноль
  байт. 2 389 организаторов архива недостижимы.
- **Росаккредитация** (`pub.fsa.gov.ru`): поиск идёт POST-запросом, инлайн-фильтр колонки
  работает только через него.
- **e-disclosure**: поиск эмитента — POST формы.

Плюс отдельная беда, которая ловилась весь день: **заголовки решают**. У hh с
`Accept: text/html,application/json` приходит 406, а с полным набором Chrome — 200. Пока
заголовки зашиты в код одним `User-Agent`, каждый такой случай выглядит как «источник
закрыт», хотя закрыт он не был ни разу за двадцать проверенных случаев.

ЧТО ДОБАВЛЯЕТ (всё необязательное, старые задания работают без изменений):

    {"url": "...",
     "method": "POST",
     "data": "PageSize=500&q=компрессор",        # строка или объект
     "json": {"pageSize": 500},                  # альтернатива data, ставит Content-Type
     "headers": {"Referer": "...", "Accept": "..."},
     "form": true                                # data как форма, а не как json
    }

- `data` объектом кодируется как форма (`application/x-www-form-urlencoded`) — то, что нужно
  ASP.NET-формам вроде Сбербанк-АСТ;
- `json` отправляется как `application/json` — для API вроде Портала поставщиков;
- `headers` **дополняют** дефолтные, а не заменяют: `User-Agent` остаётся, если не задан явно;
- метод берётся из `method`, но если передан `data` или `json`, а метод не указан, ставится
  POST — чтобы не получить молчаливый GET с потерянным телом.

В ответ добавляются `request_method` и `request_body_len`, чтобы по результату было видно,
что именно ушло: молчаливая потеря тела — ровно тот класс ошибки, где «ноль результатов»
выглядит как пустой источник.

Установка (тем же интерпретатором, которым запущена служба — сверить
`nssm get rusprom-runner Application`, это Python312):

    python patch_fetch_url_post.py
"""
import os
import py_compile
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TARGET = os.environ.get('FETCH_PATH', os.path.join(DIR, 'fetch_url.py'))

MARKER = '# --- POST и заголовки ---'
ANCHOR = "    req = urllib.request.Request(url, headers={'User-Agent': UA}, method='GET')\n"

BLOCK = '''    # --- POST и заголовки ---
    # Метод и тело: если тело передано, а метод нет — ставим POST, иначе тело потерялось бы
    # молча, и результат выглядел бы как пустой источник.
    _hdrs = {'User-Agent': UA}
    for _k, _v in (args.get('headers') or {}).items():
        if _v is not None:
            _hdrs[str(_k)] = str(_v)
    _body = None
    if args.get('json') is not None:
        _body = json.dumps(args['json'], ensure_ascii=False).encode('utf-8')
        _hdrs.setdefault('Content-Type', 'application/json; charset=utf-8')
    elif args.get('data') is not None:
        _d = args['data']
        if isinstance(_d, dict):
            _body = urllib.parse.urlencode(_d, encoding='utf-8').encode('utf-8')
            _hdrs.setdefault('Content-Type',
                             'application/x-www-form-urlencoded; charset=UTF-8')
        else:
            _body = str(_d).encode('utf-8')
            if args.get('form'):
                _hdrs.setdefault('Content-Type',
                                 'application/x-www-form-urlencoded; charset=UTF-8')
    _method = (args.get('method') or ('POST' if _body is not None else 'GET')).upper()
    out['request_method'] = _method
    out['request_body_len'] = len(_body) if _body else 0
    req = urllib.request.Request(url, data=_body, headers=_hdrs, method=_method)
'''


def main():
    if not os.path.exists(TARGET):
        sys.exit(f'не найден {TARGET} (переопредели через FETCH_PATH)')
    src = open(TARGET, encoding='utf-8').read()
    if MARKER in src:
        print('POST уже установлен — ничего не делаю')
        return
    if src.count(ANCHOR) != 1:
        sys.exit(f'якорь Request найден {src.count(ANCHOR)} раз вместо одного — отказ, '
                 'файл не тронут. Посмотри, как выглядит строка создания запроса, и '
                 'поправь ANCHOR')
    novyy = src.replace(ANCHOR, BLOCK, 1)
    # нужные модули: json и urllib.parse могут быть не импортированы
    for mod, stroka in (('json', 'import json\n'),
                        ('urllib.parse', 'import urllib.parse\n')):
        if f'import {mod}' not in novyy:
            novyy = novyy.replace('import urllib.request\n',
                                  stroka + 'import urllib.request\n', 1)

    bak = f'{TARGET}.bak-{int(time.time())}'
    shutil.copy2(TARGET, bak)
    open(TARGET, 'w', encoding='utf-8').write(novyy)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, TARGET)
        sys.exit(f'ОШИБКА КОМПИЛЯЦИИ, файл откачен из {bak}: {e}')
    print(f'POST и заголовки установлены, бэкап {bak}')
    print('перезапуск службы не нужен')
    print('проверка: отправь fetch_url с "method":"POST" и посмотри, есть ли в ответе '
          'ключи request_method / request_body_len — если их нет, блока в файле нет')


if __name__ == '__main__':
    main()
