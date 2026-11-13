# -*- coding: utf-8 -*-
"""Полный стек последней ошибки «podtyanut_pod_okno» и время изменения лога. Только чтение."""
import io, os, time
п = r"C:\sender\_ops\panel_err.log"; р = os.path.getsize(п)
with io.open(п, "rb") as f: f.seek(max(0, р - 8000000)); х = f.read().decode("utf-8", "replace").splitlines()
i = max(k for k, x in enumerate(х) if "podtyanut_pod_okno: выборка упала" in x)
print("лог изменён:", time.ctime(os.path.getmtime(п)), "| строка", i, "из", len(х))
print("\n".join(y[:220] for y in х[i:i + 22]))
