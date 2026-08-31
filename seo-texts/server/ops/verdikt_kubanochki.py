# -*- coding: utf-8 -*-
"""Вердикт по адресам «Кубаночки»: сначала в базе, потом прямо с дропа."""
import json
import sqlite3
import sys
import urllib.request

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync, РЕЗУЛЬТАТ     # noqa: E402
from sender.store import Store                                # noqa: E402

АДРЕСА = ("info@kubanochka.ru", "nfo@kubanochka.ru",
          "export@kubanochka.ru")
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
print("=== В БАЗЕ addr_probe ===")
for а in АДРЕСА:
    r = c.execute("SELECT verdict, source, substr(ts,1,19) ts, answer"
                  "  FROM addr_probe WHERE email=?", (а,)).fetchone()
    print("   %-24s %s" % (а, ("%s (%s, %s) %s"
                               % (r["verdict"], r["source"], r["ts"],
                                  str(r["answer"] or "")[:50]))
                           if r else "вердикта нет"))
c.close()

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = getattr(build_addr_probe(store, cfg), "probe_", None)
цикл = build_probe_sync(store, проба, cfg)
база, токен = цикл._ключи()
з = urllib.request.Request("%s/%s" % (база, РЕЗУЛЬТАТ))
з.add_header("X-Drop-Token", токен)
with urllib.request.urlopen(з, timeout=180) as о:
    строки = о.read().decode("utf-8", "replace").splitlines()
print("\n=== НА ДРОПЕ (строк всего %d) ===" % len(строки))
нашли = {}
for с in строки:
    try:
        z = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    а = str(z.get("email") or "").strip().lower()
    if а in АДРЕСА:
        нашли[а] = z
for а in АДРЕСА:
    z = нашли.get(а)
    print("   %-24s %s" % (а, ("%s, код %s — %s"
                               % (z.get("verdict"), z.get("code"),
                                  str(z.get("answer") or "")[:60]))
                           if z else "работник ещё не отвечал"))

# доносим найденное до базы, чтобы заслон подтверждения его видел
записано = 0
for а, z in нашли.items():
    ст = проба.cached(а)
    if ст and str(ст.get("verdict") or "") == str(z.get("verdict") or ""):
        continue
    проба._save(а, str(z.get("verdict") or ""), z.get("code"),
                str(z.get("answer") or ""), str(z.get("mx") or ""))
    записано += 1
print("\n=== ИТОГ ===")
print("вердиктов дописано в базу: %d" % записано)
