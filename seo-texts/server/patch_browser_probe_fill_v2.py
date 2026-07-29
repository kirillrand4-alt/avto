# -*- coding: utf-8 -*-
"""Патч v2 действия `fill`: искать поле во всех фреймах, а не только в главном.

ЧТО ПОКАЗАЛ ПЕРВЫЙ ПРОГОН. На `e-disclosure.ru` v1 сработал сразу: поиск по ИНН отдал
карточку компании. А на `utp.sberbank-ast.ru/Main/List/UnitedPurchaseListNew` пробник
вернул 900 КБ разметки, в которой **ноль элементов `<input>`**, и `fill` честно упал по
таймауту ожидания селектора.

Причина выяснилась по разметке из DevTools владельца: реестр процедур живёт во вложенном
документе, а `page.fill` работает только по главному фрейму. Настоящее поле —
`<input id="searchInput" type="search" onkeypress="sendRequestOnEnterPress(event)"
placeholder="Введите ключевые слова или номер процедуры">`, рядом кнопка
`<button onclick="handleMainSearch()">Поиск</button>`.

ЧТО ДЕЛАЕТ v2:

  1. **Перебирает все фреймы страницы.** Сначала пробует главный, затем каждый вложенный.
     В ответ пишет `fill_frame` — адрес фрейма, в котором нашлось поле, чтобы в следующий
     раз ходить туда сразу.
  2. **Забирает HTML того же фрейма**, а не главного: иначе результат поиска остался бы
     невидимым, даже когда ввод прошёл.
  3. Добавляет `click_after` — селектор кнопки, которую нажать вместо Enter. Нужно там,
     где отправка висит на `onclick`, а не на клавише (как на Сбербанк-АСТ).

Аргументы:

    "fill": {"selector": "#searchInput", "value": "компрессор"}
    "fill": {"selector": "#searchInput", "value": "компрессор",
             "click_after": "button.mainSearchBar-find", "enter": false}

Патч идемпотентен и ставится поверх v1: старый блок ищется по маркеру и заменяется целиком.
Если v1 не стоял — блок вставляется перед обработкой `click`, как в v1.

УСТАНОВКА:

    & "C:\\Program Files\\Python311\\python.exe" 'C:\\sender\\server\\patch_browser_probe_fill_v2.py'

Перезапуск службы не нужен. Бэкап кладётся рядом, при ошибке компиляции откат автоматом.
"""
import os
import py_compile
import re
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TARGET = os.environ.get('PROBE_PATH', os.path.join(DIR, 'browser_probe.py'))

MARKER_V1 = "        # --- fill: ввод текста в поле (патч patch_browser_probe_fill) ---"
MARKER_V2 = "        # --- fill v2: ввод текста, поиск поля во всех фреймах ---"
ANCHOR = "        if args.get('click'):\n"

BLOCK = '''        # --- fill v2: ввод текста, поиск поля во всех фреймах ---
        # Реестры вроде Сбербанк-АСТ держат поиск во вложенном документе, поэтому
        # page.fill по главному фрейму не находит поле. Перебираем все фреймы и
        # забираем HTML именно того, где ввод прошёл.
        if args.get('fill'):
            reqs = args['fill'] if isinstance(args['fill'], list) else [args['fill']]
            out['fill_used'] = None
            done = False
            for req in reqs:
                if done:
                    break
                sel = (req or {}).get('selector') or ''
                val = str((req or {}).get('value', ''))
                if not sel:
                    continue
                try:
                    frames = list(page.frames)
                except Exception:  # noqa: BLE001
                    frames = []
                for fr in frames:
                    try:
                        fr.wait_for_selector(sel, timeout=5000)
                        fr.fill(sel, '')
                        fr.fill(sel, val)
                        after = (req or {}).get('click_after')
                        if after:
                            fr.click(after, timeout=5000)
                        elif (req or {}).get('enter', True):
                            fr.press(sel, 'Enter')
                        page.wait_for_timeout(int(args.get('card_wait_ms', 7000)))
                        try:
                            html = fr.content()
                        except Exception:  # noqa: BLE001
                            html = page.content()
                        out['fill_used'] = sel
                        out['fill_frame'] = (fr.url or '')[:200]
                        done = True
                        break
                    except Exception as e:  # noqa: BLE001
                        out['fill_err'] = f'{sel}: {str(e)[:90]}'
                        continue
'''


def main():
    if not os.path.exists(TARGET):
        sys.exit(f'не найден {TARGET} (переопредели через PROBE_PATH)')
    src = open(TARGET, encoding='utf-8').read()

    if MARKER_V2 in src:
        print('fill v2 уже установлен — ничего не делаю')
        return

    bak = f'{TARGET}.bak-{int(time.time())}'
    shutil.copy2(TARGET, bak)

    if MARKER_V1 in src:
        # вырезать блок v1 целиком: от маркера до обработки click
        i = src.index(MARKER_V1)
        j = src.index(ANCHOR, i)
        new = src[:i] + BLOCK + src[j:]
        how = 'блок v1 заменён'
    else:
        if src.count(ANCHOR) != 1:
            sys.exit(f'якорь click найден {src.count(ANCHOR)} раз вместо одного — отказ')
        new = src.replace(ANCHOR, BLOCK + ANCHOR, 1)
        how = 'блок вставлен впервые'

    open(TARGET, 'w', encoding='utf-8').write(new)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, TARGET)
        sys.exit(f'ОШИБКА КОМПИЛЯЦИИ, файл откачен из {bak}: {e}')
    print(f'fill v2 установлен ({how}), бэкап {bak}')
    print('перезапуск службы не нужен')


if __name__ == '__main__':
    main()
