# -*- coding: utf-8 -*-
"""fixC: хвост лога панели (только чтение) – убедиться, что перезапуск прошёл."""
import io
t = io.open(r'C:\centro2\centro2.log', encoding='utf-8', errors='replace').read()
i = t.rfind('===== перезапуск')
print(t[i:i + 600] if i >= 0 else t[-600:])
print('...')
print(t[-800:])
