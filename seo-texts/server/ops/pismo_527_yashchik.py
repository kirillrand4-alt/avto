# -*- coding: utf-8 -*-
"""Почему письму КЦ подставился ящик Meyer: разбор конкретного письма.

Владелец 17.08 прислал панель: фильтр «КЦ» включён, письмо #527 (кампания 1,
новость про машиниста компрессорных установок в «Кубань-вино») - а в строке
«с ящика» стоит «Юрий Кузьмин, Meyer <y.kuzmin@optic-sort.ru> · meyer».

Гейт направлений (Sender.division_block) читает panel.letter_division, а с
17.08 ещё и panel.company.division. Если пусты оба - гейт молчит и ящик
законен любой. Кампания 1 «новостные» как раз смешанная, и поле там есть не
у всех: замер 17.08 дал 181 письмо из 1012 без него.

Печатаем всё, что решает выбор: направление письма, направление карточки,
чем считался ящик по умолчанию и что скажет гейт.

    python zapusk_svoego_skripta.py ops/pismo_527_yashchik.py 527
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ID = int(sys.argv[1]) if len(sys.argv) > 1 else 527

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    row = store._conn.execute(
        "SELECT id, campaign_id, email, inn, subject, status, message_id, "
        "panel_json FROM confirm_reviews WHERE id=?", (ID,)).fetchone()
if not row:
    print(f"письма #{ID} нет")
    raise SystemExit(0)

rid, camp, email, inn, subj, status, mid, pj = row
try:
    p = json.loads(pj or "{}")
except Exception:                                               # noqa: BLE001
    p = {}
comp = p.get("company") if isinstance(p.get("company"), dict) else {}
full = p.get("company_full") if isinstance(p.get("company_full"), dict) else {}

print(f"#{rid} кампания {camp} | {email} | ИНН {inn} | статус {status}")
print(f"тема: {subj}")
print(f"letter_division = {p.get('letter_division')!r} "
      f"(причина {p.get('letter_division_reason')!r})")
print(f"карточка.division = {comp.get('division')!r} | "
      f"company_full.division = {full.get('division')!r}")
print(f"ОКВЭД = {comp.get('okved')!r}")
print(f"message_id = {mid!r}")

# Что скажет гейт направлений на этом письме.
try:
    from sender.sender import Sender                            # noqa: E402
    s = Sender.__new__(Sender)
    s.store = store

    class _M:
        id = mid
    print(f"_napravlenie_pisma -> {s._napravlenie_pisma(_M())!r}")
except Exception as ex:                                         # noqa: BLE001
    print("гейт не опрошен:", str(ex)[:200])

# Ящики и их направления - из чего панель выбирает по умолчанию.
try:
    почтари = cfg.get("mailboxes") or []
    print("\nящики в конфиге:")
    for m in почтари:
        if not isinstance(m, dict):
            continue
        print(f"  {m.get('id')!r:<22} {str(m.get('from_email'))[:34]:<34} "
              f"division={m.get('division')!r} enabled={m.get('enabled')}")
except Exception as ex:                                         # noqa: BLE001
    print("ящики не прочитаны:", str(ex)[:200])

# Сколько ещё писем в очереди с пустым направлением: цена дыры.
with store._lock:
    всего = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews").fetchone()[0]
    строки = store._conn.execute(
        "SELECT campaign_id, status, panel_json FROM confirm_reviews").fetchall()
пусто = пусто_ждут = 0
по_кампаниям = {}
for c, st, j in строки:
    try:
        d = json.loads(j or "{}")
    except Exception:                                           # noqa: BLE001
        d = {}
    ld = str(d.get("letter_division") or "").strip()
    cd = ""
    cc = d.get("company")
    if isinstance(cc, dict):
        cd = str(cc.get("division") or "").strip()
    if ld in ("kc", "meyer") or cd in ("kc", "meyer"):
        continue
    пусто += 1
    по_кампаниям[c] = по_кампаниям.get(c, 0) + 1
    if st == "pending":
        пусто_ждут += 1
print(f"\nписем всего {всего}; без направления и в письме, и в карточке: "
      f"{пусто} (из них ждут подтверждения {пусто_ждут})")
for c, n in sorted(по_кампаниям.items(), key=lambda x: -x[1])[:10]:
    print(f"  кампания {c}: {n}")
