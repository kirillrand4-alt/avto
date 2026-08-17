# -*- coding: utf-8 -*-
"""В какой доле писем реально стоят вещи, о которых договаривались.

Владелец сперва «этого я совсем не вижу в письмах» про строку отказа, потом
«хотя посмотрел больше - увидел». Такой вопрос закрывается долей, а не
впечатлением от нескольких писем подряд, поэтому считаем по всей кампании.

Меряем ровно то, что обсуждали за день:
  * концовка КЦ («чтобы в дальнейшем вас не отвлекать») - обязана быть в
    каждом письме КЦ и не должна появляться у Meyer;
  * просьба перенаправить - обязана быть там, где нет именного приветствия;
  * именное приветствие - и сверено ли имя с ящиком;
  * формы захода и их доли - квота 34% на форму;
  * марки оборудования, длинное тире, объём.

    python zapusk_svoego_skripta.py ops/dolya_kanona_v_pismah.py 10
"""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import (_imennoe_privetstvie,             # noqa: E402
                              _imya_soglasuetsya_s_yashchikom,
                              _prosba_perenapravit, форма_захода)
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

КАМПАНИЯ = int(sys.argv[1]) if len(sys.argv) > 1 else 10
ОТКАЗ = "в дальнейшем вас не отвлекать"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    строки = store._conn.execute(
        "SELECT id, email, subject, body, panel_json, status FROM "
        "confirm_reviews WHERE campaign_id=? ORDER BY id", (КАМПАНИЯ,)
    ).fetchall()

счёт = Counter()
заходы = Counter()
без_отказа, без_просьбы, имя_не_сошлось = [], [], []
for rid, email, subj, body, pj, статус in строки:
    body = str(body or "")
    try:
        panel = json.loads(pj or "{}")
    except Exception:                                           # noqa: BLE001
        panel = {}
    напр = str(panel.get("letter_division") or "")
    cont = panel.get("contact") if isinstance(panel.get("contact"), dict) else {}
    имя = str(cont.get("person") or "")
    роль = str(cont.get("role") or "").lower()
    счёт["всего писем"] += 1
    счёт[f"направление {напр or '?'}"] += 1

    есть_отказ = ОТКАЗ in body
    if напр == "kc":
        счёт["КЦ: строка отказа есть" if есть_отказ
             else "КЦ: строки отказа НЕТ"] += 1
        if not есть_отказ:
            без_отказа.append(rid)
    elif напр == "meyer":
        счёт["Meyer: строка отказа есть (не должна)" if есть_отказ
             else "Meyer: строки отказа нет (верно)"] += 1

    по_имени = _imennoe_privetstvie(body)
    просьба = _prosba_perenapravit(body)
    счёт["именное приветствие" if по_имени else "безличное приветствие"] += 1
    счёт["просьба перенаправить есть" if просьба else "просьбы нет"] += 1
    if not по_имени and not просьба:
        без_просьбы.append(rid)
    if по_имени and имя:
        if _imya_soglasuetsya_s_yashchikom(имя, email):
            счёт["имя сверено с ящиком"] += 1
        else:
            счёт["ИМЯ НЕ СХОДИТСЯ С ЯЩИКОМ"] += 1
            имя_не_сошлось.append((rid, имя, email))
    заходы[форма_захода(body) or "(не опознан)"] += 1
    if "—" in body or "–" in body:
        счёт["длинное тире"] += 1
    слов = len([w for w in re.split(r"\s+", body) if w.strip()])
    if not (45 <= слов <= 140):
        счёт["объём вне нормы"] += 1

всего = max(1, счёт["всего писем"])
print(f"кампания {КАМПАНИЯ}: писем {всего}")
for k, n in счёт.most_common():
    print(f"  {k:<40} {n:>4}  {100.0 * n / всего:.0f}%")
print("\nформы захода (квота на форму 34%):")
for k, n in заходы.most_common():
    метка = "  ПЕРЕБОР" if n > всего * 0.34 else ""
    print(f"  {k:<24} {n:>4}  {100.0 * n / всего:.0f}%{метка}")
if без_отказа:
    print(f"\nКЦ без строки отказа ({len(без_отказа)}): {без_отказа[:20]}")
if без_просьбы:
    print(f"без имени и без просьбы перенаправить ({len(без_просьбы)}): "
          f"{без_просьбы[:20]}")
for rid, имя, email in имя_не_сошлось[:10]:
    print(f"  имя не сходится: #{rid} {имя!r} -> {email}")
