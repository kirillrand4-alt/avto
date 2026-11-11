# -*- coding: utf-8 -*-
"""Применить итог инженерной линзы к карточкам кампании 22 (владелец 11.11: «делай»).
  * исправления нет (газ им не нужен) — карточку снять;
  * исправление меняет газ / расплывчатое («может», «возможно», «в отдельных») / не проходит проверку фразы
    (цифры, «мы», вакуум, длина…) — карточку снять: верной фразы для нашей станции нет;
  * годное исправление — заменить фразу в тексте карточки (только если фраза встречается ровно один раз).
Карточки, тронутые оператором (edited_body ≠ body) и не pending, не трогаем. Журнал _ops/gaz-linza-primenit.jsonl.
    gaz_linza_primenit.py [--primenit]"""
import io, json, os, re, sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaz_kanon as K   # noqa: E402
ПРИМ = "--primenit" in sys.argv
лин = {}
for с in io.open(r"C:\sender\_ops\gaz-kc-linza.jsonl", encoding="utf-8"):
    try: з = json.loads(с); лин[з["karta"]] = з
    except (ValueError, KeyError): pass
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
жур = io.open(r"C:\sender\_ops\gaz-linza-primenit.jsonl", "a", encoding="utf-8")
сч = Counter()
for кид, з in лин.items():
    if з.get("ok"): continue
    р = c.execute("SELECT status, body, edited_body, message_id, panel_json FROM confirm_reviews WHERE id=?", (кид,)).fetchone()
    if not р or р[0] != "pending": сч["не pending"] += 1; continue
    if р[2] and р[2] != р[1]: сч["тронута оператором"] += 1; continue
    газ = "O2" if з.get("gaz") == "кислород" else "N2"
    fix = (з.get("fix") or "").strip()
    чужой_газ = r"(?i)кислород" if газ == "N2" else r"(?i)\bазот"
    if not fix: решение, причина = "снять", "линза: газ компании не нужен — %s" % з.get("problem", "")[:120]
    elif re.search(чужой_газ, fix) and not re.search(чужой_газ, з.get("fraza", "")): решение, причина = "снять", "линза: верной фразы про наш газ нет"
    elif re.search(r"(?i)\bможет\b|возможн|в отдельных|как правило", fix): решение, причина = "снять", "линза: исправление расплывчатое"
    else:
        f2, беда = K.фраза(fix, газ)
        if беда: решение, причина = "снять", "линза: исправление не прошло проверку (%s)" % беда
        elif (р[1] or "").count(з.get("fraza", "")) != 1: решение, причина = "пропуск", "фраза не найдена в тексте"
        else: решение, причина = "заменить", f2
    сч[решение] += 1
    if ПРИМ and решение == "снять":
        c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", (причина[:200], т, т, кид))
        if р[3]: c.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? AND status IN ('pending_review','scheduled')", (причина[:100], р[3]))
    elif ПРИМ and решение == "заменить":
        новое = р[1].replace(з["fraza"], причина, 1)
        pj = json.loads(р[4] or "{}")
        if isinstance(pj.get("gaz"), dict): pj["gaz"]["fraza"] = причина; pj["gaz"]["fraza_do_linzy"] = з["fraza"]
        c.execute("UPDATE confirm_reviews SET body=?, edited_body=CASE WHEN edited_body IS NULL THEN NULL ELSE ? END, panel_json=?, updated_at=? WHERE id=? AND status='pending'",
                  (новое, новое, json.dumps(pj, ensure_ascii=False), т, кид))
    жур.write(json.dumps({"karta": кид, "reshenie": решение, "prichina": причина if решение != "заменить" else "", "bylo": з.get("fraza"),
                          "stalo": причина if решение == "заменить" else "", "primeneno": ПРИМ, "ts": т}, ensure_ascii=False) + "\n")
if ПРИМ: c.commit()
жур.flush(); os.fsync(жур.fileno())
print("%s: %s" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон", dict(сч)))
print("pending в кампании 22:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchone()[0])
