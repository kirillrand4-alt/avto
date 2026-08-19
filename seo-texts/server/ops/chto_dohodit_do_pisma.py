# -*- coding: utf-8 -*-
"""Что РЕАЛЬНО доезжает до письма: обзвон, обогащение, паспорт сайта, текст.

Владелец: «проверь, что ты берёшь все данные необходимые, а именно включая
базу обзвона, все сквозные данные, которые пишутся в другие базы».

Проверяем не по коду, а по факту: собираем запрос ровно тем же вызовом, что
и генерация (AiQuota._request), и смотрим, какие источники в нём пусты.

Источники, которые обязаны сходиться в письме:
  obzvon-index.db  - карточка компании из базы обзвона на 161к (CompanyCards);
  enrich.db companies    - род деятельности с сайта (activity), выручка, роли;
  enrich.db site_facts   - паспорт предприятия (продукция, мощности, линии);
  enrich.db site_text    - живой текст сайта (правило 18.08: без него модель
                           выдумывает процессы);
  новость/повод          - если есть, письмо заходит от события;
  контактное лицо        - обращение по имени.

Заодно первая часть ответа: была ли база перезалита в момент дневного
прогона (11:45) - смотрим created_at/updated_at строк получателей.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

ГРУППА = "Партия 935"
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "150"))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

# --- 1. следы заливки вокруг дневного прогона ----------------------------
print("== строки получателей: когда трогали ==")
with store._lock:
    for имя, поле in (("создано", "created_at"), ("изменено", "updated_at")):
        ряд = store._conn.execute(
            f"SELECT substr(COALESCE({поле},''),1,13), COUNT(*) "
            f"FROM recipients WHERE {поле} >= '2026-08-18T09' "
            f"GROUP BY 1 ORDER BY 1").fetchall()
        print(f"  {имя}:", ", ".join(f"{ч}={n}" for ч, n in ряд) or "нет")
    всего, макс_id = store._conn.execute(
        "SELECT COUNT(*), MAX(id) FROM recipients").fetchone()
print(f"  строк всего {всего}, максимальный id {макс_id} "
      f"(разрыв {int(макс_id or 0) - int(всего or 0)} - следы удалений)")

# --- 2. что доезжает до запроса ------------------------------------------
группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
есть = Counter()
пусто_примеры = {}
взято = 0
for rid in в_группе:
    if взято >= СКОЛЬКО:
        break
    rec = store.get_recipient(rid)
    if not rec:
        есть["строки нет в recipients"] += 1
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    if not inn:
        continue
    try:
        req = q._request(rec)
    except Exception as ex:                                       # noqa: BLE001
        есть[f"запрос не собрался: {type(ex).__name__}"] += 1
        continue
    взято += 1
    ex_ = req.get("extra") or {}
    карточка = q._card_for(inn) or {}
    enrich = (карточка.get("enrich") or {}).get("company") or {}
    проверки = {
        "карточка обзвона": bool(карточка),
        "  в ней enrich.company": bool(enrich),
        "  в ней род деятельности": bool(str(enrich.get("activity") or "").strip()),
        "паспорт сайта (site_facts)": bool(q._site_facts(inn)),
        "текст сайта (site_text)": len(str(ex_.get("site_text") or "")) > 300,
        "новость-повод": bool(req.get("news") or ex_.get("news")),
        "контактное лицо": bool(str(getattr(rec, "contact_name", "") or "").strip()),
        "ОКВЭД": bool(str(getattr(rec, "okved", "") or "").strip()),
        "регион": bool(str(getattr(rec, "region", "") or "").strip()),
        "часовой пояс": bool(str(getattr(rec, "tz", "") or "").strip()),
    }
    for к, v in проверки.items():
        if v:
            есть[к] += 1
        elif к not in пусто_примеры:
            пусто_примеры[к] = f"{inn} {str(getattr(rec, 'company_name', ''))[:30]}"

print(f"\n== что доезжает до письма (выборка {взято} компаний) ==")
for к in ("карточка обзвона", "  в ней enrich.company", "  в ней род деятельности",
          "паспорт сайта (site_facts)", "текст сайта (site_text)",
          "новость-повод", "контактное лицо", "ОКВЭД", "регион", "часовой пояс"):
    n = есть.get(к, 0)
    доля = 100.0 * n / max(1, взято)
    print(f"  {к:<28} {n:>4} / {взято}  {доля:>5.0f}%"
          + (f"   пример пустого: {пусто_примеры[к]}" if к in пусто_примеры
             and доля < 100 else ""))
прочее = {k: v for k, v in есть.items() if k.startswith(("строки нет", "запрос"))}
if прочее:
    print("\nпрочее:", прочее)
