# -*- coding: utf-8 -*-
"""Разбор хвоста логов панели: откуда UnicodeEncodeError (полный стек одного случая), 500-е и запросы владельца
за последние минуты. Только чтение."""
import io, os, re, time
from collections import Counter
def хвост(путь, n=600000):
    р = os.path.getsize(путь)
    with io.open(путь, "rb") as f: f.seek(max(0, р - n)); return f.read().decode("utf-8", "replace").splitlines()
е = хвост(r"C:\sender\_ops\panel_err.log")
i = max(k for k, x in enumerate(е) if x.startswith("Traceback"))
print("=== последний стек:"); print("\n".join(x[:200] for x in е[max(0, i - 3):i + 40]))
print("=== типы ошибок в хвосте:", Counter(x.split(":")[0][:60] for x in е if re.match(r"^\w+(Error|Exception)", x)).most_common(8))
print("=== строки с временем (последние 15 не-INFO):")
print("\n".join(x[:200] for x in [x for x in е if re.search(r"\d\d:\d\d:\d\d", x)][-15:]))
о = хвост(r"C:\sender\_ops\panel_out.log", 300000)
print("=== коды ответов в хвосте out:", Counter(re.findall(r'HTTP/1.1" (\d{3})', "\n".join(о))).most_common())
print("=== 500-е:", Counter(re.sub(r"\?.*", "", x.split('"')[1])[:90] for x in о if '" 500' in x).most_common(10))
