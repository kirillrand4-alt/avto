# -*- coding: utf-8 -*-
"""Заказать у VPS срочную пробу адресов, оставшихся в партии 13.

Ничего не отправляет: работник на VPS спрашивает почтовый сервер
получателя, примет ли он письмо для такого адреса, и обрывает разговор.

argv: проба | делать
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
import sender.probe_sync as PS            # noqa: E402
from sender.addr_probe import build_addr_probe  # noqa: E402

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

ждут = [str(р["email"]).lower() for р in c.execute(
    "SELECT email FROM confirm_reviews WHERE campaign_id=13 AND status='pending'")]
вердикт = {str(р["e"]): р["verdict"] for р in c.execute(
    "SELECT LOWER(email) e, verdict FROM addr_probe")}
раскл = {}
for а in ждут:
    раскл[str(вердикт.get(а))] = раскл.get(str(вердикт.get(а)), 0) + 1
print("адресов ждут пробы: %d %s" % (len(ждут), раскл))

if not ДЕЛАТЬ:
    print("будет заказана проверка на %d адресов" % len(ждут))
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

проба = build_addr_probe(store, cfg)
# у AddrProbeLoop сам пробник лежит в .probe_, а .probe равен None
пробник = getattr(проба, "probe_", None) or проба
ps = PS.build_probe_sync(store, пробник, cfg)
рез = ps.срочно(ждут)
print("заказ отправлен работнику: %s" % рез)
