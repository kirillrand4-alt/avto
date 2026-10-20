# -*- coding: utf-8 -*-
"""Стоп-флаг повторного контакта — 30 дней и только ТЕМ ЖЕ направлением
(владелец 20.10: «30 дней только по тому направлению, к которому письмо
относится, нужен флаг только»). Было: любой контакт с компанией <90 дней.

1) Правка infopanel._stop_flags по якорю (бэкап .bak-povtor30-*, py_compile,
   откат при сбое). Вступит в силу после Restart-Service SenderPanel -Force и
   в новых прогонах генерации (они грузят модуль заново).
2) --kartochki: пересчитать флаг у карточек «Подтвердить отправку» (pending):
   поставить тем, где тем же направлением писали <30 дней, снять остальным.
   Старый panel_json — в _ops/flag-povtora-30.jsonl.

    flag_povtora_30.py [--primenit] [--kartochki] | --otkat"""
import glob
import io
import json
import py_compile
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

П = r"C:\sender\sender\infopanel.py"
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-povtor30-*"))[-1]
    shutil.copy2(б, П)
    print("откат кода из", б)
    sys.exit()

С = '''    if history.get("recent_90d"):
        last = history.get("last") or {}
        flags.append({"code": "recent_contact",
                      "label": f"контакт <90 дн ({str(last.get('ts', ''))[:10]})",
                      "severity": "red"})
    return flags'''
Н = '''    # ПОВТОРНЫЙ КОНТАКТ (владелец 20.10): флаг — только если ТЕМ ЖЕ
    # направлением писали меньше 30 дней назад. Письмо другого направления
    # (КЦ после Meyer и наоборот) и контакт старше 30 дней — не стоп.
    _когда = povtor_toy_zhe_napr(store, history, body)
    if _когда:
        flags.append({"code": "recent_contact",
                      "label": f"контакт <30 дн тем же направлением ({_когда[:10]})",
                      "severity": "red"})
    return flags


def _napr_kampanii(store, campaign_id, subject) -> Optional[str]:
    """kc|meyer|None — направление прошлого письма: имя кампании, иначе лексика темы."""
    имя = ""
    try:
        with store._lock:
            р = store._conn.execute("SELECT name FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        имя = str(р[0] if р else "").lower()
    except Exception:  # noqa: BLE001
        pass
    if "meyer" in имя or "мейер" in имя:
        return "meyer"
    if "кц" in имя or "935" in имя or "металл" in имя or "компрессор" in имя:
        return "kc"
    from sender.napravlenie_pisma import po_leksike
    return po_leksike(subject)


def povtor_toy_zhe_napr(store, history, body, dney: int = 30) -> Optional[str]:
    """Дата последней отправки ТЕМ ЖЕ направлением в окне dney — или None."""
    from sender.napravlenie_pisma import po_leksike
    моё = po_leksike(body)
    граница = datetime.now(timezone.utc).timestamp() - dney * 86400
    for it in (history or {}).get("items") or []:
        if str(it.get("outcome") or "") not in ("sent", ""):
            continue
        try:
            ts = datetime.fromisoformat(str(it.get("ts") or "").replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts.timestamp() < граница:
            continue
        его = _napr_kampanii(store, it.get("campaign_id"), it.get("subject"))
        if моё is None or его is None or его == моё:
            return str(it.get("ts") or "")
    return None'''

т = io.open(П, encoding="utf-8").read()
if "povtor_toy_zhe_napr" in т:
    print("код: УЖЕ БЫЛО")
elif т.count(С) != 1:
    print("код: якорь найден %d раз — НЕ ПРИМЕНЕНО" % т.count(С))
    sys.exit(1)
elif "--primenit" in sys.argv:
    б = П + ".bak-povtor30-%d" % int(time.time())
    shutil.copy2(П, б)
    io.open(П, "w", encoding="utf-8").write(т.replace(С, Н))
    try:
        py_compile.compile(П, doraise=True)
    except Exception as е:  # noqa: BLE001
        shutil.copy2(б, П)
        print("откат, не компилируется:", е)
        sys.exit(1)
    print("код: ПРИМЕНЕНО, бэкап", б)
else:
    print("код: сухой прогон, якорь найден")

if "--kartochki" not in sys.argv:
    sys.exit()
sys.path.insert(0, r"C:\sender")
import importlib  # noqa: E402
import sender.infopanel as ip  # noqa: E402
importlib.reload(ip)
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
поставить, снять, всего = 0, 0, 0
правки = []
for rid, inn, em, body, pj in c.execute("SELECT id, inn, email, body, panel_json FROM confirm_reviews "
                                         "WHERE status='pending' AND COALESCE(kind,'outbound')!='reply'").fetchall():
    всего += 1
    p = json.loads(pj or "{}")
    hist = ip._history_block(store, inn, em)
    когда = ip.povtor_toy_zhe_napr(store, hist, body) if hasattr(ip, "povtor_toy_zhe_napr") else None
    флаги = [f for f in (p.get("stop_flags") or []) if not (isinstance(f, dict) and f.get("code") == "recent_contact")]
    было = any(isinstance(f, dict) and f.get("code") == "recent_contact" for f in (p.get("stop_flags") or []))
    if когда:
        флаги.append({"code": "recent_contact", "label": "контакт <30 дн тем же направлением (%s)" % когда[:10],
                      "severity": "red"})
    if bool(когда) != было:
        if когда:
            поставить += 1
        else:
            снять += 1
        a = dict(p.get("actions") or {})
        a["confirm_hold"] = bool(флаги)
        p["actions"] = a
        p["stop_flags"] = флаги
        правки.append((rid, pj, json.dumps(p, ensure_ascii=False)))
print("карточек pending: %d | флаг поставить: %d | снять: %d" % (всего, поставить, снять))
if "--primenit" in sys.argv:
    with c, io.open(r"C:\sender\_ops\flag-povtora-30.jsonl", "a", encoding="utf-8") as ж:
        for rid, старый, новый in правки:
            ж.write(json.dumps({"id": rid, "panel_json": старый, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                               ensure_ascii=False) + "\n")
            c.execute("UPDATE confirm_reviews SET panel_json=? WHERE id=? AND status='pending'", (новый, rid))
    print("карточки: ПРИМЕНЕНО")
