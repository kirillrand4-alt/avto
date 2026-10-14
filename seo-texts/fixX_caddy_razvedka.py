# -*- coding: utf-8 -*-
r"""fixX: зеркала панели КЦ – как в Caddy опубликованы /obzvon (КЦ) и /obzvon-meyer (Meyer), на каких доменах. Только чтение.
Хэши, токены и пароли в выводе маскируются.

    python3 zapusk_na_servere.py fixX_caddy_razvedka.py
"""
import io
import re

t = io.open(r'C:\Caddyfile', encoding='utf-8', errors='replace').read()
t = re.sub(r'\$2[aby]\$\d\d\$[./A-Za-z0-9]{40,}', '<хэш>', t)
t = re.sub(r'(?i)((?:token|secret|password|key)\S*\s+)\S+', r'\1<скрыто>', t)
print('Caddyfile: %d знаков, строк %d' % (len(t), t.count('\n')))
print(t[:12000])
