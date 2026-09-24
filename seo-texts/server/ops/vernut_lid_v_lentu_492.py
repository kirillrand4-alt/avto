# -*- coding: utf-8 -*-
"""Вернуть карточку в ленту: «не интересно» → «новый».

Владелец закрыл карточку 10.09 по первому ответу («у нас стоит 2
фотосепаратора») — решение было верным. 16.09 пришёл второй ответ с
запросом характеристик и словами «может они окажутся лучше и мы у Вас
купим», дописался в карточку, но статус не поднял.

Возвращаем через штатный путь панели (leaddesk.set_status), чтобы легло
событие карточки и сошлась версия. Текст ответа не трогаем: note не
передаём, иначе он перезапишет поле need.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.wiring import build_deps                            # noqa: E402

ЛИД = int(sys.argv[1]) if len(sys.argv) > 1 else 492
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)

было = deps.leaddesk.get(ЛИД)
print("было:  лид %s — %s, статус %s, версия %s"
      % (ЛИД, было.company_name, было.status, было.version))

if было.status == "new":
    print("уже в ленте — ничего не делаем")
else:
    стало = deps.leaddesk.set_status(ЛИД, status="new", user_id=None)
    print("стало: статус %s, версия %s" % (стало.status, стало.version))

print("")
print("--- события карточки ---")
def поле(о, имя):
    return o_get(о, имя)


def o_get(о, имя):
    if isinstance(о, dict):
        return о.get(имя)
    return getattr(о, имя, None)


for с in deps.leaddesk.history(ЛИД):
    print("   %s  %-16s %s → %s"
          % (o_get(с, "created_at"), o_get(с, "action"),
             o_get(с, "from_status"), o_get(с, "to_status")))

print("")
print("--- видно ли её теперь в ленте (список без фильтра) ---")
нашли = False
for л in deps.leaddesk.queue(limit=200):
    if o_get(л, "id") == ЛИД:
        нашли = True
        print("   ДА: лид %s %s — %s, вердикт %s"
              % (o_get(л, "id"), o_get(л, "company_name"),
                 o_get(л, "status"), o_get(л, "reply_kind")))
if not нашли:
    print("   в первых 200 не показалась")

print("")
print("--- сколько карточек в каком статусе теперь ---")
with store._lock:
    for р in store._conn.execute("SELECT status, COUNT(*) n FROM leads "
                                 " GROUP BY 1 ORDER BY 2 DESC"):
        print("   %-18s %5d" % (р["status"], р["n"]))
print("")
print("=" * 74)
print("=== КАРТОЧКА %d ВЕРНУЛАСЬ В ЛЕНТУ ===" % ЛИД)
