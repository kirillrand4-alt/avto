# -*- coding: utf-8 -*-
import json, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
try:
    т = store.dialog_thread(29417)
except Exception as ex:
    print("dialog_thread упал: %s: %s" % (type(ex).__name__, str(ex)[:120]))
    raise SystemExit(1)
print("что покажет блок «Переписка»:")
if isinstance(т, dict):
    т = т.get("items") or т.get("threads") or [т]
for i, x in enumerate(т if isinstance(т, list) else [т]):
    if isinstance(x, dict):
        print("   %d) %s" % (i + 1, json.dumps(x, ensure_ascii=False)[:400]))
    else:
        print("   %d) %s" % (i + 1, str(x)[:400]))
