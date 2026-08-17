# -*- coding: utf-8 -*-
"""Письма в базе есть, а в панели их нет: на каком фильтре они отваливаются.

Владелец: «нету в панели ни одного письма уже минут 10, хотя и кнопку нажал».
Замер при этом говорит обратное: кампания 10 выросла с 487 до 496 строк за
90 секунд. Значит письма пишутся и ложатся, а теряются ПО ДОРОГЕ К ЭКРАНУ.

Панель режет очередь тремя ситами подряд, и каждое может съесть всё:
  1. статус pending;
  2. фильтр НАПРАВЛЕНИЯ (кнопки «Все / КЦ / Meyer»);
  3. фильтр ГРУППЫ (выпадашка «Партия 935») - группа берётся из ПОЛУЧАТЕЛЯ
     (segment + extra_json.gruppy), а не из письма;
  4. галка «скрыть письма на корпоративные серверы»;
  5. страница: список отдаётся порциями и СОРТИРУЕТСЯ, поэтому свежее письмо
     может лежать не на первой странице, а в хвосте - и выглядеть как
     «ничего не появилось».

Считаем, сколько писем доживает до каждого шага, и где именно в порядке
показа оказываются САМЫЕ СВЕЖИЕ.

    python zapusk_svoego_skripta.py ops/pochemu_panel_ne_pokazyvaet.py 10
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

КАМПАНИЯ = int(sys.argv[1]) if len(sys.argv) > 1 else 10
ГРУППА = "Партия 935"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

строки = store.confirm_list(limit=100000)
print(f"1. всего строк очереди: {len(строки)}")

pending = [r for r in строки if str(r.get("status")) == "pending"
           and (r.get("kind") or "outbound") != "reply"]
print(f"2. из них pending (не ответы): {len(pending)}")

нашей = [r for r in pending if int(r.get("campaign_id") or 0) == КАМПАНИЯ]
print(f"3. из них кампании {КАМПАНИЯ}: {len(нашей)}")

кц = []
for r in pending:
    d = str(cs.letter_division(r) or "")
    if not d:
        panel = r.get("panel") if isinstance(r.get("panel"), dict) else {}
        comp = panel.get("company") if isinstance(
            panel.get("company"), dict) else {}
        d = str(comp.get("division") or "")
    d = d.lower()
    if (not d) or ("kc" in d):
        кц.append(r)
print(f"4. фильтр «КЦ» пропускает: {len(кц)} (из всех pending)")

карта = store.recipient_groups()
по_id = карта.get("по_id") or {}
по_почте = карта.get("по_почте") or {}
в_группе = []
для_отладки = []
for r in кц:
    rid = r.get("recipient_id")
    группы = set(по_id.get(int(rid), ())) if rid else set()
    if not группы:
        группы = set(по_почте.get(str(r.get("email") or "").lower(), ()))
    if ГРУППА in группы:
        в_группе.append(r)
    elif len(для_отладки) < 8:
        для_отладки.append((r.get("id"), r.get("email"), sorted(группы)[:3]))
print(f"5. и фильтр группы «{ГРУППА}»: {len(в_группе)}")
for i, e, g in для_отладки:
    print(f"     выпало #{i} {str(e)[:34]:<36} группы: {g or 'нет'}")

# --- где в порядке показа самые свежие ------------------------------------- #
свежие = sorted(в_группе, key=lambda r: -(r.get("id") or 0))[:10]
print(f"\n6. самые свежие письма фильтра: "
      f"{[r.get('id') for r in свежие]}")

по_id_возр = sorted(в_группе, key=lambda r: (r.get("id") or 0))
позиции = {r.get("id"): i for i, r in enumerate(по_id_возр)}
print("   их место в списке, если он отсортирован по id по возрастанию "
      "(как отдаёт store.confirm_list):")
for r in свежие[:5]:
    поз = позиции.get(r.get("id"), -1)
    стр = поз // 50 + 1
    print(f"     #{r.get('id')}: позиция {поз + 1} из {len(в_группе)} "
          f"-> СТРАНИЦА {стр}")
print("\n   Если оператор смотрит первую страницу, свежие письма он не "
      "увидит: они в хвосте.")
