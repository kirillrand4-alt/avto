# -*- coding: utf-8 -*-
"""Поставить sender.py, confirm.py и api/app.py (вложения). Бэкап + проверка."""
import hashlib
import io
import json
import py_compile
import shutil
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
МЕТКА = time.strftime('%Y%m%d-%H%M%S')
ПАРЫ = (('sender.py', r'C:\sender\sender\sender.py', r'C:\sender\_tmp\sender_novyy.py'),
        ('confirm.py', r'C:\sender\sender\confirm.py', r'C:\sender\_tmp\confirm_novyy.py'),
        ('api/app.py', r'C:\sender\sender\api\app.py', r'C:\sender\_tmp\api_app_novyy2.py'))
из = {}
for имя, боевой, новый in ПАРЫ:
    бэкап = боевой + '.bak-' + МЕТКА
    shutil.copy(боевой, бэкап)
    shutil.copy(новый, боевой)
    из[имя] = {'бэкап': бэкап,
               'sha': hashlib.sha256(io.open(боевой, 'rb').read()).hexdigest()[:16]}
ошибки = []
for _и, боевой, _н in ПАРЫ:
    try:
        py_compile.compile(боевой, doraise=True)
    except Exception as e:  # noqa: BLE001
        ошибки.append('%s: %s' % (боевой, str(e)[:160]))
из['синтаксис'] = ошибки or 'чисто'
# и целиком: собирается ли приложение панели из нового кода
try:
    sys.path.insert(0, r'C:\sender')
    import importlib
    for м in ('sender.sender', 'sender.confirm', 'sender.api.app', 'sender.store'):
        importlib.import_module(м)
    из['импорт_пакета'] = 'ок'
except Exception as e:  # noqa: BLE001
    из['импорт_пакета'] = repr(e)[:200]
print(json.dumps(из, ensure_ascii=False, indent=1))
