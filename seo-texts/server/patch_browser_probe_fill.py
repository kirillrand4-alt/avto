# -*- coding: utf-8 -*-
"""Добавляет в `browser_probe` действие `fill`: ввести текст в поле и нажать Enter.

ЗАЧЕМ. Четыре источника упёрлись в одно и то же: страница открывается, но поиск идёт
не через адрес, а через форму, а в пробнике есть только `click` и нет ввода текста.

  1. `utp.sberbank-ast.ru/Main/List/UnitedPurchaseListNew` — единый реестр процедур,
     6 298 лотов по слову «компрессор» от 2 389 организаторов, публично, без входа.
  2. `zakupki.mos.ru/purchase/list` — Портал поставщиков, React, фильтр из адреса
     не применяется.
  3. `tektorg.ru/rosneft/procedures` — секция Роснефти, параметр `name` открывает
     страницу, но список не отрисовывает.
  4. `e-disclosure.ru/poisk-po-kompaniyam` — годовые отчёты; капча снимается профилем
     дельфина, но поиск требует отправки формы (поле называется `textfield`).

ЧТО ДЕЛАЕТ. Перед блоком `click` вставляется обработка аргумента `fill`:

    "fill": {"selector": "#textfield", "value": "компрессор"}
    "fill": [{"selector": "input[name=name]", "value": "компрессор", "enter": true}]

Поведение: ждём селектор, чистим поле, печатаем значение, по умолчанию жмём Enter,
ждём `card_wait_ms` (по умолчанию 7000 мс) и перечитываем HTML. Список селекторов
перебирается по очереди, первый сработавший применяется — как уже сделано в `click`.
Всё, что не получилось, пишется в `out['fill_err']`, задача не падает.

БЕЗОПАСНОСТЬ. Новых сетевых прав не появляется: пробник и так открывает произвольный
адрес по заданию с HMAC-подписью. `fill` только печатает текст в поле уже открытой
страницы. Ничего не отправляется на сторонние адреса, файлы не пишутся.

УСТАНОВКА на сервере владельца:

    "C:\\Program Files\\Python311\\python.exe" C:\\sender\\server\\patch_browser_probe_fill.py

Перезапуск службы НЕ нужен: browser_probe.py запускается отдельным процессом на каждую
задачу и читается с диска при каждом запуске (в отличие от job_runner.py).

ОТКАТ: рядом кладётся бэкап `browser_probe.py.bak-<timestamp>`. Патч идемпотентен —
повторный запуск ничего не меняет. При ошибке компиляции откат делается автоматически.
"""
import os
import py_compile
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TARGET = os.environ.get('PROBE_PATH', os.path.join(DIR, 'browser_probe.py'))

MARKER = "# --- fill: ввод текста в поле (патч patch_browser_probe_fill) ---"
ANCHOR = "        if args.get('click'):\n"

BLOCK = '''        # --- fill: ввод текста в поле (патч patch_browser_probe_fill) ---
        # Нужен площадкам, где поиск идёт формой, а не адресом: Сбербанк-АСТ,
        # Портал поставщиков Москвы, ТЭК-Торг, e-disclosure.
        if args.get('fill'):
            reqs = args['fill'] if isinstance(args['fill'], list) else [args['fill']]
            out['fill_used'] = None
            for req in reqs:
                sel = (req or {}).get('selector') or ''
                val = str((req or {}).get('value', ''))
                if not sel:
                    continue
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    page.fill(sel, '')
                    page.fill(sel, val)
                    if (req or {}).get('enter', True):
                        page.press(sel, 'Enter')
                    page.wait_for_timeout(int(args.get('card_wait_ms', 7000)))
                    html = page.content()
                    out['fill_used'] = sel
                    break
                except Exception as e:  # noqa: BLE001
                    out['fill_err'] = f'{sel}: {str(e)[:90]}'
                    continue
'''


def main():
    if not os.path.exists(TARGET):
        sys.exit(f'не найден {TARGET} (переопредели через PROBE_PATH)')
    src = open(TARGET, encoding='utf-8').read()

    if MARKER in src:
        print('fill уже установлен — ничего не делаю')
        return
    if src.count(ANCHOR) != 1:
        sys.exit(f'якорь click найден {src.count(ANCHOR)} раз вместо одного — отказ, '
                 f'чтобы не порвать файл вслепую')

    bak = f'{TARGET}.bak-{int(time.time())}'
    shutil.copy2(TARGET, bak)
    open(TARGET, 'w', encoding='utf-8').write(src.replace(ANCHOR, BLOCK + ANCHOR, 1))
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, TARGET)
        sys.exit(f'ОШИБКА КОМПИЛЯЦИИ, файл откачен из {bak}: {e}')
    print(f'fill добавлен в {TARGET} (бэкап {bak})')
    print('перезапуск службы не нужен: browser_probe читается при каждом запуске задачи')


if __name__ == '__main__':
    main()
