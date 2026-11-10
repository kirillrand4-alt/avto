# -*- coding: utf-8 -*-
"""Есть ли переменные паролей ящиков из конфига в C:\\sender\\panel.env. Печатает ТОЛЬКО имена и
есть/нет, значения не читаются наружу. Плюс хвост лога службы пикселя. Только чтение."""
import os, re
имена = set()
for ln in open(r"C:\sender\panel.env", encoding="utf-8-sig").read().splitlines():
    ln = ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
        k, _, v = ln.partition("=")
        if v.strip(): имена.add(k.strip())
нужны = set(re.findall(r"password_env:\s*['\"]?([A-Z0-9_]+)", open(r"C:\sender\sender.yaml", encoding="utf-8").read()))
print("паролей ящиков в конфиге:", len(нужны), "| нет в panel.env:", sorted(нужны - имена) or "все есть")
for p in (r"C:\sender\_ops\pixel.err.log", r"C:\sender\_ops\pixel.out.log"):
    if os.path.exists(p):
        т = open(p, encoding="utf-8", errors="replace").read()
        print("==", p, "размер", len(т)); print(т[-600:])
