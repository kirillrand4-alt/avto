# -*- coding: utf-8 -*-
"""Карточки на удержании «сайт НЕ этой компании» (site_mismatch) — проверка моделью
провайдера (владелец 28.10: «сделай, остальные скипни»). По каждой: название и
ИНН компании (база обзвона / карточка), адрес, домен, сайт из обогащения, тема и
начало письма. Вердикт: «та_же» -> штатный путь кнопки «В автоотправку»
(заслоны _guard и направлений, слот окна получателя, approved, reason
bulk-to-auto); «чужая»/«неясно» -> skipped. Журнал вердиктов
_ops/site-mismatch-proverka.jsonl (резюм). Ничего не отправляет само.
    site_mismatch_proverka.py [--primenit]"""
import io
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP                          # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402
from sender.config import Config                   # noqa: E402
from sender.store import Store                     # noqa: E402
from sender.wiring import build_deps               # noqa: E402

ЖУР = r"C:\sender\_ops\site-mismatch-proverka2.jsonl"   # 2: судим по адресу, а не по тексту
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
o = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True, timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
вердикты = {}
if os.path.exists(ЖУР):
    for s in io.open(ЖУР, encoding="utf-8"):
        x = json.loads(s)
        вердикты[x["karta"]] = x
карточки = []
for kid, inn, em, subj, body, pj in c.execute(
        "SELECT id, inn, lower(email), subject, body, panel_json FROM confirm_reviews WHERE status='pending' AND panel_json LIKE '%site_mismatch%'"):
    имя = (o.execute("SELECT name_short FROM obzvon WHERE inn=?", (str(inn),)).fetchone() or [None])[0]
    сайт, деят = (e.execute("SELECT site, activity FROM companies WHERE inn=?", (str(inn),)).fetchone() or [None, None])
    if not имя:
        имя = (c.execute("SELECT company_name FROM recipients WHERE inn=? LIMIT 1", (inn,)).fetchone() or [""])[0]
    карточки.append({"karta": kid, "inn": str(inn), "name": имя or "", "email": em, "site": сайт or "",
                     "activity": (деят or "")[:300], "tema": subj or ""})
