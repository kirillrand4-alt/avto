# -*- coding: utf-8 -*-
"""Вернуть конец окна отправки на 15:00.

Владелец расширил окно, через четверть часа оно снова 11:00. Причина
известна: экран настроек панели, сохранённый без правки, переписывает конец
на 11:00 (значение по умолчанию в форме). Ставим обратно то, что владелец и
задавал, ничего больше не трогая: дни, начало, пояс и признак «по времени
получателя» остаются как были.
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КОНЕЦ = "15:00"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
было = store.get_setting("sending_window") or {}
print("было: ", было)
if str(было.get("end")) == КОНЕЦ:
    print("уже стоит, ничего не меняю")
    raise SystemExit(0)
стало = dict(было)
стало["end"] = КОНЕЦ
store.set_setting("sending_window", стало)
print("стало:", store.get_setting("sending_window"))
