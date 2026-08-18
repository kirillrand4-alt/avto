# -*- coding: utf-8 -*-
"""Хвост лога панели по автоотправке: что цикл пишет прямо сейчас."""
import io
import os
import sys
from datetime import datetime, timezone

for путь in (r"C:\sender\_ops\panel_err.log", r"C:\sender\_ops\panel_out.log"):
    if not os.path.exists(путь):
        print(f"{путь}: нет файла")
        continue
    m = datetime.fromtimestamp(os.path.getmtime(путь), timezone.utc)
    р = os.path.getsize(путь)
    print(f"\n=== {путь} ({р} байт, изменён {m.strftime('%H:%M')} UTC)")
    with io.open(путь, "rb") as f:
        f.seek(max(0, р - 400_000))
        текст = f.read().decode("utf-8", "replace")
    строки = текст.splitlines()
    ключ = [s for s in строки
            if any(k in s for k in ("auto_send", "AutoSend", "цикл",
                                    "pick_mailbox", "gate", "Traceback"))]
    print(f"строк всего в хвосте: {len(строки)}, из них по теме: {len(ключ)}")
    for s in ключ[-25:]:
        print("  " + s[:170])
    print("  --- последние 8 строк файла:")
    for s in строки[-8:]:
        print("  " + s[:170])
