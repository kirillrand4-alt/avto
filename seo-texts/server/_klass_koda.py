# -*- coding: utf-8 -*-
"""_classify_code целиком: как 4xx превращается в повтор."""
import io, re, sys
sys.stdout.reconfigure(encoding='utf-8')
t = io.open(r'C:\sender\sender\sender.py', encoding='utf-8', errors='replace').read()
m = re.search(r'def _classify_code.*?(?=\n    def )', t, re.S)
print((m.group(0)[:1600] if m else 'не найдено'))
print('--- места 880-900 ---')
print('\n'.join('%4d| %s' % (i + 1, t.splitlines()[i][:120]) for i in range(880, 900)))
