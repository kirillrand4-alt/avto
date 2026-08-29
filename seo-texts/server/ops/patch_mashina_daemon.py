# -*- coding: utf-8 -*-
"""Ответ новым письмом, без In-Reply-To, — тоже ответ."""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
МЕТКА = "и MDaemon@"
ЗАМЕНЫ = json.loads(r'''[["    _МАШИНА = (\"noreply\", \"no-reply\", \"no_reply\", \"donotreply\", \"do-not-reply\",\n               \"mailer-daemon\", \"mailerdaemon\", \"postmaster@\", \"notification\",\n               \"notifications@\", \"notify@\", \"robot@\", \"bounce@\", \"abuse@\")", "    # «daemon» одним куском: под него подпадают и mailer-daemon@, и MDaemon@ —\n    # последний шлёт «Warning: … no such user here», то есть отбивку, а вовсе\n    # не ответ человека.\n    _МАШИНА = (\"noreply\", \"no-reply\", \"no_reply\", \"donotreply\", \"do-not-reply\",\n               \"daemon\", \"postmaster@\", \"notification\", \"notifications@\",\n               \"notify@\", \"robot@\", \"bounce@\", \"abuse@\")"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
