# -*- coding: utf-8 -*-
"""Применить линзы к кампании 23 «КЦ газ 13.11» (владелец 16.11: «да, исправь»):
  * инженерная: исправление годно → заменить фразу (сохраняя «Увидел, что …»); исправления нет / меняет газ /
    расплывчатое / не проходит проверку → снять;
  * адресат: «мимо адресата» → снять.
Правит confirm_reviews (pending, не тронутые оператором) и messages.body_rendered; снятие — skipped в обоих.
Журнал _ops/gaz-linzy-primenit-23.jsonl.   gaz_linzy_primenit_23.py [--primenit]"""
import io, json, os, re, sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaz_kanon as K
ПРИМ = "--primenit" in sys.argv
def посл(имя):
    д = {}
    for с in io.open(r"C:\sender\_ops\%s.jsonl" % имя, encoding="utf-8"):
        try: з = json.loads(с); д[з["karta"]] = з
        except (ValueError, KeyError): pass
    return д
лин, адр = посл("gaz-kc-linza-23"), посл("gaz-kc-adresat-23")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
жур = io.open(r"C:\sender\_ops\gaz-linzy-primenit-23.jsonl", "a", encoding="utf-8")
сч = Counter()
def снять(кид, mid, причина):
    if not ПРИМ: return
    c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", (причина[:200], т, т, кид))
    if mid: c.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? AND status IN ('pending_review','scheduled')", (причина[:100], mid))
for кид, body, ed, mid in c.execute("SELECT id, body, edited_body, message_id FROM confirm_reviews WHERE campaign_id=23 AND status='pending'").fetchall():
    if ed and ed != body: сч["тронута оператором"] += 1; continue
    а = адр.get(кид); л = лин.get(кид)
    if а and not а.get("ok"):
        сч["снять: мимо адресата"] += 1; снять(кид, mid, "линза адресат: мимо адресата"); жур.write(json.dumps({"karta": кид, "r": "адресат"}, ensure_ascii=False) + "\n"); continue
    if not л or л.get("ok"): сч["ok"] += 1; continue
    газ = "O2" if "кислородн" in body.split("\n\n")[1] else "N2"
    fix = (л.get("fix") or "").strip(); фраза = (л.get("fraza") or "").strip()
    чужой = r"(?i)кислород" if газ == "N2" else r"(?i)\bазот"
    if not fix: р = "линза: газ компании не нужен"
    elif re.search(чужой, fix) and not re.search(чужой, фраза): р = "линза: верной фразы про наш газ нет"
    elif re.search(r"(?i)\bможет\b|возможн|в отдельных|как правило", fix): р = "линза: исправление расплывчатое"
    else:
        f = re.sub(r"^Увидел, что\s+", "", fix); f = f[0].upper() + f[1:] if f else f
        f2, беда = K.фраза(f, газ)
        if беда: р = "линза: исправление не прошло проверку (%s)" % беда
        elif body.count(фраза) != 1: сч["фраза не найдена"] += 1; continue
        else:
            нов = K.увидел(f2) if фраза.startswith("Увидел, что") else f2
            сч["заменить"] += 1
            if ПРИМ:
                нб = body.replace(фраза, нов, 1)
                c.execute("UPDATE confirm_reviews SET body=?, updated_at=? WHERE id=? AND status='pending'", (нб, т, кид))
                if mid:
                    м = c.execute("SELECT body_rendered FROM messages WHERE id=?", (mid,)).fetchone()
                    if м and м[0] and фраза in м[0]: c.execute("UPDATE messages SET body_rendered=? WHERE id=?", (м[0].replace(фраза, нов, 1), mid))
                жур.write(json.dumps({"karta": кид, "r": "замена", "bylo": фраза, "stalo": нов}, ensure_ascii=False) + "\n")
            continue
    сч["снять: " + р.split(" (")[0]] += 1; снять(кид, mid, р); жур.write(json.dumps({"karta": кид, "r": р}, ensure_ascii=False) + "\n")
if ПРИМ: c.commit()
жур.flush(); os.fsync(жур.fileno())
print("ПРИМЕНЕНО" if ПРИМ else "сухой", dict(сч))
print("pending в 23:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=23 AND status='pending'").fetchone()[0])
