# -*- coding: utf-8 -*-
"""Перегенерировать письма, где текст спорит с направлением карточки.

Владелец на #527 («Кубань-Вино», карточка «Компрессор Центр по метке базы»,
письмо про сортировку винограда от «Руспром Мейер»): «писали +мейер когда
оно кц, почини».

Чинить правкой панели нечего: письмо УЖЕ написано не про то. Единственный
честный ремонт - переписать его под направление карточки, а это штатная
перегенерация (ai_quota.regenerate_review): она заново собирает запрос,
считает направление сегодняшними правилами и кладёт новый текст в ТУ ЖЕ
строку очереди, вместе с полем letter_division, которого у старых писем нет.

Берём ТОЛЬКО pending: отправленные переписывать поздно, skipped и stoplist
оператор уже решил. Замер 17.08: спорных писем 31, из них pending 11.

Печатаем на каждое: направление до и после, и сошлось ли с карточкой.

    python zapusk_svoego_skripta.py ops/ochered_peregenerirovat_spornye.py 11
"""
import json
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ПОТОЛОК = int(sys.argv[1]) if len(sys.argv) > 1 else 11

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))


def разбор(r):
    """(направление письма, направление карточки) для строки очереди."""
    panel = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    comp = panel.get("company") if isinstance(panel.get("company"), dict) else {}
    return (str(cs.letter_division(r) or "").strip().lower(),
            str(comp.get("division") or "").strip().lower())


спорные = []
for r in store.confirm_list(limit=100000):
    if (r.get("kind") or "outbound") == "reply":
        continue
    if str(r.get("status")) != "pending":
        continue
    письмо, карточка = разбор(r)
    if not письмо or not карточка or карточка in ("kc+meyer", "meyer+kc"):
        continue
    if письмо != карточка:
        спорные.append((r.get("id"), письмо, карточка,
                        (r.get("subject") or "")[:60]))

print(f"спорных pending: {len(спорные)}")
for rid, п, к, тема in спорные:
    print(f"  #{rid} письмо {п} против карточки {к} | {тема}")

спорные = спорные[:ПОТОЛОК]
if not спорные:
    print("перегенерировать нечего")
    raise SystemExit(0)

print(f"\nперегенерирую {len(спорные)}")
сошлось = разошлось = сбой = 0
for rid, было, карточка, _т in спорные:
    т0 = time.time()
    try:
        итог = q.regenerate_review(int(rid))
    except Exception as ex:                                     # noqa: BLE001
        сбой += 1
        print(f"  #{rid} СБОЙ {type(ex).__name__} {str(ex)[:110]}")
        continue
    if not (итог or {}).get("ok"):
        сбой += 1
        print(f"  #{rid} не переписалось: {str((итог or {}).get('reason'))[:110]}")
        continue
    with store._lock:
        строка = store._conn.execute(
            "SELECT id, subject, body, panel_json, campaign_id, email, status, "
            "kind FROM confirm_reviews WHERE id=?", (int(rid),)).fetchone()
    r2 = {"id": строка[0], "subject": строка[1], "body": строка[2],
          "panel": json.loads(строка[3] or "{}"), "campaign_id": строка[4],
          "email": строка[5], "status": строка[6], "kind": строка[7]}
    стало, карточка2 = разбор(r2)
    поле = str((r2["panel"] or {}).get("letter_division") or "") or "нет"
    знак = "СОШЛОСЬ" if стало == карточка2 else "ВСЁ ЕЩЁ СПОР"
    сошлось += стало == карточка2
    разошлось += стало != карточка2
    print(f"  #{rid} {было} -> {стало} (карточка {карточка2}, "
          f"поле {поле}) {знак} {int(time.time() - т0)}с")
    print(f"      тема: {str(r2['subject'])[:80]}")

print(f"\nсошлось {сошлось} | всё ещё спорят {разошлось} | сбоев {сбой}")
