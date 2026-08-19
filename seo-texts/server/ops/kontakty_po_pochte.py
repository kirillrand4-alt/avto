# -*- coding: utf-8 -*-
"""Все контакты компании по адресу: телефоны, люди, сайт, карточка обзвона.

Оператору ответили с почты, а звонить некому - в письме телефона нет.
Собираем из всех баз разом: recipients, карточка обзвона (161к),
enrich.companies, site_facts, плюс другие адреса той же компании.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ПОЧТА = next((a for a in sys.argv[1:] if "@" in a), "")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

rec = store.find_recipient_by_email(ПОЧТА) or {}
if not rec:
    print("получателя с таким адресом нет")
    raise SystemExit(0)
инн = str(rec.get("inn") or "")
print(f"== {ПОЧТА} ==")
print(f"  компания: {rec.get('company_name')}")
print(f"  ИНН: {инн}   ОКВЭД: {rec.get('okved')}")
print(f"  контактное лицо в карточке: {rec.get('contact_name')!r}")
print(f"  регион: {rec.get('region')}   домен: {rec.get('domain')}")
try:
    ex = json.loads(rec.get("extra_json") or "{}")
except Exception:                                                # noqa: BLE001
    ex = {}
for к in ("phone", "phones", "телефон", "телефоны", "site", "сайт",
          "activity", "должность", "role"):
    if ex.get(к):
        print(f"  extra.{к}: {ex[к]}")

print("\n== другие адреса этой компании ==")
with store._lock:
    ряды = store._conn.execute(
        "SELECT id, email, COALESCE(contact_name,''), COALESCE(role_based,0) "
        "FROM recipients WHERE inn=?", (rec.get("inn"),)).fetchall()
for rid, email, имя, роль in ряды:
    print(f"  #{rid:<7} {str(email)[:38]:<40} {имя!r} "
          f"{'(ролевой)' if роль else ''}")

print("\n== карточка из базы обзвона ==")
карточка = q._card_for(инн) or {}
if not карточка:
    print("  карточки нет")
else:
    def _показать(d, префикс="  "):
        for k, v in (d or {}).items():
            if isinstance(v, dict):
                print(f"{префикс}{k}:")
                _показать(v, префикс + "  ")
            elif isinstance(v, list):
                if v and not isinstance(v[0], dict):
                    print(f"{префикс}{k}: {', '.join(str(x)[:60] for x in v[:6])}")
                else:
                    for э in v[:4]:
                        _показать(э if isinstance(э, dict) else {"": э},
                                  префикс + "  ")
            elif v not in (None, "", []):
                print(f"{префикс}{k}: {str(v)[:120]}")
    _показать(карточка)

print("\n== enrich: компания и паспорт сайта ==")
try:
    con = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True,
                          timeout=15)
    for таблица, поля in (("companies", "name, site, phone, activity"),
                          ("site_facts", "site, facts_json")):
        try:
            r = con.execute(
                f"SELECT {поля} FROM {таблица} WHERE inn=?", (инн,)).fetchone()
            print(f"  {таблица}: {str(r)[:600] if r else 'нет строки'}")
        except Exception as ex_:                                 # noqa: BLE001
            print(f"  {таблица}: {type(ex_).__name__} {str(ex_)[:80]}")
    con.close()
except Exception as ex_:                                         # noqa: BLE001
    print("  enrich не открылся:", str(ex_)[:100])
