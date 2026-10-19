import json, re, sqlite3, time
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db")
от = time.strftime("%Y-%m-%d", time.gmtime())
проба = {str(e).lower(): v for e, v in c.execute("SELECT email, verdict FROM addr_probe")}
отпр = Counter(); сч = Counter(); по_ящ = Counter(); прим = {}
for (mb,) in c.execute("SELECT mailbox_id FROM messages WHERE status='sent' AND sent_at>=?", (от,)):
    отпр["КЦ" if "ompressor" in str(mb) else "Meyer"] += 1
for mb, dj, em, ts, et in c.execute("SELECT e.mailbox_id, e.detail_json, r.email, e.event_ts, e.event_type FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('bounce','failed') AND e.event_ts>=?", (от,)):
    d = json.loads(dj or "{}"); dsn = d.get("dsn") or {}
    диаг = str(dsn.get("diagnostic") or d.get("error") or "")
    к = ("спам" if re.search(r"(?i)spam|спам|5\.7\.1", диаг) else "нет ящика" if re.search(r"(?i)no such|unknown|not exist|не существ|5\.1\.1|mailbox unavailable|недоступ", диаг)
         else "переполнен" if re.search(r"(?i)quota|full|переполн|5\.2\.2", диаг) else "политика/релей" if re.search(r"(?i)relay|policy|not permitted|blocked|reject", диаг) else "прочее")
    напр = "КЦ" if "ompressor" in str(mb) else "Meyer"
    сч[(напр, к, проба.get(str(em or "").lower(), "не проверен"))] += 1; по_ящ[(напр, str(mb))] += 1
    прим.setdefault((напр, к), (em, диаг[:150]))
f = c.execute("SELECT m.mailbox_id, m.last_error FROM messages m WHERE m.status='failed' AND m.updated_at>=?", (от,)).fetchall()
print("отправлено сегодня:", dict(отпр))
print("отбивок (события):", sum(сч.values()))
for k, v in sorted(сч.items(), key=lambda x: -x[1]): print("  %3d %s" % (v, k))
print("примеры:"); [print("  ", k, v) for k, v in прим.items()]
print("ящики с отбивками:", по_ящ.most_common(8))
print("сообщений failed сегодня:", len(f), Counter(re.sub(r"\d{6,}.*", "", str(e or ""))[:70] for _, e in f).most_common(5))
