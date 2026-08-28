# -*- coding: utf-8 -*-
"""Что реально уходит в письмо: проверяем через КОД ОТПРАВКИ, а не по конфигу."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
from sender.wiring import build_deps                               # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
s = getattr(deps, "sender", None) or getattr(deps, "smtp_sender", None)
print("объект отправки: %s" % type(s).__name__ if s else "не найден в deps")
ящики = cfg.mailboxes()
mb = ящики[0]
шапка = s._list_unsubscribe_headers("ТЕСТОВЫЙ_ТОКЕН", mb)
print("ящик: %s" % getattr(mb, "mailbox_id", "?"))
print("заголовки отписки: %r" % шапка)
строка = " ".join("%s: %s" % кv for кv in шапка.items())
print("   http в заголовке:     %s" % ("ДА" if "http" in строка.lower() else "нет"))
print("   помеченный домен:     %s"
      % ("ДА" if "parsercompressor" in строка.lower() else "нет"))
print("   One-Click заявлен:    %s"
      % ("ДА" if "One-Click" in строка else "нет"))
print("   сайт компании в шапке: %s"
      % ("ДА" if "prokompressor" in строка.lower() else "нет"))
try:
    from sender.tracking import OpenTracker
    т = OpenTracker(cfg)
    print("пиксель открытий включён: %r"
          % getattr(т, "enabled", cfg.get("tracking.open_enabled", None)))
except Exception as ex:
    print("трекер: %s" % ex)
