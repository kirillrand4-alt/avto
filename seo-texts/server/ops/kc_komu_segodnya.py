import json, sqlite3, time
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db")
от = time.strftime("%Y-%m-%d", time.gmtime())
otr, gr, okv, обр = Counter(), Counter(), Counter(), []
n = 0
for em, name, okved, ex, subj, sa in c.execute(
        "SELECT r.email, r.company_name, r.okved, r.extra_json, m.subject, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status='sent' AND m.sent_at>=? AND m.campaign_id IN (1,5,6,10,15,16) ORDER BY m.sent_at DESC", (от,)):
    n += 1; x = json.loads(ex or "{}")
    otr[x.get("otrasl") or "-"] += 1; gr[",".join(x.get("gruppy") or []) or "-"] += 1; okv[str(okved or "-")[:2]] += 1
    if len(обр) < 12: обр.append((sa[11:16], name, em, subj))
print("КЦ отправлено сегодня:", n)
print("группы:", gr.most_common(5)); print("отрасль (метка базы):", otr.most_common(8)); print("ОКВЭД:", okv.most_common(10))
for x in обр: print("  %s %s <%s> | %s" % x)
print("в очереди КЦ на сегодня:", c.execute("SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','approved') AND campaign_id IN (1,5,6,10,15,16)").fetchone()[0])
