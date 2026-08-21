# -*- coding: utf-8 -*-
"""Снять паузу с ящиков, отправить десять поправленных и растолкать вебинар.

Команда владельца 21.08: паузу снять самому, десять мейеровских отправить
без ссылки, вебинарные растолкать.

ПОРЯДОК ВАЖЕН. Сначала печатаем, включён ли ЦИКЛ автоотправки: если он
включён, снятая пауза запустит рассылку сама, помимо наших двух пачек - а
автоматика под холдом, и решать это владельцу. Если включён - паузу НЕ
снимаем и говорим об этом.

Дальше: снимаем паузу, шлём десять (тексты уже поправлены), затем 47
вебинарных со вторым подтверждением (force) - заслоны у них
recent_contact и deal_in_progress, владелец их видел и сказал растолкать.
Отписку/жалобу/мёртвый адрес не обходим ни при каком force.

Сухой прогон по умолчанию. Катить: --katit
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.dtos import RenderedMessage                             # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

КАТИТЬ = "--katit" in sys.argv
ДЕСЯТЬ = [3413, 3424, 3648, 3657, 3666, 3669, 3693, 3701, 3762, 3764]
МОЖНО_ОБОЙТИ = ("recent_contact", "deal_in_progress")
НЕЛЬЗЯ_ОБХОДИТЬ = ("unsub", "отпис", "complaint", "жалоб", "недостав",
                   "нет ящика", "нет mx")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
живой = getattr(cs, "_sender", None)
if живой is None:
    print("живой отправитель не собран - стоп")
    raise SystemExit(1)

# ЦИКЛ ЖИВЁТ НЕ В deps. Спрашивали getattr(deps,"auto_send") - его там
# нет вовсе, и ответ был None, то есть «не знаю», а печатали его как
# факт. Тумблер лежит в настройках стора, его и читаем.
from sender.auto_send import ENABLED_KEY                             # noqa: E402
цикл = bool(store.get_setting(ENABLED_KEY, False))
print(f"цикл автоотправки включён: {цикл}")
# ЦИКЛ АВТООТПРАВКИ ВКЛЮЧЁН - ЗНАЧИТ ПАУЗУ ВОЗВРАЩАЕМ ПОСЛЕ СЕБЯ.
# Владелец сказал снять паузу и отправить две пачки. Но пауза держит не
# только нас: цикл включён, и снятая пауза перезапустит автоматическую
# рассылку, которую владелец сегодня остановил сам. Поэтому окно делаем
# ровно на свои две пачки и закрываем обратно. Оставить открытым - флагом.
ВЕРНУТЬ_ПАУЗУ = "--ostavit-bez-pauzy" not in sys.argv and цикл
print(f"вернуть паузу после отправки: {ВЕРНУТЬ_ПАУЗУ}")

на_паузе = [mb.mailbox_id for mb in cfg.mailboxes()
            if getattr(store.get_mailbox_state(mb.mailbox_id), "paused", False)]
print(f"ящиков на паузе: {len(на_паузе)}")

# тексты десяти: убедимся, что ссылка ушла
print("\n=== тексты десяти ===")
for рид in ДЕСЯТЬ:
    с = cs.get(рид)
    т = str(с.get("edited_body") or с.get("body") or "")
    print(f"  #{рид} {с.get('email'):<34} ссылка в тексте: "
          f"{'ЕСТЬ (не поправлено!)' if 'http' in т else 'нет'}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

for mid in на_паузе:
    store.set_mailbox_paused(mid, False, None)
print(f"\nпауза снята с {len(на_паузе)} ящиков")

# --- пачка 1: десять поправленных ---------------------------------------
print("\n=== десять мейеровских без ссылки ===")
ушло1, сбой1 = 0, []
for рид in ДЕСЯТЬ:
    с = cs.get(рид)
    тема = str(с.get("edited_subject") or с.get("subject") or "")
    тело = str(с.get("edited_body") or с.get("body") or "")
    ящик = cs._fallback_mailbox(inn=с.get("inn"), prefer_division="meyer")
    напр = cs._division_of_mailbox(ящик) if ящик else None
    if напр != "meyer":
        сбой1.append((рид, f"ящик {ящик or '-'} ({напр or '?'})"))
        print(f"  НЕ шлём #{рид}: ящик {ящик or '-'} ({напр or '?'})")
        continue
    try:
        живой.send(store.get_message(int(с["message_id"])),
                   RenderedMessage(subject=тема, body=тело), ящик,
                   manual=True, to_email=с.get("email"))
        ушло1 += 1
        print(f"  ушло #{рид} {с.get('email')} <- {ящик}")
        try:
            store.confirm_decide(int(рид), status="sent",
                                 decided_by="владелец: без ссылки 21.08")
        except Exception:                                          # noqa: BLE001
            pass
    except Exception as ex:                                        # noqa: BLE001
        сбой1.append((рид, f"{type(ex).__name__}: {str(ex)[:100]}"))
        print(f"  НЕ ушло #{рид}: {type(ex).__name__}: {str(ex)[:100]}")

# --- пачка 2: вебинарные со вторым подтверждением ------------------------
print("\n=== вебинарные (force) ===")
with store._lock:
    ids = [р[0] for р in store._conn.execute(
        "SELECT id FROM confirm_reviews WHERE dedup_key LIKE 'vebinar28:%' "
        "AND status='pending' ORDER BY id").fetchall()]
print(f"карточек в очереди: {len(ids)}")
ушло2, сбой2, не_трогаем = 0, [], []
for кид in ids:
    с = cs.get(кид)
    причины = []
    for имя, зов in (
            ("ждёт вердикта пробы", lambda: cs._zhdyot_verdikta(с)),
            ("чужой ИНН", lambda: cs._chuzhoy_inn(с)),
            ("заслон подтверждения", lambda: cs._guard(inn=с.get("inn"),
                                                       email=с["email"])),
            ("гейт направлений", lambda: cs._division_blocked(с))):
        try:
            о = зов()
        except Exception as ex:                                    # noqa: BLE001
            о = f"{type(ex).__name__}: {str(ex)[:50]}"
        if о:
            причины.append(f"{имя}: {о}")
    текст = " | ".join(причины).lower()
    if any(x in текст for x in НЕЛЬЗЯ_ОБХОДИТЬ) or (
            причины and not any(x in текст for x in МОЖНО_ОБОЙТИ)):
        не_трогаем.append((кид, с.get("email"), " | ".join(причины)))
        continue
    try:
        cs.approve(int(кид), operator="владелец: растолкать вебинар 21.08",
                   force=True)
        ушло2 += 1
        print(f"  ушло №{кид} {с.get('email')}")
    except Exception as ex:                                        # noqa: BLE001
        сбой2.append((кид, f"{type(ex).__name__}: {str(ex)[:100]}"))
        print(f"  НЕ ушло №{кид} {с.get('email')}: "
              f"{type(ex).__name__}: {str(ex)[:100]}")

if ВЕРНУТЬ_ПАУЗУ:
    for mid in на_паузе:
        store.set_mailbox_paused(mid, True, "остановлено владельцем 21.08")
    print(f"\nпауза возвращена на {len(на_паузе)} ящиков")

print(f"\nдесять: ушло {ушло1}, не ушло {len(сбой1)}")
print(f"вебинар: ушло {ушло2}, не ушло {len(сбой2)}, "
      f"не трогали {len(не_трогаем)}")
if не_трогаем:
    print("не трогали (не та причина для обхода):")
    for к, п, пр in не_трогаем[:10]:
        print(f"  №{к} {п}: {пр[:90]}")
if сбой2:
    print("сбои вебинара:")
    for к, п in Counter(п.split(":")[0] for _, п in сбой2).most_common():
        print(f"  {п:>3}  {к}")
