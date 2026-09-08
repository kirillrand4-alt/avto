# -*- coding: utf-8 -*-
"""Потолок 20 писем на ящик и снятие паузы, поставленной заслоном по спаму.

Потолок живёт в настройке панели send_limits и работает ТОЛЬКО ВНИЗ - выше
рамп-кривой не поднять, и это правильно. Сейчас рампа даёт около 36 писем на
ящик, значит 20 её прижимает.

Паузу снимаем ТОЛЬКО ту, что поставил заслон по спаму. Ящик, про который
владелец написал «в спаме, не использовать», и ящики с непонятной ручной
пометкой не трогаем: чужое решение снимать молча нельзя.

    python potolok_i_snyat_pauzu.py            # вхолостую
    python potolok_i_snyat_pauzu.py --primenit
"""
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.gates import Gates                                  # noqa: E402
from sender.sender import Sender                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ПОТОЛОК = 20
ПРИЗНАК_ЗАСЛОНА = "отказ почтовика по спаму"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
СНИМОК = (r"C:\sender\_ops\send-limits-do-"
          + time.strftime("%m%d-%H%M%S") + ".json")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True)
теперь = datetime.now(timezone.utc)

было = None
try:
    было = store.get_setting("send_limits")
except Exception as ex:                                         # noqa: BLE001
    было = "нет: " + str(ex)[:50]
print("send_limits было: %r" % (было,))

счёт = Counter()
снимем = []
оставим = []
for mb in cfg.mailboxes():
    if str(getattr(mb, "division", "")).lower() != "meyer":
        continue
    st = store.get_mailbox_state(mb.mailbox_id)
    if st is None or not getattr(st, "paused", False):
        счёт["не на паузе"] += 1
        continue
    причина = str(getattr(st, "pause_reason", "") or "")
    if ПРИЗНАК_ЗАСЛОНА in причина:
        снимем.append((mb.mailbox_id, причина))
        счёт["СНЯТЬ ПАУЗУ (заслон по спаму)"] += 1
    else:
        оставим.append((mb.mailbox_id, причина))
        счёт["оставить на паузе (чужое решение)"] += 1

# СТАРУЮ НАСТРОЙКУ НЕ ЗАТИРАЕМ ЦЕЛИКОМ. В send_limits уже лежали ручные
# потолки: шести ящикам по 60 и a.kozlov ноль («не использовать»). Ноль -
# решение владельца, его сохраняем; шестьдесят выше сегодняшних двадцати и
# по правилу «лимит ящика важнее общего» перебило бы новый потолок, поэтому
# эти строки убираем. Прежнее значение уходит в durable-файл и в коммит.
if ПРИМЕНИТЬ:
    прежние = было if isinstance(было, dict) else {}
    по_ящикам = {}
    for я, з in (прежние.get("per_mailbox") or {}).items():
        try:
            ц = int(з)
        except (TypeError, ValueError):
            continue
        if ц < ПОТОЛОК:            # ноль и другие прижатия оставляем как есть
            по_ящикам[я] = ц
    новая = {"all": ПОТОЛОК, "per_mailbox": по_ящикам}
    with io.open(СНИМОК, "w", encoding="utf-8") as ф:
        ф.write(json.dumps({"send_limits_до": прежние,
                            "send_limits_после": новая},
                           ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())
    store.set_setting("send_limits", json.dumps(новая, ensure_ascii=False))
    print("send_limits стало: %r" % (новая,))
    for mid, _п in снимем:
        store.set_mailbox_paused(mid, False, reason="")
    счёт["ПАУЗА СНЯТА"] = len(снимем)

# что получилось: сколько каждый ящик реально может отправить сегодня
свободно = 0
готовых = 0
for mb in cfg.mailboxes():
    if str(getattr(mb, "division", "")).lower() != "meyer":
        continue
    г = snd.mailbox_readiness(mb.mailbox_id, now=теперь)
    л = int(getattr(г, "daily_limit", 0) or 0)
    s = int(getattr(г, "sent_today", 0) or 0)
    st = store.get_mailbox_state(mb.mailbox_id)
    if st is not None and getattr(st, "paused", False):
        continue
    готовых += 1
    свободно += max(0, л - s)

print("")
print("--- оставляем на паузе ---")
for i, п in оставим:
    print("   %-38s %s" % (i[:38], п[:50]))
print("")
print("=" * 74)
print("=== ПОТОЛОК И ПАУЗА: %s ==="
      % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("потолок на ящик: %d" % ПОТОЛОК)
for к, в in счёт.most_common():
    print("   %-40s %3d" % (к, в))
print("ящиков Meyer готово слать: %d; свободного лимита сегодня: %d"
      % (готовых, свободно))
if not ПРИМЕНИТЬ:
    print("")
    print("вхолостую. Применить — --primenit")
