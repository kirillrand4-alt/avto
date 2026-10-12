# -*- coding: utf-8 -*-
"""609 тупиков: паспорт из книги — новый или он и так был полный?

Владелец 12.10: «а по ним есть наиболее полный паспорт или он и так был
полный?». Сравниваем, что про эти компании знает обогащение СЕЙЧАС и что
даёт книга: пустой/короткий паспорт в enrich = письмо им писали «вслепую»,
и повторное письмо будет содержательно другим.
"""
import glob
import io
import json
import sqlite3
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

по_компании = {}
for а in адреса:
    по_компании.setdefault(а["inn"], []).append(а)

store = Store(r"C:\sender\sender.db")
все = {а["email"] for а in адреса} | {
    str(к.get("pismo") or "") for к in компании if к.get("pismo")}
все.discard("")
ушло = set()
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

тупики = []
for к in компании:
    выбран = str(к.get("pismo") or "").strip().lower()
    if not выбран or выбран not in ушло:
        continue
    свои = [а for а in по_компании.get(к["inn"], [])
            if а["email"] not in ушло and а["email"] != выбран
            and "не для письма" not in str(а.get("role") or "").lower()]
    if not свои:
        тупики.append(к)
print("тупиков (замены нет): %d" % len(тупики))

cx = sqlite3.connect(r"C:\sender\enrich.db")
cx.row_factory = sqlite3.Row
колонки = {р["name"] for р in cx.execute("PRAGMA table_info(companies)")}
поле_акт = "activity" if "activity" in колонки else None
поле_факт = "site_facts" if "site_facts" in колонки else None
print("колонки companies, что нас интересует: activity=%s site_facts=%s okved=%s"
      % (поле_акт, поле_факт, "okved" in колонки))

свод = Counter()
дл_было, дл_будет = [], []
примеры = []
for к in тупики:
    р = cx.execute("SELECT * FROM companies WHERE inn=?", (к["inn"],)).fetchone()
    книга = str(к.get("activity") or "")
    дл_будет.append(len(книга))
    if р is None:
        свод["компании в обогащении НЕТ вовсе"] += 1
        дл_было.append(0)
        if len(примеры) < 6:
            примеры.append((к["name"], 0, len(книга)))
        continue
    было = str((р[поле_акт] if поле_акт else "") or "")
    факты = str((р[поле_факт] if поле_факт else "") or "")
    стар = max(len(было), len(факты))
    дл_было.append(стар)
    if стар < 40:
        свод["паспорта не было (пусто/обрывок)"] += 1
    elif len(книга) > стар * 3 // 2:
        свод["паспорт был, книга заметно полнее"] += 1
    elif len(книга) > стар:
        свод["паспорт был, книга чуть полнее"] += 1
    else:
        свод["книга не добавляет (было не хуже)"] += 1
    if len(примеры) < 6 and стар < 40:
        примеры.append((к["name"], стар, len(книга)))
cx.close()

print("")
for кл, n in свод.most_common():
    print("   %-42s %5d" % (кл, n))


def срез(сп):
    сп = sorted(сп)
    if not сп:
        return "нет"
    return "мин %d, медиана %d, макс %d, пустых %d" % (
        сп[0], сп[len(сп) // 2], сп[-1], sum(1 for x in сп if x < 40))


print("")
print("   длина паспорта БЫЛО:  %s" % срез(дл_было))
print("   длина паспорта БУДЕТ: %s" % срез(дл_будет))
print("")
print("--- примеры: писали без паспорта, теперь он есть ---")
for имя, б, н in примеры:
    print("   %-38s было %4d симв → станет %4d" % (str(имя)[:38], б, н))
print("")
print("=" * 74)
print("=== ПАСПОРТ 609 ТУПИКОВ ===")
print("   всего тупиков:                      %5d" % len(тупики))
print("   писали ВСЛЕПУЮ (паспорта не было):  %5d"
      % (свод.get("компании в обогащении НЕТ вовсе", 0)
         + свод.get("паспорта не было (пусто/обрывок)", 0)))
print("   книга заметно полнее прежнего:      %5d"
      % свод.get("паспорт был, книга заметно полнее", 0))
print("   книга ничего не добавляет:          %5d"
      % свод.get("книга не добавляет (было не хуже)", 0))
