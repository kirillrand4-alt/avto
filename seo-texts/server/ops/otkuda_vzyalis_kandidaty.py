# -*- coding: utf-8 -*-
"""Откуда взялись 4594 кандидата, если днём было 0, а залили 1220.

Владелец поймал расхождение, и объяснять его словами нельзя - меряем.
Смотрим на дату заведения карточки получателя (recipients.created_at) у
тех, кто СЕЙЧАС проходит отбор, и сравниваем с моментом дневного замера
(11:45 UTC 18.08, «в группе 6023 строки | к генерации 0»).

Заодно проверяем вторую версию: днём 1466 строк группы не превращались в
получателя вовсе (partiya_gen пропускает такие молча, без счётчика) - то
есть карточки к ним появились позже.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ГРУППА = "Партия 935"
РУБЕЖ = "2026-08-18T11:45"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print(f"строк в группе: {len(в_группе)}")

with store._lock:
    ряды = dict((r[0], (r[1], r[2], r[3])) for r in store._conn.execute(
        "SELECT id, COALESCE(created_at,''), COALESCE(mx_provider,''), "
        "COALESCE(company_name,'') FROM recipients"))

по_дате = Counter()
нет_карточки = 0
for rid in в_группе:
    r = ряды.get(rid)
    if not r:
        нет_карточки += 1
        continue
    создан = str(r[0])[:10] or "?"
    по_дате[создан] += 1
print(f"нет карточки получателя: {нет_карточки}")
print("\nкогда заведены карточки строк группы:")
for д, n in sorted(по_дате.items()):
    print(f"  {д}  {n}")

свежие = [rid for rid in в_группе
          if ряды.get(rid) and str(ряды[rid][0]) > РУБЕЖ]
print(f"\nзаведены ПОСЛЕ дневного замера ({РУБЕЖ}): {len(свежие)}")
пров = Counter(str(ряды[rid][1] or "?") for rid in свежие)
print("почтовик у свежих:")
for k, n in пров.most_common(8):
    print(f"  {n:>5}  {k}")
# РЕШАЮЩАЯ ПРОВЕРКА: сколько СЕГОДНЯШНИХ кандидатов существовало уже во
# время дневного замера. Если много - значит днём их не «не было», а я их
# не увидел, и виноват замер, а не база.
from sender.ai_letter import target_division                     # noqa: E402
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.confirm import ConfirmSend                            # noqa: E402
from sender.suppression import Suppression                        # noqa: E402
from sender.target_gate import минус_класс                        # noqa: E402
import io as _io, json as _json
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
сделано = set()
for _s in _io.open(r"C:\sender\_ops\gen-partiya-935.jsonl", encoding="utf-8",
                   errors="replace"):
    try:
        _z = _json.loads(_s)
    except Exception:                                             # noqa: BLE001
        continue
    if _z.get("ок") or _z.get("тело"):
        сделано.add(str(_z.get("inn") or ""))
когда = Counter()
видели2 = set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    имя = str(getattr(rec, "company_name", "") or "")
    if not inn or not email or inn in видели2 or inn in сделано:
        continue
    видели2.add(inn)
    if минус_класс(getattr(rec, "okved", ""), имя):
        continue
    if cs._guard(inn=inn, email=email):
        continue
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    if mx in ("other", "unknown", ""):
        continue
    try:
        req = q._request(rec)
        _я = str(req.get("target_division") or "")
        div = _я if _я in ("kc", "meyer") else target_division(
            req, default="kc")[0]
    except Exception:                                             # noqa: BLE001
        continue
    if div != "kc":
        continue
    создан = str((ряды.get(rid) or ("",))[0])
    когда["заведён ПОСЛЕ дневного замера" if создан > РУБЕЖ
          else "существовал УЖЕ во время дневного замера"] += 1
print("\nКЦ на публичной почте — когда появились:")
for k, n in когда.most_common():
    print(f"  {n:>5}  {k}")

print("\nпримеры свежих:")
for rid in свежие[:8]:
    print(f"  #{rid:<7} {ряды[rid][2][:44]:<46} {ряды[rid][1]} "
          f"{str(ряды[rid][0])[:19]}")
