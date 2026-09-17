# -*- coding: utf-8 -*-
"""Держит ли мёртвый работник проб что-нибудь у нас прямо сейчас.

Работник на VPS не оплачен и лежит. Вопрос владельца: занимает ли он базу.
Смотрим три вещи: (1) не заперто ли что-то в базе в состоянии «отдано
работнику», (2) крутятся ли циклы панели вхолостую, (3) чего это стоит —
сколько писем уходит без проверки адреса и сколько из них отбивается.
"""
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
вых = []

with store._lock:
    c = store._conn
    вых.append("--- рубильники проб ---")
    for ключ in ("probe_sync_enabled", "addr_probe_enabled",
                 "auto_send_enabled"):
        try:
            з = store.get_setting(ключ, None)
        except Exception as ex:                                 # noqa: BLE001
            з = "не прочиталось: %s" % str(ex)[:40]
        вых.append("   %-22s %s" % (ключ, з))

    вых.append("")
    вых.append("--- таблица вердиктов addr_probe ---")
    всего = c.execute("SELECT COUNT(*) FROM addr_probe").fetchone()[0]
    вых.append("   строк всего: %d" % всего)
    for р in c.execute("SELECT verdict, COUNT(*) n, MAX(ts) п FROM addr_probe "
                       " GROUP BY 1 ORDER BY 2 DESC"):
        вых.append("   %-16s %6d   последний %s"
                   % (str(р["verdict"])[:16], р["n"], str(р["п"])[:16]))
    вых.append("")
    вых.append("   --- по источнику ---")
    for р in c.execute("SELECT COALESCE(source,'(пусто)') и, COUNT(*) n, "
                       "       MAX(ts) п FROM addr_probe GROUP BY 1 "
                       " ORDER BY 2 DESC LIMIT 8"):
        вых.append("   %-20s %6d   последний %s"
                   % (str(р["и"])[:20], р["n"], str(р["п"])[:16]))

    вых.append("")
    вых.append("--- есть ли в базе состояние «отдано работнику» ---")
    имена = [t[0] for t in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    подозрительные = [t for t in имена
                      if any(k in t.lower() for k in
                             ("probe", "lease", "claim", "lock", "inflight"))]
    вых.append("   таблиц про пробы: %s" % (", ".join(подозрительные) or "нет"))
    for т in подозрительные:
        кол = [x[1] for x in c.execute("PRAGMA table_info(%s)" % т)]
        n = c.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        вых.append("   %-14s строк %-7d колонки: %s" % (т, n, ", ".join(кол)))

    # сколько карточек очереди ждёт вердикта
    вых.append("")
    вых.append("--- очередь подтверждения против вердиктов ---")
    for статус in ("approved", "pending"):
        всего_с = c.execute(
            "SELECT COUNT(*) FROM confirm_reviews WHERE status=?",
            (статус,)).fetchone()[0]
        без = c.execute(
            "SELECT COUNT(*) FROM confirm_reviews r "
            " WHERE r.status=? AND NOT EXISTS (SELECT 1 FROM addr_probe p "
            "   WHERE p.email = lower(r.email))", (статус,)).fetchone()[0]
        вых.append("   %-10s всего %5d, без вердикта %5d (%.0f%%)"
                   % (статус, всего_с, без,
                      100.0 * без / всего_с if всего_с else 0))

    # цена простоя: письма после смерти работника
    вых.append("")
    вых.append("--- письма по дням: была ли проба ДО отправки ---")
    for р in c.execute("""
        SELECT substr(m.sent_at,1,10) д,
               COUNT(*) ушло,
               SUM(CASE WHEN p.email IS NOT NULL
                         AND p.ts < m.sent_at
                         AND COALESCE(p.source,'') NOT LIKE '%bounce%'
                        THEN 1 ELSE 0 END) с_пробой
          FROM messages m
          JOIN recipients r ON m.recipient_id = r.id
          LEFT JOIN addr_probe p ON p.email = lower(r.email)
         WHERE m.status='sent' AND m.sent_at >= '2026-09-05'
         GROUP BY 1 ORDER BY 1"""):
        д, ушло, с_пробой = str(р["д"]), int(р["ушло"]), int(р["с_пробой"] or 0)
        # отбивки этих же писем
        отб = c.execute(
            "SELECT COUNT(DISTINCT e.message_id) FROM events e "
            "  JOIN messages m2 ON e.message_id = m2.id "
            " WHERE e.event_type='bounce' AND substr(m2.sent_at,1,10)=?",
            (д,)).fetchone()[0]
        вых.append("   %s  ушло %4d, с пробой до отправки %4d (%3.0f%%), "
                   "отбилось %3d (%.1f%%)"
                   % (д, ушло, с_пробой, 100.0 * с_пробой / ушло if ушло else 0,
                      отб, 100.0 * отб / ушло if ушло else 0))

print("\n".join(вых))
print("")
print("=" * 74)
print("=== ДЕРЖИТ ЛИ РАБОТНИК ЧТО-НИБУДЬ ===")
