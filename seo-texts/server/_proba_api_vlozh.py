# -*- coding: utf-8 -*-
"""Проверить новый api/app.py: импортируется ли и есть ли ручка вложений."""
import importlib.util
import io
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
путь = r'C:\sender\_tmp\api_app_novyy2.py'
из = {}
try:
    сп = importlib.util.spec_from_file_location('api_app_novyy2', путь)
    м = importlib.util.module_from_spec(сп)
    сп.loader.exec_module(м)
    из['импорт'] = 'ок'
    из['есть_make_site_app'] = hasattr(м, 'make_site_app') or hasattr(м, 'create_app')
except Exception as e:  # noqa: BLE001
    из['импорт'] = 'сбой: %s' % repr(e)[:200]
t = io.open(путь, encoding='utf-8', errors='replace').read()
из['ручка_vlozheniya'] = '@app.post("/vlozheniya")' in t
из['поле_attachments'] = 'attachments: Optional[list[str]]' in t
из['передача_в_panel'] = 'panel["vlozheniya"] = вложения' in t
print(json.dumps(из, ensure_ascii=False, indent=1))
