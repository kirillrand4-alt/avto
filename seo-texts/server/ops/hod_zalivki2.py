# -*- coding: utf-8 -*-
"""Сколько уже залито агро-компаний: получателей и строк обогащения."""
import glob, io, os, sqlite3, sys
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
n = c.execute("SELECT COUNT(*) FROM recipients WHERE source='чеко-агро-2026'").fetchone()[0]
c.close()
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
инн = {r[0] for r in e.execute(
    "SELECT inn FROM requisites WHERE src='checko-sbor-agro'")}
есть = 0
for (и,) in e.execute("SELECT inn FROM companies"):
    if и in инн:
        есть += 1
e.close()
логи = sorted(glob.glob(r"C:\sender\_ops\zalit_agro_v_bazu-*.log"))
хвост = ""
if логи:
    т = io.open(логи[-1], encoding="utf-8", errors="replace").read()
    хвост = т[-700:]
ош = sorted(glob.glob(r"C:\sender\_ops\zalit_agro_v_bazu-*.err"))
ошх = ""
if ош:
    ошх = io.open(ош[-1], encoding="utf-8", errors="replace").read()[-700:]
print("=" * 70)
print("=== ХОД ЗАЛИВКИ АГРО ===")
print("получателей source='чеко-агро-2026': %d" % n)
print("агро-ИНН уже в enrich.companies:     %d" % есть)
print("лог: %s" % (логи[-1] if логи else "нет"))
print(хвост)
if ошх.strip():
    print("--- ошибки ---")
    print(ошх)
