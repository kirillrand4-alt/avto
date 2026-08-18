# -*- coding: utf-8 -*-
"""Вопрос владельца 18.08: «если я включу ящики Meyer, на них не начнётся
опять отправка?»

Отвечаем числами, а не рассуждением. Отправка на ящике начнётся ТОЛЬКО если
сойдутся все условия сразу:
  1) ящик снят с паузы и у него есть дневной лимит;
  2) есть письма в статусе approved (автоотправка берёт ТОЛЬКО их);
  3) письмо meyer-направления - иначе гейт направления не пустит его на
     meyer-ящик (division_block);
  4) кампания активна, автоотправка включена, окно отправки открыто.
Здесь печатаем каждое из четырёх, чтобы владелец решал по фактам.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# --- 1. ЯЩИКИ ------------------------------------------------------------- #
print("=== ЯЩИКИ (направление, пауза, лимит, отправлено сегодня)")
состояния = {}
try:
    with store._lock:
        for r in store._conn.execute(
            "SELECT mailbox_id, paused, daily_limit, sent_today, ramp_day "
                "FROM mailbox_state"):
            состояния[str(r[0])] = tuple(r[1:])
except Exception as ex:                                          # noqa: BLE001
    print("  mailbox_state не прочитан:", str(ex)[:120])

for mb in cfg.mailboxes():
    п, л, с, рд = состояния.get(mb.mailbox_id, (None, None, None, None))
    print(f"  {mb.mailbox_id:<28} направление={str(mb.division or '-'):<6} "
          f"пул={str(mb.pool or '-'):<10} пауза={п} лимит={л} "
          f"сегодня={с} рамп={рд} прогрев={mb.is_warmup_node}")

мейер = [m.mailbox_id for m in cfg.mailboxes() if (m.division or "") == "meyer"]
print(f"  ящиков meyer: {len(мейер)} -> {мейер}")

# --- 2. ОЧЕРЕДЬ ----------------------------------------------------------- #
print("\n=== ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ по кампаниям и статусам")
with store._lock:
    камп = {int(r[0]): (str(r[1]), str(r[2])) for r in store._conn.execute(
        "SELECT id, name, status FROM campaigns")}
    ряды = store._conn.execute(
        "SELECT campaign_id, status, COUNT(*) FROM confirm_reviews "
        "GROUP BY campaign_id, status").fetchall()
по_кампании = {}
for cid, ст, n in ряды:
    по_кампании.setdefault(cid, {})[ст] = n
for cid in sorted(по_кампании, key=lambda x: (x is None, x)):
    имя, статус = камп.get(cid, ("(нет кампании)", "-"))
    д = по_кампании[cid]
    вид = " ".join(f"{k}={v}" for k, v in sorted(д.items()))
    print(f"  кампания {str(cid):<5} {имя[:28]:<30} статус={статус:<10} {вид}")

# --- 3. НАПРАВЛЕНИЕ ГОТОВЫХ ПИСЕМ ----------------------------------------- #
print("\n=== APPROVED-ПИСЬМА: какого направления")
with store._lock:
    готовые = store._conn.execute(
        "SELECT id, campaign_id, email, panel_json FROM confirm_reviews "
        "WHERE status='approved'").fetchall()
свод = Counter()
мейеровские = []
for rid, cid, email, pj in готовые:
    try:
        p = json.loads(pj or "{}")
    except Exception:                                            # noqa: BLE001
        p = {}
    d = str(p.get("letter_division") or "").strip().lower()
    if d not in ("kc", "meyer"):
        c = p.get("company") if isinstance(p.get("company"), dict) else {}
        d = str((c or {}).get("division") or "").strip().lower() or "(пусто)"
    свод[(cid, d)] += 1
    if d == "meyer":
        мейеровские.append((rid, cid, email))
print(f"  всего approved: {len(готовые)}")
for (cid, d), n in sorted(свод.items(), key=lambda x: -x[1]):
    print(f"    кампания {cid}: направление {d} — {n}")
if мейеровские:
    print("  ПИСЬМА MEYER В ГОТОВЫХ (уедут при включении ящика):")
    for rid, cid, email in мейеровские[:20]:
        print(f"    #{rid} кампания {cid} {email}")

# --- 4. РУБИЛЬНИКИ -------------------------------------------------------- #
print("\n=== РУБИЛЬНИКИ")
for ключ in ("auto_send_enabled", "confirm_required", "probe_sync_enabled",
             "addr_probe_enabled"):
    print(f"  {ключ}: {store.get_setting(ключ, '(нет)')}")
w = cfg.sending_window()
print(f"  окно отправки: дни={w.days} {w.start}-{w.end} tz={w.tz}")
print(f"  окно по времени получателя: "
      f"{store.get_setting('sending_window', '(нет)')}")
print(f"  confirm.live_send: {cfg.get('confirm.live_send', '(нет)')}")
