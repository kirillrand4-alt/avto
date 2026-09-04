# -*- coding: utf-8 -*-
"""Только чтение: что VPS уже знает про адреса партии 13."""
import datetime as dt
import inspect
import io
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")

print("=== КАК УСТРОЕНА ПРОБА (шапка probe_sync) ===")
т = io.open(r"C:\sender\sender\probe_sync.py", encoding="utf-8",
            errors="replace").read().splitlines()
for л in т[1:20]:
    print("  " + л[:100])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
почты = [str(р["email"]).lower() for р in c.execute(
    "SELECT email FROM confirm_reviews WHERE campaign_id=13")]
print("\n=== ПОКРЫТИЕ 611 АДРЕСОВ ===")
есть, вердикты, свежесть = 0, {}, []
for i in range(0, len(почты), 800):
    к = почты[i:i + 800]
    q = ",".join("?" * len(к))
    for р in c.execute("SELECT email, verdict, ts, source FROM addr_probe"
                       " WHERE LOWER(email) IN (%s)" % q, к):
        есть += 1
        вердикты[str(р["verdict"])] = вердикты.get(str(р["verdict"]), 0) + 1
        if р["ts"]:
            свежесть.append(str(р["ts"])[:10])
print("  всего адресов: %d" % len(почты))
print("  уже проверены VPS: %d" % есть)
print("  ни разу не проверялись: %d" % (len(почты) - есть))
print("\n  вердикты по проверенным:")
for в, n in sorted(вердикты.items(), key=lambda x: -x[1]):
    print("    %-16s %d" % (в, n))
if свежесть:
    свежесть.sort()
    print("\n  самая старая проверка: %s, самая свежая: %s"
          % (свежесть[0], свежесть[-1]))

print("\n=== ЧТО ИЗ ЭТОГО СНИМЕТ ПИСЬМО С ОЧЕРЕДИ ===")
import sender.addr_probe as AP  # noqa: E402
print("  снимают вердикты: %s" % (AP.СНЯТЬ_С_ОЧЕРЕДИ,))
print("  хоронят адрес:    %s" % (AP.ПОХОРОНИТЬ_АДРЕС,))
снимут = sum(n for в, n in вердикты.items() if в in AP.СНЯТЬ_С_ОЧЕРЕДИ)
print("  по нынешним вердиктам снимется: %d из %d" % (снимут, len(почты)))

print("\n=== ЖИВ ЛИ РАННЕР VPS ===")
try:
    ф = getattr(AP, "build_addr_probe", None)
    print("  addr_probe_enabled: %s"
          % __import__("sender.store", fromlist=["Store"]))
except Exception:
    pass
