# -*- coding: utf-8 -*-
"""Протолкнуть оставшиеся вебинарные письма (команда владельца 21.08).

force=True - это ВТОРОЕ подтверждение оператора: заслон обходится и обход
пишется в аудит (решение владельца 26.07). Владелец видел раскладку по
причинам и сказал «протолкни».

ЧТО ПРОТАЛКИВАЕМ И ЧТО НЕТ. Обходим только те две причины, что владелец
видел: recent_contact<90d (гигиена частоты) и suppressed:deal_in_progress
(у продаж живая сделка). Отписку, жалобу и мёртвый адрес не обходим ни при
каком force - это ФЗ-38 и сожжённые домены, а не гигиена; такие письма
печатаем отдельным списком и оставляем стоять.

Ящик проверяем ровно как в прошлом прогоне: уходить должно с мейеровского.

Сухой прогон по умолчанию. Отправка: --katit
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

КАТИТЬ = "--katit" in sys.argv
# что разрешено обходить вторым подтверждением
МОЖНО = ("recent_contact", "deal_in_progress")
# что не обходим никогда
НЕЛЬЗЯ = ("unsub", "отпис", "complaint", "жалоб", "недостав", "нет ящика",
          "нет mx", "bounce", "hard")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
if getattr(cs, "_sender", None) is None:
    print("confirm.live_send выключен - отправлять нечем, стоп")
    raise SystemExit(1)

with store._lock:
    ids = [р[0] for р in store._conn.execute(
        "SELECT id FROM confirm_reviews WHERE dedup_key LIKE 'vebinar28:%' "
        "AND status='pending' ORDER BY id").fetchall()]
print(f"вебинарных карточек в очереди: {len(ids)}")

тащим, не_тащим, чужой_ящик = [], [], []
for кид in ids:
    строка = cs.get(кид)
    try:
        как = cs.send_as(строка, prefer_division="meyer")
        # ЯЩИК ЛЕЖИТ В mailbox_id (ключа "chosen" у send_as нет).
        ящик = как.get("mailbox_id") or ""
        напр = как.get("division") or (cs._division_of_mailbox(ящик) if ящик else None)
    except Exception as ex:                                       # noqa: BLE001
        чужой_ящик.append((кид, строка.get("email"),
                           f"send_as: {type(ex).__name__}: {str(ex)[:60]}"))
        continue
    if напр != "meyer":
        чужой_ящик.append((кид, строка.get("email"),
                           f"ящик {ящик or '-'} направления {напр or '?'}"))
        continue
    причины = []
    for имя, зов in (
            ("ждёт вердикта пробы", lambda: cs._zhdyot_verdikta(строка)),
            ("чужой ИНН", lambda: cs._chuzhoy_inn(строка)),
            ("заслон подтверждения", lambda: cs._guard(
                inn=строка.get("inn"), email=строка["email"])),
            ("гейт направлений", lambda: cs._division_blocked(строка))):
        try:
            ответ = зов()
        except Exception as ex:                                   # noqa: BLE001
            ответ = f"{type(ex).__name__}: {str(ex)[:60]}"
        if ответ:
            причины.append(f"{имя}: {ответ}")
    текст = " | ".join(причины).lower()
    if any(с in текст for с in НЕЛЬЗЯ):
        не_тащим.append((кид, строка.get("email"), " | ".join(причины)))
        continue
    if причины and not any(с in текст for с in МОЖНО):
        не_тащим.append((кид, строка.get("email"), " | ".join(причины)))
        continue
    тащим.append((кид, строка.get("email"), ящик, " | ".join(причины) or "чисто"))

print(f"\nпротолкнуть можно: {len(тащим)}")
print("причины, которые обходим:",
      dict(Counter("recent_contact" if "recent_contact" in т[3] else
                   "сделка в работе" if "deal_in_progress" in т[3] else
                   "без заслонов" for т in тащим)))
if не_тащим:
    print(f"\nНЕ ОБХОДИМ (отписка/жалоба/мёртвый адрес или незнакомая "
          f"причина): {len(не_тащим)}")
    for кид, поч, п in не_тащим:
        print(f"  №{кид} {поч}: {п[:100]}")
if чужой_ящик:
    print(f"\nЧУЖОЙ ЯЩИК - не трогаем: {len(чужой_ящик)}")
    for кид, поч, п in чужой_ящик[:10]:
        print(f"  №{кид} {поч}: {п}")

if not КАТИТЬ:
    print("\nсухой прогон. Отправка - --katit")
    raise SystemExit(0)

ушло, сбой = 0, []
print(f"\nотправляем со вторым подтверждением {len(тащим)}:")
for кид, поч, ящик, почему in тащим:
    try:
        cs.approve(int(кид), operator="владелец: протолкнуть вебинар 21.08",
                   force=True)
        ушло += 1
        print(f"  ушло №{кид} {поч} <- {ящик}  [{почему[:48]}]")
    except Exception as ex:                                       # noqa: BLE001
        сбой.append((кид, поч, f"{type(ex).__name__}: {str(ex)[:100]}"))
        print(f"  НЕ ушло №{кид} {поч}: {type(ex).__name__}: {str(ex)[:100]}")
print(f"\nотправлено: {ушло} | сбоев: {len(сбой)}")
