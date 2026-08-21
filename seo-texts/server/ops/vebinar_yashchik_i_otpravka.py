# -*- coding: utf-8 -*-
"""Вебинарные Meyer: проставить направление, показать ящик, отправить вручную.

Команда владельца 21.08: «вебинарные мейровские отправь вручную но проследи
что бы правильный ящик был указан».

ПОЧЕМУ СНАЧАЛА ПРОСТАВЛЯЕМ ПОЛЕ. У этих карточек нет panel.letter_division:
их собирали отдельно, а поле ставит генератор. Ровно из-за этой дыры 20.08
две копии «Гастрофабрике» ушли с компрессорных ящиков за подписью
«Компрессор Центр». Ручной путь спасает лексика письма, но полагаться на
лексику там, где направление известно точно, незачем: пишем meyer в поле -
и его видят и панель, и подбор ящика, и гейт на последнем рубеже.

ЧТО ДЕЛАЕМ ПО ШАГАМ:
  1. письмам без поля пишем letter_division=meyer (panel_json);
  2. на каждой карточке спрашиваем send_as - С КАКОГО ЯЩИКА уйдёт, и
     проверяем, что направление ящика meyer; чужой ящик = стоп;
  3. считаем заслоны (те же, что спросит approve);
  4. с --katit отправляем ЖИВЬЁМ те, что заслоны пропускают.

Заслоны НЕ обходим: force здесь не предусмотрен вовсе. Письма, которым он
нужен (контакт моложе 90 дней, сделка в работе), показываем списком -
решение по ним за владельцем.

Сухой прогон по умолчанию. Отправка: --katit
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

КАТИТЬ = "--katit" in sys.argv
ПОТОЛОК = int(next((а.split("=")[1] for а in sys.argv if а.startswith("potolok=")),
                   "0"))

# СОБИРАЕМ ТУ ЖЕ СБОРКУ, ЧТО И ПАНЕЛЬ. Голый ConfirmSend(cfg, store,
# Suppression) - не панель: у него нет ни боевого Sender (значит нечем
# слать и нечем подбирать ящик - send_as вернул пусто на всех 73), ни
# CompanyCards (значит молчит гейт направлений). Ровно эта разница и
# делает проверку ящика бессмысленной, а её здесь допускать нельзя.
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
живая = getattr(cs, "_sender", None) is not None
print(f"живая отправка в панели: {'да' if живая else 'НЕТ (уйдёт в очередь)'}")
if not живая:
    print("confirm.live_send выключен - ручная отправка невозможна, стоп")
    raise SystemExit(1)

with store._lock:
    ids = [р[0] for р in store._conn.execute(
        "SELECT id FROM confirm_reviews WHERE dedup_key LIKE 'vebinar28:%' "
        "AND status='pending' ORDER BY id").fetchall()]
print(f"вебинарных карточек в очереди: {len(ids)}")

# --- шаг 1: направление в поле -------------------------------------------
надо_поле = []
for кид in ids:
    строка = cs.get(кид)
    панель = строка.get("panel") if isinstance(строка.get("panel"), dict) else {}
    if str((панель or {}).get("letter_division") or "").lower() != "meyer":
        надо_поле.append(кид)
print(f"карточек без letter_division=meyer: {len(надо_поле)}")
if КАТИТЬ and надо_поле:
    with store.transaction() as conn:
        for кид in надо_поле:
            стр = conn.execute("SELECT panel_json FROM confirm_reviews "
                               "WHERE id=?", (кид,)).fetchone()
            try:
                п = json.loads(стр[0] or "{}")
            except Exception:                                     # noqa: BLE001
                п = {}
            п["letter_division"] = "meyer"
            п["letter_division_reason"] = "вебинар Meyer (проставлено 21.08)"
            conn.execute("UPDATE confirm_reviews SET panel_json=? WHERE id=?",
                         (json.dumps(п, ensure_ascii=False), кид))
    print(f"проставлено meyer: {len(надо_поле)}")

# --- шаг 2 и 3: ящик и заслоны -------------------------------------------
готовы, чужой_ящик, стоп = [], [], []
счёт = Counter()
for кид in ids:
    строка = cs.get(кид)
    try:
        как = cs.send_as(строка, prefer_division="meyer")
    except Exception as ex:                                       # noqa: BLE001
        чужой_ящик.append((кид, строка.get("email"), f"send_as упал: "
                                                     f"{type(ex).__name__}: {str(ex)[:60]}"))
        continue
    ящик = как.get("chosen") or как.get("mailbox_id") or ""
    напр = cs._division_of_mailbox(ящик) if ящик else None
    счёт[f"ящик {напр or '?'}"] += 1
    if not ящик or напр != "meyer":
        чужой_ящик.append((кид, строка.get("email"),
                           f"подобран ящик {ящик or '-'} направления {напр or '?'}"))
        continue
    почему = None
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
            почему = f"{имя}: {ответ}"
            break
    if почему:
        стоп.append((кид, строка.get("email"), почему))
        счёт[почему.split(":")[1].split("<")[0].strip()] += 1
    else:
        готовы.append((кид, строка.get("email"), ящик))
        счёт["ПРОЙДЁТ"] += 1

print("\nраскладка:")
for к, н in счёт.most_common():
    print(f"  {н:>3}  {к}")
print(f"\nготовы к отправке с Meyer-ящика: {len(готовы)}")
for кид, поч, ящик in готовы[:10]:
    print(f"  №{кид} {поч} <- {ящик}")
if чужой_ящик:
    print(f"\nЧУЖОЙ ЯЩИК - НЕ ОТПРАВЛЯЕМ: {len(чужой_ящик)}")
    for кид, поч, п in чужой_ящик[:10]:
        print(f"  №{кид} {поч}: {п}")
if стоп:
    print(f"\nдержат заслоны (решение за владельцем): {len(стоп)}")
    for кид, поч, п in стоп[:12]:
        print(f"  №{кид} {поч}: {п}")

if not КАТИТЬ:
    print("\nсухой прогон, ничего не отправлено. Отправка - --katit")
    raise SystemExit(0)

ушло, сбой = 0, []
цель = готовы[:ПОТОЛОК] if ПОТОЛОК else готовы
print(f"\nотправляем {len(цель)} писем:")
for кид, поч, ящик in цель:
    try:
        cs.approve(int(кид), operator="владелец: вебинар вручную 21.08")
        ушло += 1
        print(f"  ушло №{кид} {поч} <- {ящик}")
    except Exception as ex:                                       # noqa: BLE001
        сбой.append((кид, поч, f"{type(ex).__name__}: {str(ex)[:90]}"))
        print(f"  НЕ ушло №{кид} {поч}: {type(ex).__name__}: {str(ex)[:90]}")
print(f"\nотправлено: {ушло} | сбоев: {len(сбой)}")
