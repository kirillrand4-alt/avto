# -*- coding: utf-8 -*-
"""Что реально легло в очередь по второму адресу."""
import io, json, sqlite3
почты = []
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    почты.append(json.loads(с)["email"])
print("в следе: %d" % len(почты))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(почты))
for r in c.execute(
        "SELECT id, status, email, subject, message_id, recipient_id, panel_json, body "
        "  FROM confirm_reviews WHERE email IN (%s) ORDER BY id" % зн, почты):
    п = {}
    try:
        п = json.loads(r["panel_json"] or "{}").get("vtoroy_adres") or {}
    except Exception:
        pass
    print("   rev %-6s %-9s %-28s msg=%-6s | первый: %s"
          % (r["id"], r["status"], r["email"][:28], r["message_id"],
             str(п.get("pervyy_adres"))[:26]))
r = c.execute("SELECT body, subject, email FROM confirm_reviews "
              " WHERE email=? LIMIT 1", (почты[0],)).fetchone()
print("")
print("=== ЦЕЛИКОМ первое письмо (%s) ===" % r["email"])
print("тема: %s" % r["subject"])
print(r["body"])
c.close()
