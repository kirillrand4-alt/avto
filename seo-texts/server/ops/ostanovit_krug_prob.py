# -*- coding: utf-8 -*-
"""Остановить цикл синхронизации проб: владелец рассылку не ведёт.

Рубильник probe_sync_enabled читается в начале каждого тика. По умолчанию
(ключа нет) цикл считается включённым — поэтому ставим явное «нет», а не
удаляем ключ. Идущий прямо сейчас проход этим не прервётся: флаг проверяется
между кругами, а не внутри. Круг обрывается перезапуском службы.

argv: vkl — включить обратно.
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.probe_sync import ENABLED_KEY                       # noqa: E402

ВКЛЮЧИТЬ = "vkl" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

было = store.get_setting(ENABLED_KEY, None)
store.set_setting(ENABLED_KEY, bool(ВКЛЮЧИТЬ))
стало = store.get_setting(ENABLED_KEY, None)
print("рубильник %s: было %s → стало %s" % (ENABLED_KEY, было, стало))

# идёт ли прямо сейчас запись
сейчас = datetime.now(timezone.utc)
with store._lock:
    р = store._conn.execute(
        "SELECT MAX(ts) б FROM addr_probe WHERE source='проба'").fetchone()
б = datetime.fromisoformat(str(р["б"]))
print("")
print("последняя запись вердикта: %s (%.1f минут назад)"
      % (б.isoformat(timespec="seconds"), (сейчас - б).total_seconds() / 60.0))
print("время на сервере:          %s" % сейчас.isoformat(timespec="seconds"))
print("")
print("=" * 74)
print("=== ЦИКЛ СИНХРОНИЗАЦИИ ПРОБ %s ==="
      % ("ВКЛЮЧЁН" if ВКЛЮЧИТЬ else "ОСТАНОВЛЕН"))
