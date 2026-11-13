# -*- coding: utf-8 -*-
"""Хвост лога газовой генерации и ход (только чтение)."""
import io, os
print("".join(io.open(r"C:\sender\_ops\gaz-kc.log", encoding="utf-8", errors="replace").readlines()[-12:]))
п = r"C:\sender\_ops\gaz-kc-hod.json"
if os.path.exists(п): print(io.open(п, encoding="utf-8").read()[:800])
