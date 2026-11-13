# -*- coding: utf-8 -*-
"""После последнего старта панели: сколько «claim_approved_due упал» / «another row available» / прочих ошибок,
и что было прямо перед первой «another row». Только чтение."""
import io, os, re
п = r"C:\sender\_ops\panel_err.log"; р = os.path.getsize(п)
with io.open(п, "rb") as f: f.seek(max(0, р - 12000000)); х = f.read().decode("utf-8", "replace").splitlines()
ст = max((k for k, x in enumerate(х) if "Started server process" in x or "Application startup complete" in x), default=0)
п2 = х[ст:]
print("строк после старта:", len(п2), "| старт:", х[ст][:120])
for м in ("claim_approved_due упал", "another row available", "выборка упала", "tick упал", "auth failed", "database is locked"):
    print("  %-28s %d" % (м, sum(1 for x in п2 if м in x)))
i = next((k for k, x in enumerate(п2) if "another row available" in x), None)
if i is not None: print("--- перед первой:\n" + "\n".join(y[:200] for y in п2[max(0, i - 40):i + 2]))
from collections import Counter
ш = re.compile(r"^\s+File |^\s+\^|^Traceback|^\s{4}\S|^\s*$")
print("--- уникальные строки после старта (без стеков):")
for стр, н in Counter(x[:150] for x in п2 if not ш.search(x)).most_common(25): print("%5d  %s" % (н, стр))
