# -*- coding: utf-8 -*-
"""Почему не уходят письма КЦ-1: на 5 scheduled-письмах вызвать pick_mailbox и division_block
(только чтение, без отправки) + состояние ящиков КЦ."""
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, st, dry_run=True)
s = deps.sender if hasattr(deps, "sender") else None
print("sender:", type(s).__name__)
c = st._conn
now = datetime.now(timezone.utc)
print("таблицы:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%sett%' OR name LIKE '%kv%')")])
for (mid,) in c.execute("SELECT id FROM messages WHERE campaign_id=17 AND status='scheduled' ORDER BY scheduled_at LIMIT 5").fetchall():
    m = st.get_message(mid) if hasattr(st, "get_message") else None
    r = st.get_recipient(m.recipient_id); camp = st.get_campaign(m.campaign_id)
    try:
        mb = s.pick_mailbox(r, camp, now=now, message=m)
    except Exception as ex:  # noqa: BLE001
        mb = "ОШИБКА %s" % ex
    try:
        бл = s.division_block(r, mb, message=m) if mb and not str(mb).startswith("ОШИБКА") else "-"
    except Exception as ex:  # noqa: BLE001
        бл = "ОШИБКА %s" % ex
    print(mid, m.scheduled_at, r.email, "| ящик:", mb, "| блок:", бл)
for r in c.execute("SELECT mailbox_id, sent_today, daily_limit, paused, pause_reason, last_sent_at FROM mailbox_state WHERE mailbox_id LIKE '%kompress%' OR mailbox_id LIKE '%compress%' LIMIT 6"):
    print(tuple(r))
print("\n=== разбор первого письма по ящикам ===")
mid0 = c.execute("SELECT id FROM messages WHERE campaign_id=17 AND status='scheduled' ORDER BY scheduled_at LIMIT 1").fetchone()[0]
m = st.get_message(mid0); r = st.get_recipient(m.recipient_id); camp = st.get_campaign(m.campaign_id)
пул = s._route_pool(r, camp)
print("mx:", r.mx_provider, "| пул:", пул, "| пул кампании:", camp.provider_pool)
пулы = cfg.provider_pools()
print("пулы:", {k: len(v) for k, v in пулы.items()})
for mb in (пулы.get("pool_kc") or [])[:6]:
    try:
        print("  ", mb, "| блок направления:", s.division_block(r, mb, message=m), "| can_send_now:", s.can_send_now(mb, now=now))
    except Exception as ex:  # noqa: BLE001
        print("  ", mb, "ОШИБКА", ex)
if hasattr(s, "_zapasnye_yashchiki"):
    print("запасные из пула письма:", len(s._zapasnye_yashchiki(пулы.get(пул, []))))
print("\n=== направление письма ===")
from sender.sender import napravlenie_pisma  # noqa: E402
import collections
сч = collections.Counter()
for (mid,) in c.execute("SELECT id FROM messages WHERE campaign_id=17 AND status='scheduled'").fetchall():
    row = st.confirm_review_for_message(mid)
    p = (row or {}).get("panel") or {}
    сч[(p.get("letter_division") if isinstance(p, dict) else "?", napravlenie_pisma(row) if row else "нет карточки")] += 1
print(сч.most_common())
row = st.confirm_review_for_message(mid0)
print("пример панели:", {k: (row["panel"].get(k) if isinstance(row.get("panel"), dict) else None) for k in ("letter_division", "division", "company")})
print("\n=== can_send_now по шагам (первые 4 ящика КЦ) ===")
print("окно:", s._within_window(now), "| глоб. гейт:", s.gates.check_global().tripped)
for mb in (пулы.get("pool_kc") or [])[:4]:
    стт = st.get_mailbox_state(mb); cfgmb = s._mailbox_cfg(mb)
    гм = s.gates.check_mailbox(mb)
    print("  ", mb, "| гейт ящика:", гм.tripped, getattr(гм, "reason", ""), "| пауза:", стт and стт.paused,
          "| ramp:", стт and стт.ramp_day, "| лимит:", s._daily_limit(cfgmb.provider, (стт.ramp_day if стт else 0), mb))
print("\n=== окно ===")
print("override:", s._window_override())
print("праздник сегодня:", now.astimezone(s._zone("Europe/Moscow")).date() in cfg.holidays(), "| ближайшие праздники:", sorted(d for d in cfg.holidays() if str(d) >= "2026-11-01")[:5])
