# -*- coding: utf-8 -*-
"""Уходят ли письма на корпоративные серверы автоматом или их держит заслон.

Владелец 24.08: «и отправлять после отправки в автоотправку» — хочет,
чтобы корпоративные шли тем же путём, что и остальные.

В коде записано, что такие письма оператор шлёт руками, но причина этого
— гейт молодых доменов, а он управляется конфигом: min_age_days = 0 или
нет секции, и гейт выключен. Плюс домены с 05.08 повзрослели. Значит
запрет мог давно сняться сам, и править ничего не надо.

Проверяем фактом: настройка гейта, возраст доменов-отправителей и —
главное — уходили ли письма получателям на своих серверах на самом деле.
"""
import sqlite3
import sys
from datetime import date, datetime

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.config import Config                               # noqa: E402

СВОЙ_СЕРВЕР = ("other", "unknown", "")
cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== НАСТРОЙКА ГЕЙТА МОЛОДЫХ ДОМЕНОВ ===")
мин = cfg.get("gates.young_domain.min_age_days", 0)
print("  min_age_days = %s  (%s)"
      % (мин, "ВЫКЛЮЧЕН" if not мин else "включён"))
пров = cfg.get("gates.young_domain.providers", None)
print("  providers    = %s" % пров)
домены = cfg.get("gates.young_domain.domains", None) or {}
if домены:
    сегодня = date.today()
    print("  возраст доменов-отправителей:")
    for д, создан in sorted(dict(домены).items()):
        try:
            дн = (сегодня - datetime.fromisoformat(str(создан)[:10]).date()).days
            метка = "зрелый" if (not мин or дн >= int(мин)) else "МОЛОДОЙ"
        except Exception:                                      # noqa: BLE001
            дн, метка = "?", "дата не разобрана"
        print("    %-38s %s дн. — %s" % (д, дн, метка))
else:
    print("  список доменов пуст — гейту нечего держать")

print("\n=== УХОДИЛИ ЛИ ПИСЬМА НА СВОИ СЕРВЕРЫ ===")
всего = c.execute(
    "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent' AND (r.mx_provider IS NULL OR r.mx_provider IN "
    "       ('other','unknown',''))").fetchone()[0]
print("  отправлено таким получателям всего: %d" % всего)
за_сегодня = c.execute(
    "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent' AND substr(m.sent_at,1,10)=date('now') "
    "   AND (r.mx_provider IS NULL OR r.mx_provider IN "
    "        ('other','unknown',''))").fetchone()[0]
print("  из них за сегодня: %d" % за_сегодня)

print("\n  последние восемь:")
for р in c.execute(
        "SELECT m.id, m.sent_at, m.mailbox_id, r.email, r.mx_provider, "
        "       r.company_name FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status='sent' AND (r.mx_provider IS NULL OR r.mx_provider IN "
        "       ('other','unknown','')) ORDER BY m.sent_at DESC LIMIT 8"):
    print("    #%-6s %s | %-30s | mx=%s | %s"
          % (р["id"], str(р["sent_at"])[:16], str(р["email"])[:30],
             str(р["mx_provider"] or "нет"), str(р["company_name"] or "")[:22]))

print("\n=== ЧЕМ КОНЧАЛИСЬ ПИСЬМА НА СВОИ СЕРВЕРЫ ===")
for р in c.execute(
        "SELECT m.status, COUNT(*) n FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE r.mx_provider IS NULL OR r.mx_provider IN "
        "       ('other','unknown','') GROUP BY m.status ORDER BY n DESC"):
    print("  %-16s %d" % (р["status"], р["n"]))

print("\n=== ОТБИВКИ У НИХ ПРОТИВ ОСТАЛЬНЫХ ===")
for имя, усл in (("на своих серверах",
                  "(r.mx_provider IS NULL OR r.mx_provider IN "
                  "('other','unknown',''))"),
                 ("на публичных почтовиках",
                  "r.mx_provider NOT IN ('other','unknown','') "
                  "AND r.mx_provider IS NOT NULL")):
    ушло = c.execute(
        "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.status='sent' AND %s" % усл).fetchone()[0]
    отбито = c.execute(
        "SELECT COUNT(*) FROM events e JOIN recipients r ON r.id=e.recipient_id"
        " WHERE e.event_type='bounce' AND %s" % усл).fetchone()[0]
    доля = (100.0 * отбито / ушло) if ушло else 0.0
    print("  %-26s отправлено %-6s отбито %-5s (%.1f%%)"
          % (имя, ушло, отбито, доля))
