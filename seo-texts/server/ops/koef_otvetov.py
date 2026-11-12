# -*- coding: utf-8 -*-
"""Коэффициент ответов за 30 дней: по дням отправки и по кампаниям (группам), КЦ/Meyer. Когорты честные: ответ
считается, если пришёл в течение 2 суток после письма (письма последних 2 суток досчитываются как есть — помечены).
Ответ = событие reply (без автоответов reply_auto), по паре получатель+кампания. Только чтение."""
import json, re, sqlite3
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
сейчас = datetime.now(timezone.utc).replace(tzinfo=None)
С = (сейчас - timedelta(days=30)).isoformat()
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
отв = defaultdict(list)   # (rid, camp) -> [ts, kind]
for rid, camp, ts, dj in c.execute("SELECT recipient_id, campaign_id, event_ts, detail_json FROM events WHERE event_type='reply' AND event_ts>=?", (С,)):
    try: k = json.loads(dj or "{}").get("reply_kind") or ""
    except ValueError: k = ""
    отв[(rid, camp)].append((str(ts)[:19], k))
def пар(t): return datetime.fromisoformat(str(t)[:19])
окна = defaultdict(lambda: [0, 0, 0])   # (напр, день) -> писем, ответ ≤6ч, ответ ≤24ч
дни = defaultdict(lambda: [0, 0, 0, 0]); гр = defaultdict(lambda: [0, 0, 0, 0]); напр_д = defaultdict(lambda: [0, 0, 0, 0])
for rid, camp, mb, sent in c.execute("SELECT recipient_id, campaign_id, mailbox_id, sent_at FROM messages WHERE status='sent' AND sent_at>=? AND COALESCE(in_reply_to,'')=''", (С,)):
    д = str(sent)[:10]; т = пар(sent)
    н = "Meyer" if re.search(r"sort|rentgen|inspection|optic", mb or "") else "КЦ"
    о48 = [x for x in отв.get((rid, camp), []) if т <= пар(x[0]) <= т + timedelta(hours=48)]
    овсе = [x for x in отв.get((rid, camp), []) if пар(x[0]) >= т]
    окна[(н, д)][0] += 1
    окна[(н, д)][1] += any(т <= пар(x[0]) <= т + timedelta(hours=6) for x in овсе)
    окна[(н, д)][2] += any(т <= пар(x[0]) <= т + timedelta(hours=24) for x in овсе)
    отказ = any(x[1] == "not_interested" for x in овсе)
    for ключ, хр in ((д, дни), ((camp, н), гр), ((н, д), напр_д)):
        хр[ключ][0] += 1; хр[ключ][1] += bool(о48); хр[ключ][2] += bool(овсе); хр[ключ][3] += отказ
print("сейчас UTC:", сейчас.isoformat()[:16], "| ответ за 48ч / ответ всего / из них отказ")
print("\nПО ДНЯМ (все кампании):")
for д in sorted(дни):
    п, о, в, к = дни[д]; свеж = " (<48ч, неполн.)" if д >= (сейчас - timedelta(days=2)).isoformat()[:10] else ""
    print("  %s писем %5d  ответ48ч %4d (%.1f%%)  всего %4d (%.1f%%)  отказов %3d%s" % (д, п, о, 100 * о / max(1, п), в, 100 * в / max(1, п), к, свеж))
print("\nПО НАПРАВЛЕНИЯМ И ДНЯМ:")
for (н, д) in sorted(напр_д):
    п, о, в, к = напр_д[(н, д)]
    if п >= 20: print("  %-6s %s писем %5d  ответ48ч %.1f%%  всего %.1f%%" % (н, д, п, 100 * о / п, 100 * в / п))
print("\nПО КАМПАНИЯМ (30 дней):")
for (камп, н), (п, о, в, к) in sorted(гр.items(), key=lambda x: -x[1][0]):
    if п >= 30: print("  #%-3s %-6s %-40s писем %5d  ответ48ч %4d (%.1f%%)  всего %4d (%.1f%%)  отказов %d" % (камп, н, (кам.get(камп) or "")[:40], п, о, 100 * о / п, в, 100 * в / п, к))

print("\nРАВНЫЕ ОКНА (честно сравнить последние дни): ответ ≤6ч / ≤24ч от письма")
for (н, д) in sorted(окна):
    п, а, б = окна[(н, д)]
    if п >= 100 and д >= "2026-10-26": print("  %-6s %s писем %5d  ≤6ч %.2f%%  ≤24ч %.2f%%%s" % (н, д, п, 100 * а / п, 100 * б / п, "  (24ч ещё не прошли)" if д >= (сейчас - timedelta(days=1)).isoformat()[:10] else ""))
