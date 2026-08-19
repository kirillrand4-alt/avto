# -*- coding: utf-8 -*-
"""Поставить новые store.py и api/app.py, сохранив прежние рядом.

Служба держит старый код в памяти — правка вступит в силу при перезапуске
SenderPanel. Перезапуск делает владелец: панель боевая, в ней очередь
подтверждений и автоотправка.
"""
import hashlib
import io
import json
import shutil
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
МЕТКА = time.strftime('%Y%m%d-%H%M%S')
из = {}
for имя, боевой, новый in (
        ('store.py', r'C:\sender\sender\store.py', r'C:\sender\_tmp\store_novyy.py'),
        ('api/app.py', r'C:\sender\sender\api\app.py', r'C:\sender\_tmp\api_app_novyy.py')):
    бэкап = боевой + '.bak-' + МЕТКА
    shutil.copy(боевой, бэкап)
    shutil.copy(новый, боевой)
    из[имя] = {'бэкап': бэкап,
               'sha_после': hashlib.sha256(io.open(боевой, 'rb').read()).hexdigest()[:16]}
# синтаксис на месте
import py_compile
ошибки = []
for п in (r'C:\sender\sender\store.py', r'C:\sender\sender\api\app.py'):
    try:
        py_compile.compile(п, doraise=True)
    except Exception as e:  # noqa: BLE001
        ошибки.append(str(e)[:200])
из['синтаксис'] = ошибки or 'чисто'
print(json.dumps(из, ensure_ascii=False, indent=1))
