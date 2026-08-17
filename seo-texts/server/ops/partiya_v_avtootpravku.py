# -*- coding: utf-8 -*-
"""В автоотправку: письма КЦ партии 935, у которых адрес ПРОВЕРЕН работником.

Команда владельца 17.08. Повторяем путь кнопки панели (bulk-to-auto), но с
двумя сужениями, которых у кнопки нет:
  * только кампания КЦ (10) - Meyer в автоотправку не идёт по решению
    владельца, а фильтр кнопки работает по группе, а не по кампании;
  * только адреса с вердиктом тяжёлой пробы, и вердикт не смертельный.

Каждое письмо проходит те же заслоны, что одиночное подтверждение
(стоп-лист, мёртвый адрес, контакт <90 дней, стоп-флаги карточки); срок -
ближайший слот окна В ЗОНЕ ПОЛУЧАТЕЛЯ.

Сухой прогон; писать - argv[1] == "primenit".
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (ENABLED_KEY, next_slot,                # noqa: E402
                              recipient_tz_name, window_from)
from sender.config import Config                                     # noqa: E402
from sender.confirm import ConfirmSend                               # noqa: E402
from sender.store import Store                                       # noqa: E402
from sender.suppression import Suppression                           # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
КАМПАНИЯ_КЦ = 10
ГРУППА = "Партия 935"
СМЕРТЕЛЬНЫЕ = {"нет ящика", "нет MX"}
# «Неясно» - это НЕ результат проверки, а её провал: три четверти таких
# вердиктов - таймаут разговора и грейлистинг («зайдите позже»), то есть
# сервер про ящик не сказал ничего. Владелец просил отправлять тем, у кого
# почта ПРОВЕРЕНА, - значит «неясно» сюда не входит. «Принимает всё»
# входит: домен ответил, и владелец отдельно велел такие оставлять.
НЕ_ПРОВЕРЕН = {"неясно", "отказ пробе"}
ЖУРНАЛ = r"C:\sender\_ops\v-avtootpravku.jsonl"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

группы = store.recipient_groups().get("по_id") or {}
в_группе = {rid for rid, gr in группы.items() if ГРУППА in gr}

# вердикты пробы: кэш панели - он же то, что видит заслон отправки
with store._lock:
    вердикт = {str(e).lower(): str(v) for e, v in store._conn.execute(
        "SELECT email, verdict FROM addr_probe").fetchall()}

оч = [r for r in (store.confirm_list(status="pending", limit=100000) or [])
      if int(r.get("campaign_id") or 0) == КАМПАНИЯ_КЦ
      and int(r.get("recipient_id") or 0) in в_группе
      and (r.get("kind") or "outbound") != "reply"]
print(f"писем КЦ партии в очереди: {len(оч)}")

счёт = Counter()
годные = []
for r in оч:
    em = str(r.get("email") or "").strip().lower()
    в = вердикт.get(em)
    if not в:
        счёт["адрес не проверен работником"] += 1
        continue
    if в in СМЕРТЕЛЬНЫЕ:
        счёт[f"проба: {в}"] += 1
        continue
    if в in НЕ_ПРОВЕРЕН:
        счёт[f"проба не удалась: {в}"] += 1
        continue
    заслон = cs._guard(inn=r.get("inn"), email=em)
    if заслон:
        счёт[f"заслон: {заслон.split(':')[0]}"] += 1
        continue
    panel_r = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    if ((panel_r or {}).get("actions") or {}).get("confirm_hold"):
        счёт["стоп-флаг карточки"] += 1
        continue
    счёт[f"годно ({в})"] += 1
    годные.append((r, в))

print(f"режим: {'ПРИМЕНЯЮ' if ПРИМЕНИТЬ else 'сухой прогон'}")
for k, n in счёт.most_common():
    print(f"  {k:<34} {n}")
print(f"К ОТПРАВКЕ: {len(годные)}")

if not ПРИМЕНИТЬ:
    for r, в in годные[:15]:
        print(f"  #{r['id']:<6} {str(r.get('email'))[:34]:<36} проба: {в}")
    print("\nсухой прогон: в автоотправку никто не ушёл")
    raise SystemExit(0)

win = window_from(store, cfg)
now = datetime.now(timezone.utc)
ушло, сбои = 0, []
for r, в in годные:
    rid = int(r["id"])
    try:
        rec = store.get_recipient(int(r["recipient_id"]))
        слот = next_slot(win, recipient_tz_name(win, rec), now)
        mid = r.get("message_id")
        if mid is None:
            сбои.append((rid, "нет message_id"))
            continue
        store.reschedule_message(int(mid), слот)
        ок = store.confirm_decide(rid, status="approved",
                                  decided_by="1-я сессия (команда владельца)",
                                  reason="в автоотправку: адрес проверен")
        if not ок:
            сбои.append((rid, "карточка уже решена"))
            continue
        ушло += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps({"review_id": rid, "email": r.get("email"),
                                "проба": в, "слот": слот.isoformat(),
                                "ts": int(time.time())},
                               ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex:                                          # noqa: BLE001
        сбои.append((rid, str(ex)[:90]))

print(f"\nв автоотправку ушло: {ушло} | сбоев: {len(сбои)}")
for rid, п in сбои[:10]:
    print(f"  #{rid}: {п}")
if ушло:
    store.set_setting(ENABLED_KEY, True)
    print("автоотправка ВКЛЮЧЕНА")
print("окно:", store.get_setting("sending_window"))
