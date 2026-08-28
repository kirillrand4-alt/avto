# -*- coding: utf-8 -*-
"""Корпоративный сервер получателя против публичного: отбивки и ответы.

Срез, где данных хватает: в обеих группах тысячи писем, а не десятки, — в
отличие от дневных долей, где всё тонет в шуме.
"""
import math
import sqlite3
import sys
import time
from collections import defaultdict

БАЗА = r"C:\sender\sender.db"
ОКНО = (int(sys.argv[1]) if len(sys.argv) > 1 else 24) * 3600
ПУБЛИЧНЫЕ = ("yandex", "mail.ru", "mxs.mail", "google", "gmail", "outlook",
             "microsoft", "protection.outlook", "rambler", "yandex.net")


def _сек(ts):
    т = str(ts or "")[:19].replace("T", " ")
    try:
        return time.mktime(time.strptime(т, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0.0


def уилсон(k, n, z=1.96):
    if not n:
        return 0.0, 0.0, 0.0
    p = k / n
    зн = 1 + z * z / n
    ц = (p + z * z / (2 * n)) / зн
    пол = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / зн
    return p, max(0.0, ц - пол), min(1.0, ц + пол)


def две(k1, n1, k2, n2):
    if not n1 or not n2:
        return 0.0, 0.0, 1.0
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    зн = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if not зн:
        return p1 - p2, 0.0, 1.0
    z = (p1 - p2) / зн
    return p1 - p2, z, math.erfc(abs(z) / math.sqrt(2))


c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
mx = {}
for r in c.execute("SELECT LOWER(email) e, LOWER(COALESCE(mx,'')) m FROM addr_probe"):
    mx[r["e"]] = r["m"]
письма = [(r["recipient_id"], str(r["sent_at"]), str(r["email"] or "").lower())
          for r in c.execute(
              "SELECT m.recipient_id, m.sent_at, r.email FROM messages m "
              "  JOIN recipients r ON r.id=m.recipient_id "
              " WHERE m.sent_at IS NOT NULL AND m.status='sent'")]
события = defaultdict(list)
for r in c.execute("SELECT recipient_id, event_type, event_ts FROM events "
                   " WHERE event_type IN ('reply','bounce') "
                   "   AND recipient_id IS NOT NULL"):
    события[(r["recipient_id"], r["event_type"])].append(_сек(r["event_ts"]))
c.close()

группы = defaultdict(lambda: {"n": 0, "reply": 0, "bounce": 0})
сейчас = time.time()
без_mx = 0
for rid, когда, почта in письма:
    т0 = _сек(когда)
    if сейчас - т0 < ОКНО:
        continue                       # письмо ещё не созрело
    хост = mx.get(почта)
    if хост is None:
        без_mx += 1
        группа = "нет данных по MX"
    elif not хост:
        группа = "MX не определился"
    elif any(п in хост for п in ПУБЛИЧНЫЕ):
        группа = "публичный почтовик"
    else:
        группа = "свой корпоративный сервер"
    г = группы[группа]
    г["n"] += 1
    for вид in ("reply", "bounce"):
        for т in события.get((rid, вид), ()):
            if т0 <= т <= т0 + ОКНО:
                г[вид] += 1
                break

print("окно ожидания: %d ч; писем без записи о MX: %d" % (ОКНО // 3600, без_mx))
print()
print("%-28s %7s %7s %-20s %7s %-20s"
      % ("сервер получателя", "писем", "отв.", "доля ответов",
         "отб.", "доля отбивок"))
for г in sorted(группы, key=lambda x: -группы[x]["n"]):
    з = группы[г]
    p, lo, hi = уилсон(з["reply"], з["n"])
    bp, blo, bhi = уилсон(з["bounce"], з["n"])
    print("%-28s %7d %7d %5.2f%% [%.2f..%.2f] %7d %5.2f%% [%.2f..%.2f]"
          % (г, з["n"], з["reply"], 100 * p, 100 * lo, 100 * hi,
             з["bounce"], 100 * bp, 100 * blo, 100 * bhi))

к = группы.get("свой корпоративный сервер", {"n": 0, "reply": 0, "bounce": 0})
п = группы.get("публичный почтовик", {"n": 0, "reply": 0, "bounce": 0})
print()
print("=" * 72)
if к["n"] and п["n"]:
    d, z, pz = две(к["bounce"], к["n"], п["bounce"], п["n"])
    print("ОТБИВКИ: корпораты %.2f%% против публичных %.2f%% — разница %.2f п.п., "
          "p = %.4f" % (100 * к["bounce"] / к["n"], 100 * п["bounce"] / п["n"],
                        100 * d, pz))
    print("   %s" % ("разница РЕАЛЬНА" if pz < 0.05 else "не отличимо от шума"))
    d, z, pz = две(к["reply"], к["n"], п["reply"], п["n"])
    print("ОТВЕТЫ:  корпораты %.2f%% против публичных %.2f%% — разница %.2f п.п., "
          "p = %.4f" % (100 * к["reply"] / к["n"], 100 * п["reply"] / п["n"],
                        100 * d, pz))
    print("   %s" % ("разница РЕАЛЬНА" if pz < 0.05 else "не отличимо от шума"))
else:
    print("одна из групп пуста — сравнивать нечего")
