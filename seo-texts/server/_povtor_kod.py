# -*- coding: utf-8 -*-
"""Какие SMTP-ответы отправщик считает временными и повторяет."""
import io, json, re, sys
sys.stdout.reconfigure(encoding='utf-8')
из = {}
for имя in ('orchestrator.py', 'smtp_client.py', 'sender_smtp.py', 'mailer.py'):
    п = r'C:\sender\sender\%s' % имя
    import os
    if not os.path.exists(п):
        continue
    t = io.open(п, encoding='utf-8', errors='replace').read()
    m = re.search(r'def .*retryable.*?(?=\ndef |\n    def |\nclass )', t, re.S)
    if m:
        из[имя] = m.group(0)[:1400]
    for м in re.finditer(r'retryable\s*=\s*[^\n]{0,160}', t):
        из.setdefault(имя + '_места', []).append(м.group(0)[:160])
print(json.dumps(из, ensure_ascii=False, indent=1)[:3500])
