# -*- coding: utf-8 -*-
"""Хвост лога vse_v_avto (только чтение)."""
import io
print("".join(io.open(r"C:\sender\_ops\vse-v-avto.log", encoding="utf-8", errors="replace").readlines()[-25:]))
