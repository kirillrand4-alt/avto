# -*- coding: utf-8 -*-
"""Привести текст письма в ПАНЕЛИ карточки к тому, что реально уйдёт.

Текст письма лежит в карточке трижды: confirm_reviews.body (его берёт
отправка) и внутри panel_json - letter.body и letter.final_body (их видит
оператор). Замена текста 08.09 поправила только первое. Это хуже, чем
«не обновилось»: оператор подтверждал бы старое письмо, а уходило бы новое.

final_body собирается тем же правилом, что и в infopanel._letter_block:
подпись приклеивается через пустую строку, а если тело уже кончается на
«С уважением,», эта строка второй раз не печатается.

highlights - подсветка фрагментов в теле. Те, что в новом тексте не
встречаются, выбрасываем: подсветка по несуществующему куску либо не
покажет ничего, либо подсветит не то.

    python pochinit_panel_agro.py            # вхолостую
    python pochinit_panel_agro.py --primenit
    python pochinit_panel_agro.py --sverit    # сверить с заново собранной панелью
"""
import io
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
СВЕРИТЬ = "--sverit" in sys.argv
СНИМОК = (r"C:\sender\_ops\agro-panel-do-pravki-"
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


store = Store(r"C:\sender\sender.db")
счёт = Counter()
правки = []
with store._lock:
    строки = store._conn.execute(
        "SELECT id, status, email, body, panel_json FROM confirm_reviews "
        " WHERE subject=?", (ТЕМА,)).fetchall()

for р in строки:
    счёт["карточек всего"] += 1
    if str(р["status"]) != "pending":
        счёт["не pending — не трогаем"] += 1
        continue
    тело = str(р["body"] or "")
    try:
        панель = json.loads(р["panel_json"] or "{}")
    except Exception:                                           # noqa: BLE001
        счёт["panel_json не читается"] += 1
        continue
    письмо = панель.get("letter")
    if not isinstance(письмо, dict):
        счёт["в панели нет блока letter"] += 1
        continue
    if str(письмо.get("body") or "") == тело:
        счёт["панель уже верная"] += 1
        continue
    низ = тело.lower()
    подсветка = [h for h in (письмо.get("highlights") or [])
                 if isinstance(h, dict)
                 and str(h.get("text") or "").lower() in низ]
    счёт["подсветок выброшено"] += (len(письмо.get("highlights") or [])
                                    - len(подсветка))
    новое = dict(письмо)
    новое["body"] = тело
    новое["final_body"] = собрать_final(тело, письмо.get("signature"))
    новое["highlights"] = подсветка
    панель["letter"] = новое
    правки.append((int(р["id"]), str(р["email"] or ""), р["panel_json"],
                   json.dumps(панель, ensure_ascii=False)))
    счёт["К ПРАВКЕ"] += 1

if ПРИМЕНИТЬ and правки:
    with io.open(СНИМОК, "w", encoding="utf-8") as ф:
        for rid, поч, было, _стало in правки:
            ф.write(json.dumps({"review_id": rid, "почта": поч,
                                "panel_json_до": было},
                               ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())
    счёт["снимок сохранён"] = len(правки)
    сделано = 0
    for нач in range(0, len(правки), 500):
        кусок = правки[нач:нач + 500]
        for _ in range(20):
            try:
                with store.transaction() as conn:
                    for rid, _п, _б, стало in кусок:
                        conn.execute(
                            "UPDATE confirm_reviews SET panel_json=?, "
                            "       updated_at=datetime('now') "
                            " WHERE id=? AND status='pending'", (стало, rid))
                сделано += len(кусок)
                break
            except Exception as ex:                             # noqa: BLE001
                if "locked" not in str(ex) and "busy" not in str(ex):
                    print("   кусок не лёг: %s" % str(ex)[:100], flush=True)
                    break
                time.sleep(3.0)
    счёт["ПЕРЕПИСАНО"] = сделано

# СВЕРКА С ЗАНОВО СОБРАННОЙ ПАНЕЛЬЮ. Правка хирургическая: меняю только блок
# letter. Проверяю на живых карточках, что остальные блоки от текста письма
# не зависят - иначе хирургии мало и надо пересобирать панель целиком.
if СВЕРИТЬ:
    from datetime import date
    from sender.ai_quota import build_ai_quota                   # noqa: E402
    from sender.config import Config                            # noqa: E402
    cfg = Config.load(r"C:\sender\sender.yaml")
    q = build_ai_quota(store, cfg)
    расхождения = Counter()
    проверено = 0
    with store._lock:
        обр = store._conn.execute(
            "SELECT id, recipient_id, body, panel_json FROM confirm_reviews "
            " WHERE subject=? AND status='pending' LIMIT 3", (ТЕМА,)).fetchall()
    for р in обр:
        rec = store.get_recipient(int(р["recipient_id"]))
        свежая = q._panel(rec, {"subject": ТЕМА, "body": str(р["body"] or ""),
                                "division": "meyer", "division_reason": "",
                                "rounds": []}, date.today().isoformat(), {})
        текущая = json.loads(р["panel_json"] or "{}")
        проверено += 1
        for k in set(list(свежая.keys()) + list(текущая.keys())):
            if k in ("letter", "quota_day", "history"):
                continue
            if json.dumps(свежая.get(k), ensure_ascii=False, sort_keys=True) != \
               json.dumps(текущая.get(k), ensure_ascii=False, sort_keys=True):
                расхождения[k] += 1
    print("--- сверка с заново собранной панелью (%d карточек) ---" % проверено)
    if расхождения:
        for k, v in расхождения.most_common():
            print("   блок %-22s расходится у %d из %d" % (k, v, проверено))
    else:
        print("   расхождений нет: от текста письма зависит только блок letter")

print("")
print("=" * 74)
print("=== ПАНЕЛЬ КАРТОЧКИ: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
for к, в in счёт.most_common():
    print("   %-34s %6d" % (к, в))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Поправить — --primenit")
