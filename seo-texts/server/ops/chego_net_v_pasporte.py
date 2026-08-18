# -*- coding: utf-8 -*-
"""Каких полей паспорта не хватает — по компаниям нашей партии.

Паспорт до промпта доезжает (проверено), и промпт им пользуется. Значит
вопрос не «видел ли», а «что там лежит». Письмо говорит про цеха и
процессы; в паспорте за это отвечает ключ «оборудование_линии». Считаем
заполненность каждого ключа отдельно у «годных» и у «не годных» писем.
"""
import io
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ENRICH = r"C:\sender\enrich.db"
КЛЮЧИ = ("продукция", "оборудование_линии", "мощности", "контроль_качества",
         "сырьё", "упаковка_фасовка", "экспорт", "география_поставок",
         "масштаб", "новости")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

вердикт = {}
for s in io.open(r"C:\sender\_ops\rezenzii-pisem.jsonl", encoding="utf-8",
                 errors="replace"):
    try:
        z = json.loads(s)
        вердикт[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        continue

with store._lock:
    ряд = store._conn.execute(
        "SELECT id, inn FROM confirm_reviews WHERE campaign_id=10 "
        "AND inn IS NOT NULL").fetchall()

con = sqlite3.connect(f"file:{ENRICH}?mode=ro", uri=True, timeout=10)
кэш = {}
свод = {"годно": Counter(), "не годно": Counter(), "(без вердикта)": Counter()}
всего = Counter()
for cid, inn in ряд:
    в = вердикт.get(int(cid)) or "(без вердикта)"
    if в not in свод:
        continue
    i = str(inn).strip()
    if i not in кэш:
        r = con.execute("SELECT facts_json FROM site_facts WHERE inn=?",
                        (i,)).fetchone()
        try:
            кэш[i] = json.loads(r[0]) if r and r[0] else {}
        except Exception:                                        # noqa: BLE001
            кэш[i] = {}
    п = кэш[i]
    всего[в] += 1
    for k in КЛЮЧИ:
        v = п.get(k)
        if v and (not isinstance(v, (list, str)) or len(v) > 0):
            свод[в][k] += 1
con.close()

print(f"{'ключ паспорта':<24} {'годно':>12} {'не годно':>12}")
for k in КЛЮЧИ:
    г = свод["годно"][k]
    н = свод["не годно"][k]
    вг = 100.0 * г / max(1, всего["годно"])
    вн = 100.0 * н / max(1, всего["не годно"])
    print(f"  {k:<22} {г:>5} ({вг:>4.0f}%) {н:>5} ({вн:>4.0f}%)")
print(f"\nписем: годно {всего['годно']}, не годно {всего['не годно']}, "
      f"без вердикта {всего['(без вердикта)']}")
