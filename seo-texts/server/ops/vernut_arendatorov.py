# -*- coding: utf-8 -*-
"""Вернуть арендодателей: суд конкурентов разошёлся с правилом владельца.

19.08 владелец прямо поправил гейт: «АРЕНДА И ПАРК СПЕЦТЕХНИКИ —
покупатель. У арендодателя своя ремонтная база (пневмоинструмент, подкачка
колёс, продувка, покраска)». Правило записано в промпте гейта и действует.

А суд конкурентов 26.08 снял трёх арендодателей компрессоров как
конкурентов. Логика суда понятна — они дают компрессор чужому предприятию,
- но она противоречит стоящему решению владельца, а такие вещи молча
переигрывать нельзя: слово владельца выше вывода модели.

Возвращаем их и ждём решения. «БК Урал» не трогаем: там не аренда, а
поставка передвижных компрессорных станций клиентам — это ближе к дилеру.

    python vernut_arendatorov.py            # показать
    python vernut_arendatorov.py primenit   # вернуть
"""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.ne_nash import НеНаш                              # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
БАЗА = r"C:\sender\sender.db"
КАРТОЧКИ = (8768, 6577, 8630)      # Альпкор, ТЭКО, Рентстрой

c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=90000")
c.row_factory = sqlite3.Row
цели = []
for cid in КАРТОЧКИ:
    r = c.execute(
        "SELECT cr.id, cr.status, cr.reason, cr.message_id, r.inn, "
        "       r.company_name, substr(cr.subject,1,50) s "
        "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE cr.id=?", (cid,)).fetchone()
    if r is None:
        print("карточки #%s нет" % cid)
        continue
    print("#%-6s %-9s %-34s %s" % (r["id"], r["status"],
                                   str(r["company_name"])[:34], r["s"]))
    print("      причина: %s" % str(r["reason"])[:110])
    цели.append(r)

if not ДЕЛАТЬ:
    print("\nвхолостую. Вернуть — primenit")
    raise SystemExit(0)

# СНАЧАЛА КАРТОЧКИ, ПОТОМ РЕЕСТР, и то и другое с повторами: sender.db
# делят панель, авто-отправка и часовая сверка приговоров, и одиночный
# «database is locked» не должен стоить возврата.
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")


def с_повтором(что, попыток=6):
    посл = None
    for i in range(попыток):
        try:
            return что()
        except sqlite3.OperationalError as ex:
            посл = ex
            time.sleep(2 * (i + 1))
    raise посл


возвращено = 0


def вернуть_карточки():
    global возвращено
    for r in цели:
        c.execute("UPDATE confirm_reviews SET status='pending', reason=NULL, "
                  "decided_at=NULL, decided_by=NULL, updated_at=? "
                  " WHERE id=? AND status='stoplist'", (сейчас, r["id"]))
        if r["message_id"]:
            c.execute("UPDATE messages SET status='pending_review', "
                      "last_error=NULL, updated_at=? WHERE id=? "
                      "  AND status='skipped'", (сейчас, r["message_id"]))
        возвращено += 1
    c.commit()


с_повтором(вернуть_карточки)
print("\nвозвращено в очередь: %d" % возвращено)
c.close()

реестр = НеНаш(БАЗА, зеркало=r"C:\sender\enrich.db")
убрано = 0
for r in цели:
    try:
        с_повтором(lambda: реестр.убрать(r["inn"]))
        убрано += 1
    except Exception as ex:                                   # noqa: BLE001
        print("   из реестра не убрался %s: %s" % (r["inn"], str(ex)[:70]))
print("убрано из реестра: %d" % убрано)
