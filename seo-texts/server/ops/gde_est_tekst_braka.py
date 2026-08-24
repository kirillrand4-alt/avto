# -*- coding: utf-8 -*-
"""Есть ли брак, у которого текст письма всё-таки сохранён.

В журнале у забракованных по заходу тела нет вовсе. Но письмо могло
успеть попасть в очередь подтверждения и быть снятым уже там — тогда
текст лежит в confirm_reviews и его можно спасти переписыванием первого
абзаца, а не новой генерацией.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== СНЯТЫЕ КАРТОЧКИ ПО ПРИЧИНАМ (у них есть текст) ===")
for р in c.execute(
        "SELECT substr(COALESCE(reason,'(пусто)'),1,58) п, COUNT(*) n, "
        "       SUM(CASE WHEN COALESCE(body,'')<>'' THEN 1 ELSE 0 END) с_текстом "
        "  FROM confirm_reviews WHERE status='skipped' "
        " GROUP BY п ORDER BY n DESC LIMIT 18"):
    print("  %-60s %5d  с текстом %5d" % (р["п"], р["n"], р["с_текстом"]))

print("\n=== ИЗ НИХ ПО ЗАХОДУ/ОДНООБРАЗИЮ ===")
строки = c.execute(
    "SELECT id, recipient_id, subject, body, reason FROM confirm_reviews "
    " WHERE status='skipped' AND (reason LIKE '%заход%' OR reason LIKE '%однообраз%' "
    "   OR reason LIKE '%израсходован%')").fetchall()
с_текстом = [р for р in строки if str(р["body"] or "").strip()]
print("  карточек: %d, из них с текстом: %d" % (len(строки), len(с_текстом)))
for р in с_текстом[:3]:
    print("\n  #%s | %s" % (р["id"], str(р["reason"])[:90]))
    print("    тема: %s" % str(р["subject"])[:70])
    print("    начало: %s…" % str(р["body"])[:160].replace("\n", " "))

print("\n=== ЧТО ВООБЩЕ МОЖНО СПАСТИ (любой брак с текстом) ===")
всего = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews WHERE status='skipped' "
    "  AND COALESCE(body,'')<>''").fetchone()["n"]
print("  снятых карточек с сохранённым текстом: %d" % всего)

print("\n=== ЕСТЬ ЛИ ТЕЛО В messages У СНЯТЫХ ===")
for р in c.execute(
        "SELECT m.status, COUNT(*) n, "
        "       SUM(CASE WHEN COALESCE(m.body_rendered,'')<>'' THEN 1 ELSE 0 END) с_текстом "
        "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='skipped' GROUP BY m.status ORDER BY n DESC"):
    print("  письмо %-12s %5d  с текстом %5d" % (р["status"], р["n"], р["с_текстом"]))
