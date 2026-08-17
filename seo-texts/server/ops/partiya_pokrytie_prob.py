# -*- coding: utf-8 -*-
"""Сколько адресов партии 935 реально имеют вердикт пробы и насколько свежий.

Пункт «проверить, что VPS проверил все почты полностью». Меряем по базе
панели (`addr_probe`), но с оговоркой, из-за которой 1-я сессия ошиблась:
поле `ts` в `addr_probe` - это время ЗАПИСИ В КЭШ, а не время пробы. Когда
вердикты приезжают из накопительного файла работника VPS, `ts` ставится
заново при каждом перечитывании файла, и весь архив выглядит свежим.

Поэтому:
  * покрытие («у скольких адресов вообще есть вердикт») по базе честное -
    оно про наличие, а не про время;
  * свежесть по `ts` НЕ доказывает, что проба была сегодня; её надо сверять
    с `probe-rezultat.jsonl` на дропе. Здесь считаем и то и другое и прямо
    показываем расхождение.

База только на чтение.
"""
import io
import json
import os
import sqlite3
import urllib.request
from collections import Counter

БАЗА = r"C:\sender\sender.db"
ГРУППА = "Партия 935"

conn = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row

# --- адреса партии -------------------------------------------------------
# Группа получателя = поле segment ПЛЮС список extra_json.gruppy (одно поле
# segment одно-значное, а компания бывает сразу в отраслевой партии и в
# новостной кампании). Колонки groups_json в таблице нет - её выдумывать
# нельзя, тут и упал первый заход.
группы = {}
for r in conn.execute("SELECT id, email, COALESCE(segment,'') AS segment, "
                      "COALESCE(extra_json,'') AS extra_json FROM recipients"):
    в_партии = (str(r["segment"]).strip() == ГРУППА) or (ГРУППА in r["extra_json"])
    if в_партии:
        e = str(r["email"] or "").strip().lower()
        if e:
            группы[e] = r["id"]
print(f"адресов в группе «{ГРУППА}»: {len(группы)} (различных почт)")

# --- вердикты ------------------------------------------------------------
проба = {}
for r in conn.execute("SELECT email, verdict, code, ts FROM addr_probe"):
    проба[str(r["email"] or "").strip().lower()] = dict(r)
print(f"строк в addr_probe всего: {len(проба)}")

есть = {e: проба[e] for e in группы if e in проба}
нет = [e for e in группы if e not in проба]
print(f"\nПОКРЫТИЕ: вердикт есть у {len(есть)} из {len(группы)} "
      f"({100 * len(есть) // max(1, len(группы))}%), без вердикта {len(нет)}")

вердикты = Counter(v["verdict"] for v in есть.values())
print("\nпо вердиктам:")
for в, n in вердикты.most_common():
    print(f"  {str(в)[:44]:<46} {n}")

по_дням = Counter(str(v["ts"])[:10] for v in есть.values())
print("\nпо ts в addr_probe (ВРЕМЯ ЗАПИСИ В КЭШ, не время пробы):")
for д in sorted(по_дням):
    print(f"  {д}  {по_дням[д]}")

# --- сверка с файлом работника на дропе ----------------------------------
print("\n--- сверка с probe-rezultat.jsonl на дропе ---")
try:
    req = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/probe-rezultat.jsonl",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(req, timeout=180) as r:
        сырое = r.read().decode("utf-8", "replace")
    дни = Counter()
    почты = set()
    поздний = ""
    for s in сырое.splitlines():
        s = s.strip()
        if not s:
            continue
        try:
            z = json.loads(s)
        except Exception:                                      # noqa: BLE001
            continue
        ts = str(z.get("ts") or "")
        дни[ts[:10]] += 1
        почты.add(str(z.get("email") or "").strip().lower())
        поздний = max(поздний, ts)
    print(f"строк в файле работника: {sum(дни.values())}, "
          f"различных почт: {len(почты)}")
    print("по дням:", dict(sorted(дни.items())))
    print("самый поздний вердикт работника:", поздний or "нет")
    наши_у_работника = sum(1 for e in группы if e in почты)
    print(f"адресов партии, встречающихся у работника: {наши_у_работника} "
          f"из {len(группы)}")
    print(f"адресов партии с вердиктом в базе, но НЕ у работника: "
          f"{sum(1 for e in есть if e not in почты)} "
          f"(эти проверены не работником VPS, а иначе)")
except Exception as ex:                                        # noqa: BLE001
    print("файл работника не прочитался:", str(ex)[:200])

# --- что это значит для отправки ----------------------------------------
годные = {"есть", "принимает всё"}
можно = sum(1 for v in есть.values()
            if any(g in str(v["verdict"]).lower() for g in годные))
print(f"\nадресов партии с вердиктом, годным под отправку: {можно}")
print(f"адресов партии БЕЗ вердикта вовсе: {len(нет)}")
if нет:
    print("  первые 10 без вердикта:", sorted(нет)[:10])
