# -*- coding: utf-8 -*-
"""Ушёл ли ответ оператора: ищем его по всем следам за последние часы.

Вопрос владельца: «оператор ответила на письмо, но нигде нету информации,
как узнать отправился ответ или нет». Ответ живёт не там же, где холодное
письмо: у него kind='reply' в очереди подтверждений и своя строка в
messages. Смотрим оба места и события отправки.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("== очередь подтверждений: ответы (kind='reply') за сутки ==")
with store._lock:
    ряды = store._conn.execute(
        "SELECT id, COALESCE(kind,''), status, COALESCE(email,''), "
        "COALESCE(created_at,''), COALESCE(updated_at,''), message_id "
        "FROM confirm_reviews WHERE COALESCE(kind,'')='reply' "
        "AND updated_at >= datetime('now','-1 day') "
        "ORDER BY updated_at DESC LIMIT 20").fetchall()
for rid, kind, st, email, соз, обн, mid in ряды:
    print(f"  #{rid}  {st:<10} {email:<34} создано {соз[:19]} "
          f"обновлено {обн[:19]} message_id={mid}")
if not ряды:
    print("  за сутки ответов в очереди нет")

print("\n== письма (messages) за 6 часов ==")
with store._lock:
    ряды2 = store._conn.execute(
        "SELECT id, status, COALESCE(subject,''), COALESCE(sent_at,''), "
        "COALESCE(created_at,''), COALESCE(in_reply_to,''), "
        "COALESCE(last_error,'') FROM messages "
        "WHERE COALESCE(created_at,'') >= datetime('now','-6 hours') "
        "OR COALESCE(sent_at,'') >= datetime('now','-6 hours') "
        "ORDER BY COALESCE(sent_at, created_at) DESC LIMIT 25").fetchall()
счёт = Counter()
for mid, st, тема, отпр, соз, отв, ошибка in ряды2:
    счёт[st] += 1
    метка = "ОТВЕТ" if отв else "     "
    print(f"  {метка} #{mid}  {st:<12} {тема[:44]:<46} "
          f"отправлено {отпр[:19] or '—'}"
          + (f"  ошибка: {ошибка[:60]}" if ошибка else ""))
print("  по статусам:", dict(счёт))

print("\n== события отправки за 6 часов ==")
with store._lock:
    ряды3 = store._conn.execute(
        "SELECT event_type, COUNT(*) FROM events "
        "WHERE created_at >= datetime('now','-6 hours') "
        "GROUP BY event_type ORDER BY 2 DESC").fetchall()
for т, n in ряды3:
    print(f"  {n:>4}  {т}")
