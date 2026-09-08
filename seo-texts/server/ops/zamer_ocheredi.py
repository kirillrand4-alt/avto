# -*- coding: utf-8 -*-
"""Сколько стоит один заход на экран подтверждения и мой ли в этом вклад."""
import glob, io, json, os, sys, time
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

т0 = time.time()
rows = cs.pending(campaign_id=None, limit=100000, offset=0)
т1 = time.time()
байт = sum(len(json.dumps(r.get("panel") or {}, ensure_ascii=False)) for r in rows)
т2 = time.time()
print("   pending(limit=100000): %d строк за %.2f с" % (len(rows), т1 - т0))
print("   объём панелей в ответе: %.1f МБ (сериализация %.2f с)"
      % (байт / 1048576.0, т2 - т1))

# мой ли вклад: сравниваем панели до моей правки и сейчас
до = сейчас = n = 0
for п in sorted(glob.glob(r"C:\sender\_ops\agro-panel-do-pravki-*.jsonl"))[-1:]:
    for с in io.open(п, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        try:
            z = json.loads(с)
        except Exception:                                       # noqa: BLE001
            continue
        rid = z.get("review_id")
        if rid is None:
            continue
        до += len(str(z.get("panel_json_до") or ""))
        n += 1
    print("   снимок: %s" % os.path.basename(п))
if n:
    with store._lock:
        for р in store._conn.execute(
                "SELECT LENGTH(panel_json) L FROM confirm_reviews "
                " WHERE subject=?", ("для качества: вопрос по сортировке зерна",)):
            сейчас += int(р["L"] or 0)
    print("   панели партии: было %.1f МБ на %d карточек, стало %.1f МБ"
          % (до / 1048576.0, n, сейчас / 1048576.0))
print("")
print("=" * 70)
print("=== ЦЕНА ОДНОГО ЗАХОДА НА ЭКРАН ===")
