# -*- coding: utf-8 -*-
"""Что ждёт штатный импорт: аргументы команды и колонки CSV."""
import io
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
t = io.open(r'C:\sender\sender\cli.py', encoding='utf-8', errors='replace').read()
m = re.search(r'def _cmd_import.*?(?=\ndef )', t, re.S)
итог['команда'] = (m.group(0)[:1200] if m else '')
m2 = re.search(r"add_parser\(\s*['\"]import['\"].*?(?=add_parser\()", t, re.S)
итог['аргументы'] = (m2.group(0)[:900] if m2 else '')
i = io.open(r'C:\sender\sender\importer.py', encoding='utf-8', errors='replace').read()
m3 = re.search(r'def import_csv.*?(?=\ndef )', i, re.S)
итог['import_csv'] = (m3.group(0)[:1800] if m3 else '')
итог['колонки_в_импортёре'] = sorted(set(re.findall(r"['\"]([a-z_]{3,20})['\"]\s*[:,]", i)))[:40]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3500])
