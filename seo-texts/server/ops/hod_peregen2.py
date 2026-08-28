# -*- coding: utf-8 -*-
import glob, io, json, os, sqlite3, time
л = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"), key=os.path.getmtime)
for п in л[-2:]:
    print("=== %s (%.1f мин назад) ===" % (os.path.basename(п),
                                           (time.time()-os.path.getmtime(п))/60))
    ст = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for с in ст[:3]:
        print("   " + с[:140])
    print("   ...")
    for с in ст[-8:]:
        print("   " + с[:140])
    о = os.path.splitext(п)[0] + ".err"
    if os.path.exists(о) and os.path.getsize(о):
        print("   --- ошибки ---")
        for с in io.open(о, encoding="utf-8", errors="replace").read().splitlines()[-5:]:
            print("      " + с[:140])
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
n = c.execute("SELECT COUNT(*) FROM recipients "
              " WHERE extra_json LIKE '%peregen2%'").fetchone()[0]
print("")
print("в группе peregen2 получателей: %d" % n)
for r in c.execute(
        "SELECT cr.status, COUNT(*) n FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE r.extra_json LIKE '%peregen2%' AND cr.created_at >= date('now') "
        " GROUP BY 1"):
    print("   карточки сегодня: %-12s %4d" % (r["status"], r["n"]))
c.close()
