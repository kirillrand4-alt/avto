# -*- coding: utf-8 -*-
"""Есть ли у ops-процесса пароли ящиков и как устроен Sender.send."""
import inspect, os, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.sender import Sender                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
есть = нет = 0
первый = None
for mb in cfg.mailboxes():
    имя = str(getattr(mb, "password_env", "") or "")
    if имя and os.environ.get(имя):
        есть += 1
        if первый is None and str(getattr(mb, "division", "")).lower() == "meyer":
            первый = (mb.mailbox_id, имя, str(getattr(mb, "from_name", "")))
    else:
        нет += 1
print("паролей ящиков видно процессу: есть %d, нет %d" % (есть, нет))
print("первый доступный Meyer: %s" % (первый[0] if первый else "нет"))
print("")
print("--- Sender.send ---")
try:
    print(str(inspect.signature(Sender.send)))
    док = (Sender.send.__doc__ or "").strip().splitlines()
    for с in док[:12]:
        print("   " + с)
except Exception as ex:                                         # noqa: BLE001
    print("не прочиталось: %s" % str(ex)[:80])
print("")
print("=" * 70)
print("=== ЧЕМ ОТПРАВИТЬ КОПИЮ ===")
