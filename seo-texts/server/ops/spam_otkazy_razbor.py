# -*- coding: utf-8 -*-
"""Отказы Яндекса «подозрение на спам» с 12.11: по кампаниям, ящикам, шагам цепочки (первое письмо / напоминание /
ответ), по часам; доля от отправленного тем же ящиком. Только чтение (адреса получателей не печатаем)."""
import sqlite3
from collections import Counter, defaultdict
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
шаги = {i: (n, ст) for i, n, ст in c.execute("SELECT id, step_index, campaign_id FROM sequence_steps")} if c.execute("SELECT name FROM sqlite_master WHERE name='sequence_steps'").fetchone() else {}
спам = c.execute("SELECT id, campaign_id, mailbox_id, sequence_step_id, COALESCE(in_reply_to,''), substr(updated_at,1,13), subject, attempt_count FROM messages "
                 "WHERE (last_error LIKE '%спам%' OR lower(last_error) LIKE '%spam%') AND updated_at>='2026-11-12'").fetchall()
print("отказов «спам» с 12.11:", len(спам))
def вид(r):
    if r[4]: return "ответ/продолжение переписки"
    ш = шаги.get(r[3])
    return "шаг %s" % (ш[0] if ш else "?")
print("по кампаниям:", Counter("#%s %s" % (r[1], (кам.get(r[1]) or "")[:30]) for r in спам).most_common())
print("по виду письма:", Counter(вид(r) for r in спам).most_common())
print("по часам (UTC):", sorted(Counter(r[5] for r in спам).items()))
отпр = Counter(mb for (mb,) in c.execute("SELECT mailbox_id FROM messages WHERE status='sent' AND sent_at>='2026-11-12'"))
пп = Counter(r[2] for r in спам)
print("по ящикам (отказов / отправлено сегодня):")
for mb, n in пп.most_common(): print("   %-45s %d / %d" % (mb, n, отпр.get(mb, 0)))
print("темы отказанных:", Counter((r[6] or "")[:50] for r in спам).most_common(8))
print("всего отправлено сегодня:", sum(отпр.values()))
шаг_сег = Counter()
for sid, irt in c.execute("SELECT sequence_step_id, COALESCE(in_reply_to,'') FROM messages WHERE status='sent' AND sent_at>='2026-11-12'"):
    шаг_сег["ответ" if irt else "шаг %s" % (шаги.get(sid, ("?",))[0])] += 1
print("отправлено сегодня по шагам:", шаг_сег.most_common())
