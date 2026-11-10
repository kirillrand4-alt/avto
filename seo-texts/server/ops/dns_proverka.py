# -*- coding: utf-8 -*-
"""DNS с сервера: A-запись и MX (как у пробы). Только чтение.  dns_proverka.py домен [...]"""
import socket, subprocess, sys
sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe   # noqa: E402
from sender.config import Config                 # noqa: E402
from sender.store import Store                   # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
p = build_addr_probe(Store(cfg.get("service.db_path", r"C:\sender\sender.db")), cfg); p = getattr(p, "probe_", p)
for д in sys.argv[1:]:
    try: a = socket.gethostbyname(д)
    except Exception as ex: a = "ОШИБКА %s" % str(ex)[:60]
    try: mx = p.mx_for(д)
    except Exception as ex: mx = "ОШИБКА %s" % str(ex)[:60]
    r = subprocess.run(["nslookup", "-type=mx", д], capture_output=True, text=True, timeout=30)
    print(д, "| A:", a, "| mx_for:", mx, "| nslookup:", " ".join((r.stdout or r.stderr).split())[-160:])
