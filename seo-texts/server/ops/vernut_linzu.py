# -*- coding: utf-8 -*-
"""Вернуть в отправку письма, снятые моей линзой у ПОДТВЕРЖДЁННОЙ владельцем
вечерней партии 24.08.

Владелец сам просмотрел и подтвердил эти письма, а линза сняла их после него.
По правилу доверия слово владельца стоит выше вердикта моей модели, поэтому
возвращаем — но не вслепую: адрес с приговором (нет ящика / нет MX) остаётся
снятым, иначе вернём письмо в никуда.

  --набор=ошибка       только мой брак: правило 2 и сбой разбора линзы
  --набор=всё          всё, кроме гейта направления (он снимал по делу)
  --вернуть            без него — сухой прогон
"""
import sqlite3
import sys

НАБОР = "ошибка"
for а in sys.argv[1:]:
    if а.startswith("--набор="):
        НАБОР = а.split("=", 1)[1]
ДЕЛАТЬ = "--вернуть" in sys.argv

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
try:
    приговор = {(р[0] or "").strip().lower(): (р[1] or "")
                for р in c.execute("SELECT email, verdict FROM addr_probe")}
except Exception:  # noqa: BLE001
    приговор = {}
ПЛОХО = ("нет ящика", "нет MX")

ряды = c.execute(
    "SELECT cr.id, cr.status st, cr.message_id mid, "
    "       COALESCE(NULLIF(m.last_error,''),'') le, "
    "       LOWER(COALESCE(r.email,'')) адрес, r.company_name имя "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.decided_by='kirill' AND substr(cr.decided_at,1,10)='2026-08-24' "
    "   AND substr(cr.decided_at,12,2) >= '11' AND m.status='skipped'").fetchall()


def мой_брак(п):
    п = (п or "").lower()
    return "правило 2" in п or "не разобрался" in п


def по_делу(п):
    п = (п or "").lower().replace("confirm:skipped:", "")
    return ("не то направление" in п or "направление:" in п
            or "минус-класс" in п or "адрес не существует" in п
            or "проба не добилась" in п or "нет mx" in п)


цель = [р for р in ряды
        if (мой_брак(р["le"]) if НАБОР == "ошибка" else not по_делу(р["le"]))]
мёртвые = [р for р in цель if приговор.get(р["адрес"], "") in ПЛОХО]
цель = [р for р in цель if приговор.get(р["адрес"], "") not in ПЛОХО]
без_пробы = [р for р in цель if not приговор.get(р["адрес"])]

print("снято линзой у вечерней партии: %d" % len(ряды))
print("набор «%s» → к возврату: %d" % (НАБОР, len(цель)))
print("   из них адрес ещё не пробован: %d (уйдут после пробы, если заслон включён)"
      % len(без_пробы))
print("   оставлены снятыми из-за приговора адресу: %d" % len(мёртвые))
for р in цель[:5]:
    print("   #%-7s %-34s %s" % (р["id"], str(р["имя"] or "")[:34],
                                 (р["le"] or "")[:52]))
if not ДЕЛАТЬ:
    print("\nсухой прогон. Вернуть — --вернуть")
    raise SystemExit(0)

вернули = 0
for р in цель:
    c.execute("UPDATE messages SET status='scheduled', last_error=NULL, "
              "       scheduled_at=datetime('now'), updated_at=datetime('now') "
              " WHERE id=? AND status='skipped'", (р["mid"],))
    вернули += c.total_changes and 1 or 0
    if р["st"] == "skipped":
        c.execute("UPDATE confirm_reviews SET status='approved', "
                  "       reason='подтверждено владельцем 24.08, снято линзой "
                  "ошибочно, возвращено 25.08', updated_at=datetime('now') "
                  " WHERE id=?", (р["id"],))
c.commit()
print("\nвернулось писем: %d" % len(цель))
print("очередь теперь: %d" % c.execute(
    "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','sending')"
    ).fetchone()[0])
