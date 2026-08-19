# -*- coding: utf-8 -*-
"""Кто выставляет retryable в самом SMTP-клиенте: код 4xx против 5xx."""
import io, json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
из = {}
for имя in ('smtp.py', 'sender.py', 'transport.py'):
    п = r'C:\sender\sender\%s' % имя
    if not os.path.exists(п):
        continue
    t = io.open(п, encoding='utf-8', errors='replace').read()
    места = [(i + 1, l.strip()[:140]) for i, l in enumerate(t.splitlines())
             if re.search(r'retryable|SMTPResponseException|smtp_code|code\s*//\s*100|'
                          r'\b4\d\d\b|SMTPServerDisconnected|SMTPRecipientsRefused', l)]
    if места:
        из[имя] = места[:16]
print(json.dumps(из, ensure_ascii=False, indent=1)[:3600])
