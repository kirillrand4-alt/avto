# -*- coding: utf-8 -*-
"""Разбор очереди подтверждения кампаний 18/22/23 (владелец 16.11: «отправляй 120; записана за мейер, а пишет кц —
добавь направление кц (если письма реально подходят); остальные сними»).
  · проходит по правилам (тот же адрес: КЦ 15+ дн / Meyer / не писали) → ручная отправка approve(force=True);
  · гейт направлений + линза адресата ok → дописать kc в obzvon.division (журнал kc-v-metku-1611.jsonl,
    откат --otkat) и ручная отправка; линза «мимо адресата» → снять; линзы нет → оставить на подтверждении;
  · стоп-флаги (сайт не той компании, проба MX), нет почты у домена, КЦ <15 дн, отвечали → снять.
Кампания 13 (на паузе) не трогается. Пауза 20 с между письмами, порядок перемешан (mail.ru вразброс).
    razobrat_ozhidanie_1611.py [--primenit|--zapusk|--otkat]   лог _ops/razobrat-ozhidanie-1611.log"""
import io, json, os, random, re, sqlite3, sys, time
from collections import Counter
from datetime import datetime, timezone
ОПС = r"C:\sender\_ops"; МЕТКИ = os.path.join(ОПС, "kc-v-metku-1611.jsonl"); ЖУР = os.path.join(ОПС, "razobrat-ozhidanie-1611.jsonl")
ПРИМ = "--primenit" in sys.argv
if "--zapusk" in sys.argv:
    import subprocess
    л = io.open(os.path.join(ОПС, "razobrat-ozhidanie-1611.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--primenit"], cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
if "--otkat" in sys.argv:
    with o:
        for с in io.open(МЕТКИ, encoding="utf-8"):
            з = json.loads(с); o.execute("UPDATE obzvon SET division=? WHERE inn=?", (з["bylo"], з["inn"]))
    print("откат меток сделан"); sys.exit(0)
if ПРИМ:
    for с in io.open(r"C:\sender\panel.env", encoding="utf-8-sig"):
        if "=" in с and not с.lstrip().startswith("#"):
            к, v = с.split("=", 1); os.environ.setdefault(к.strip(), v.strip().strip('"'))
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
cs = build_deps(cfg, st, dry_run=not ПРИМ).confirm
адресат = {}
for ф in ("gaz-kc-adresat.jsonl", "gaz-kc-adresat-23.jsonl"):
    try:
        for с in io.open(os.path.join(ОПС, ф), encoding="utf-8"):
            з = json.loads(с); адресат[int(з["karta"])] = з["ok"]
    except FileNotFoundError: pass
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True); c.row_factory = sqlite3.Row
now = datetime.now(timezone.utc); сч = Counter(); слать = []; снять = []
for r in c.execute("SELECT * FROM confirm_reviews WHERE status='pending' AND campaign_id IN (18,22,23) AND COALESCE(kind,'outbound')!='reply'").fetchall():
    rid = int(r["id"]); п = json.loads(r["panel_json"] or "{}") or {}
    if (п.get("actions") or {}).get("confirm_hold"):
        коды = "+".join(sorted({(f.get("code") if isinstance(f, dict) else str(f)) for f in (п.get("stop_flags") or [])}))
        снять.append((rid, r["message_id"], "стоп-флаг: " + коды)); continue
    б = cs._guard(inn=r["inn"], email=r["email"] or "")
    if б and str(б).startswith("recent_contact"):
        em = (r["email"] or "").lower()
        посл = c.execute("SELECT m.mailbox_id, m.sent_at FROM messages m JOIN recipients rr ON rr.id=m.recipient_id WHERE lower(rr.email)=? AND m.status='sent' ORDER BY m.sent_at DESC LIMIT 1", (em,)).fetchone()
        if посл:
            мейер = bool(re.search(r"sort|rentgen|inspection|optic", посл[0] or ""))
            дн = (now - datetime.fromisoformat(посл[1][:19]).replace(tzinfo=timezone.utc)).days
            if not мейер and дн < 15: снять.append((rid, r["message_id"], "КЦ на этот адрес <15 дн")); continue
        б = None
    if б: снять.append((rid, r["message_id"], "заслон: " + str(б)[:60])); continue
    if cs._division_blocked(dict(r)):
        ок = адресат.get(rid)
        if ок is None: сч["гейт: линзы нет — оставлено"] += 1; continue
        if not ок: снять.append((rid, r["message_id"], "гейт направлений + линза: мимо адресата")); continue
        слать.append((rid, r["inn"], "гейт → kc в метку")); continue
    слать.append((rid, None, "по правилам"))
for _, _, п in снять: сч["снять: " + п[:50]] += 1
for _, инн, п in слать: сч["отправить: " + п] += 1
print("сухой" if not ПРИМ else "ПРИМЕНЯЮ", dict(сч), flush=True)
if not ПРИМ: sys.exit(0)
т = now.isoformat(timespec="seconds")
w = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with w:
    for rid, мид, п in снять:
        причина = "владелец 16.11: не подходит (%s)" % п
        w.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", (причина, т, т, rid))
        if мид: w.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? AND status IN ('pending_review','scheduled')", (причина, мид))
ж = io.open(ЖУР, "a", encoding="utf-8")
for rid, мид, п in снять: ж.write(json.dumps({"karta": rid, "snyato": п, "ts": т}, ensure_ascii=False) + "\n")
ж.flush(); os.fsync(ж.fileno())
with o, io.open(МЕТКИ, "a", encoding="utf-8") as жм:
    for _, инн, _ in слать:
        if not инн: continue
        row = o.execute("SELECT division FROM obzvon WHERE inn=?", (str(инн),)).fetchone()
        if not row or "kc" in str(row[0] or "").split("+"): continue
        было = row[0] or ""; стало = (было + "+kc") if было else "kc"
        o.execute("UPDATE obzvon SET division=? WHERE inn=?", (стало, str(инн)))
        жм.write(json.dumps({"inn": str(инн), "bylo": было, "stalo": стало, "ts": т}, ensure_ascii=False) + "\n")
print("снято %d, метки дописаны; шлю %d" % (len(снять), len(слать)), flush=True)
random.shuffle(слать); ит = Counter()
for i, (rid, _, п) in enumerate(слать, 1):
    try:
        р = cs.approve(rid, operator="владелец 16.11: по правилам / kc дописан в метку", force=True)
        ит["отправлено" if getattr(р, "ok", р) else "не ушло"] += 1; ок = "ok"
    except Exception as ex:  # noqa: BLE001
        ит["ошибка: " + str(ex)[:50]] += 1; ок = str(ex)[:100]
    ж.write(json.dumps({"karta": rid, "otpravka": ок, "put": п}, ensure_ascii=False) + "\n"); ж.flush(); os.fsync(ж.fileno())
    if i % 10 == 0: print("%s %d/%d %s" % (time.strftime("%H:%M:%S"), i, len(слать), dict(ит)), flush=True)
    time.sleep(20)
print("ГОТОВО", dict(ит), flush=True)
