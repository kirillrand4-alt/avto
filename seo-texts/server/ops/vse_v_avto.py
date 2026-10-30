# -*- coding: utf-8 -*-
"""Кнопка «В автоотправку» на всю очередь подтверждения сразу (владелец 30.10:
«клацни в автоотправку для писем которые панель пропустит… я посмотрел
письма, подходят»).

Повторяет /confirm/bulk-to-auto построчно: ответы (kind=reply) не берёт,
стоп-флаг карточки (confirm_hold), живой заслон confirm._guard и гейт
направлений — пропуск с причиной, срок — ближайший слот окна в зоне
получателя. Разница одна: не первые 300 по баллу, а все — кнопка упирается
в одни и те же заблокированные верхние карточки.
    vse_v_avto.py [--katit] [--zapusk]   (без --katit — сухой подсчёт)
Журнал: _ops/vse-v-avto.jsonl, лог: _ops/vse-v-avto.log
"""
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

if "--zapusk" in sys.argv:
    import subprocess
    л = io.open(r"C:\sender\_ops\vse-v-avto.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)]
                         + [a for a in sys.argv[1:] if a != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(5)
    print("запущено, pid %d, жив %s" % (п.pid, п.poll() is None))
    raise SystemExit(0)

sys.path.insert(0, r"C:\sender")
sys.path.insert(1, r"C:\sender\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
from sender.dtos import MessageIn                                 # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from, ENABLED_KEY  # noqa: E402

КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
win = window_from(store, cfg)
now = datetime.now(timezone.utc)
ряды = [r for r in cs.pending(limit=100_000) if (r.get("kind") or "outbound") != "reply"]
print("%s в подтверждении (без ответов): %d" % (time.strftime("%H:%M:%S"), len(ряды)), flush=True)
итог = Counter()
поток = io.open(r"C:\sender\_ops\vse-v-avto.jsonl", "a", encoding="utf-8") if КАТИТЬ else None
for i, r in enumerate(ряды, 1):
    rid = int(r["id"])
    панель = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    if ((панель or {}).get("actions") or {}).get("confirm_hold"):
        итог["стоп-флаг карточки"] += 1
        continue
    блок = None
    try:
        блок = cs._guard(inn=r.get("inn"), email=r.get("email") or "")
    except Exception:                                            # noqa: BLE001
        pass
    if блок:
        итог["заслон: " + str(блок)[:40]] += 1
        continue
    дб = None
    try:
        дб = cs._division_blocked(r)
    except Exception:                                            # noqa: BLE001
        pass
    if дб:
        итог["гейт направлений: " + str(дб)[:30]] += 1
        continue
    rec = store.get_recipient(int(r["recipient_id"])) if r.get("recipient_id") else None
    if rec is None and r.get("email"):
        рр = store.find_recipient_by_email(r["email"])
        rec = store.get_recipient(int(рр["id"])) if рр else None
    if rec is None:
        итог["нет получателя"] += 1
        continue
    if not КАТИТЬ:
        итог["пройдёт"] += 1
        continue
    try:
        слот = next_slot(win, recipient_tz_name(win, rec), now)
        mid = r.get("message_id")
        if mid is None:
            cid = r.get("campaign_id")
            steps = store.get_steps(int(cid)) if cid else []
            if not steps:
                итог["нет кампании/шага"] += 1
                continue
            mid, _ = store.enqueue_message(MessageIn(
                idempotency_key="confirm-auto-%d" % rid, campaign_id=int(cid),
                recipient_id=int(rec.id), sequence_step_id=int(steps[0].id),
                scheduled_at=слот))
            store.confirm_set_message(rid, mid)
        else:
            store.reschedule_message(int(mid), слот)
        ок = store.confirm_decide(rid, status="approved", decided_by="владелец 30.10 (все разом)",
                                  reason="bulk-to-auto")
        итог["в автоотправку" if ок else "уже решена"] += 1
        if ок:
            поток.write(json.dumps({"review": rid, "email": r.get("email"),
                                    "slot": слот.isoformat()}, ensure_ascii=False) + "\n")
            поток.flush(); os.fsync(поток.fileno())
    except Exception as ex:                                      # noqa: BLE001
        итог["ошибка: " + str(ex)[:40]] += 1
    if i % 500 == 0:
        print("%s %d/%d %s" % (time.strftime("%H:%M:%S"), i, len(ряды), dict(итог)), flush=True)
if КАТИТЬ and итог["в автоотправку"]:
    store.set_setting(ENABLED_KEY, True)
print("")
for к, n in итог.most_common():
    print("   %-60s %5d" % (к, n))
print("=== ГОТОВО ===", flush=True)
