# -*- coding: utf-8 -*-
"""Почему справочники подразделений вернули «обработано 0»: полная трасса, а не хвост.

ПОВОД. Шесть заданий подряд легли с `URLError: [Errno 111] Connection refused`, а итог
напечатался бодрый: «обработано 0». По правилу В8 это отказ инструмента, а не пустой
результат. Сеть сервера при этом исправна — только что с него же открылись xmlriver,
google, roseltorg и evraz. Значит соединение отказывают НЕ внешние узлы: либо модуль ходит
на localhost (панель, локальный прокси), либо ему подсунут HTTPS_PROXY, которого нет.
Печатаю окружение и адрес, к которому он обращается, до того как звать его повторно.
"""
import os
import sys
import traceback

print('HTTP_PROXY  =', os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy') or '(нет)')
print('HTTPS_PROXY =', os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '(нет)')
print('NO_PROXY    =', os.environ.get('NO_PROXY') or '(нет)')
sys.path.insert(0, r'C:\sender')
try:
    import dept_directory as D
    print('модуль загружен:', getattr(D, '__file__', '?'))
    for imya in dir(D):
        if imya.isupper() and isinstance(getattr(D, imya), str) and '://' in getattr(D, imya):
            print(f'  адрес {imya} = {getattr(D, imya)}')
    fn = [x for x in dir(D) if not x.startswith('_') and callable(getattr(D, x))]
    print('функции:', ', '.join(fn[:25]))
except Exception:  # noqa: BLE001
    traceback.print_exc()
