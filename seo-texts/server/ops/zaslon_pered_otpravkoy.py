# -*- coding: utf-8 -*-
"""Успеет ли заслон снять одобренные письма по мёртвым адресам.

sender.send() дважды спрашивает suppression, так что приговорённый адрес
письмо не получит — ЕСЛИ он в suppression попал. Проверяем именно это, а
не «стоит приговор в кэше».
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

кол = [к[1] for к in c.execute("PRAGMA table_info(suppression)")]
print("колонки suppression: %s" % ", ".join(кол))
поле = "value" if "value" in кол else ("email" if "email" in кол else кол[0])

def в_заслоне(адрес):
    р = c.execute("SELECT reason, source FROM suppression WHERE lower(%s)=? "
                  "LIMIT 1" % поле, (адрес.lower(),)).fetchone()
    return ("%s / %s" % (р["reason"], р["source"] or "-")) if р else None

print("\n=== ОДОБРЕННЫЕ КАРТОЧКИ ПО ПРИГОВОРЁННЫМ АДРЕСАМ ===")
строки = c.execute(
    "SELECT cr.id, cr.status, r.email, p.verdict, p.source "
    "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    "  JOIN addr_probe p ON lower(p.email)=lower(r.email) "
    " WHERE cr.status IN ('approved','pending') "
    "   AND p.verdict IN ('нет ящика','нет MX')").fetchall()
защищено = голых = 0
for р in строки:
    з = в_заслоне(р["email"])
    if з:
        защищено += 1
    else:
        голых += 1
    print("  #%-6s %-10s %-32s %-12s [%s] заслон: %s"
          % (р["id"], р["status"], str(р["email"])[:32], р["verdict"],
             str(р["source"] or "-"), з or "❗ НЕТ — письмо уйдёт и отобьётся"))
print("  ---- в заслоне: %d, без заслона: %d" % (защищено, голых))

print("\n=== СЕГОДНЯШНИЕ 14 БАУНСОВ: ПОПАЛИ ЛИ В ЗАСЛОН ПОСЛЕ ===")
for р in c.execute(
        "SELECT DISTINCT r.email FROM events e "
        "  JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)='2026-08-24'"):
    print("  %-34s %s" % (str(р["email"])[:34],
                          в_заслоне(р["email"]) or "❗ не в заслоне"))

print("\n=== ОДОБРЕННЫЕ, КОТОРЫХ ПРОБА НЕ ВИДЕЛА ВОВСЕ ===")
нет = c.execute(
    "SELECT cr.id, r.email FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
    " WHERE cr.status='approved' AND p.email IS NULL").fetchall()
print("  всего: %d" % len(нет))
for р in нет[:15]:
    print("    #%-6s %s" % (р["id"], р["email"]))

print("\n=== ЧТО ПРОБА ВООБЩЕ БЕРЁТ В РАБОТУ ===")
for р in c.execute(
        "SELECT status, COUNT(*) n FROM confirm_reviews GROUP BY status "
        "ORDER BY n DESC"):
    метка = " ← проба смотрит только сюда" if р["status"] == "pending" else ""
    print("  %-14s %6d%s" % (р["status"], р["n"], метка))
