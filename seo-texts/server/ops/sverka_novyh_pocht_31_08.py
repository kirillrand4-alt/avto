# -*- coding: utf-8 -*-
"""Только чтение: чем получатели, заведённые вчера, отличаются от прежних."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ПОЛУЧАТЕЛИ ПО ДАТЕ СОЗДАНИЯ (последние 12 дней с записями) ===")
дни = list(s.execute(
    "SELECT substr(created_at,1,10) д, COUNT(*) n FROM recipients"
    " GROUP BY д ORDER BY д DESC LIMIT 12"))
for р in дни:
    print("  %s  %6d" % (р["д"], р["n"]))

цель = [р["д"] for р in дни][:6]
print("\n=== ЗАПОЛНЕННОСТЬ ПОЛЕЙ ПО ДНЯМ ===")
print("  %-12s %7s %8s %9s %9s %8s %8s %9s"
      % ("день", "всего", "mx пуст", "valid пуст", "extra пуст", "роль", "домен", "сегмент"))
for д in цель:
    р = s.execute(
        "SELECT COUNT(*) n,"
        " SUM(CASE WHEN mx_provider IS NULL OR mx_provider='' THEN 1 ELSE 0 END) mx,"
        " SUM(CASE WHEN valid_status IS NULL OR valid_status='' THEN 1 ELSE 0 END) vs,"
        " SUM(CASE WHEN extra_json IS NULL OR extra_json='' THEN 1 ELSE 0 END) ex,"
        " SUM(CASE WHEN role_based=1 THEN 1 ELSE 0 END) rb,"
        " SUM(CASE WHEN domain IS NULL OR domain='' THEN 1 ELSE 0 END) dm,"
        " SUM(CASE WHEN segment IS NULL OR segment='' THEN 1 ELSE 0 END) sg"
        " FROM recipients WHERE substr(created_at,1,10)=?", (д,)).fetchone()
    n = р["n"] or 1
    print("  %-12s %7d %7.0f%% %8.0f%% %8.0f%% %7.0f%% %7.0f%% %8.0f%%"
          % (д, р["n"], 100.0 * (р["mx"] or 0) / n, 100.0 * (р["vs"] or 0) / n,
             100.0 * (р["ex"] or 0) / n, 100.0 * (р["rb"] or 0) / n,
             100.0 * (р["dm"] or 0) / n, 100.0 * (р["sg"] or 0) / n))

print("\n=== ИСТОЧНИК (source) ПО ДНЯМ ===")
for д in цель[:4]:
    ист = Counter(str(р["source"]) for р in s.execute(
        "SELECT source FROM recipients WHERE substr(created_at,1,10)=?", (д,)))
    print("  %s: %s" % (д, dict(ист.most_common(5))))

print("\n=== СЕГМЕНТЫ ПО ДНЯМ ===")
for д in цель[:4]:
    сег = Counter(str(р["segment"]) for р in s.execute(
        "SELECT segment FROM recipients WHERE substr(created_at,1,10)=?", (д,)))
    print("  %s: %s" % (д, dict(сег.most_common(5))))

print("\n=== ЕСТЬ ЛИ ПРОБА АДРЕСА (addr_probe) ===")
for д in цель[:5]:
    р = s.execute(
        "SELECT COUNT(*) n, SUM(CASE WHEN ap.email IS NULL THEN 1 ELSE 0 END) нет"
        " FROM recipients r LEFT JOIN addr_probe ap ON lower(ap.email)=lower(r.email)"
        " WHERE substr(r.created_at,1,10)=?", (д,)).fetchone()
    n = р["n"] or 1
    print("  %s: без пробы %d из %d (%.0f%%)"
          % (д, р["нет"] or 0, р["n"], 100.0 * (р["нет"] or 0) / n))

print("\n=== ИТОГ ===")
print("  сравни строку вчерашнего дня с предыдущими: где проценты скачут,")
print("  там и разница в способе заведения")
