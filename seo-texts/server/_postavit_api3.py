# -*- coding: utf-8 -*-
"""Поставить api/app.py с блоком контактов; бэкап и проверка импорта."""
import hashlib
import io
import json
import py_compile
import shutil
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
боевой = r'C:\sender\sender\api\app.py'
новый = r'C:\sender\_tmp\api_app_novyy3.py'
бэкап = боевой + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
shutil.copy(боевой, бэкап)
shutil.copy(новый, боевой)
из = {'бэкап': бэкап,
      'sha': hashlib.sha256(io.open(боевой, 'rb').read()).hexdigest()[:16]}
try:
    py_compile.compile(боевой, doraise=True)
    sys.path.insert(0, r'C:\sender')
    import importlib
    importlib.import_module('sender.api.app')
    из['проверка'] = 'ок'
except Exception as e:  # noqa: BLE001
    из['проверка'] = repr(e)[:200]
print(json.dumps(из, ensure_ascii=False, indent=1))
