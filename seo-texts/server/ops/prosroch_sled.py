import glob, io, os, sqlite3
ids = ["19286", "21338", "21953", "19572", "19598"]
emails = ["info@volcov.ru", "icewell.ru", "tmk.meat@gmail.com", "garskoe@bk.ru", "koporsky-tea.ru"]
c = sqlite3.connect(r"C:\sender\sender.db")
for e in emails:
    print(e, "send_log:", c.execute("SELECT ts, outcome FROM send_log WHERE email LIKE ? ORDER BY ts DESC LIMIT 2", ("%" + e + "%",)).fetchall(),
          "| suppression:", c.execute("SELECT COUNT(*) FROM suppression WHERE value LIKE ?", ("%" + e.split("@")[-1] + "%",)).fetchone() if "suppression" in [r[0] for r in c.execute("SELECT name FROM sqlite_master")] else "-")
for ф in sorted(glob.glob(r"C:\sender\logs\*.log") + glob.glob(r"C:\sender\*.log"), key=os.path.getmtime)[-6:]:
    т = io.open(ф, encoding="utf-8", errors="replace").read()[-3000000:].splitlines()
    х = [s for s in т if any(("msg=" + i in s or "id=" + i in s or " " + i + " " in s or "#" + i in s) for i in ids)]
    if х: print("==", ф); print("\n".join(s[:220] for s in х[-8:]))
