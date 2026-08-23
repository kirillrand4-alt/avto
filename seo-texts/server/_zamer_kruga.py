# -*- coding: utf-8 -*-
r"""Сколько секунд стоит каждый шаг круга моста — по шагам, с секундомером."""
import json
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import zenno_most as ZM  # noqa: E402

d = {}
t = time.time()
d['длина_очереди'] = ZM._dlina_ocheredi()
d['сек_длина'] = round(time.time() - t, 2)
t = time.time()
d['сторож'] = ZM.storozh()
d['сек_сторож'] = round(time.time() - t, 2)
t = time.time()
d['приём'] = ZM.priyom()
d['сек_приём'] = round(time.time() - t, 2)
print(json.dumps(d, ensure_ascii=False, indent=1)[:1600])
