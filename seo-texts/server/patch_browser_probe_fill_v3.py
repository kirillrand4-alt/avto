# -*- coding: utf-8 -*-
"""Патч v3: `fill_seq` — заполнить НЕСКОЛЬКО полей подряд, потом отправить.

ЗАЧЕМ. У `fill` (v1/v2) семантика «перебрать варианты селектора, остановиться на первом
сработавшем». Она правильная, когда мы не знаем имя поля. Но появилась другая задача:
**заполнить сразу несколько разных полей одной формы**.

Конкретный случай. Реестр Сбербанк-АСТ по умолчанию применяет фильтр «С начала 2024го»
(в разметке: «Дата публикации: с 01.01.2024 00:00»). Из-за него «компрессор» даёт 994 лота
от 460 организаторов — это только последние 2,5 года. Кнопка «Очистить все» снимает фильтр,
но заодно стирает поисковый запрос, и счётчик уходит на весь реестр (13 129 459 лотов).

Архив при этом нужен не меньше свежих закупок: **кто покупал компрессор раньше — тот, у кого
машина уже стоит**, то есть кандидат на замену. Это ровно наш целевой список.

Решение: заполнить поле поиска И поле «Дата публикации с» ранней датой, потом нажать «Поиск».

ЧТО ДОБАВЛЯЕТ v3 (аргумент `fill_seq`, старый `fill` работает как раньше):

    "fill_seq": {
      "steps": [
        {"selector": "#searchInput", "value": "компрессор"},
        {"selector": "#filterDateFrom", "value": "01.01.2005"}
      ],
      "submit": "button.mainSearchBar-find",
      "open_first": "button[onclick^=showHideFilters]"
    }

  - `steps` применяются **все по очереди**, ошибка одного шага не отменяет остальные
    (пишется в `fill_seq_err`, чтобы было видно, что именно не заполнилось);
  - `open_first` — необязательный селектор, который надо нажать до заполнения: панели
    фильтров часто свёрнуты, и поля внутри них не видны, пока панель не раскрыта;
  - `submit` — селектор кнопки отправки; если не задан, жмётся Enter в последнем поле;
  - поиск шагов идёт по всем фреймам, как в v2;
  - в ответ пишется `fill_seq_done` — сколько шагов удалось.

Идемпотентен, ставится поверх v1/v2. Перезапуск службы не нужен.

УСТАНОВКА:
    & "C:\\Program Files\\Python311\\python.exe" 'C:\\sender\\server\\patch_browser_probe_fill_v3.py'
"""
import os
import py_compile
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TARGET = os.environ.get('PROBE_PATH', os.path.join(DIR, 'browser_probe.py'))

MARKER_V3 = "        # --- fill_seq: заполнить несколько полей подряд и отправить ---"
ANCHOR = "        if args.get('click'):\n"

BLOCK = '''        # --- fill_seq: заполнить несколько полей подряд и отправить ---
        # Нужен там, где кроме строки поиска надо поменять фильтр (например снять
        # умолчание «с 01.01.2024» на Сбербанк-АСТ, чтобы достать архив).
        if args.get('fill_seq'):
            cfg = args['fill_seq'] or {}
            steps = cfg.get('steps') or []
            out['fill_seq_done'] = 0

            def _find_frame(sel):
                try:
                    frames = list(page.frames)
                except Exception:  # noqa: BLE001
                    frames = []
                for fr in frames:
                    try:
                        fr.wait_for_selector(sel, timeout=4000)
                        return fr
                    except Exception:  # noqa: BLE001
                        continue
                return None

            opener = cfg.get('open_first')
            if opener:
                fr = _find_frame(opener)
                if fr is not None:
                    try:
                        fr.click(opener, timeout=4000)
                        page.wait_for_timeout(1500)
                    except Exception as e:  # noqa: BLE001
                        out['fill_seq_err'] = f'open_first: {str(e)[:70]}'

            last_fr, last_sel = None, None
            for st in steps:
                sel = (st or {}).get('selector') or ''
                val = str((st or {}).get('value', ''))
                if not sel:
                    continue
                fr = _find_frame(sel)
                if fr is None:
                    out['fill_seq_err'] = f'{sel}: не найден ни в одном фрейме'
                    continue
                try:
                    fr.fill(sel, '')
                    fr.fill(sel, val)
                    out['fill_seq_done'] += 1
                    last_fr, last_sel = fr, sel
                except Exception as e:  # noqa: BLE001
                    out['fill_seq_err'] = f'{sel}: {str(e)[:70]}'

            submit = cfg.get('submit')
            try:
                if submit:
                    fr = _find_frame(submit) or last_fr
                    if fr is not None:
                        fr.click(submit, timeout=6000)
                elif last_fr is not None and last_sel:
                    last_fr.press(last_sel, 'Enter')
                page.wait_for_timeout(int(args.get('card_wait_ms', 9000)))
                fr = last_fr or page
                try:
                    html = fr.content()
                except Exception:  # noqa: BLE001
                    html = page.content()
                out['fill_frame'] = (getattr(fr, 'url', '') or '')[:200]
            except Exception as e:  # noqa: BLE001
                out['fill_seq_err'] = f'submit: {str(e)[:70]}'
'''


def main():
    if not os.path.exists(TARGET):
        sys.exit(f'не найден {TARGET} (переопредели через PROBE_PATH)')
    src = open(TARGET, encoding='utf-8').read()
    if MARKER_V3 in src:
        print('fill_seq уже установлен — ничего не делаю')
        return
    if src.count(ANCHOR) != 1:
        sys.exit(f'якорь click найден {src.count(ANCHOR)} раз вместо одного — отказ')

    bak = f'{TARGET}.bak-{int(time.time())}'
    shutil.copy2(TARGET, bak)
    open(TARGET, 'w', encoding='utf-8').write(src.replace(ANCHOR, BLOCK + ANCHOR, 1))
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, TARGET)
        sys.exit(f'ОШИБКА КОМПИЛЯЦИИ, файл откачен из {bak}: {e}')
    print(f'fill_seq установлен, бэкап {bak}')
    print('перезапуск службы не нужен')


if __name__ == '__main__':
    main()
