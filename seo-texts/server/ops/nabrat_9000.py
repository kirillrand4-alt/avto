# -*- coding: utf-8 -*-
"""Набрать партию 9000 из книг паспортов.

Владелец 12.10:
  * `segment` = отрасль, группа 9000 живёт в `extra_json.gruppy` — партию
    можно брать и по отрасли, и целиком;
  * адрес уже отработан → берём следующий по лесенке ролей;
  * замены нет совсем → всё равно пишем повторно, если книга добавляет
    паспорт (их 595 из 609); у кого книга ничего не добавляет — мимо.

Направление кладём в extra_json явно: `segment` теперь отрасль, и вывести
по нему kc/meyer больше нельзя.

Запуск: nabrat_9000.py [--primenit]   (без флага — сухой прогон).
"""
import glob
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
from sender.store import Store                                  # noqa: E402
try:
    from lead_scoring import _rol_ball                          # noqa: E402
except Exception:                                               # noqa: BLE001
    def _rol_ball(р):
        return 0

ПРИМЕНИТЬ = "--primenit" in sys.argv
ГРУППА = "9000"
ЖУРНАЛ = r"C:\sender\_ops\partiya-9000.jsonl"

компании, адреса = [], []
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi2_*.json")):
    д = json.load(io.open(п, encoding="utf-8"))
    компании.extend(д.get("компании") or [])
    адреса.extend(д.get("адреса") or [])
по_компании = {}
for а in адреса:
    по_компании.setdefault(а["inn"], []).append(а)
print("книги: компаний %d, адресов %d" % (len(компании), len(адреса)))

store = Store(r"C:\sender\sender.db")
все = {а["email"] for а in адреса} | {
    str(к.get("pismo") or "") for к in компании if к.get("pismo")}
все.discard("")
ушло, в_базе = set(), {}
стоп_почта, стоп_инн = set(), set()
with store._lock:
    c = store._conn
    сп = list(все)
    for н in range(0, len(сп), 400):
        к_ = сп[н:н + 400]
        м = ",".join("?" * len(к_))
        for р in c.execute(
                "SELECT DISTINCT lower(r.email) e FROM messages m "
                " JOIN recipients r ON m.recipient_id = r.id "
                "WHERE m.status='sent' AND lower(r.email) IN (" + м + ")", к_):
            ушло.add(р["e"])
        for р in c.execute(
                "SELECT id, lower(email) e, segment, extra_json "
                "FROM recipients WHERE lower(email) IN (" + м + ")", к_):
            в_базе[р["e"]] = (р["id"], р["segment"], р["extra_json"])
        for р in c.execute(
                "SELECT value FROM suppression WHERE scope='email' "
                "AND lower(value) IN (" + м + ")", к_):
            стоп_почта.add(str(р["value"]).lower())
    инны = [к["inn"] for к in компании]
    for н in range(0, len(инны), 400):
        к_ = инны[н:н + 400]
        м = ",".join("?" * len(к_))
        for р in c.execute(
                "SELECT value FROM suppression WHERE scope='inn' "
                "AND value IN (" + м + ")", к_):
            стоп_инн.add(str(р["value"]))
print("уже писали адресов: %d, в получателях: %d, стоп: почт %d, ИНН %d"
      % (len(ушло), len(в_базе), len(стоп_почта), len(стоп_инн)))

cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
паспорт_был = {}
for н in range(0, len(инны), 400):
    к_ = инны[н:н + 400]
    м = ",".join("?" * len(к_))
    for р in cx.execute(
            "SELECT inn, activity FROM companies WHERE inn IN (" + м + ")", к_):
        паспорт_был[р["inn"]] = len(str(р["activity"] or ""))
cx.close()

