# -*- coding: utf-8 -*-
"""Адреса, которые нам дали в ответах (перенаправления, «пишите на …»), и ушло ли
на них письмо. Источник — тексты лидов (leads.need) и событий reply. Только чтение."""
import json, re, sqlite3
from collections import defaultdict
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
НАШИ = re.compile(r"(?i)(compressor-|kompressor-|inspection|rentgen|sort|prokompressor|meyer|rusprom|mailer-daemon|noreply|no-reply|yandex\.ru$|support@)")
АДР = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# кому уже писали (любое письмо, кроме снятых) и как
писали = defaultdict(set)
for em, st in c.execute("SELECT lower(r.email), m.status FROM messages m JOIN recipients r ON r.id=m.recipient_id"):
    писали[em].add(st)
выдали = {}
for r in c.execute("SELECT id, email, company_name, need, status FROM leads"):
    сам = str(r["email"] or "").lower()
    for a in set(x.lower().rstrip(".") for x in АДР.findall(str(r["need"] or ""))):
        if a == сам or НАШИ.search(a.split("@")[-1]) or НАШИ.search(a):
            continue
        выдали.setdefault(a, (r["id"], r["company_name"], сам, r["status"]))
итог = defaultdict(list)
for a, (lid, name, от, st) in выдали.items():
    s = писали.get(a, set())
    if "sent" in s: k = "отправлено"
    elif s & {"pending_review", "approved", "scheduled", "sending"}: k = "в очереди"
    elif s: k = "было, но не ушло: " + ",".join(sorted(s))
    else: k = "НЕ ПИСАЛИ"
    итог[k].append((lid, name, от, a, st))
for k in sorted(итог, key=lambda x: x != "НЕ ПИСАЛИ"):
    print("\n== %s: %d" % (k, len(итог[k])))
    if k != "отправлено":
        for x in итог[k]: print("  лид #%s %s | ответил %s | дал %s | статус лида %s" % x)
import io as _io
with _io.open(r"C:\sender\_ops\kontakty-iz-otvetov.tsv", "w", encoding="utf-8") as _f:
    for k, v in итог.items():
        for x in v: _f.write("\t".join(map(str, (k,) + x)) + "\n")
print("\nСВОД:", {k: len(v) for k, v in итог.items()})
