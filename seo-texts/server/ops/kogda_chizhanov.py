# -*- coding: utf-8 -*-
import io, json, sqlite3
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "incab" in str(d.get("email", "")):
                print("след партии %d: %s" % (п, d))
    except FileNotFoundError:
        pass
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT id, status, email, created_at, reason, decided_by, panel_json "
              "  FROM confirm_reviews WHERE email LIKE '%incab%' ORDER BY id").fetchall()
for x in r:
    try:
        п = json.loads(x["panel_json"] or "{}") or {}
    except Exception:
        п = {}
    в = п.get("vtoroy_adres") or {}
    print("rev %-6s %-9s %-26s создана %s" % (x["id"], x["status"],
                                              str(x["email"])[:26],
                                              str(x["created_at"])[:16]))
    if в:
        print("    партия: роль %s, первый адрес %s" % (в.get("rol"), в.get("pervyy_adres")))
c.close()
