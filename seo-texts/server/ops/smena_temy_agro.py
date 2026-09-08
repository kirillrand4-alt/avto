# -*- coding: utf-8 -*-
"""Сменить тему письма партии во всех местах, где она записана.

Тема лежит втроём: confirm_reviews.subject (её берёт отправка),
panel_json.letter.subject (её видит оператор) и messages.subject (у
ПОДТВЕРЖДЁННОГО письма тема уже скопирована туда).

Отправленные не трогаем: письмо ушло с прежней темой, и переписывать её в
базе значит соврать себе о том, что получил адресат.

    python smena_temy_agro.py            # вхолостую
    python smena_temy_agro.py --primenit
"""
import io
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

БЫЛО = "для качества: вопрос по сортировке зерна"
СТАЛО = "Для качества: вопрос по сортировке зерна"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
СНИМОК = (r"C:\sender\_ops\agro-tema-do-zameny-"
          + time.strftime("%m%d-%H%M%S") + ".jsonl")

store = Store(r"C:\sender\sender.db")
счёт = Counter()
правки = []
with store._lock:
    строки = store._conn.execute(
        """SELECT c.id AS cid, c.status AS cst, c.subject, c.panel_json,
                  m.id AS mid, m.status AS mst, m.subject AS msub
             FROM confirm_reviews c LEFT JOIN messages m
                  ON c.message_id = m.id
            WHERE c.subject=?""", (БЫЛО,)).fetchall()

for р in строки:
    счёт["карточек с прежней темой"] += 1
    mst = str(р["mst"] or "нет письма")
    if str(р["cst"]) == "sent" or mst == "sent":
        счёт["УЖЕ ОТПРАВЛЕНО — не трогаем"] += 1
        continue
    try:
        панель = json.loads(р["panel_json"] or "{}")
    except Exception:                                           # noqa: BLE001
        панель = {}
    новая_панель = None
    письмо = панель.get("letter")
    if isinstance(письмо, dict):
        письмо = dict(письмо)
        письмо["subject"] = СТАЛО
        панель["letter"] = письмо
        новая_панель = json.dumps(панель, ensure_ascii=False)
    # тема письма переписывается только там, где она уже проставлена
    менять_письмо = bool(р["mid"]) and mst not in ("sent", "нет письма") \
        and str(р["msub"] or "").strip()
    правки.append((int(р["cid"]), новая_панель,
                   int(р["mid"]) if менять_письмо else None,
                   str(р["panel_json"] or ""), str(р["msub"] or "")))
    счёт["К СМЕНЕ (карточка %s / письмо %s)" % (str(р["cst"]), mst)] += 1

if ПРИМЕНИТЬ and правки:
    with io.open(СНИМОК, "w", encoding="utf-8") as ф:
        for cid, _нп, mid, панель_до, тема_письма in правки:
            ф.write(json.dumps({"review_id": cid, "message_id": mid,
                                "тема_до": БЫЛО,
                                "тема_письма_до": тема_письма,
                                "panel_json_до": панель_до},
                               ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())
    счёт["снимок сохранён"] = len(правки)
    карточек = писем = 0
    for нач in range(0, len(правки), 400):
        кусок = правки[нач:нач + 400]
        for _ in range(20):
            try:
                with store.transaction() as conn:
                    for cid, нп, mid, _п, _т in кусок:
                        if нп is not None:
                            conn.execute(
                                "UPDATE confirm_reviews SET subject=?, "
                                "       panel_json=?, updated_at=datetime('now')"
                                " WHERE id=? AND status<>'sent'",
                                (СТАЛО, нп, cid))
                        else:
                            conn.execute(
                                "UPDATE confirm_reviews SET subject=?, "
                                "       updated_at=datetime('now')"
                                " WHERE id=? AND status<>'sent'", (СТАЛО, cid))
                        карточек += 1
                        if mid:
                            conn.execute(
                                "UPDATE messages SET subject=?, updated_at="
                                "datetime('now') WHERE id=? AND status NOT IN "
                                "('sent','failed')", (СТАЛО, mid))
                            писем += 1
                break
            except Exception as ex:                             # noqa: BLE001
                if "locked" not in str(ex) and "busy" not in str(ex):
                    print("   кусок не лёг: %s" % str(ex)[:110], flush=True)
                    break
                time.sleep(3.0)
    счёт["ПЕРЕПИСАНО карточек"] = карточек
    счёт["ПЕРЕПИСАНО тем писем"] = писем

print("=" * 74)
print("=== СМЕНА ТЕМЫ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("было:  %r" % БЫЛО)
print("стало: %r" % СТАЛО)
for к, в in счёт.most_common(12):
    print("   %-48s %5d" % (к, в))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Сменить — --primenit")
