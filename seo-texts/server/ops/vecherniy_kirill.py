# -*- coding: utf-8 -*-
"""Вечерняя партия владельца 24.08: поимённо, кто и чем её снял.

Карточка осталась approved (её решал kirill), а письмо сняли позже — правду
пишет messages.last_error. Разбираем именно её, а не «письма, созданные
24.08»: это разные множества, и я вчера спутал их.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.status st, COALESCE(m.status,'нет письма') ms, "
    "       COALESCE(NULLIF(m.last_error,''),'') le, cr.reason rs, "
    "       substr(COALESCE(m.sent_at,''),1,10) ушло "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.decided_by='kirill' AND substr(cr.decided_at,1,10)='2026-08-24' "
    "   AND substr(cr.decided_at,12,2) >= '11'").fetchall()
print("=== ПОДТВЕРЖДЕНО ВЛАДЕЛЬЦЕМ ПОСЛЕ ОСНОВНОЙ ОТПРАВКИ 24.08: %d ===" % len(ряды))
for к, н in Counter(
        ("ушло " + р["ушло"]) if р["ms"] == "sent" else
        ("в очереди" if р["ms"] in ("scheduled", "sending") else
         ("ждёт" if р["st"] in ("pending", "edited") else
          ("сорвалось" if р["ms"] == "failed" else "снято")))
        for р in ряды).most_common():
    print("   %-24s %5d" % (к, н))

снятые = [р for р in ряды if р["ms"] == "skipped"]
print("\n=== ЧЕМ СНЯТЫ ЭТИ %d ===" % len(снятые))


def разряд(п):
    п = (п or "").lower().replace("confirm:skipped:", "")
    if "не разобрался" in п:
        return "МОЯ ОШИБКА: сбой разбора линзы"
    if "правило 2" in п:
        return "МОЯ ОШИБКА: линза, правило 2 (строка отказа)"
    if ("адрес не существует" in п or "нет mx" in п or "отказ пробе" in п
            or "проба не добилась" in п or "неясно" in п):
        return "проба адреса (по делу)"
    if "минус-класс" in п:
        return "минус-класс (по делу)"
    if "не то направление" in п or "направление:" in п:
        return "гейт направления (по делу)"
    if "человечность" in п:
        return "линза человечности"
    if "механическ" in п:
        return "механическая схема (по вашей команде)"
    return "линза, прочие правила текста"


разбор = Counter(разряд(р["le"]) for р in снятые)
for к, н in разбор.most_common():
    print("   %-52s %5d" % (к, н))
вернуть = [р for р in снятые if разряд(р["le"]).startswith("МОЯ ОШИБКА")]
print("\nвозвращаемо без вопросов: %d" % len(вернуть))
print("под вопросом (линза человечности): %d"
      % sum(1 for р in снятые if разряд(р["le"]) == "линза человечности"))
print("\nпримеры того, что снято моей ошибкой:")
for р in вернуть[:6]:
    print("   #%-7s %s" % (р["id"], (р["le"] or "")[:88]))
