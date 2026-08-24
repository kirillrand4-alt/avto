# -*- coding: utf-8 -*-
"""Каждое тридцатое письмо текущего прогона — глазами.

Владелец 24.08: «глазами проверь каждое 30-ое». Берём письма, положенные
sonnet-конвейером сегодня, и печатаем каждое тридцатое целиком, вместе с
тем, что о компании знает паспорт — иначе не проверить, не выдумано ли.
"""
import io
import json
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ШАГ = int(next((a for a in sys.argv[1:] if a.isdigit()), "30"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"

письма = []
for с in io.open(ЖУРНАЛ, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if (з.get("этап") == "итог" and з.get("ок") and з.get("тело")
            and з.get("модель") == "claude-sonnet-4-6"):
        письма.append(з)
# журнал пишет две строки на письмо — снимаем дубли по review_id
видели, уник = set(), []
for з in письма:
    к = з.get("review_id") or з.get("inn")
    if к in видели:
        continue
    видели.add(к)
    уник.append(з)
print("писем sonnet-конвейера: %d, смотрим каждое %d-е" % (len(уник), ШАГ))

for i in range(ШАГ - 1, len(уник), ШАГ):
    з = уник[i]
    print("\n" + "=" * 78)
    print("[%d] %s  (%s, #%s)" % (i + 1, str(з.get("имя"))[:50],
                                  з.get("направление"), з.get("review_id")))
    try:
        п = q._site_facts(з.get("inn")) or {}
    except Exception:  # noqa: BLE001
        п = {}
    for к in ("продукция", "оборудование_линии", "сырьё", "мощности"):
        v = п.get(к)
        if v:
            т = v if isinstance(v, str) else "; ".join(map(str, v))
            print("  паспорт/%s: %s" % (к, т[:150]))
    print("-" * 78)
    print("ТЕМА: %s" % з.get("тема"))
    print(з.get("тело"))
