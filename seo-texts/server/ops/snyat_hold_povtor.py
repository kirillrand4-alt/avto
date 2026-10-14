# -*- coding: utf-8 -*-
"""Снять «удержание» карточки (confirm_hold) у писем очереди, где единственный
стоп-флаг — recent_contact, а повтор по правилам владельца разрешён (владелец
14.10: «попробуй ещё раз»). Для каждого письма заново:
  * штатный заслон адреса ConfirmSend._recent_contact (с _povtor_razreshen)
    пропускает — адрес не писали в окне или повтор разрешён правилом 13.10;
  * компания нам не отвечала (ConfirmSend._otvechali);
  * адрес не в стоп-листе.
Флаги site_mismatch / mx_dead / стоп-лист НЕ трогаем.
Резерв старой панели — _ops/snyat-hold-povtor.jsonl (fsync) до записи.

    snyat_hold_povtor.py [--primenit]   (без флага — сухой прогон)
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

ПРИМ = "--primenit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
supp = Suppression(store)
cs = ConfirmSend(cfg, store, supp)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row


def в_стоп_листе(email, inn):
    """Штатная проверка стоп-листа: email → домен → ИНН."""
    from types import SimpleNamespace
    return supp.is_suppressed(SimpleNamespace(email=email, domain=None, inn=inn)) is not None


св, правки = Counter(), []
for р in c.execute("SELECT id, campaign_id, inn, email, panel_json FROM confirm_reviews WHERE status='pending'"):
    try:
        п = json.loads(р["panel_json"] or "{}")
    except Exception:  # noqa: BLE001
        continue
    if not (п.get("actions") or {}).get("confirm_hold"):
        continue
    коды = {f.get("code") for f in (п.get("stop_flags") or [])}
    if коды != {"recent_contact"}:
        св["другие флаги, не трогаем: " + ",".join(sorted(str(x) for x in коды))] += 1
        continue
    if cs._recent_contact(email=р["email"]) is not None:
        св["адрес писали в окне, повтор правилом не разрешён"] += 1
        continue
    if cs._otvechali(р["inn"]):
        св["компания отвечала"] += 1
        continue
    if в_стоп_листе(р["email"], р["inn"]):
        св["стоп-лист"] += 1
        continue
    св["снять удержание"] += 1
    стар = р["panel_json"]
    п["stop_flags"] = [f for f in (п.get("stop_flags") or []) if f.get("code") != "recent_contact"]
    п.setdefault("actions", {})["confirm_hold"] = False
    п["povtor_razreshen"] = ("контакт компании < 90 дн, повтор по правилу владельца 13.10 "
                             "(удержание снято %s)" % time.strftime("%d.%m %H:%M"))
    правки.append((р["id"], стар, json.dumps(п, ensure_ascii=False)))

print("свод: %s" % dict(св.most_common()))
if ПРИМ and правки:
    with io.open(r"C:\sender\_ops\snyat-hold-povtor.jsonl", "a", encoding="utf-8") as ж:
        for rid, стар, _н in правки:
            ж.write(json.dumps({"review_id": rid, "panel_bylo": стар}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    n = 0
    for rid, _с, нов in правки:
        n += c.execute("UPDATE confirm_reviews SET panel_json=?, updated_at=? WHERE id=? AND status='pending'",
                       (нов, time.strftime("%Y-%m-%dT%H:%M:%S"), rid)).rowcount
    c.commit()
    print("снято удержание: %d" % n)
print("=== СНЯТЬ HOLD: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
