# -*- coding: utf-8 -*-
"""Собрать отчёт цепочки на сервере в файл (запускается через na_servere.py)."""
import io
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import cepochka_otchet as C  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
t = C.отчёт(n)
p = r'C:\sender\server\cepochka50.html'
with io.open(p, 'w', encoding='utf-8') as f:
    f.write(t)
    f.flush()
    os.fsync(f.fileno())
print('готово:', p, len(t))
