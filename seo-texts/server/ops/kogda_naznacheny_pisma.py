# -*- coding: utf-8 -*-
"""На КОГДА назначены оставшиеся письма — и почему расширение окна их не сдвинуло.

Окно применяется дважды: при НАЗНАЧЕНИИ слота (cadence кладёт письму
scheduled_at внутрь окна получателя) и при отправке. Расширив окно, вы
поменяли правило на будущее, но у писем, которым слот уже назначили по
старому окну, scheduled_at остался прежним — у восточных поясов это
завтрашнее утро. Поэтому «окно шире» и «письма пошли» — разные вещи.

    python zapusk_svoego_skripta.py ops/kogda_naznacheny_pisma.py
"""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)

with store._lock:
    по_статусу = store._conn.execute(
        "SELECT m.status, COUNT(*) FROM confirm_reviews c "
        "JOIN messages m ON m.id=c.message_id WHERE c.status='approved' "
        "GROUP BY m.status").fetchall()
print("готовые письма по статусу самого сообщения:")
for с, n in по_статусу:
    print(f"  {с:<14} {n}")

with store._lock:
    ряд = store._conn.execute(
        "SELECT m.scheduled_at, m.status, COALESCE(r.tz,'(пусто)') "
        "FROM confirm_reviews c JOIN messages m ON m.id=c.message_id "
        "LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='approved'").fetchall()

по_дням = Counter()
готовы_сейчас = 0
пояса_завтра = Counter()
for ts, статус, tz in ряд:
    д = str(ts or "")[:10] or "(без слота)"
    по_дням[д] += 1
    if ts and str(ts) <= сейчас.isoformat():
        готовы_сейчас += 1
    elif ts:
        пояса_завтра[tz] += 1

print(f"\nназначено на день (scheduled_at):")
for д in sorted(по_дням):
    print(f"  {д:<14} {по_дням[д]}")
print(f"\nсрок которых УЖЕ настал (можно слать прямо сейчас): {готовы_сейчас}")
print("ждут будущего слота, по поясам:")
for tz, n in пояса_завтра.most_common(12):
    print(f"  {tz:<22} {n}")

# ближайшие слоты
with store._lock:
    ближ = store._conn.execute(
        "SELECT m.scheduled_at, COUNT(*) FROM confirm_reviews c "
        "JOIN messages m ON m.id=c.message_id WHERE c.status='approved' "
        "AND m.scheduled_at>? GROUP BY substr(m.scheduled_at,1,13) "
        "ORDER BY m.scheduled_at LIMIT 12", (сейчас.isoformat(),)).fetchall()
print("\nближайшие слоты (час UTC -> писем):")
for ts, n in ближ:
    print(f"  {str(ts)[:16]}  {n}")
