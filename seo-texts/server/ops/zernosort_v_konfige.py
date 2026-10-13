# -*- coding: utf-8 -*-
"""Где zernosort.ru в sender.yaml (секреты маскируем) + очередь/расписание с этих ящиков.
С --udalit: бэкап, вырезаем блоки ящиков zernosort из mailboxes, проверяем Config.load."""
import io
import re
import shutil
import sqlite3
import sys
import time
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
П = r"C:\sender\sender.yaml"
т = io.open(П, encoding="utf-8").read()
стр = т.splitlines(True)
for i, с in enumerate(стр):
    if "zernosort" in с:
        for j in range(max(0, i - 2), min(len(стр), i + 12)):
            л = re.sub(r"(?i)(pass\w*|token|secret)\s*:\s*\S+", r"\1: ***", стр[j].rstrip())
            print("%5d  %s" % (j + 1, л[:150]))
        print("   ...")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print("письма с назначенным ящиком zernosort в незавершённых статусах:",
      c.execute("SELECT mailbox_id, status, count(*) FROM messages WHERE mailbox_id LIKE '%zernosort%' "
                "AND status NOT IN ('sent','skipped','failed','bounced') GROUP BY 1,2").fetchall())
cfg = Config.load(П)
print("ящиков в конфиге: %d, из них zernosort: %s" % (len(cfg.mailboxes()), [m.mailbox_id for m in cfg.mailboxes() if "zernosort" in m.mailbox_id]))
if "--udalit" in sys.argv:
    ЯЩ = ("a.kozlov@zernosort.ru", "i.boyarkin@zernosort.ru")
    бэкап = П + ".bak-%d" % int(time.time())
    shutil.copy2(П, бэкап)
    нов, пропуск = [], False
    for с in стр:
        м = re.match(r"\s*- mailbox_id:\s*\"?([^\"\s]+)", с)
        if м:
            пропуск = м.group(1) in ЯЩ
        elif пропуск and not re.match(r"\s{4,}\S", с):
            пропуск = False
        if пропуск:
            continue
        if re.match(r"\s*(a\.kozlov|i\.boyarkin)@zernosort\.ru:\s", с):
            continue
        for я in ЯЩ:
            с = re.sub(r"\s*\b" + re.escape(я) + r"\s*,", "", с)
            с = re.sub(r",\s*" + re.escape(я) + r"\b", "", с)
        нов.append(с)
    io.open(П, "w", encoding="utf-8").write("".join(нов))
    try:
        cfg2 = Config.load(П)
        осталось = [m.mailbox_id for m in cfg2.mailboxes()]
        assert not any("zernosort" in x for x in осталось), "остался ящик"
        assert "zernosort" not in "".join(нов).replace("zernosort.ru: \"2026-07-21\"", ""), "осталось упоминание"
        print("удалено; ящиков теперь %d; бэкап %s" % (len(осталось), бэкап))
        print("пулы:", [л.strip()[:200] for л in нов if "pool_yandex:" in л or "pool_fallback:" in л])
    except Exception as е:  # noqa: BLE001
        shutil.copy2(бэкап, П)
        print("ОТКАТ: %s" % е)
print("=== ZERNOSORT В КОНФИГЕ ===")
