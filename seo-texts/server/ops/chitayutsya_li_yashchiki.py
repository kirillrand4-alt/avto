# -*- coding: utf-8 -*-
"""Читаются ли входящие по ящикам: ошибки IMAP и когда последний раз брали почту."""
import io, os, re, sys, time
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

п = r"C:\sender\logs\inbox_poll.log"
if os.path.exists(п):
    р = os.path.getsize(п)
    with io.open(п, "rb") as f:
        f.seek(max(0, р - 120000))
        т = f.read().decode("utf-8", errors="replace")
    строки = [с for с in т.splitlines() if с.strip()]
    print("лог входящих: %.1f МБ, изменён %s"
          % (р / 1048576.0, time.strftime("%m-%d %H:%M",
                                          time.localtime(os.path.getmtime(п)))))
    ошибки = Counter()
    ящики = Counter()
    for с in строки:
        if re.search(r"(?i)authenticationfailed|invalid credentials|imap is disabled", с):
            м = re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+", с, re.I)
            ящики[м.group(0).lower() if м else "ящик не назван"] += 1
        if re.search(r"(?i)error|ошибк|traceback|fail", с):
            ошибки[re.sub(r"\d", "N", с)[:80]] += 1
    print("")
    print("--- ящики с отказом входа (IMAP) ---")
    for к, в in ящики.most_common(12):
        print("   %-44s %5d" % (к[:44], в))
    print("")
    print("--- прочие ошибки в логе (топ-6) ---")
    for к, в in ошибки.most_common(6):
        print("   %5d  %s" % (в, к))
    print("")
    print("--- последние строки лога ---")
    for с in строки[-8:]:
        print("   " + с[:150])
else:
    print("лога входящих нет: %s" % п)

# сколько лидов вообще заводилось по дням
with store._lock:
    по_дням = Counter()
    for р2 in store._conn.execute(
            "SELECT substr(created_at,1,10) d, COUNT(*) n FROM leads "
            " WHERE created_at >= datetime('now','-14 days') GROUP BY 1"):
        по_дням[str(р2["d"])] = int(р2["n"])
print("")
print("=" * 74)
print("=== ЛИДЫ ПО ДНЯМ (14 дней) ===")
for к in sorted(по_дням):
    print("   %s  %4d" % (к, по_дням[к]))
