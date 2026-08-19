# -*- coding: utf-8 -*-
"""Проверить новый код БЕЗ подмены боевого: импортируем копии и зовём метод."""
import importlib.util
import json
import shutil
import sys
import tempfile
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
врем = os.path.join(tempfile.gettempdir(), 'proba_sender.db')
shutil.copy(r'C:\sender\sender.db', врем)
# грузим НОВЫЙ store как отдельный модуль
сп = importlib.util.spec_from_file_location('store_novyy', r'C:\sender\_tmp\store_novyy.py')
м = importlib.util.module_from_spec(сп)
sys.modules['store_novyy'] = м
сп.loader.exec_module(м)
s = м.Store(врем)
почты = ['chernyavin@rostkran.ru', 'stroygroups23@mail.ru', 'ysada@bk.ru']
из = s.poslednie_otvety(emails=почты, inns=['7713468789'])
print(json.dumps({'найдено': len(из),
                  'по_почтам': {k: v for k, v in из.items() if '@' in k}},
                 ensure_ascii=False, indent=1)[:1200])
