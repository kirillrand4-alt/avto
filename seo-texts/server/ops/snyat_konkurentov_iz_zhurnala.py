# -*- coding: utf-8 -*-
"""Снять из очереди конкурентов, осуждённых моделью, и завести в реестр.

Порядок важен: СНАЧАЛА снимаем письма (это срочно — конкурент не должен
получить наше предложение), ПОТОМ пишем в реестр. Обе записи с повторами:
sender.db делят панель, авто-отправка и разовые прогоны, и одиночный
«database is locked» не повод потерять решение.

    python snyat_konkurentov_iz_zhurnala.py            # показать
    python snyat_konkurentov_iz_zhurnala.py primenit   # снять
"""
import io
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")

ДЕЛАТЬ = "primenit" in sys.argv[1:]
БАЗА = r"C:\sender\sender.db"
ЖУРНАЛ = r"C:\sender\_ops\konkurenty-sud.jsonl"

осуждено = {}
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    if з.get("инн"):
        осуждено[str(з["инн"])] = з
конкуренты = [з for з in осуждено.values() if з.get("вердикт") == "конкурент"]
print("осуждено всего: %d, конкурентов: %d" % (len(осуждено), len(конкуренты)))
for з in конкуренты:
    print("   #%-6s %-40s %s" % (з.get("crid"), str(з.get("имя"))[:40],
                                 str(з.get("почему"))[:70]))
if not ДЕЛАТЬ:
    print("\nвхолостую. Снять — primenit")
    raise SystemExit(0)


def с_повтором(что, попыток=5):
    посл = None
    for i in range(попыток):
        try:
            return что()
        except sqlite3.OperationalError as ex:
            посл = ex
            time.sleep(2 * (i + 1))
    raise посл


сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
снято = 0


def снять_карточки():
    global снято
    c = sqlite3.connect(БАЗА, timeout=90)
    c.execute("PRAGMA busy_timeout=90000")
    try:
        for з in конкуренты:
            причина = "конкурент: %s" % str(з.get("почему") or "")[:150]
            cur = c.execute(
                "UPDATE confirm_reviews SET status='stoplist', reason=?, "
                "decided_at=?, decided_by='суд конкурентов', updated_at=? "
                " WHERE id=? AND status IN ('pending','approved','edited')",
                (причина, сейчас, сейчас, з.get("crid")))
            if cur.rowcount:
                снято += 1
            r = c.execute("SELECT message_id FROM confirm_reviews WHERE id=?",
                          (з.get("crid"),)).fetchone()
            if r and r[0]:
                c.execute("UPDATE messages SET status='skipped', last_error=?, "
                          "updated_at=? WHERE id=? "
                          "  AND status NOT IN ('sent','sending')",
                          (причина, сейчас, r[0]))
        c.commit()
    finally:
        c.close()


с_повтором(снять_карточки)
print("\nснято писем: %d" % снято)

from sender.ne_nash import НеНаш                              # noqa: E402

реестр = НеНаш(БАЗА, зеркало=r"C:\sender\enrich.db")
в_реестр = сбоев = 0
for з in конкуренты:
    причина = "конкурент: %s" % str(з.get("почему") or "")[:150]
    try:
        с_повтором(lambda: реестр.записать(з["инн"], причина, "суд 26.08"))
        в_реестр += 1
    except Exception as ex:                                   # noqa: BLE001
        сбоев += 1
        print("   не записался %s: %s" % (з["инн"], str(ex)[:70]))
print("в реестр «не наш адресат»: %d, сбоев: %d" % (в_реестр, сбоев))
