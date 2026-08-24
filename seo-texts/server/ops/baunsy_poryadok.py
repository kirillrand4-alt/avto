# -*- coding: utf-8 -*-
"""Что было раньше: приговор пробы или наша отправка.

Если проба сказала «нет ящика» ДО отправки — мы писали по заведомо
мёртвому адресу и виноват отбор. Если ПОСЛЕ — приговор поставлен по самой
отбивке, и претензий к отбору нет. Разница принципиальная, на глаз по
одинаковым «10:30» её не понять.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("колонки addr_probe: %s"
      % ", ".join(к[1] for к in c.execute("PRAGMA table_info(addr_probe)")))

строки = c.execute(
    "SELECT e.event_ts, r.email, e.message_id, m.sent_at, m.mailbox_id "
    "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
    "  LEFT JOIN messages m ON m.id=e.message_id "
    " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)='2026-08-24' "
    " ORDER BY e.event_ts").fetchall()

кол = [к[1] for к in c.execute("PRAGMA table_info(addr_probe)")]
доп = [п for п in ("source", "answer", "ts") if п in кол]

print("\n%-32s %-16s %-16s %-16s %s"
      % ("адрес", "отправлено", "баунс", "проба", "приговор / порядок"))
итог = {"проба раньше отправки": 0, "проба после отправки": 0,
        "пробы не было": 0, "не приговор": 0}
for р in строки:
    поля = ", ".join(["verdict"] + доп)
    п = c.execute("SELECT %s FROM addr_probe WHERE email=? "
                  "ORDER BY ts LIMIT 1" % поля, (р["email"],)).fetchone()
    отпр = str(р["sent_at"] or "")[:16]
    баунс = str(р["event_ts"])[:16]
    if not п:
        вывод, итог_ключ = "пробы не было", "пробы не было"
        проба = "-"
    else:
        проба = str(п["ts"] if "ts" in доп else "")[:16]
        приговор = п["verdict"]
        ист = (" [%s]" % п["source"]) if "source" in доп and п["source"] else ""
        if приговор not in ("нет ящика", "нет MX"):
            вывод, итог_ключ = "%s%s — не приговор" % (приговор, ист), "не приговор"
        elif проба and отпр and проба < отпр:
            вывод = "%s%s ← ДО отправки" % (приговор, ист)
            итог_ключ = "проба раньше отправки"
        else:
            вывод = "%s%s — после отправки" % (приговор, ист)
            итог_ключ = "проба после отправки"
    итог[итог_ключ] += 1
    print("%-32s %-16s %-16s %-16s %s"
          % (str(р["email"] or "?")[:32], отпр, баунс, проба, вывод))

print("\n=== ИТОГ ===")
for к, н in итог.items():
    print("  %-26s %d" % (к, н))

print("\n=== ПИШЕТ ЛИ ОТБИВКА ПРИГОВОР В addr_probe ===")
if "source" in доп:
    for р in c.execute("SELECT COALESCE(source,'(пусто)') s, verdict v, "
                       "COUNT(*) n FROM addr_probe GROUP BY 1,2 "
                       "ORDER BY n DESC LIMIT 20"):
        print("  источник=%-18s приговор=%-16s %d" % (р["s"], р["v"], р["n"]))
else:
    print("  колонки source нет — источник приговора не различить")

print("\n=== ЧТО ГОВОРИТ ФИЛЬТР ОТБОРА (сколько мёртвых знали на момент партии) ===")
for р in c.execute(
        "SELECT verdict, COUNT(*) n, MIN(ts) a, MAX(ts) b FROM addr_probe "
        " GROUP BY verdict ORDER BY n DESC"):
    print("  %-16s %5d   с %s по %s"
          % (р["verdict"], р["n"], str(р["a"])[:16], str(р["b"])[:16]))
