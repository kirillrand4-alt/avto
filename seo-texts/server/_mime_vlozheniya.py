# -*- coding: utf-8 -*-
"""Как собирается письмо и есть ли место для вложений."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
из = {}
for имя in ('sender.py', 'mime.py', 'render.py'):
    п = r'C:\sender\sender\%s' % имя
    if not os.path.exists(п):
        continue
    t = io.open(п, encoding='utf-8', errors='replace').read()
    из[имя] = {
        'MIME_импорты': [l.strip()[:90] for l in t.splitlines()
                         if re.search(r'import.*(email|mime)', l, re.I)][:8],
        'сборка': [l.strip()[:100] for l in t.splitlines()
                   if re.search(r'MIMEText|MIMEMultipart|EmailMessage|add_attachment|'
                                r'set_content|attach\(', l)][:12],
        'функции': [l.strip()[:80] for l in t.splitlines()
                    if re.match(r'\s*def .*(mime|build|render|deliver)', l, re.I)][:10],
    }
print(json.dumps(из, ensure_ascii=False, indent=1)[:3000])
