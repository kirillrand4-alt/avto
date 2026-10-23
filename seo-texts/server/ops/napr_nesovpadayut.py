# -*- coding: utf-8 -*-
"""Карточки «Подтвердить отправку» (pending), которые гейт направлений
блокирует: «НАПРАВЛЕНИЯ НЕ СОВПАДАЮТ» (кампания kc, компании подходит meyer и
наоборот). По кампаниям, по группам получателя, примеры. Только чтение.
Пишет _ops/napr-nesovpadayut.json (id карточек)."""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.confirm import ConfirmSend      # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.wiring import build_deps        # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, st, dry_run=True).confirm
кам = {r[0]: r[1] for r in st._conn.execute("SELECT id, name FROM campaigns")}
сч, гр, ids, пр = Counter(), Counter(), [], []
for kid, cid, inn, rid in st._conn.execute("SELECT id, campaign_id, inn, recipient_id FROM confirm_reviews "
                                           "WHERE status='pending' AND kind='outbound'").fetchall():
    ф = [f for f in cs._division_flags(inn=inn, campaign_id=cid) if f.get("code") == "division_mismatch"]
    if not ф:
        continue
    ids.append(kid)
    сч[кам.get(cid, cid)] += 1
    ex = st._conn.execute("SELECT extra_json FROM recipients WHERE id=?", (rid,)).fetchone()
    for g in (json.loads((ex and ex[0]) or "{}").get("gruppy") or ["—"]):
        гр[g] += 1
    if len(пр) < 6:
        пр.append((kid, кам.get(cid), inn, ф[0]["label"][:90]))
print("заблокировано гейтом направлений:", len(ids), dict(сч))
print("группы получателей:", гр.most_common(8))
for p in пр:
    print("  ", p)
json.dump(ids, io.open(r"C:\sender\_ops\napr-nesovpadayut.json", "w"))
