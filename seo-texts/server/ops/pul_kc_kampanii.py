# -*- coding: utf-8 -*-
"""Письма КЦ в автоотправке ждали вечно (владелец 15.10: «я отправлял в
автоотправку кц письма»): пул выбирается по провайдеру получателя -> pool_yandex
с ящиками Meyer, а заслон направлений их не даёт; перелив выключен. Делаем:
  * sender._route_pool: пул направления КЦ (pool_kc), заданный у кампании,
    главнее раскладки по провайдеру получателя;
  * кампании «КЦ тест — КЦ» (15) и «Партия 935 — КЦ» (10) — provider_pool=pool_kc.
Нужен перезапуск службы. Правка по якорям, бэкап, py_compile."""
import io
import py_compile
import shutil
import sqlite3
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\sender.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "_пул_направления" not in т:
    с = '''        routing = self.config.get("provider_split.routing", {}) or {}
        if self.config.get("provider_split.match_recipient_provider", True):'''
    н = '''        routing = self.config.get("provider_split.routing", {}) or {}
        # Пул НАПРАВЛЕНИЯ (pool_kc у кампаний КЦ) главнее раскладки по
        # провайдеру получателя: провайдерные пулы состоят из ящиков Meyer, и
        # заслон направлений отдал бы письму КЦ пустой список (владелец 15.10).
        _пул_направления = getattr(campaign, "provider_pool", None) if campaign is not None else None
        if _пул_направления and str(_пул_направления).startswith("pool_kc"):
            return _пул_направления
        if self.config.get("provider_split.match_recipient_provider", True):'''
    if т.count(с) != 1:
        print("якорь (%d)" % т.count(с))
        print("=== ПУЛ КЦ: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
    бэкап = ПУТЬ + ".bak-%d" % int(time.time())
    shutil.copy2(ПУТЬ, бэкап)
    io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(с, н))
    try:
        py_compile.compile(ПУТЬ, doraise=True)
    except Exception as е:  # noqa: BLE001
        shutil.copy2(бэкап, ПУТЬ)
        print("откат: %s" % е)
        sys.exit(0)
    print("sender.py поправлен, бэкап %s" % бэкап)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with c:
    n = c.execute("UPDATE campaigns SET provider_pool='pool_kc' WHERE id IN (10, 15)").rowcount
print("кампаний с pool_kc: %d" % n)
print("=== ПУЛ КЦ: ПРИМЕНЕНО ===")
