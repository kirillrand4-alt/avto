import json, re, sqlite3, time
from collections import Counter, defaultdict
c = sqlite3.connect(r"C:\sender\sender.db")
от = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 7 * 86400))
def напр(mb): return "КЦ" if "ompressor" in str(mb) else "Meyer"
отпр = Counter()
for d, mb in c.execute("SELECT substr(sent_at,1,10), mailbox_id FROM messages WHERE status='sent' AND sent_at>=?", (от,)):
    отпр[(d, напр(mb))] += 1
отб = Counter(); вид = defaultdict(Counter); ip = Counter()
for d, mb, dj in c.execute("SELECT substr(event_ts,1,10), mailbox_id, detail_json FROM events WHERE event_type='bounce' AND event_ts>=?", (от,)):
    x = json.loads(dj or "{}"); диаг = str((x.get("dsn") or {}).get("diagnostic") or "")
    к = ("спам/IP" if re.search(r"(?i)spam|спам|5\.7\.1|IP you", диаг) else "нет ящика" if re.search(r"(?i)no such|unknown|not exist|не существ|5\.1\.1|5\.1\.10|unavailable|недоступ", диаг)
         else "переполнен" if re.search(r"(?i)quota|full|переполн|5\.2\.2", диаг) else "политика/релей" if re.search(r"(?i)relay|policy|not permitted|blocked|reject", диаг) else "прочее")
    н = напр(mb); отб[(d, н)] += 1; вид[н][к] += 1
    for m in re.findall(r"\[(\d+\.\d+\.\d+\.\d+)\]", диаг): ip[m] += 1
print("день       | КЦ отпр/отб/% | Meyer отпр/отб/%")
for d in sorted({k[0] for k in отпр} | {k[0] for k in отб}):
    def s(n): o, b = отпр[(d, n)], отб[(d, n)]; return "%4d/%3d/%4.1f%%" % (o, b, 100 * b / o if o else 0)
    print(d, "|", s("КЦ"), "|", s("Meyer"))
for n in ("КЦ", "Meyer"):
    o = sum(v for k, v in отпр.items() if k[1] == n); b = sum(v for k, v in отб.items() if k[1] == n)
    print("\n%s за неделю: отправлено %d, отбивок %d (%.1f%%)" % (n, o, b, 100 * b / o if o else 0), dict(вид[n].most_common()))
print("\nIP в отказах:", ip.most_common(5))
