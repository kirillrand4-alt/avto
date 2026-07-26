#!/usr/bin/env python3
"""Dry-run приёмка BASE-MERGE (§5 ТЗ): 20 писем на реальных данных.

- индекс обзвона: ПОЛНЫЙ (161 761, из CSV с дропа), enrich: снапшот сервера;
- >=5 новостных лидов (карточка события со ссылками), остальные холодные;
- 3 негативных кейса гейта направлений — все три точки обязаны отбить;
- ничего никуда не отправляется (confirm-очередь, live_send выключен).
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
# Пути к данным: env OBZVON_INDEX / ENRICH_DB / DRYRUN_WORKDIR
SCRATCH = os.environ.get("DRYRUN_WORKDIR", os.getcwd())
INDEX = os.environ.get("OBZVON_INDEX", os.path.join(SCRATCH, "obzvon-index.db"))
ENRICH = os.environ.get("ENRICH_DB_SNAPSHOT",
                        os.path.join(SCRATCH, "enrich_snapshot.db"))
UTC = timezone.utc

from sender.company_card import CompanyCards, campaign_division  # noqa: E402
from sender.confirm import ConfirmBlockedError, ConfirmSend  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import CampaignIn, MessageIn, RecipientIn, SequenceStepIn  # noqa: E402
from sender.errors import SuppressedError  # noqa: E402
from sender.infopanel import build_panel  # noqa: E402
from sender.orchestrator import Orchestrator  # noqa: E402
from sender.sender import RenderedMessage, Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.tests.test_division_gate import _Cfg, _Gates  # noqa: E402

# --- сборка окружения -------------------------------------------------------
for i in range(1, 6):
    os.environ[f"BOX{i}_PASSWORD"] = "secret"
os.environ["UNSUB_SIGNING_SECRET"] = "dryrun_secret_key_min_32_chars_long"
db_path = os.path.join(SCRATCH, "dryrun-sender.db")
if os.path.exists(db_path):
    os.unlink(db_path)
yaml = (BASE_YAML.replace("/tmp/sender.db", db_path)
        .replace("password_env: BOX1_PASSWORD",
                 "password_env: BOX1_PASSWORD\n    division: kc")
        .replace("password_env: BOX2_PASSWORD",
                 "password_env: BOX2_PASSWORD\n    division: kc"))
cfg_path = os.path.join(SCRATCH, "dryrun-config.yaml")
open(cfg_path, "w", encoding="utf-8").write(yaml)
config = Config.load(cfg_path)
store = Store(db_path)
store.init_schema()
supp = Suppression(store)
cards = CompanyCards(index_path=INDEX, enrich_db_path=ENRICH)
sndr = Sender(config, store, supp, _Gates(), dry_run=True, cards=cards)
cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                 cards=cards)

# --- отбор реальных компаний ------------------------------------------------
ecx = sqlite3.connect(ENRICH)
ecx.row_factory = sqlite3.Row
news_inns = [r["inn"] for r in ecx.execute(
    "SELECT DISTINCT inn FROM signals WHERE source_url LIKE 'http%'")]
enr_inns = [r["inn"] for r in ecx.execute(
    "SELECT inn FROM companies WHERE best_email IS NOT NULL "
    "AND best_email != ''")]
ocx = sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)
ocx.row_factory = sqlite3.Row


def obz(inn):
    r = ocx.execute("SELECT inn, division, name_short FROM obzvon WHERE inn=?",
                    (inn,)).fetchone()
    return dict(r) if r else None


news_kc = [i for i in news_inns if (obz(i) or {}).get("division") == "kc"]
news_meyer = [i for i in news_inns
              if (obz(i) or {}).get("division") == "meyer"]
news_no_div = [i for i in news_inns if (obz(i) or {}).get("division") is None]
cold_kc = [i for i in enr_inns
           if (obz(i) or {}).get("division") == "kc" and i not in news_kc]
meyer_one = news_meyer[0] if news_meyer else ocx.execute(
    "SELECT inn FROM obzvon WHERE division='meyer' LIMIT 1").fetchone()["inn"]
# 20 писем: КЦ-кампания (новостные КЦ + холодные КЦ) + Meyer-кампания
# (новостные Meyer) — гейт требует совпадения кампания×компания.
kc_list = news_kc + cold_kc
meyer_list = news_meyer
picked = [(i, "kc") for i in kc_list[:20 - len(meyer_list[:4])]] + \
         [(i, "meyer") for i in meyer_list[:4]]
picked = picked[:20]
assert len(picked) == 20, f"нужно 20, есть {len(picked)}"

# --- кампания КЦ + 20 писем в confirm-очередь -------------------------------
cids = {}
sids = {}
for seg, label in (("КЦ", "kc"), ("Meyer", "meyer")):
    c = store.create_campaign(CampaignIn(
        name=f"Dry-run BASE-MERGE ({seg})", legal_entity="ООО «Руспром»",
        legal_inn="2221239841", config={"segment": seg}))
    cids[label] = c
    sids[label] = store.add_step(SequenceStepIn(
        campaign_id=c, step_index=0, delay_hours=0, subject_tmpl="s",
        body_tmpl="b"))
cid, sid = cids["kc"], sids["kc"]
report = {"letters": [], "gate_cases": [], "needs_data": None,
          "news_leads_without_division": len(news_no_div)}
news_count = 0
for n, (inn, seg) in enumerate(picked, 1):
    ccid, csid = cids[seg], sids[seg]
    card = cards.card(inn)
    ob = card["obzvon"] or {}
    email = None
    for e in card["contacts"]["emails"]:
        email = e["email"]
        break
    email = email or f"office@company-{inn}.ru"
    rid = store.upsert_recipient(RecipientIn(
        email=email, domain=email.rsplit("@", 1)[-1], inn=inn,
        company_name=ob.get("name_short") or "", segment="КЦ"))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=f"dr{n}", campaign_id=ccid, recipient_id=rid,
        sequence_step_id=csid, scheduled_at=datetime.now(UTC)),
        status="pending_review")
    signals = card["enrich"]["signals"]
    subject = f"Компрессорное решение для {ob.get('name_short', 'вас')}"
    body = ("Здравствуйте! Видели новость про вашу площадку.\n--\n"
            "ООО «Руспром», ИНН 2221239841")
    panel = build_panel(inn=inn, email=email, letter_subject=subject,
                        letter_body=body, store=store, card=card)
    r = cs.submit(email=email, inn=inn, campaign_id=ccid, recipient_id=rid,
                  message_id=mid, subject=subject, body=body, panel=panel)
    ne = panel["news_events"]
    if ne["count"]:
        news_count += 1
    report["letters"].append({
        "n": n, "inn": inn, "email": email,
        "company": ob.get("name_short"), "division": card["division"],
        "campaign": seg,
        "review_status": r.status, "review_id": r.review_id,
        "news_events": ne["count"],
        "news_links": [e["source_url"] for e in ne["events"]][:3],
        "signal_match": [e["signal_match"] for e in ne["events"]][:3],
        "stop_flags": [f["code"] for f in panel["stop_flags"]],
        "full_card": panel["company_full"]["available"],
        "division_flags": [f["code"] for f in panel["stop_flags"]
                           if f["code"].startswith("division")],
    })

# --- 3 негативных кейса гейта -----------------------------------------------
now = datetime.now(UTC)


def _neg(name, inn, mailbox, key):
    rid = store.upsert_recipient(RecipientIn(
        email=f"{key}@negcase.ru", domain="negcase.ru", inn=inn))
    store.set_recipient_validation(rid, valid_status="valid",
                                   mx_provider="yandex")
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=key, campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=now))
    case = {"case": name, "inn": inn, "mailbox": mailbox}
    # точка 1: сборка очереди
    orch = Orchestrator(config=config, store=store, sender=sndr,
                        cadence=None, gates=_Gates(), imap=None, warmup=None,
                        analytics=None, cards=cards)
    msg_in = MessageIn(idempotency_key=key + "q", campaign_id=cid,
                       recipient_id=rid, sequence_step_id=sid,
                       scheduled_at=now)
    case["point1_queue_block"] = orch._division_queue_block(
        msg_in, store.get_campaign(cid))
    # точка 2: подтверждение
    r = cs.submit(email=f"{key}@negcase.ru", inn=inn, campaign_id=cid,
                  recipient_id=rid, subject="s", body="b",
                  panel={"stop_flags": []})
    row = store.confirm_get(r.review_id)
    case["point2_flags"] = [f["code"] for f in row["panel"]["stop_flags"]]
    try:
        cs.approve(r.review_id, operator="dryrun")
        case["point2_approve"] = "ПРОПУСТИЛ (ОШИБКА!)"
    except ConfirmBlockedError as e:
        case["point2_approve"] = f"blocked: {e}"
    # точка 3: SMTP-диспетчер
    for mb in ("box1@rusprom.ru", "box3@rusprom.ru"):
        from sender.dtos import MailboxState
        store.upsert_mailbox_state(MailboxState(
            mailbox_id=mb, provider="yandex",
            day_key=now.strftime("%Y-%m-%d"), sent_today=0, sent_total=0,
            ramp_day=60, daily_limit=200, last_sent_at=None, paused=False,
            pause_reason=None))
    try:
        sndr.send(store.get_message(mid),
                  RenderedMessage(subject="s", body="b", unfilled_fields=()),
                  mailbox, now=now, manual=True)
        case["point3_smtp"] = "ПРОПУСТИЛ (ОШИБКА!)"
    except SuppressedError as e:
        case["point3_smtp"] = f"blocked: {e}"
    report["gate_cases"].append(case)


_neg("КЦ-ящик × Meyer-компания", meyer_one, "box1@rusprom.ru", "neg1")  # кампания КЦ
_neg("ящик без division (КЦ-компания)", picked[0][0], "box3@rusprom.ru", "neg2")
_neg("компания без division (ИНН не из базы)", "9909999999",
     "box1@rusprom.ru", "neg3")

# события division_gate_block записались
evs = store.list_events(event_type="division_gate_block", limit=20)
report["division_gate_events"] = len(evs)

# --- контракт news_object/city: лид падает в «дозаполнить данные» ------------
rid = store.upsert_recipient(RecipientIn(
    email="nd@case.ru", domain="case.ru", inn=picked[1]))
mid, _ = store.enqueue_message(MessageIn(
    idempotency_key="ndX", campaign_id=cid, recipient_id=rid,
    sequence_step_id=sid, scheduled_at=now))
try:
    sndr.send(store.get_message(mid),
              RenderedMessage(subject="s", body="b",
                              unfilled_fields=("news_object", "city")),
              "box1@rusprom.ru", now=now, manual=True)
except Exception:
    pass
nd = store.list_needs_data()
report["needs_data"] = {"rows": len(nd),
                        "reason": nd[0]["last_error"] if nd else None}

# --- итоги -------------------------------------------------------------------
report["summary"] = {
    "letters_total": len(report["letters"]),
    "letters_pending": sum(1 for x in report["letters"]
                           if x["review_status"] == "pending"),
    "news_letters": news_count,
    "division_matches_campaign": all(
        x["division"] == x["campaign"] for x in report["letters"]),
    "full_card_everywhere": all(x["full_card"] for x in report["letters"]),
    "gate_cases_all_blocked": all(
        c["point1_queue_block"] and "blocked" in c["point2_approve"]
        and "blocked" in c["point3_smtp"] for c in report["gate_cases"]),
}
out = os.path.join(SCRATCH, "dryrun-basemerge-report.json")
json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False,
          indent=1)
print(json.dumps(report["summary"], ensure_ascii=False, indent=1))
print("gate cases:")
for c in report["gate_cases"]:
    print(f"  [{c['case']}] q={c['point1_queue_block']} | "
          f"approve={c['point2_approve'][:60]} | smtp={c['point3_smtp'][:60]}")
print(f"needs_data: {report['needs_data']}")
print(f"события division_gate_block: {report['division_gate_events']}")
print(f"отчёт: {out}")
store.close()
