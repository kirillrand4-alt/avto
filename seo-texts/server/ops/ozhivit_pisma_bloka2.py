# -*- coding: utf-8 -*-
"""Оживить письма, которые прогон написал в уже снятые карточки.

ЧТО СЛУЧИЛОСЬ. Утром я вернул в пул генерации фирмы, чьи письма были сняты
по качеству текста. Вернул только для ОТБОРА: генератор перестал считать их
отработанными и написал им новые письма. А очередь подтверждения отдала ему
ту же самую карточку — снятую, — и свежий текст лёг в неё. Карточка как
была skipped, так и осталась: оператор этих писем не видит, хотя они
оплачены. 632 письма.

ЧТО ДЕЛАЕМ. Берём текст из журнала (он пишется ДО постановки в очередь),
кладём его в письмо карточки и поднимаем обе строки: карточка pending,
письмо pending_review. Второй раз модели не платим.

ЧЕГО НЕ ДЕЛАЕМ. Не оживляем карточки, снятые по делу: мёртвый адрес,
отписка, «не наш профиль», «сайт не подтверждает». Оживляем только те, что
сняты за КАЧЕСТВО ТЕКСТА — им новое письмо и писалось.

    pl_run.py ozhivit_pisma_bloka2.py            # вхолостую
    pl_run.py ozhivit_pisma_bloka2.py primenit   # оживить
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ОТЧЁТ = r"C:\sender\_ops\ozhivlennye-pisma.jsonl"
ДЕЛАТЬ = "primenit" in sys.argv[1:]

КАЧЕСТВО = ("механическая сборка", "чистка механической схемы", "линза",
            "человечност", "реклама", "правило", "написанное до 2026-08-10",
            "чужая кампания", "заход")
ПО_ДЕЛУ = ("адрес", "ящик", "mx", "проба", "отпис", "стоп", "suppress",
           "не наш", "вне профиля", "не покупател", "минус-класс",
           "направлени", "сайт не подтверждает", "уже писали", "сделка")

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 3000000))
    хвост = ф.read().decode("utf-8", "replace").splitlines()[1:]

кандидаты, причины, отказ = [], Counter(), Counter()
for с in хвост:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if not (з.get("ок") and з.get("тело") and з.get("review_id")):
        continue
    р = c.execute(
        "SELECT cr.id, cr.status cs, COALESCE(cr.reason,'') причина, "
        "       cr.message_id, COALESCE(m.status,'нет') ms, r.email, "
        "       r.company_name FROM confirm_reviews cr "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        "  LEFT JOIN recipients r ON r.id=cr.recipient_id WHERE cr.id=?",
        (int(з["review_id"]),)).fetchone()
    if not р or (р["cs"] != "skipped" and р["ms"] != "skipped"):
        continue
    низ = р["причина"].lower()
    if any(с2 in низ for с2 in ПО_ДЕЛУ):
        отказ[р["причина"][:44]] += 1
        continue
    if not any(с2 in низ for с2 in КАЧЕСТВО):
        отказ["непонятная причина: " + р["причина"][:34]] += 1
        continue
    причины[р["причина"][:44]] += 1
    кандидаты.append((р, з))

print("=== ОЖИВЛЯЕМ (сняты за качество текста): %d ===" % len(кандидаты))
for к, н in причины.most_common(8):
    print("   %-46s %5d" % (к, н))
print("\n=== ОСТАВЛЯЕМ СНЯТЫМИ (сняты по делу): %d ===" % sum(отказ.values()))
for к, н in отказ.most_common(8):
    print("   %-46s %5d" % (к, н))

if not ДЕЛАТЬ:
    print("\nвхолостую. Оживить — primenit")
    raise SystemExit(0)

оживлено = 0
with io.open(ОТЧЁТ, "a", encoding="utf-8") as ж:
    for р, з in кандидаты:
        if not р["message_id"]:
            continue
        c.execute("UPDATE messages SET subject=?, body_rendered=?, "
                  "       status='pending_review', last_error=NULL, "
                  "       updated_at=datetime('now') WHERE id=?",
                  (з.get("тема") or "", з.get("тело") or "", р["message_id"]))
        c.execute("UPDATE confirm_reviews SET status='pending', "
                  "       decided_by=NULL, decided_at=NULL, "
                  "       reason='письмо переписано 25.08, карточка оживлена', "
                  "       updated_at=datetime('now') WHERE id=?", (р["id"],))
        ж.write(json.dumps({"карточка": р["id"], "письмо": р["message_id"],
                            "инн": з.get("inn"), "имя": з.get("имя"),
                            "было": р["причина"][:80], "ts": time.time()},
                           ensure_ascii=False) + "\n")
        оживлено += 1
    ж.flush()
    os.fsync(ж.fileno())
c.commit()
print("\nоживлено писем: %d" % оживлено)
print("ждут подтверждения теперь: %d"
      % c.execute("SELECT COUNT(*) FROM confirm_reviews "
                  " WHERE status IN ('pending','edited')").fetchone()[0])
