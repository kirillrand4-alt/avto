# -*- coding: utf-8 -*-
"""Кто именно приехал в Партию 935 сегодня: род занятий, адреса, готовность.

«Добавилось 5381» само по себе ничего не значит. Важно, кому из них вообще
можно писать: род деятельности (медицина и розница уже снимались как «не
наш адресат»), есть ли ИНН и почта, и что о почте говорит проба.
"""
import json
import sqlite3
from collections import Counter

ДЕНЬ = "2026-08-24"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT r.id, r.email, r.company_name, r.inn, r.okved, r.region, r.source, "
    "       r.segment, COALESCE(r.extra_json,'') extra, r.mx_provider, "
    "       r.valid_status, r.catch_all, r.role_based, r.contact_name "
    "  FROM recipients r WHERE substr(r.created_at,1,10)=?", (ДЕНЬ,)).fetchall()
print(f"заведено {ДЕНЬ}: {len(ряды)}")
if not ряды:
    raise SystemExit(0)

print("\nсегменты:", dict(Counter(str(р["segment"] or "-") for р in ряды).most_common(6)))
print("источник:", dict(Counter(str(р["source"] or "-") for р in ряды).most_common(6)))
print("регионы (топ):", dict(Counter(str(р["region"] or "-")
                                     for р in ряды).most_common(8)))

def класс(оквэд):
    о = str(оквэд or "").strip()
    гр = о.split(".")[0] if о else ""
    имена = {"86": "медицина", "47": "розница", "46": "опт", "10": "пищепром",
             "25": "металлоизделия", "28": "машиностроение", "41": "стройка",
             "43": "строймонтаж", "01": "сельхоз", "68": "недвижимость",
             "49": "перевозки", "62": "IT", "71": "проектирование",
             "35": "энергетика", "36": "вода", "20": "химия", "22": "пластик",
             "23": "стройматериалы", "24": "металлургия", "16": "дерево",
             "11": "напитки", "13": "текстиль", "17": "бумага", "45": "авто"}
    return f"{гр} {имена.get(гр, '')}".strip() or "нет ОКВЭД"

print("\nрод занятий (по ОКВЭД, топ-16):")
for к, н in Counter(класс(р["okved"]) for р in ряды).most_common(16):
    print(f"  {н:>6}  {к}")

без_инн = sum(1 for р in ряды if not str(р["inn"] or "").strip())
без_почты = sum(1 for р in ряды if not str(р["email"] or "").strip())
роль = sum(1 for р in ряды if р["role_based"])
кэтч = sum(1 for р in ряды if р["catch_all"])
print(f"\nбез ИНН: {без_инн} | без почты: {без_почты} | "
      f"ролевой адрес: {роль} | catch-all: {кэтч}")
print("почтовик получателя:",
      dict(Counter(str(р["mx_provider"] or "-") for р in ряды).most_common(6)))

проба = {str(р["email"]).lower(): str(р["verdict"] or "")
         for р in c.execute("SELECT email, verdict FROM addr_probe") if р["email"]}
вердикты = Counter(проба.get(str(р["email"] or "").lower(), "не проверялся")
                   for р in ряды)
print("\nвердикт пробы по адресам:")
for в, н in вердикты.most_common():
    print(f"  {н:>6}  {в}")

# не наш адресат: вечный реестр по ИНН
try:
    не_наши = {str(р[0]) for р in c.execute("SELECT inn FROM ne_nash_adresat")}
    пересечение = sum(1 for р in ряды
                      if str(р["inn"] or "") in не_наши)
    print(f"\nсреди новых уже помечены «не наш адресат»: {пересечение}")
except Exception as ex:                                            # noqa: BLE001
    print(f"реестр «не наш адресат» не прочитан: {str(ex)[:60]}")
