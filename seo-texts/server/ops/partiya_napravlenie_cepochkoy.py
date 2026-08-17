# -*- coding: utf-8 -*-
"""Что даст цепочка тем, кому направление не задали ни партия, ни карточка.

Правка partiya_gen.py убрала подстановку 'kc' и вернула разбор направления
цепочке ai_letter.target_division (новость -> потребности -> метка базы ->
профиль по ОКВЭДу -> запасной kc). Прежде чем гонять на этом деньги, надо
увидеть, что цепочка отвечает: если она на всех тех же 15% отвечает 'kc'
запасным вариантом, правка ничего не меняет и это надо сказать честно.

Считаем ТОЛЬКО тех, у кого _request вернул None, и печатаем, каким правилом
цепочка решила и что получилось.

    python zapusk_svoego_skripta.py ops/partiya_napravlenie_cepochkoy.py 400
"""
import io
import os
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import target_division                   # noqa: E402
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.confirm import ConfirmSend                         # noqa: E402
from sender.store import Store                                 # noqa: E402
from sender.suppression import Suppression                     # noqa: E402

ГРУППА = "Партия 935"
ИМЯ = "NAPRAVLENIE-CEPOCHKOY.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 else 400

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
шаг = max(1, len(в_группе) // max(1, СКОЛЬКО * 2))

счёт, правила, примеры = Counter(), Counter(), []
разобрано = 0
видели = set()
for rid in в_группе[::шаг]:
    if разобрано >= СКОЛЬКО:
        break
    r = store.get_recipient(rid)
    if not r:
        continue
    inn = "".join(c for c in str(getattr(r, "inn", "") or "") if c.isdigit())
    email = str(getattr(r, "email", "") or "").strip().lower()
    if not inn or not email or inn in видели:
        continue
    видели.add(inn)
    if cs._guard(inn=inn, email=email):
        continue
    try:
        req = q._request(r)
    except Exception:                                          # noqa: BLE001
        continue
    разобрано += 1
    явное = str(req.get("target_division") or "")
    if явное in ("kc", "meyer"):
        счёт["направление задано партией/карточкой"] += 1
        continue
    счёт["направление НЕ задано - решает цепочка"] += 1
    d, почему = target_division(req, default="kc")
    правила[f"{d} по правилу «{почему}»"] += 1
    if len(примеры) < 12:
        примеры.append(
            f"{req.get('company_name')} | ОКВЭД "
            f"{str(req.get('okved') or '-')[:40]} -> **{d}** ({почему})")

С = [f"# Направление для тех, кому его не задали (выборка {разобрано})", "",
     "Прежде правка подставляла им 'kc' молча. Теперь решает та же цепочка,",
     "что и в генераторе.", ""]
for k, n in счёт.most_common():
    С.append(f"- {k}: **{n}**")
С += ["", "## Чем именно решила цепочка", ""]
for k, n in правила.most_common():
    С.append(f"- {k}: **{n}**")
С += ["", "## Примеры", ""] + [f"- {s}" for s in примеры]

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                        # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

for k, n in счёт.most_common():
    print(f"  {k:<44} {n}")
print("--- чем решила цепочка ---")
for k, n in правила.most_common():
    print(f"  {k:<44} {n}")
for s in примеры[:8]:
    print("  " + s.replace("**", ""))
