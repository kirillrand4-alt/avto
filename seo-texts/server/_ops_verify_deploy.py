# -*- coding: utf-8 -*-
"""Проверка, что на сервере лежит ИМЕННО тот код, который мы выкатили.

Прогон упал на 70 компаниях с «module has no attribute find_zakupki_supplier»,
хотя пробный запуск за десять минут до этого ту же функцию видел. Значит между
выкладкой и запуском файл на сервере мог откатиться или Python подхватил
устаревший .pyc. Печатаем размер файла, время правки и наличие функций —
и на всякий случай сносим кэш байткода.
"""
import json
import os
import sys

ПУТЬ = r'C:\sender\server\enrich_contacts.py'
КЭШ = r'C:\sender\server\__pycache__'


def main():
    out = {'файл': ПУТЬ}
    try:
        st = os.stat(ПУТЬ)
        out['байт'] = st.st_size
        out['изменён'] = st.st_mtime
        текст = open(ПУТЬ, encoding='utf-8', errors='replace').read()
        for имя in ('find_zakupki_supplier', 'бренд_компании', '_pdf_text',
                    'hh_страница_наша', 'site_domain', 'phones_in'):
            out['есть_' + имя] = ('def ' + имя) in текст
    except Exception as ex:  # noqa: BLE001
        out['ошибка_файла'] = f'{type(ex).__name__}: {str(ex)[:90]}'
    # сносим кэш байткода: если .pyc старше исходника по записанному в нём
    # времени, интерпретатор может взять именно его
    убрано = []
    try:
        for имя in os.listdir(КЭШ):
            if имя.startswith('enrich_contacts') and имя.endswith('.pyc'):
                p = os.path.join(КЭШ, имя)
                убрано.append({'файл': имя, 'байт': os.path.getsize(p)})
                os.remove(p)
    except Exception as ex:  # noqa: BLE001
        out['кэш'] = f'{type(ex).__name__}: {str(ex)[:70]}'
    out['удалён_байткод'] = убрано
    # и проверяем импортом, как это делает боевой op
    sys.path.insert(0, r'C:\sender\server')
    try:
        import enrich_contacts as EC
        out['импорт_видит_функцию'] = hasattr(EC, 'find_zakupki_supplier')
        out['импорт_из'] = getattr(EC, '__file__', '')
    except Exception as ex:  # noqa: BLE001
        out['импорт'] = f'{type(ex).__name__}: {str(ex)[:90]}'
    print(json.dumps(out, ensure_ascii=False, indent=1)[:3000])


if __name__ == '__main__':
    main()
