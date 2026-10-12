# -*- coding: utf-8 -*-
"""Кому писать, если выбранный адрес уже использован: следующий по лесенке.

Владелец 12.10: «тут берём следующий адрес по приоритету, если совсем нет
адресов следующих — напиши сколько таких будет».

Порядок задаёт та же лестница, что и в панели: lead_scoring._rol_ball.
Использованным считаем адрес, на который письмо УХОДИЛО (status='sent'),
а не просто заведённый в получателях.
"""
import glob
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
from sender.store import Store                                  # noqa: E402
try:
    from lead_scoring import _rol_ball                          # noqa: E402
except Exception:                                               # noqa: BLE001
    def _rol_ball(р):
        return 0

компании, адреса = [], []
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi_*.json")):
    д = json.load(io.open(п, encoding="utf-8"))
    компании.extend(д.get("компании") or [])
    адреса.extend(д.get("адреса") or [])
print("прочитано: компаний %d, адресов %d" % (len(компании), len(адреса)))

по_компании = {}
for а in адреса:
    по_компании.setdefault(а["inn"], []).append(а)

store = Store(r"C:\sender\sender.db")
все_адреса = {а["email"] for а in адреса}
все_адреса |= {str(к.get("pismo") or "") for к in компании if к.get("pismo")}
все_адреса.discard("")
ушло = set()
with store._lock:
    c = store._conn
    сп = list(все_адреса)
    for н in range(0, len(сп), 400):
        куски = сп[н:н + 400]
        м = ",".join("?" * len(куски))
        for р in c.execute(
                "SELECT DISTINCT lower(r.email) e FROM messages m "
                "  JOIN recipients r ON m.recipient_id = r.id "
                " WHERE m.status='sent' AND lower(r.email) IN (" + м + ")",
                куски):
            ушло.add(р["e"])
print("адресов из книг, на которые письмо уже уходило: %d" % len(ушло))

свод = Counter()
замены, тупики = [], []
for к in компании:
    выбран = str(к.get("pismo") or "").strip().lower()
    свои = по_компании.get(к["inn"], [])
    if not выбран:
        свод["адреса письма не было вовсе"] += 1
        continue
    if выбран not in ушло:
        свод["выбранный адрес свободен"] += 1
        continue
    # ищем следующий по лесенке, которым ещё не писали
    кандидаты = sorted(
        (а for а in свои
         if а["email"] not in ушло and а["email"] != выбран
         and "не для письма" not in str(а.get("role") or "").lower()),
        key=lambda а: -_rol_ball(а.get("role")))
    if кандидаты:
        свод["нашлась замена"] += 1
        замены.append((к["name"], выбран, кандидаты[0]["email"],
                       кандидаты[0].get("role")))
    else:
        свод["ЗАМЕНЫ НЕТ — все адреса использованы"] += 1
        тупики.append((к["name"], выбран, len(свои)))

print("")
for кл, n in свод.most_common():
    print("   %-44s %5d" % (кл, n))
print("")
print("--- примеры замен ---")
for имя, было, стало, роль in замены[:8]:
    print("   %-30s %-28s → %-28s %s"
          % (str(имя)[:30], было[:28], стало[:28], str(роль)[:22]))
print("")
print("--- примеры тупиков (замены нет) ---")
for имя, было, сколько in тупики[:8]:
    print("   %-34s %-30s адресов у компании: %d"
          % (str(имя)[:34], было[:30], сколько))
print("")
print("=" * 74)
print("=== СЛЕДУЮЩИЙ АДРЕС ПО ЛЕСЕНКЕ ===")
print("   компаний в книгах:            %5d" % len(компании))
print("   выбранный адрес уже использован: %4d"
      % (свод.get("нашлась замена", 0)
         + свод.get("ЗАМЕНЫ НЕТ — все адреса использованы", 0)))
print("   из них замена найдена:        %5d" % свод.get("нашлась замена", 0))
print("   из них писать НЕКОМУ:         %5d"
      % свод.get("ЗАМЕНЫ НЕТ — все адреса использованы", 0))
