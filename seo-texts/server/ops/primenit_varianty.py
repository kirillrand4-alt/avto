# -*- coding: utf-8 -*-
"""Разложить письма партии по вариантам: своё письмо и своя тема каждому.

Текст и тема лежат в четырёх местах: confirm_reviews.body/subject,
panel_json.letter.body/final_body/subject и, у подтверждённого письма,
messages.body_rendered/subject. Пишем во все, кроме отправленных.

    python primenit_varianty.py            # вхолостую
    python primenit_varianty.py --primenit
"""
import io
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sender.store import Store                                  # noqa: E402
from imya_v_pismo import итоговое_имя                           # noqa: E402
import varianty_pisma as V                                      # noqa: E402

ТЕМЫ_ПАРТИИ = tuple(V.ТЕМЫ)
ИМЕНА = r"C:\sender\_ops\agro-imena.jsonl"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
СНИМОК = (r"C:\sender\_ops\agro-varianty-do-"
          + time.strftime("%m%d-%H%M%S") + ".jsonl")


def собрать_final(тело, подпись):
    подпись = (подпись or "").strip()
    хвост = (тело or "").rstrip()
    if not подпись:
        return тело or ""
    первая = подпись.split("\n")[0].rstrip()
    if первая and хвост.endswith(первая):
        return хвост + "\n" + "\n".join(подпись.split("\n")[1:]).lstrip("\n")
    return хвост + "\n\n" + подпись


имена = {}
for с in io.open(ИМЕНА, encoding="utf-8", errors="replace"):
    с = с.strip()
    if с:
        try:
            z = json.loads(с)
            if z.get("сыро"):
                имена[z["сыро"]] = (z.get("имя"), bool(z.get("человек")))
        except Exception:                                       # noqa: BLE001
            pass

store = Store(r"C:\sender\sender.db")
счёт = Counter()
правки = []
with store._lock:
    строки = store._conn.execute(
        """SELECT c.id AS cid, c.status AS cst, c.inn, c.subject, c.body,
                  c.panel_json, c.recipient_id,
                  m.id AS mid, m.status AS mst, m.body_rendered,
                  r.company_name, r.region
             FROM confirm_reviews c
             LEFT JOIN messages m ON c.message_id = m.id
             LEFT JOIN recipients r ON c.recipient_id = r.id
            WHERE c.subject IN (%s)"""
        % ",".join("?" * len(ТЕМЫ_ПАРТИИ)), ТЕМЫ_ПАРТИИ).fetchall()

for р in строки:
    счёт["карточек партии"] += 1
    mst = str(р["mst"] or "нет письма")
    if str(р["cst"]) == "sent" or mst == "sent":
        счёт["УЖЕ ОТПРАВЛЕНО — не трогаем"] += 1
        continue
    инн = str(р["inn"] or "") or str(р["cid"])
    сыро = " ".join(str(р["company_name"] or "").split())
    пара = имена.get(сыро)
    if пара:
        кто, _вид = итоговое_имя(пара[0], пара[1])
    else:
        кто = "Ваше хозяйство"
        счёт["названия нет в разборе — «Ваше хозяйство»"] += 1
    тело = V.письмо(инн, кто, р["region"])
    тема = V.тема(инн)
    if тело == str(р["body"] or "") and тема == str(р["subject"] or ""):
        счёт["уже разложено"] += 1
        continue
    try:
        панель = json.loads(р["panel_json"] or "{}")
    except Exception:                                           # noqa: BLE001
        панель = {}
    новая_панель = None
    письмо_п = панель.get("letter")
    if isinstance(письмо_п, dict):
        низ = тело.lower()
        новое = dict(письмо_п)
        новое["subject"] = тема
        новое["body"] = тело
        новое["final_body"] = собрать_final(тело, письмо_п.get("signature"))
        новое["highlights"] = [h for h in (письмо_п.get("highlights") or [])
                               if isinstance(h, dict)
                               and str(h.get("text") or "").lower() in низ]
        панель["letter"] = новое
        новая_панель = json.dumps(панель, ensure_ascii=False)
    менять_письмо = bool(р["mid"]) and mst not in ("sent", "нет письма") \
        and str(р["body_rendered"] or "").strip()
    правки.append((int(р["cid"]), тема, тело, новая_панель,
                   int(р["mid"]) if менять_письмо else None,
                   str(р["subject"] or ""), str(р["body"] or ""),
                   str(р["panel_json"] or "")))
    счёт["К РАСКЛАДКЕ"] += 1

if ПРИМЕНИТЬ and правки:
    with io.open(СНИМОК, "w", encoding="utf-8") as ф:
        for cid, _т, _б, _нп, mid, тема_до, тело_до, панель_до in правки:
            ф.write(json.dumps({"review_id": cid, "message_id": mid,
                                "тема_до": тема_до, "тело_до": тело_до,
                                "panel_json_до": панель_до},
                               ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())
    счёт["снимок сохранён"] = len(правки)
    карточек = писем = 0
    for нач in range(0, len(правки), 300):
        кусок = правки[нач:нач + 300]
        for _ in range(20):
            try:
                with store.transaction() as conn:
                    for cid, тема, тело, нп, mid, _a, _b, _c in кусок:
                        if нп is not None:
                            conn.execute(
                                "UPDATE confirm_reviews SET subject=?, body=?,"
                                " panel_json=?, updated_at=datetime('now')"
                                " WHERE id=? AND status<>'sent'",
                                (тема, тело, нп, cid))
                        else:
                            conn.execute(
                                "UPDATE confirm_reviews SET subject=?, body=?,"
                                " updated_at=datetime('now')"
                                " WHERE id=? AND status<>'sent'",
                                (тема, тело, cid))
                        карточек += 1
                        if mid:
                            conn.execute(
                                "UPDATE messages SET subject=?, body_rendered=?,"
                                " updated_at=datetime('now') WHERE id=? AND "
                                "status NOT IN ('sent','failed')",
                                (тема, тело, mid))
                            писем += 1
                break
            except Exception as ex:                             # noqa: BLE001
                if "locked" not in str(ex) and "busy" not in str(ex):
                    print("   кусок не лёг: %s" % str(ex)[:110], flush=True)
                    break
                time.sleep(3.0)
    счёт["ПЕРЕПИСАНО карточек"] = карточек
    счёт["ПЕРЕПИСАНО писем"] = писем

# насколько письма разошлись
уник_тел = len({т for _c, _тм, т, _n, _m, _a, _b, _p in правки})
уник_тем = len({тм for _c, тм, _т, _n, _m, _a, _b, _p in правки})
print("=" * 74)
print("=== РАСКЛАДКА ПО ВАРИАНТАМ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
for к, в in счёт.most_common(10):
    print("   %-46s %5d" % (к, в))
print("   разных тел писем среди правок:                 %5d" % уник_тел)
print("   разных тем:                                    %5d" % уник_тем)
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Разложить — --primenit")
