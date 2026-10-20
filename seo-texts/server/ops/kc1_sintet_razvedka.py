# -*- coding: utf-8 -*-
"""КЦ-1 без ИНН — разведка перед синтетическими ИНН (владелец 20.10: «по
Meyer таким синтетические ИНН писали»). Только чтение:
  * какие синтетические ИНН уже есть в панели (вид, диапазон);
  * что в inn_raw у КЦ-1 без ИНН и есть ли эти ключи в панели у ДРУГИХ компаний;
  * где лежит исходный файл заливки (для данных компании)."""
import glob
import io
import json
import os
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
синт = [str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM recipients WHERE inn LIKE '000%' OR inn LIKE '999%'")]
print("синтетических ИНН в панели:", len(синт), "| вид:", Counter((len(i), i[:4]) for i in синт).most_common(6),
      "| мин/макс 000-ряда:", min((i for i in синт if i.startswith("000")), default=None), max((i for i in синт if i.startswith("000")), default=None))
домен_по_инн = {}
for inn, em in c.execute("SELECT inn, lower(email) FROM recipients WHERE inn LIKE '000%'"):
    домен_по_инн.setdefault(str(inn), set()).add(em.split("@")[-1])
сырьё = []
for rid, em, ex in c.execute("SELECT id, lower(email), extra_json FROM recipients WHERE inn IS NULL AND extra_json LIKE '%КЦ-1%'"):
    x = json.loads(ex or "{}")
    if "КЦ-1" in (x.get("gruppy") or []):
        сырьё.append((rid, em, str(x.get("inn_raw") or ""), x.get("site")))
print("КЦ-1 без ИНН:", len(сырьё))
совп = чужие = 0
for rid, em, raw, site in сырьё:
    if re.fullmatch(r"0{3,}\d+", raw):
        if raw in домен_по_инн:
            совп += 1
            if em.split("@")[-1] not in домен_по_инн[raw]:
                чужие += 1
print("ключ вида 000…: есть в панели у кого-то %d, из них на ДРУГОМ домене (коллизия) %d" % (совп, чужие))
print("двузначные и прочие примеры:", [r for _i, _e, r, _s in сырьё if not r.startswith("САЙТ") and not re.fullmatch(r"0{3,}\d+", r)][:15])
print("доменов-ключей уникальных среди САЙТ:", len({r for _i, _e, r, _s in сырьё if r.startswith("САЙТ")}))
for п in glob.glob(r"C:\seostat\drop\drop-storage\kc1*.json") + glob.glob(r"C:\sender\_ops\kc1*.json*"):
    print("файл:", п, os.path.getsize(п))
