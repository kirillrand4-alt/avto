# -*- coding: utf-8 -*-
"""Почему часть мейеровских ящиков стоит на нуле, а три везут всё.

Владелец увидел: три ящика по 13-14 отправок, четвёртый один, три по нулям.
Ротация в pick_mailbox берёт САМЫЙ НЕЗАГРУЖЕННЫЙ — значит пустые ящики
отсекаются раньше, до ротации. Здесь проверяем все заслоны по очереди:
пул провайдера, гейт направлений, пауза, гейт репутации, лимит дня, пейсинг.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards                           # noqa: E402
from sender.config import Config                                       # noqa: E402
from sender.gates import Gates                                         # noqa: E402
from sender.sender import Sender                                       # noqa: E402
from sender.store import Store                                         # noqa: E402
from sender.suppression import Suppression                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cards = CompanyCards(
    index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store),
             dry_run=True, cards=cards)
now = datetime.now(timezone.utc)
пулы = cfg.provider_pools()
маршрут = cfg.get("provider_split.routing", {}) or {}

print("== маршрутизация получателей по пулам ==")
for k, v in маршрут.items():
    print(f"  mx={k:<10} -> пул {v}")

print("\n== в каких пулах лежат мейеровские ящики ==")
мейер = []
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    if "meyer" not in div and "мейер" not in div:
        continue
    мейер.append(mb)
    в_пулах = [p for p, lst in пулы.items() if mb.mailbox_id in lst]
    st = store.get_mailbox_state(mb.mailbox_id)
    сег = getattr(st, "sent_today", 0) if st else 0
    рд = getattr(st, "ramp_day", 0) if st else 0
    посл = getattr(st, "last_sent_at", None) if st else None
    пауза = getattr(st, "paused", False) if st else False
    гейт = snd.gates.check_mailbox(mb.mailbox_id)
    лим = snd._daily_limit(mb.provider, рд, mb.mailbox_id)
    можно = snd.can_send_now(mb.mailbox_id, now=now)
    # разбираем, что именно мешает
    почему = []
    if пауза:
        почему.append("ПАУЗА")
    if гейт.tripped:
        почему.append(f"ГЕЙТ({getattr(гейт,'reason','')})")
    if сег >= лим:
        почему.append(f"ЛИМИТ ДНЯ {сег}/{лим}")
    if посл is not None:
        зазор = (now - посл.replace(tzinfo=посл.tzinfo or timezone.utc)
                 ).total_seconds()
        мин = int(cfg.get("send_pacing.min_interval_sec", 90) or 0)
        if зазор < мин:
            почему.append(f"ПЕЙСИНГ (прошло {int(зазор)}с из {мин})")
    if not в_пулах:
        почему.append("НЕ В ПУЛЕ")
    if not можно and not почему:
        почему.append("пейсинг/окно (свежая отправка)")
    print(f"  {mb.mailbox_id:<38} провайдер={mb.provider:<8} рамп{рд:>3} "
          f"{сег:>3}/{лим:<3} можно_слать={можно}  пулы={в_пулах or 'НЕТ'}"
          + (f"  << {', '.join(почему)}" if почему else ""))

print("\n== куда маршрутизируются ждущие письма кампании 11 ==")
with store._lock:
    ждут = store._conn.execute(
        "SELECT m.id, m.recipient_id, m.campaign_id FROM messages m "
        "JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE c.campaign_id=11 AND m.status='scheduled' "
        "AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id "
        "     ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited') "
        "LIMIT 200").fetchall()
по_пулам = Counter()
кто_годен = Counter()
for r in ждут:
    rec = store.get_recipient(r["recipient_id"])
    camp = store.get_campaign(r["campaign_id"])
    if rec is None:
        continue
    pool = snd._route_pool(rec, camp)
    по_пулам[f"mx={rec.mx_provider} -> пул {pool}"] += 1
    with store._lock:
        row = store._conn.execute("SELECT * FROM messages WHERE id=?",
                                  (r["id"],)).fetchone()
    from sender.store import _row_to_message                            # noqa: E402
    m = _row_to_message(row)
    for mb in пулы.get(pool or "", []):
        if snd.division_block(rec, mb, message=m) is None:
            кто_годен[mb] += 1
for k, v in по_пулам.most_common():
    print(f"  {v:>4}  {k}")

print("\n== какие ящики ВООБЩЕ проходят гейт направлений для этих писем ==")
if not кто_годен:
    print("  НИ ОДНОГО — письма некуда слать в своём пуле")
for k, v in кто_годен.most_common():
    print(f"  {v:>4}  {k}")
