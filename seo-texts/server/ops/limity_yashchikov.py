# -*- coding: utf-8 -*-
"""Лимиты и паузы ящиков: кто превысил и за что поставлен на паузу.

Замер 24.08 показал строку, которой быть не должно:

    a.kozlov@zernosort.ru | paused=1 | daily_limit=5 | sent_today=27

Двадцать семь писем при суточном лимите пять — это либо лимит не
применяется, либо значение в таблице протухло, и настоящий потолок
считает рампа по дню разогрева. Разница важная: в первом случае мы жжём
репутацию доменов, во втором врёт только табличка.

Печатаем состояние всех ящиков целиком, причину паузы дословно и рядом —
что говорит сама рампа для их дня. И смотрим, к каким ящикам привязаны
просроченные письма: если они ждут паузы, то стоят не просто так.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== СОСТОЯНИЕ ЯЩИКОВ ===")
print("%-40s %-9s %-6s %-6s %-5s %s"
      % ("ящик", "провайдер", "лимит", "ушло", "день", "пауза"))
строки = c.execute(
    "SELECT mailbox_id, provider, daily_limit, sent_today, sent_total, "
    "       ramp_day, paused, pause_reason, day_key, last_sent_at "
    "  FROM mailbox_state ORDER BY sent_today DESC").fetchall()
for р in строки:
    пауза = "ДА" if р["paused"] else "—"
    if р["pause_reason"]:
        пауза += " (%s)" % str(р["pause_reason"])[:44]
    print("%-40s %-9s %-6s %-6s %-5s %s"
          % (str(р["mailbox_id"])[:40], str(р["provider"] or "?")[:9],
             р["daily_limit"], р["sent_today"], р["ramp_day"], пауза))

превысили = [р for р in строки
             if (р["daily_limit"] or 0) and (р["sent_today"] or 0) > р["daily_limit"]]
print("\nящиков, где ушло больше записанного лимита: %d" % len(превысили))

print("\n=== ЧТО ГОВОРИТ САМА РАМПА ===")
try:
    from sender.config import Config
    from sender.ramp import daily_send_limit
    cfg = Config.load(r"C:\sender\sender.yaml")
    видели = set()
    for р in строки:
        ключ = (str(р["provider"] or ""), р["ramp_day"])
        if ключ in видели:
            continue
        видели.add(ключ)
        try:
            л = daily_send_limit(р["provider"], р["ramp_day"], р["mailbox_id"])
        except TypeError:
            try:
                л = daily_send_limit(р["provider"], р["ramp_day"])
            except Exception as e:                             # noqa: BLE001
                л = "не посчитан (%s)" % str(e)[:40]
        except Exception as e:                                 # noqa: BLE001
            л = "не посчитан (%s)" % str(e)[:40]
        print("  провайдер %-10s день %-3s -> лимит %s"
              % (str(р["provider"] or "?"), р["ramp_day"], л))
except Exception as e:                                         # noqa: BLE001
    print("  рампа не собралась: %s: %s" % (type(e).__name__, str(e)[:110]))

print("\n=== ПРОСРОЧЕННЫЕ ПИСЬМА: ЧЬИ ОНИ ===")
for р in c.execute(
        "SELECT m.id, m.scheduled_at, m.mailbox_id, m.campaign_id, "
        "       r.email, r.company_name "
        "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status IN ('scheduled','sending') "
        "   AND m.scheduled_at < datetime('now') ORDER BY m.scheduled_at"):
    print("  #%-6s срок %s | ящик %s | кому %s | %s"
          % (р["id"], str(р["scheduled_at"])[:16],
             str(р["mailbox_id"] or "НЕ НАЗНАЧЕН")[:32],
             str(р["email"] or "?")[:30], str(р["company_name"] or "")[:24]))

print("\n=== СКОЛЬКО УШЛО С КАЖДОГО ЯЩИКА ЗА СЕГОДНЯ (по событиям) ===")
for р in c.execute(
        "SELECT mailbox_id, COUNT(*) n FROM events WHERE event_type='sent' "
        "  AND substr(event_ts,1,10)=date('now') "
        " GROUP BY mailbox_id ORDER BY n DESC LIMIT 25"):
    print("  %-42s %d" % (str(р["mailbox_id"] or "?")[:42], р["n"]))
