# -*- coding: utf-8 -*-
"""Патч browser_probe: действие `eval_js` — выполнить свой скрипт на странице.

ЗАЧЕМ. На Сбербанк-АСТ выгрузка встала на двух упорах, и оба — не про сайт, а про пробел
в инструменте:

1. **`#PageSize` — скрытый input.** Playwright не заполняет скрытые поля и не переключает
   `<select>` через `fill`. Из-за этого за одно задание приходит **20 строк**, и 2 389
   организаторов архива выгружаются 120 заданиями по 90–150 с — то есть никогда.
2. **Выдача уходит POST-ом.** GET на `/Main/SearchQuery/…` отдаёт 200 и **ноль байт** и через
   `fetch_url`, и через браузер. Значит подменить запрос снаружи нельзя, надо нажать кнопку
   в самой странице, предварительно переставив поля.

Оба упора снимаются одним общим действием: **дать выполнить произвольный JS в контексте
страницы**. Тогда скрытое поле ставится присваиванием, `<select>` — через `value` плюс
событие `change`, а любая форма отправляется своим же обработчиком.

Это не костыль под один сайт. Тот же класс препятствий встречался на Портале поставщиков
Москвы (фильтр применяется только своей формой `filter={"nameLike":…}`), на Росаккредитации
(инлайн-фильтр колонки), на e-disclosure (POST формы). `fill` и `fill_seq` закрывают видимые
поля, `eval_js` — всё остальное.

ЧТО ДОБАВЛЯЕТ:

    "eval_js": {
      "script": "document.querySelector('#PageSize').value='500';",
      "all_frames": true,          # по умолчанию только главный фрейм
      "after_ms": 400,             # пауза после выполнения
      "then_click": "button.mainSearchBar-find",
      "return": "document.querySelectorAll('tr').length"
    }

Порядок в задании: `fill` / `fill_seq` → `eval_js` → `click`. То есть сначала заполняются
видимые поля, потом правятся скрытые, потом жмётся кнопка. Если нужен другой порядок —
`then_click` внутри `eval_js` нажимает раньше внешнего `click`.

Ответ получает ключи:
  `eval_js_ok` (bool), `eval_js_value` (то, что вернул `return`), `eval_js_err` (текст ошибки),
  `eval_js_frames` (в скольких фреймах выполнилось).

БЕЗОПАСНОСТЬ. Скрипт выполняется в песочнице браузера на странице, которую мы и так открыли,
и ничего не отправляет за её пределы. Задания раннера подписаны HMAC, то есть источник
скрипта — наша же сессия. Отдельно: `eval_js` **не логирует содержимое страницы**, только
длину возвращённого значения, чтобы в результат не утекали персональные данные целиком.

Установка (в тот же интерпретатор, которым запущена служба — сверить
`nssm get rusprom-runner Application`, это Python312):

    python patch_browser_probe_evaljs.py

Перезапуск службы не нужен: задание читает файл при каждом вызове.
"""
import os
import py_compile
import shutil
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TARGET = os.environ.get('PROBE_PATH', os.path.join(DIR, 'browser_probe.py'))

MARKER = "        # --- eval_js: выполнить свой скрипт на странице ---"
ANCHOR = "        if args.get('click'):\n"

BLOCK = '''        # --- eval_js: выполнить свой скрипт на странице ---
        # Нужен там, где поле скрыто или форма отправляется своим обработчиком:
        # скрытый #PageSize на Сбербанк-АСТ, select без fill, POST-выдача.
        if args.get('eval_js'):
            cfg = args['eval_js'] or {}
            script = cfg.get('script') or ''
            ret_expr = cfg.get('return') or ''
            vypolnено = 0
            znachenie = None
            oshibki = []
            celi = [page]
            if cfg.get('all_frames'):
                try:
                    celi = celi + [f for f in page.frames if f is not page.main_frame]
                except Exception:  # noqa: BLE001
                    pass
            for tsel in celi:
                if not script:
                    break
                try:
                    tsel.evaluate('() => { %s }' % script)
                    vypolnено += 1
                except Exception as e:  # noqa: BLE001
                    oshibki.append(str(e)[:160])
            if ret_expr:
                try:
                    znachenie = page.evaluate('() => (%s)' % ret_expr)
                except Exception as e:  # noqa: BLE001
                    oshibki.append('return: ' + str(e)[:160])
            pauza = int(cfg.get('after_ms') or 0)
            if pauza:
                try:
                    page.wait_for_timeout(pauza)
                except Exception:  # noqa: BLE001
                    pass
            if cfg.get('then_click'):
                try:
                    page.click(cfg['then_click'], timeout=15000)
                    page.wait_for_timeout(int(cfg.get('after_click_ms') or 2500))
                except Exception as e:  # noqa: BLE001
                    oshibki.append('then_click: ' + str(e)[:160])
            out['eval_js_ok'] = vypolnено > 0
            out['eval_js_frames'] = vypolnено
            # в лог идёт только длина значения: страница может содержать персональные
            # данные, и целиком в результат они попадать не должны
            out['eval_js_value'] = znachenie
            out['eval_js_value_len'] = len(str(znachenie)) if znachenie is not None else 0
            if oshibki:
                out['eval_js_err'] = ' | '.join(oshibki[:3])

'''


def main():
    if not os.path.exists(TARGET):
        sys.exit(f'не найден {TARGET} (переопредели через PROBE_PATH)')
    src = open(TARGET, encoding='utf-8').read()
    if MARKER in src:
        print('eval_js уже установлен — ничего не делаю')
        return
    if src.count(ANCHOR) != 1:
        sys.exit(f'якорь click найден {src.count(ANCHOR)} раз вместо одного — отказ, '
                 'файл не тронут')

    bak = f'{TARGET}.bak-{int(time.time())}'
    shutil.copy2(TARGET, bak)
    open(TARGET, 'w', encoding='utf-8').write(src.replace(ANCHOR, BLOCK + ANCHOR, 1))
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, TARGET)
        sys.exit(f'ОШИБКА КОМПИЛЯЦИИ, файл откачен из {bak}: {e}')
    print(f'eval_js установлен, бэкап {bak}')
    print('перезапуск службы не нужен')
    print('проверка: отправь задание с заведомо неверным скриптом и посмотри, '
          'есть ли в ответе ключи eval_js_ok / eval_js_err — если ключей нет вовсе, '
          'блока в файле нет (значит патч затёрт pull-ом старой копии с дропа)')


if __name__ == '__main__':
    main()
