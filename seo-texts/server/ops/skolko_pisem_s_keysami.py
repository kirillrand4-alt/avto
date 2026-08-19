# -*- coding: utf-8 -*-
"""Сколько уже написанных писем нарушали бы новое правило про кейсы.

Правило меняет поведение будущих партий, но полезно знать цену прошлого:
если счётчик кейсов стоит в половине писем очереди, их придётся переписать,
а если в единицах — можно не трогать.
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import _ОПУБЛИКОВАННЫЕ_КЕЙСЫ as RX          # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    with store._lock:
        строки = store._conn.execute(
            "SELECT c.id, c.status, c.body FROM confirm_reviews c "
            "WHERE c.campaign_id=? AND c.body IS NOT NULL", (камп,)).fetchall()
    счёт = Counter()
    по_статусу = Counter()
    примеры = []
    for r in строки:
        тело = re.sub(r"<[^>]+>", " ", str(r["body"] or ""))
        м = RX.search(тело)
        счёт[bool(м)] += 1
        if not м:
            continue
        по_статусу[str(r["status"])] += 1
        if len(примеры) < 4:
            примеры.append((r["id"], r["status"], м.group(0)[:60]))
    всего = sum(счёт.values())
    if not всего:
        continue
    print(f"\n== {имя} (кампания {камп}): писем {всего} ==")
    print(f"  с упоминанием кейсов: {счёт[True]} "
          f"({счёт[True]/всего*100:.1f}%)")
    print("  из них по статусу карточки:")
    for с, n in по_статусу.most_common():
        print(f"    {с:<12} {n}")
    # РЕАЛЬНАЯ ОЧЕРЕДЬ - это не «approved», а одобренное письмо, которое ещё
    # НЕ УШЛО. Одобренных много, но большинство уже отправлено.
    with store._lock:
        ждут = store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews c "
            "JOIN messages m ON m.id=c.message_id "
            "WHERE c.campaign_id=? AND c.status IN ('approved','edited') "
            "AND m.status='scheduled' AND c.body LIKE '%кейс%' ",
            (камп,)).fetchone()[0]
        ждут2 = store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews c "
            "JOIN messages m ON m.id=c.message_id "
            "WHERE c.campaign_id=? AND c.status IN ('approved','edited') "
            "AND m.status='scheduled'", (камп,)).fetchone()[0]
    print(f"  ЖДУТ ОТПРАВКИ (approved + scheduled): {ждут2}, "
          f"из них со словом «кейс»: {ждут}")
    for i, с, ф in примеры:
        print(f"    #{i} [{с}] «{ф}»")
