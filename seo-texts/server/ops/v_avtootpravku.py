# -*- coding: utf-8 -*-
"""Перевести письма первой партии в автоотправку — тем же путём, что кнопка
панели «/confirm/bulk-to-auto»: слот в окне получателя + confirm_decide
approved. НЕ approve() — тот при confirm.live_send шлёт немедленно, мимо
окна и темпа.

Владелец 28.08: «первая партия если прошла все проверки, можешь переводить
в автоотправку, я перезагрузил панель».

Берём ТОЛЬКО письма с вердиктом судьи «годно». «Поправить» держим: у них
известные огрехи (склонения, факты, обращение).

    v_avtootpravku.py [сколько] [--katit]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\sender")
sys.path.remove(r"C:\sender\sender")
sys.path.insert(1, r"C:\sender\sender")

КАТИТЬ = "--katit" in sys.argv
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "20"))
ПАРТИЯ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("partiya=")), "1")
_Х = "" if ПАРТИЯ == "1" else "-%s" % ПАРТИЯ
АДРЕСА = r"C:\sender\_ops\vtorye-adresa%s.jsonl" % _Х
ВЕРДИКТЫ = r"C:\sender\_ops\sud-vtoryh%s.jsonl" % _Х
СЛЕД = r"C:\sender\_ops\v-avtootpravku%s.jsonl" % _Х

партия = {}
for с in io.open(АДРЕСА, encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = str(d["inn"])
вердикт = {}
for с in io.open(ВЕРДИКТЫ, encoding="utf-8"):
    try:
        d = json.loads(с)
        вердикт[int(d["id"])] = str(d.get("verdikt") or "")
    except Exception:                                            # noqa: BLE001
        pass
годные = [r for r in партия if вердикт.get(r) == "годно"]
print("в партии %d, вердиктов %d, «годно» %d" % (len(партия), len(вердикт), len(годные)))

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
from sender.auto_send import ENABLED_KEY, next_slot, recipient_tz_name, window_from  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
вкл = store.get_setting(ENABLED_KEY, None)
print("цикл автоотправки включён: %r" % вкл)
win = window_from(store, cfg)
now = datetime.now(timezone.utc)
print("окно: %s" % str(win)[:150])

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(годные))
строки = c.execute(
    "SELECT id, inn, email, recipient_id, message_id, campaign_id, panel_json "
    "  FROM confirm_reviews WHERE id IN (%s) AND status='pending' "
    " ORDER BY id" % зн, годные).fetchall()
c.close()
print("из «годных» ещё в очереди: %d" % len(строки))

сделано = set()
if os.path.exists(СЛЕД):
    for с in io.open(СЛЕД, encoding="utf-8", errors="replace"):
        try:
            сделано.add(int(json.loads(с)["review"]))
        except Exception:                                        # noqa: BLE001
            pass
итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8") if КАТИТЬ else None
взято = 0
for r in строки:
    if взято >= СКОЛЬКО:
        break
    rid = int(r["id"])
    if rid in сделано:
        итог["уже переведено"] += 1
        continue
    try:
        панель = json.loads(r["panel_json"] or "{}") or {}
    except Exception:                                            # noqa: BLE001
        панель = {}
    if ((панель.get("actions") or {}).get("confirm_hold")):
        итог["стоп-флаг карточки"] += 1
        continue
    блок = None
    try:
        блок = cs._guard(inn=r["inn"], email=r["email"] or "")
    except Exception as ex:                                      # noqa: BLE001
        блок = "заслон не отработал: %s" % str(ex)[:40]
    if блок:
        итог["заслон: " + str(блок)[:40]] += 1
        continue
    try:
        дб = cs._division_blocked(dict(r))
    except Exception:                                            # noqa: BLE001
        дб = None
    if дб:
        итог["гейт направлений"] += 1
        continue
    rec = store.get_recipient(int(r["recipient_id"])) if r["recipient_id"] else None
    if rec is None or r["message_id"] is None:
        итог["нет получателя/письма"] += 1
        continue
    взято += 1
    if not КАТИТЬ:
        итог["перевели бы"] += 1
        continue
    try:
        слот = next_slot(win, recipient_tz_name(win, rec), now)
        store.reschedule_message(int(r["message_id"]), слот)
        # «КОПИЯ НА ВТОРОЙ АДРЕС» В ПРИЧИНЕ — НЕ УКРАШЕНИЕ. Цикл автоотправки
        # держит СВОЙ заслон «уже писали» и без этих слов сверяет по ИНН, а у
        # компании отправка уже есть — первое письмо. Из первых 470 он молча
        # снял 31. Слова включают предусмотренную в нём ветку «спрашиваем
        # только адрес»: тому же адресу дважды не пишем никогда.
        ок = store.confirm_decide(
            rid, status="approved", decided_by="партия вторых адресов",
            reason="bulk-to-auto: копия на второй адрес (судья: годно)")
        итог["переведено" if ок else "решение не легло"] += 1
        if ок:
            поток.write(json.dumps(
                {"review": rid, "email": r["email"], "slot": str(слот),
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
    except Exception as ex:                                      # noqa: BLE001
        итог["ошибка: " + str(ex)[:44]] += 1
if поток:
    поток.close()
print("")
for к, n in итог.most_common():
    print("   %-44s %5d" % (к, n))
