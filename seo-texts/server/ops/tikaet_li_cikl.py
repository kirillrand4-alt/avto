# -*- coding: utf-8 -*-
"""Тикает ли цикл автоотправки: ищем его следы в обоих логах панели."""
import io
import os

for путь in (r"C:\sender\_ops\panel_out.log", r"C:\sender\_ops\panel_err.log"):
    р = os.path.getsize(путь)
    with io.open(путь, "rb") as f:
        f.seek(max(0, р - 3_000_000))
        текст = f.read().decode("utf-8", "replace")
    print(f"\n=== {os.path.basename(путь)} ({р} байт, смотрю хвост "
          f"{min(р, 3_000_000)})")
    for фраза in ("auto_send", "claim_approved_due", "AutoSend",
                  "цикл запущен", "released", "within_window"):
        print(f"  {фраза!r}: {текст.count(фраза)}")
    следы = [s for s in текст.splitlines() if "auto_send" in s][-12:]
    for s in следы:
        print("   | " + s[:170])
