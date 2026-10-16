import glob, io, json, sqlite3, time
from collections import Counter
рид = json.load(io.open(r"C:\sender\_ops\spisok-kc-iz-9000.json"))
c = sqlite3.connect(r"C:\sender\sender.db")
инн = {str(c.execute("SELECT inn FROM recipients WHERE id=?", (r,)).fetchone()[0]) for r in рид}
for db in (r"C:\sender\sender.db", r"C:\sender\enrich.db"):
    try:
        d = sqlite3.connect(db)
        вс = {r[0]: (r[1], r[2]) for r in d.execute("SELECT inn, verdict, ts FROM target_verdicts")}
    except Exception as e:
        continue
    сегодня = Counter(v for i, (v, ts) in вс.items() if i in инн and str(ts) >= time.strftime("%Y-%m-%d", time.gmtime()))
    всего = Counter(v for i, (v, ts) in вс.items() if i in инн)
    print(db, "| из списка 2570 судимо всего:", sum(всего.values()), dict(всего), "| сегодня:", sum(сегодня.values()), dict(сегодня))
