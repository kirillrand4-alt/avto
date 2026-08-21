# -*- coding: utf-8 -*-
"""Отказы НАШЕГО почтовика на выходе: сколько, по каким ящикам, когда.

Это не отбивка получателя. 554 5.7.1 «Message rejected under suspicion of
SPAM» отдаёт Яндекс, через который стоят наши ящики: письмо он не принял
вовсе, до чужого сервера оно не доехало. Такой отказ - оценка НАШЕЙ
репутации и текста, и если доля растёт, следующий шаг Яндекса - придушить
или закрыть домен целиком.

Считаем по всей истории: сколько таких отказов, на каких ящиках и в какие
дни, плюс общее число попыток тех же дней - чтобы доля была честной.
"""
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

# 1. письма с ошибкой в самом сообщении
ряды = c.execute(
    "SELECT id, mailbox_id, status, substr(COALESCE(updated_at,''),1,10) день, "
    "       COALESCE(last_error,'') err FROM messages "
    " WHERE COALESCE(last_error,'') <> ''"
).fetchall()
спам = [р for р in ряды if re.search(r"5\.7\.1|suspicion of SPAM|"
                                     r"rejected under suspicion", р["err"], re.I)]
print(f"писем с непустой ошибкой всего: {len(ряды)}")
print(f"из них отказ нашего почтовика по спаму: {len(спам)}")

if спам:
    print("\nпо дням:")
    for д, н in sorted(Counter(str(р["день"]) for р in спам).items()):
        print(f"  {н:>3}  {д}")
    print("\nпо ящикам:")
    for я, н in Counter(str(р["mailbox_id"]) for р in спам).most_common():
        print(f"  {н:>3}  {я}")
    print("\nтексты отказов (уникальные):")
    for т, н in Counter(str(р["err"])[:110] for р in спам).most_common(6):
        print(f"  {н:>3}  {т}")

# 2. знаменатель: сколько всего уходило в те же дни
дни = sorted({str(р["день"]) for р in спам})
if дни:
    print("\nдоля от отправленного в те же дни:")
    for д in дни:
        всего = c.execute(
            "SELECT COUNT(*) FROM messages WHERE status='sent' "
            "AND substr(COALESCE(sent_at,updated_at),1,10)=?", (д,)).fetchone()[0]
        н = sum(1 for р in спам if str(р["день"]) == д)
        доля = (100.0 * н / (всего + н)) if (всего + н) else 0
        print(f"  {д}: отказов {н} на {всего} ушедших = {доля:.1f}%")

# 3. и по событиям - вдруг часть отказов легла только туда
try:
    соб = c.execute(
        "SELECT event_type, COUNT(*) n FROM events "
        " WHERE COALESCE(payload_json,'') LIKE '%5.7.1%' "
        "    OR COALESCE(payload_json,'') LIKE '%suspicion of SPAM%' "
        " GROUP BY event_type").fetchall()
    print("\nв журнале событий:", {р["event_type"]: р["n"] for р in соб} or "пусто")
except Exception as ex:                                            # noqa: BLE001
    print(f"\nжурнал событий не прочитан: {str(ex)[:80]}")
