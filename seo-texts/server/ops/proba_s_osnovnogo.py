# -*- coding: utf-8 -*-
"""Может ли проверять адреса САМ основной сервер, без работника на VPS.

Владелец 17.08: «функции работника вроде есть и на основном сервере -
можем через него проверить». Функции действительно есть: AddrProbe.probe
целиком локальный - находит MX и говорит с чужим почтовым сервером по 25-му
порту. Работника на VPS заводили не потому, что кода нет, а потому, что
хостеры обычно рубят исходящий 25-й порт. Это и проверяем - сначала голым
сокетом (репутацию не тратит), потом парой настоящих проб.

Ничего не меняет, кроме кэша вердиктов по трём пробным адресам.
"""
import socket
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                 # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

ГРУППА = "Партия 935"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
loop = build_addr_probe(store, cfg)
probe = loop.probe_

print("=== 1. открыт ли исходящий 25-й порт ===")
for домен in ("yandex.ru", "mail.ru", "gmail.com"):
    хост = probe.mx_for(домен)
    if not хост:
        print(f"  {домен:<12} MX не нашёлся")
        continue
    т0 = time.time()
    try:
        s = socket.create_connection((хост, 25), timeout=12)
        баннер = ""
        try:
            s.settimeout(8)
            баннер = s.recv(200).decode("utf-8", "replace").strip()[:90]
        except Exception:                                      # noqa: BLE001
            баннер = "(баннер не пришёл)"
        s.close()
        print(f"  {домен:<12} {хост:<34} ОТКРЫТ за {time.time()-т0:.1f}с | "
              f"{баннер}")
    except Exception as e:                                     # noqa: BLE001
        print(f"  {домен:<12} {хост:<34} ЗАКРЫТ/молчит "
              f"({time.time()-т0:.1f}с): {str(e)[:70]}")

print("\n=== 2. как сервер представляется ===")
print(f"  helo={probe.helo!r} mail_from={probe.mail_from!r} "
      f"source_ip={probe.source_ip!r} на_домен={probe.per_domain} "
      f"пауза={probe.pause}с таймаут={probe.timeout}с")

print("\n=== 3. три настоящие пробы по адресам партии ===")
группы = store.recipient_groups().get("по_id") or {}
адреса = []
for rid, g in группы.items():
    if ГРУППА not in g:
        continue
    rec = store.get_recipient(rid)
    e = str(getattr(rec, "email", "") or "").strip().lower()
    if e and "@" in e:
        адреса.append(e)
    if len(адреса) >= 3:
        break
probe.new_pass()
for а in адреса:
    т0 = time.time()
    р = probe.probe(а, force=True)
    print(f"  {а:<38} {str(р.get('verdict')):<14} код={р.get('code')} "
          f"{time.time()-т0:.1f}с | {str(р.get('answer'))[:70]}")
