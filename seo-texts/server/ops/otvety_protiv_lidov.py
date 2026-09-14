# -*- coding: utf-8 -*-
"""Ответы против лидов по дням: где теряются входящие."""
import io, os, re, sys, time
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("event_ts", "created_at", "ts") if c in кол), None)
    тп = next((c for c in ("event_type", "type") if c in кол), None)
    отв = Counter()
    for р in store._conn.execute(
            "SELECT substr(%s,1,10) d, COUNT(*) n FROM events "
            " WHERE %s IN ('reply','reply_auto') AND %s >= datetime('now','-16 days')"
            " GROUP BY 1" % (вр, тп, вр)):
        отв[str(р["d"])] = int(р["n"])
    лиды = Counter()
    for р in store._conn.execute(
            "SELECT substr(created_at,1,10) d, COUNT(*) n FROM leads "
            " WHERE created_at >= datetime('now','-16 days') GROUP BY 1"):
        лиды[str(р["d"])] = int(р["n"])
    ушло = Counter()
    for р in store._conn.execute(
            "SELECT substr(sent_at,1,10) d, COUNT(*) n FROM messages "
            " WHERE status='sent' AND sent_at >= datetime('now','-16 days')"
            " GROUP BY 1"):
        ушло[str(р["d"])] = int(р["n"])

print("   %-12s %8s %9s %7s" % ("день", "ушло", "ответов", "лидов"))
for д in sorted(set(list(отв) + list(лиды) + list(ушло))):
    print("   %-12s %8d %9d %7d"
          % (д, ушло.get(д, 0), отв.get(д, 0), лиды.get(д, 0)))

п = r"C:\sender\logs\inbox_poll.log"
дни = Counter()
if os.path.exists(п):
    р = os.path.getsize(п)
    with io.open(п, "rb") as f:
        f.seek(max(0, р - 3000000))
        т = f.read().decode("utf-8", errors="replace")
    for с in т.splitlines():
        м = re.match(r"\[?(\d{4}-\d{2}-\d{2})", с.strip())
        if м:
            дни[м.group(1)] += 1
print("")
print("--- строк в логе входящих по дням ---")
for д in sorted(дни)[-14:]:
    print("   %s  %6d" % (д, дни[д]))
print("")
print("=" * 74)
print("=== ОТВЕТЫ ПРОТИВ ЛИДОВ ===")