print("на удержании site_mismatch:", len(карточки), "| уже с вердиктом:", sum(1 for k in карточки if k["karta"] in вердикты))
ЗАДАНИЕ = """Мы рассылаем деловые письма компаниям. Проверка нашла, что сайт, привязанный к компании,
возможно, принадлежит ДРУГОЙ фирме — тогда и адрес почты мог быть взят с чужого сайта.
Для каждой карточки реши: принадлежит ли АДРЕС ПОЧТЫ этой компании (название, ИНН, деятельность)?
ВАЖНО: текст письма НЕ доказательство — он всегда написан по карточке компании. Суди по самому
адресу: домен, имя ящика (local part), сайт.
- "та_же": корпоративный домен совпадает с названием/брендом компании или её сайтом; либо публичная
  почта, где имя ящика явно про эту компанию (название, бренд, город+профиль);
- "чужая": домен или имя ящика указывают на другую фирму/другой профиль (katunstroy@ у пищевого
  холдинга, гигант вроде rosneft у мелкой фирмы, сайт другой отрасли);
- "неясно": публичная почта с безликим именем (цифры, фамилия) или данных мало.
Ответ СТРОГО JSON: {"verdikty":[{"karta":0,"verdikt":"та_же|чужая|неясно","pochemu":"до 15 слов"}]}

КАРТОЧКИ:
%s"""
ж = io.open(ЖУР, "a", encoding="utf-8")
новые = [k for k in карточки if k["karta"] not in вердикты]
for i in range(0, len(новые), 10):
    пачка = новые[i:i + 10]
    try:
        m = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ % json.dumps(пачка, ensure_ascii=False, indent=1)}],
                           "claude-sonnet-4-6", 3000, thinking=False, effort="low")
        т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        вх = [x.start() for x in re.finditer(r'\{\s*"verdikty"', т)]
        д = json.JSONDecoder(strict=False).raw_decode(т[вх[-1]:])[0] if вх else {}
    except Exception as ex:  # noqa: BLE001
        print("пачка не судилась:", str(ex)[:150], flush=True)
        continue
    for v in д.get("verdikty") or []:
        try:
            kid = int(v.get("karta"))
        except (TypeError, ValueError):
            continue
        if kid not in {k["karta"] for k in пачка}:
            continue
        x = {"karta": kid, "verdikt": str(v.get("verdikt") or "неясно"), "pochemu": str(v.get("pochemu") or "")[:200]}
        вердикты[kid] = x
        ж.write(json.dumps(x, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
from collections import Counter  # noqa: E402
print("вердикты:", dict(Counter(вердикты[k["karta"]]["verdikt"] for k in карточки if k["karta"] in вердикты)))
for k in карточки[:8]:
    if k["karta"] in вердикты:
        print("  %s %s %s | %s" % (k["karta"], k["email"], вердикты[k["karta"]]["verdikt"], вердикты[k["karta"]]["pochemu"]))
# Два взгляда: прогон 1 судил по тексту письма (профиль компании vs адрес), прогон 2 — по
# самому адресу. В автоотправку — только где ОБА сказали «та_же», иначе снимаем.
_п1 = {}
if os.path.exists(r"C:\sender\_ops\site-mismatch-proverka.jsonl"):
    for s_ in io.open(r"C:\sender\_ops\site-mismatch-proverka.jsonl", encoding="utf-8"):
        x_ = json.loads(s_)
        _п1[x_["karta"]] = x_["verdikt"]
for kid_, v_ in вердикты.items():
    if v_["verdikt"] == "та_же" and _п1.get(kid_, "та_же") != "та_же":
        v_["verdikt"] = "спорно"
        v_["pochemu"] = "по тексту письма — %s; %s" % (_п1.get(kid_), v_["pochemu"])
print("итог двух прогонов:", dict(Counter(вердикты[k["karta"]]["verdikt"] for k in карточки if k["karta"] in вердикты)))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
now = datetime.now(timezone.utc)
win = window_from(store, cfg)
итог = Counter()
for k in карточки:
    v = вердикты.get(k["karta"])
    if not v:
        итог["без вердикта — оставлено"] += 1
        continue
    if v["verdikt"] != "та_же":
        store.confirm_decide(k["karta"], status="skipped", decided_by="claude (владелец 28.10)",
                             reason="site_mismatch: модель — %s (%s)" % (v["verdikt"], v["pochemu"][:120]))
        mid = c.execute("SELECT message_id FROM confirm_reviews WHERE id=?", (k["karta"],)).fetchone()[0]
        if mid:
            with c:
                c.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? AND status IN ('pending_review','scheduled')",
                          ("site_mismatch: " + v["verdikt"], mid))
        итог["снято: " + v["verdikt"]] += 1
        continue
    r = next((x for x in deps.confirm.pending(limit=100_000) if x.get("id") == k["karta"]), None)
    if not r:
        итог["карточка уже не pending"] += 1
        continue
    bl = deps.confirm._guard(inn=r.get("inn"), email=r.get("email") or "")
    if bl:
        итог["та_же, но заслон — оставлено: " + re.sub(r"\d+", "N", str(bl))[:40]] += 1
        continue
    dv = deps.confirm._division_blocked(r)
    if dv:
        итог["та_же, но направления — оставлено"] += 1
        continue
    rec = deps.store.get_recipient(int(r["recipient_id"])) if r.get("recipient_id") else None
    if rec is None or not r.get("message_id"):
        итог["нет получателя/письма — оставлено"] += 1
        continue
    слот = next_slot(win, recipient_tz_name(win, rec), now)
    deps.store.reschedule_message(int(r["message_id"]), слот)
    if deps.store.confirm_decide(k["karta"], status="approved", decided_by="claude (владелец 28.10)",
                                 reason="bulk-to-auto: site_mismatch проверен моделью (та же компания)"):
        итог["в автоотправку"] += 1
print("ИТОГ:", dict(итог))
