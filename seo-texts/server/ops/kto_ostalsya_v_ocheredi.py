# -*- coding: utf-8 -*-
"""Кто остался в очереди после снятия брака и перевода годных.

Владелец смотрит на панель: «в очереди 210», «писем в группе 176», «таких
33 на корпоративных серверах» - и спрашивает, что это за люди. Разбираем
остаток по причине, по которой он не уехал в автоотправку, а не по одному
числу.

Причины могут накладываться (корпоративный сервер + нет вердикта), поэтому
печатаем и раздельный разрез, и пересечение.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ЧУЖИЕ_ПОЧТОВИКИ = ("yandex", "mailru", "google", "outlook")

верд = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, c.campaign_id, COALESCE(rc.mx_provider,''),
                  COALESCE(p.verdict,''), COALESCE(c.panel_json,''),
                  COALESCE(rc.company_name, c.email, ''), c.recipient_id
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
             LEFT JOIN addr_probe p ON p.email=lower(c.email)
            WHERE c.status='pending'""").fetchall()

по_кампаниям = Counter()
разрез = Counter()
пара = Counter()
напр = Counter()
примеры = {}
for rid, camp, mx, проба, pj, фирма, rcid in ряды:
    по_кампаниям[camp] += 1
    if camp != 10:
        continue
    корп = str(mx).strip().lower() not in ЧУЖИЕ_ПОЧТОВИКИ
    в = верд.get(rid, "не рецензировано")
    if not в:
        в = "не рецензировано"
    разрез[в] += 1
    if корп:
        разрез[f"[почтовик] корпоративный ({mx or 'неизвестен'})"] += 1
    if проба in ("нет ящика", "нет MX"):
        разрез[f"[проба] {проба}"] += 1
    пара[(в, "корпоративный" if корп else "публичный")] += 1
    try:
        d = json.loads(pj or "{}")
        напр[str(d.get("division") or d.get("напр") or "?")] += 1
    except Exception:                                            # noqa: BLE001
        напр["?"] += 1
    примеры.setdefault((в, корп), []).append(f"#{rid} {фирма[:38]}")

# ПАНЕЛЬ СЧИТАЕТ НЕ ПО КАМПАНИИ, А ПО ГРУППЕ ПОЛУЧАТЕЛЯ (segment +
# extra_json.gruppy), поэтому «писем в группе 176» и «в кампании 10 - 133»
# это разные разрезы одного остатка: часть писем партии 935 лежит в старых
# кампаниях. Считаем группу тем же кодом, что и панель.
карта = {}
try:
    карта = store.recipient_groups() or {}
except Exception as ex:                                          # noqa: BLE001
    print("группы получателей не прочитались:", str(ex)[:90])
по_id = карта.get("по_id") or {}
группа_писем = Counter()
разрез935 = Counter()
for rid, camp, mx, проба, pj, фирма, rcid in ряды:
    гр = по_id.get(rcid) or по_id.get(str(rcid)) or []
    if isinstance(гр, str):
        гр = [гр]
    for g in гр:
        группа_писем[str(g)] += 1
    if any("935" in str(g) for g in гр):
        в = верд.get(rid) or "не рецензировано"
        корп = str(mx).strip().lower() not in ЧУЖИЕ_ПОЧТОВИКИ
        разрез935[(в, "корпоративный" if корп else "публичный", camp)] += 1

print("pending по группам (топ):")
for г, n in группа_писем.most_common(8):
    print(f"  {n:>5}  {г}")
print("\nостаток группы «Партия 935» - вердикт х почтовик х кампания:")
for (в, п, camp), n in разрез935.most_common():
    print(f"  {n:>5}  {в:<20} {п:<14} кампания {camp}")

print("pending по кампаниям:", dict(по_кампаниям))
print(f"\nостаток кампании 10: {sum(n for (в, _), n in пара.items())}")
print("\nпо вердикту рецензента:")
for к, n in разрез.most_common():
    print(f"  {n:>5}  {к}")
print("\nвердикт х почтовик:")
for (в, п), n in пара.most_common():
    print(f"  {n:>5}  {в:<22} {п}")
print("\nнаправление:", dict(напр))
print("\nпримеры:")
for (в, корп), сп in list(примеры.items())[:8]:
    print(f"  {в} / {'корп' if корп else 'публичный'}: {'; '.join(сп[:3])}")
