# -*- coding: utf-8 -*-
"""Насколько точнее гейт адресата, когда видит паспорт сайта.

Берём тех же компаний, что гейт снял РАНЬШЕ (вердикт лежит в
target_verdicts), и судим заново — теми же двумя линзами, но с паспортом
в промпте. Кэш не спрашиваем и не пишем: зовём _партия напрямую, иначе
вернётся старый вердикт по ИНН.

Печатаем рядом: что гейт говорил тогда и что говорит теперь.
"""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.target_gate import (НЕ_ПОКУПАТЕЛЬ, НЕЯСНО,           # noqa: E402
                                ПОКУПАТЕЛЬ)

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "10"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
гейт = q._gate()
if гейт is None:
    print("гейт не собрался")
    raise SystemExit(2)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT tv.inn, tv.verdict, COALESCE(tv.chem,'') chem, "
    "       COALESCE(tv.pochemu,'') pochemu, "
    "       (SELECT company_name FROM recipients WHERE inn=tv.inn LIMIT 1) имя, "
    "       (SELECT okved FROM recipients WHERE inn=tv.inn LIMIT 1) оквэд "
    "FROM target_verdicts tv WHERE tv.verdict NOT IN ('покупатель','buyer') "
    "ORDER BY tv.ts DESC LIMIT ?", (СКОЛЬКО,)).fetchall()

компании = []
старое = {}
for r in ряды:
    инн = str(r["inn"])
    карточка = q._card_for(инн) or {}
    ec = (карточка.get("enrich") or {}).get("company") or {}
    компании.append({
        "inn": инн,
        "name": str(r["имя"] or "") or ec.get("name") or "",
        "okved": str(r["оквэд"] or "") or ec.get("okved") or "",
        "activity": ec.get("activity") or "",
        "pasport": q._pasport_dlya_geyta(инн),
    })
    старое[инн] = (str(r["verdict"]), str(r["pochemu"])[:120])

с_паспортом = sum(1 for к in компании if к["pasport"])
print(f"компаний: {len(компании)} | с паспортом: {с_паспортом}")

п = гейт._партия(компании, "продавец")
с = гейт._партия(компании, "скептик")

счёт = Counter()
print()
for к in компании:
    инн = к["inn"]
    вп = (п.get(инн) or {}).get("verdict")
    вс = (с.get(инн) or {}).get("verdict")
    if вп == вс == НЕ_ПОКУПАТЕЛЬ:
        новый = НЕ_ПОКУПАТЕЛЬ
    elif ПОКУПАТЕЛЬ in (вп, вс):
        новый = ПОКУПАТЕЛЬ
    else:
        новый = НЕЯСНО
    было, почему = старое[инн]
    метка = "ТО ЖЕ" if новый == было else "ИЗМЕНИЛСЯ"
    счёт[f"{было} -> {новый}"] += 1
    print(f"  {метка:<10} {str(к['name'])[:36]:<36} "
          f"было «{было}» стало «{новый}»  (продавец={вп}, скептик={вс})")
    if новый != было:
        поч = ((п.get(инн) or {}).get("pochemu")
               or (с.get(инн) or {}).get("pochemu") or "")
        print(f"             теперь: {str(поч)[:170]}")
        print(f"             было:   {почему}")

print("\nсводка переходов:", dict(счёт))