свод = Counter()
набор = []
for к in компании:
    инн, отр = к["inn"], str(к.get("otrasl") or "")
    выбран = str(к.get("pismo") or "").strip().lower()
    if инн in стоп_инн:
        свод["мимо: ИНН в стоп-листе"] += 1
        continue
    if not выбран:
        свод["мимо: адреса письма в книге нет"] += 1
        continue
    повтор = False
    адрес = выбран
    if выбран in ушло:
        дальше = sorted(
            (а for а in по_компании.get(инн, [])
             if а["email"] not in ушло and а["email"] != выбран
             and "не для письма" not in str(а.get("role") or "").lower()),
            key=lambda а: -_rol_ball(а.get("role")))
        if дальше:
            адрес = дальше[0]["email"]
            свод["адрес заменён следующим по лесенке"] += 1
        else:
            # тупик: пишем повторно, только если книга добавляет паспорт
            было = паспорт_был.get(инн, 0)
            стало = len(str(к.get("activity") or ""))
            if стало < 40 or (было >= 40 and стало <= было * 3 // 2):
                свод["мимо: тупик, книга ничего не добавляет"] += 1
                continue
            повтор = True
            свод["тупик: повторное письмо по новому паспорту"] += 1
    else:
        свод["адрес как в книге"] += 1
    if адрес in стоп_почта:
        свод["мимо: адрес в стоп-листе"] += 1
        continue
    набор.append((к, адрес, повтор, отр))

print("")
for кл, n in свод.most_common():
    print("   %-44s %6d" % (кл, n))

по_отрасли = Counter(о for _, _, _, о in набор)
print("")
print("--- партия по отраслям (это и будет segment) ---")
for о, n in по_отрасли.most_common():
    print("   %-36s %6d" % (о[:36], n))

заведено = обновлено = 0
журнал = io.open(ЖУРНАЛ, "a", encoding="utf-8") if ПРИМЕНИТЬ else None
ts = int(time.time())
сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
with store._lock:
    c = store._conn
    for к, адрес, повтор, отр in набор:
        доп = {"gruppy": [ГРУППА], "division": "meyer", "otrasl": отр,
               "istochnik": "knigi-meyer7"}
        if к.get("klass"):
            доп["klass_somneniya"] = к["klass"]
        if повтор:
            доп["povtornoe"] = True
        if к.get("fio"):
            доп["fio"] = к["fio"]
        if к.get("dolzh"):
            доп["dolzhnost"] = к["dolzh"]
        есть = в_базе.get(адрес)
        if есть is None:
            заведено += 1
            if ПРИМЕНИТЬ:
                c.execute(
                    "INSERT INTO recipients (inn,email,domain,company_name,"
                    "okved,segment,contact_name,source,region,extra_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (к["inn"], адрес, адрес.split("@")[-1],
                     к.get("name"), к.get("okved"), отр, к.get("fio") or None,
                     "knigi-meyer7", к.get("region"),
                     json.dumps(доп, ensure_ascii=False), сейчас, сейчас))
        else:
            обновлено += 1
            if ПРИМЕНИТЬ:
                старое = {}
                try:
                    старое = json.loads(есть[2] or "{}") or {}
                except Exception:  # noqa: BLE001
                    старое = {}
                группы = [str(g) for g in (старое.get("gruppy") or [])]
                if ГРУППА not in группы:
                    группы.append(ГРУППА)
                старое.update(доп)
                старое["gruppy"] = группы
                c.execute("UPDATE recipients SET segment=?, extra_json=?,"
                          " updated_at=? WHERE id=?",
                          (отр, json.dumps(старое, ensure_ascii=False),
                           сейчас, есть[0]))
        if ПРИМЕНИТЬ:
            журнал.write(json.dumps(
                {"ts": ts, "inn": к["inn"], "email": адрес, "otrasl": отр,
                 "povtor": повтор, "novyy": есть is None},
                ensure_ascii=False) + "\n")
    if ПРИМЕНИТЬ:
        c.commit()
        журнал.flush()
        os.fsync(журнал.fileno())
        журнал.close()

print("")
print("=" * 70)
print("=== ПАРТИЯ 9000 ===")
print("   режим:                     %s"
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
print("   получателей в партии:      %6d" % len(набор))
print("     из них заведём заново:   %6d" % заведено)
print("     из них обновим в базе:   %6d" % обновлено)
print("   отраслей (segment):        %6d" % len(по_отрасли))
print("   повторных по новому паспорту: %3d"
      % свод.get("тупик: повторное письмо по новому паспорту", 0))
print("   журнал:                    %s" % ЖУРНАЛ)
