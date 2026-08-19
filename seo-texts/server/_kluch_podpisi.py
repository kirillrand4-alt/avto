# -*- coding: utf-8 -*-
"""Имя ключа подписи заданий: как его читает панель."""
import io, json, re, sys
sys.stdout.reconfigure(encoding='utf-8')
t = io.open(r'C:\sender\sender\probe_sync.py', encoding='utf-8', errors='replace').read()
m = re.search(r'def _подпись.*?(?=\n    def )', t, re.S)
из = {'функция': m.group(0)[:600] if m else ''}
env = {}
for l in io.open(r'C:\sender\server\runner-secrets.env', encoding='utf-8', errors='replace'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip()
из['ключи_в_файле'] = sorted(env)
print(json.dumps(из, ensure_ascii=False, indent=1)[:1200])
