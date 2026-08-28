# -*- coding: utf-8 -*-
import io, json, sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
партии = {}
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                партии[int(d["review"])] = п
    except FileNotFoundError:
        pass
вердикт = {}
for ф in (r"C:\sender\_ops\sud-vtoryh.jsonl", r"C:\sender\_ops\sud-vtoryh-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            вердикт[int(d["id"])] = str(d.get("verdikt") or "").replace(
                "o", "о").replace("p", "р")
    except FileNotFoundError:
        pass
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партии))
строки = c.execute("SELECT id, inn, email, panel_json, recipient_id, message_id "
                   "  FROM confirm_reviews WHERE id IN (%s) AND status='pending'" % зн,
                   list(партии)).fetchall()
сч = Counter()
без = []
for r in строки:
    try:
        п = json.loads(r["panel_json"] or "{}") or {}
    except Exception:
        п = {}
    держ = bool((п.get("actions") or {}).get("confirm_hold"))
    коды = {(f.get("code") if isinstance(f, dict) else str(f))
            for f in (п.get("stop_flags") or [])}
    сч["confirm_hold=%s" % держ] += 1
    if держ:
        сч["   держит: " + ("+".join(sorted(коды)) or "без кода")] += 1
    else:
        без.append((int(r["id"]), r["email"], вердикт.get(int(r["id"]), "не судили"),
                    "+".join(sorted(коды)) or "нет флагов",
                    r["message_id"], r["recipient_id"]))
print("в pending: %d" % len(строки))
for к, n in сч.most_common():
    print("   %-46s %4d" % (к, n))
print("")
print("=== pending БЕЗ confirm_hold: %d ===" % len(без))
for i, e, в, к, mid, rid in без[:14]:
    print("   rev %-6s %-28s судья:%-12s флаги:%-22s msg=%s rid=%s"
          % (i, str(e)[:28], в, к[:22], mid, rid))
c.close()
