# -*- coding: utf-8 -*-
"""Сколько раз и на чём падает claim автоотправки в логе панели."""
import io
import os
import re
from collections import Counter

путь = r"C:\sender\_ops\panel_err.log"
р = os.path.getsize(путь)
with io.open(путь, "rb") as f:
    f.seek(max(0, р - 2_000_000))
    текст = f.read().decode("utf-8", "replace")

for фраза in ("claim_approved_due упал", "another row available",
              "auto_send: тик", "probe_sync", "addr_probe",
              "Cannot operate on a closed database", "database is locked"):
    print(f"{фраза!r}: {текст.count(фраза)}")

# последние 40 строк файла — что происходило перед тишиной
строки = текст.splitlines()
print(f"\nпоследние 25 непустых строк лога ошибок:")
for s in [x for x in строки if x.strip()][-25:]:
    print("  " + s[:170])
