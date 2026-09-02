# -*- coding: utf-8 -*-
"""Только чтение: отдача тем писем и ограничения гейта на тему."""
import inspect
import re
import sqlite3
from collections import defaultdict

import sys
sys.path.insert(0, r"C:\sender")

print("=== ПРАВИЛА ГЕЙТА ПРО ТЕМУ ===")
import sender.ai_letter as A  # noqa: E402
т = inspect.getsource(A)
for м in re.finditer(r"(?i)(тема|subject)", т):
    н = т[:м.start()].count("\n")
    с = т.splitlines()[н].strip()
    if any(k in с for k in ("fails.append", "if ", "len(")) and \
            any(k in с.lower() for k in ("тем", "subject")):
        print("  %s" % с[:112])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
ушли = list(c.execute("SELECT id, recipient_id, subject FROM messages"
                      " WHERE status='sent' AND subject<>''"))
живые = {р["recipient_id"] for р in c.execute(
    "SELECT recipient_id FROM events WHERE event_type='reply'")}
print("\nписем с темой: %d, получателей с ответом: %d" % (len(ушли), len(живые)))

по = defaultdict(lambda: [0, 0])
for р in ушли:
    к = re.sub(r"\s+", " ", р["subject"]).strip()
    по[к][0] += 1
    if р["recipient_id"] in живые:
        по[к][1] += 1
годные = [(k, n, o) for k, (n, o) in по.items() if n >= 40]
годные.sort(key=lambda x: -x[2] / x[1])
print("\n=== ЛУЧШИЕ ТЕМЫ (от 40 писем) ===")
for k, n, o in годные[:12]:
    print("  %5.1f%% (%3d/%4d) %s" % (100.0 * o / n, o, n, k[:66]))
print("\n=== ХУДШИЕ ===")
for k, n, o in годные[-8:]:
    print("  %5.1f%% (%3d/%4d) %s" % (100.0 * o / n, o, n, k[:66]))

print("\n=== ПРИЗНАКИ ТЕМЫ ===")
приз = {
    "есть слово «вопрос»": lambda s: "вопрос" in s.lower(),
    "начинается с «по »": lambda s: s.lower().startswith("по "),
    "есть название компании": lambda s: bool(re.search(r"[«\"]", s)),
    "длина <= 30 знаков": lambda s: len(s) <= 30,
    "длина 31..45": lambda s: 31 <= len(s) <= 45,
    "длина > 45": lambda s: len(s) > 45,
    "есть цифра": lambda s: bool(re.search(r"\d", s)),
}
for имя, ф in приз.items():
    n = o = 0
    for р in ушли:
        if ф(р["subject"]):
            n += 1
            o += 1 if р["recipient_id"] in живые else 0
    if n >= 40:
        print("  %-28s %5.1f%% (%3d/%4d)" % (имя, 100.0 * o / n, o, n))
