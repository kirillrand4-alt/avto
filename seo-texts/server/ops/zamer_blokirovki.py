# -*- coding: utf-8 -*-
"""Диагностика: ждёт ли панель запись в sqlite из-за параллельных писателей
(генерация, проба). Ничего не пишет: BEGIN IMMEDIATE сразу ROLLBACK — ровно то
ожидание, которое платит recover_stale_reviews() на каждом показе очереди.
Плюс отклик живой службы на запрос без токена (401) — нагрузка без обхода
авторизации. Аргумент: число проб (по умолчанию 40)."""
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.request

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
c = sqlite3.connect(r"C:\sender\sender.db", isolation_level=None, timeout=10)
c.execute("PRAGMA busy_timeout=5000")
print("journal_mode:", c.execute("PRAGMA journal_mode").fetchone()[0],
      "| busy_timeout панели: 5000 мс (Store.__init__)")
ждём, сбои = [], 0
for i in range(N):
    t0 = time.perf_counter()
    try:
        c.execute("BEGIN IMMEDIATE")
        dt = (time.perf_counter() - t0) * 1000
        c.execute("ROLLBACK")
        ждём.append(dt)
    except sqlite3.OperationalError as e:
        сбои += 1
        ждём.append((time.perf_counter() - t0) * 1000)
        print("  сбой:", e)
    time.sleep(0.5)
ждём.sort()
print(f"BEGIN IMMEDIATE (захват записи), {N} проб раз в 0,5 с: медиана "
      f"{statistics.median(ждём):.0f} мс, p90 {ждём[int(len(ждём)*0.9)-1]:.0f} мс, "
      f"макс {ждём[-1]:.0f} мс, >1 с: {sum(1 for x in ждём if x > 1000)}, "
      f"сбоев 'locked': {сбои}")
t0 = time.perf_counter()
c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'").fetchone()
print(f"чтение (без захвата записи): {(time.perf_counter()-t0)*1000:.1f} мс")

отк = []
for i in range(15):
    t0 = time.perf_counter()
    try:
        urllib.request.urlopen("http://127.0.0.1:8091/api/confirm/counts", timeout=30)
    except urllib.error.HTTPError as e:
        код = e.code
    except Exception as e:  # noqa: BLE001
        код = type(e).__name__
    else:
        код = 200
    отк.append((time.perf_counter() - t0) * 1000)
    time.sleep(0.3)
отк.sort()
print(f"живая служба, /api/confirm/counts без токена (код {код}): медиана "
      f"{statistics.median(отк):.0f} мс, макс {отк[-1]:.0f} мс")
t0 = time.perf_counter()
urllib.request.urlopen("http://127.0.0.1:8091/", timeout=30).read()
print(f"живая служба, index.html: {(time.perf_counter()-t0)*1000:.0f} мс")
print("=== ГОТОВО ===")
