# -*- coding: utf-8 -*-
"""Только чтение: сравнить запись СТАРОГО и НОВОГО ящика в конфиге.
Секреты не печатаем — только имена полей и признак «задано/пусто»."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

СЕКРЕТ = ("pass", "secret", "token", "key", "pwd")


def безопасно(k, v):
    if any(x in str(k).lower() for x in СЕКРЕТ):
        return "<задано>" if v else "<ПУСТО>"
    s = str(v)
    return s[:58] + ("…" if len(s) > 58 else "")


cfg = Config.load(r"C:\sender\sender.yaml")
я = cfg.get("mailboxes") or ()
print("=== ящиков в конфиге: %d ===" % len(я))

новые = ("food-sort.ru", "sorting-systems", "rentgen-control", "optical-sort",
         "rentgen-inspec", "inspection-syst")
стар, нов = [], []
for m in я:
    d = dict(m) if not isinstance(m, dict) else m
    адрес = str(d.get("login") or d.get("email") or d.get("address") or "")
    (нов if any(x in адрес for x in новые) else стар).append((адрес, d))

print("  старых: %d, новых: %d" % (len(стар), len(нов)))

все_поля = set()
for _, d in стар + нов:
    все_поля |= set(d.keys())

print("\n=== ЗАПОЛНЕННОСТЬ ПОЛЕЙ: старые против новых ===")
print("  %-24s %14s %14s" % ("поле", "старые", "новые"))
for п in sorted(все_поля):
    с = sum(1 for _, d in стар if d.get(п) not in (None, "", [], {}))
    н = sum(1 for _, d in нов if d.get(п) not in (None, "", [], {}))
    метка = ""
    if стар and нов:
        дс, дн = 100.0 * с / len(стар), 100.0 * н / len(нов)
        if abs(дс - дн) > 40:
            метка = "   <<< РАСХОЖДЕНИЕ"
    print("  %-24s %6d/%-6d %6d/%-6d%s" % (п, с, len(стар), н, len(нов), метка))

print("\n=== ОБРАЗЕЦ СТАРОГО ===")
if стар:
    а, d = стар[0]
    print("  %s" % а)
    for k in sorted(d):
        print("    %-20s %s" % (k, безопасно(k, d.get(k))))

print("\n=== ИТОГ: ОБРАЗЕЦ НОВОГО ===")
if нов:
    а, d = нов[0]
    print("  %s" % а)
    for k in sorted(d):
        print("    %-20s %s" % (k, безопасно(k, d.get(k))))
    print("\n  поля, которых у нового НЕТ, а у старого есть:")
    if стар:
        _, ds = стар[0]
        нет = [k for k in sorted(ds) if k not in d or d.get(k) in (None, "", [], {})]
        print("    %s" % (", ".join(нет) if нет else "таких нет"))
