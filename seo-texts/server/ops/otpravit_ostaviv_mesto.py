# -*- coding: utf-8 -*-
"""Обычные письма - в автоотправку, оставив место рассылке про вебинар.

Кнопка панели «в автоотправку» фильтрует ТОЛЬКО по группе и не знает про
направления: она берёт первые N по баллу вперемешку. Нам нужно развести
КЦ и Meyer, потому что ёмкость дня у них разная, а в мейеровской надо
придержать слоты под 74 письма вебинара.

Своей логики решения не заводим: по каждому письму зовём те же штатные
методы, что и кнопка, - _guard, _division_blocked, next_slot,
enqueue_message/reschedule_message, confirm_decide. Отличается только
отбор кандидатов.

Ёмкость считаем как ops/skolko_ne_hvataet_segodnya.py: рампом каждого
ящика, минус ушедшее сегодня и минус уже готовое к отправке.

Аргументы: rezerv=74 (сколько слотов Meyer придержать), primenit.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (ENABLED_KEY, next_slot,               # noqa: E402
                              recipient_tz_name, window_from)
from sender.company_card import CompanyCards                        # noqa: E402
from sender.config import Config                                    # noqa: E402
from sender.confirm import ConfirmSend                              # noqa: E402
from sender.dtos import MessageIn                                   # noqa: E402
from sender.gates import Gates                                      # noqa: E402
from sender.sender import Sender                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.suppression import Suppression                          # noqa: E402

РЕЗЕРВ = int(next((a.split("=", 1)[1] for a in sys.argv[1:]
                   if a.startswith("rezerv=")), "74"))
писать = "primenit" in sys.argv[1:]
КАМПАНИИ = {10: "КЦ", 9: "КЦ", 11: "Meyer", 7: "Meyer", 8: "Meyer"}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
supp = Suppression(store)
cs = ConfirmSend(cfg, store, supp)
snd = Sender(cfg, store, supp, Gates(cfg, store), dry_run=True,
             cards=CompanyCards(
                 index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                 enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "")
                 or None))
сегодня = datetime.now(timezone.utc).date().isoformat()

ёмкость, ушло, готово = Counter(), Counter(), Counter()
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    напр = "Meyer" if ("meyer" in div or "мейер" in div) else "КЦ"
    st = store.get_mailbox_state(mb.mailbox_id)
    рд = getattr(st, "ramp_day", 0) if st else 0
    ёмкость[напр] += snd._daily_limit(mb.provider, рд + 1, mb.mailbox_id)
with store._lock:
    for camp, имя in КАМПАНИИ.items():
        ушло[имя] += store._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE campaign_id=? "
            "AND status='sent' AND substr(updated_at,1,10)=?",
            (camp, сегодня)).fetchone()[0]
        готово[имя] += store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews cr "
            "ON cr.message_id=m.id WHERE m.campaign_id=? "
            "AND cr.status IN ('approved','edited') "
            "AND m.status IN ('scheduled','sending')", (camp,)).fetchone()[0]
    вебинар = {р[0] for р in store._conn.execute(
        "SELECT id FROM confirm_reviews "
        " WHERE dedup_key LIKE 'vebinar28:%'").fetchall()}

свободно = {и: max(0, ёмкость[и] - ушло[и] - готово[и]) for и in ("КЦ", "Meyer")}
квота = {"КЦ": свободно["КЦ"], "Meyer": max(0, свободно["Meyer"] - РЕЗЕРВ)}
print(f"свободно сегодня: КЦ {свободно['КЦ']}, Meyer {свободно['Meyer']}")
print(f"резерв под вебинар: {РЕЗЕРВ} -> квота обычным: "
      f"КЦ {квота['КЦ']}, Meyer {квота['Meyer']}\n")

строки = [r for r in (cs.pending(limit=100_000) or [])
          if (r.get("kind") or "outbound") != "reply"
          and int(r.get("id") or 0) not in вебинар]


def балл(r):
    try:
        return float(((r.get("panel") or {}).get("scoring")
                      or {}).get("score") or -1)
    except (TypeError, ValueError):
        return -1.0


корзины = {"КЦ": [], "Meyer": []}
для_чужих = 0
for r in строки:
    имя = КАМПАНИИ.get(int(r.get("campaign_id") or 0))
    if имя:
        корзины[имя].append(r)
    else:
        для_чужих += 1
for имя in корзины:
    корзины[имя].sort(key=lambda r: (-балл(r), r.get("id") or 0))
    корзины[имя] = корзины[имя][:квота[имя]]
print(f"обычных писем в очереди: КЦ {len(корзины['КЦ'])} к отправке, "
      f"Meyer {len(корзины['Meyer'])} к отправке "
      f"(кампаний вне карты: {для_чужих})")

if not писать:
    for имя in ("КЦ", "Meyer"):
        for r in корзины[имя][:3]:
            print(f"  {имя} №{r['id']} балл={балл(r):.0f} {r.get('email')}")
    print("\nсухой прогон: ничего не менял (primenit — записать)")
    raise SystemExit(0)

win = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
ушли, сняты = Counter(), []
for имя in ("КЦ", "Meyer"):
    for r in корзины[имя]:
        rid = int(r["id"])
        пан = r.get("panel") if isinstance(r.get("panel"), dict) else {}
        if ((пан or {}).get("actions") or {}).get("confirm_hold"):
            сняты.append((rid, "стоп-флаг карточки"))
            continue
        поч = r.get("email") or ""
        блок = None
        try:
            блок = cs._guard(inn=r.get("inn"), email=поч)
        except Exception:                                         # noqa: BLE001
            блок = None
        if блок:
            сняты.append((rid, str(блок)[:60]))
            continue
        try:
            если_напр = cs._division_blocked(r)
        except Exception:                                         # noqa: BLE001
            если_напр = None
        if если_напр:
            сняты.append((rid, f"гейт направлений: {если_напр}"))
            continue
        rec = None
        if r.get("recipient_id"):
            rec = store.get_recipient(int(r["recipient_id"]))
        if rec is None and поч:
            строка = store.find_recipient_by_email(поч)
            if строка:
                rec = store.get_recipient(int(строка["id"]))
        if rec is None:
            сняты.append((rid, "получателя нет в recipients"))
            continue
        слот = next_slot(win, recipient_tz_name(win, rec), сейчас)
        try:
            mid = r.get("message_id")
            if mid is None:
                cid = r.get("campaign_id")
                шаги = store.get_steps(int(cid)) if cid else None
                if not шаги:
                    сняты.append((rid, "у кампании нет шага-письма"))
                    continue
                mid, _ = store.enqueue_message(MessageIn(
                    idempotency_key=f"confirm-auto-{rid}",
                    campaign_id=int(cid), recipient_id=int(rec.id),
                    sequence_step_id=int(шаги[0].id), scheduled_at=слот))
                store.confirm_set_message(rid, mid)
            else:
                store.reschedule_message(int(mid), слот)
            ок = store.confirm_decide(rid, status="approved",
                                      decided_by="ops:ostaviv-mesto",
                                      reason="bulk-to-auto")
            if not ок:
                сняты.append((rid, "карточка уже решена"))
                continue
        except Exception as ex:                                   # noqa: BLE001
            сняты.append((rid, f"{type(ex).__name__} {str(ex)[:60]}"))
            continue
        ушли[имя] += 1

store.set_setting(ENABLED_KEY, True)
print(f"\nв автоотправку: КЦ {ушли['КЦ']}, Meyer {ушли['Meyer']}")
print(f"снято заслонами: {len(сняты)}")
for rid, почему in сняты[:15]:
    print(f"  №{rid}: {почему}")
