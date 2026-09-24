# -*- coding: utf-8 -*-
"""Что панель отдаёт в ленту диалога карточки: оба ли ответа там."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ЛИД = int(sys.argv[1]) if len(sys.argv) > 1 else 492
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def п(о, имя, умолч=None):
    if isinstance(о, dict):
        return о.get(имя, умолч)
    return getattr(о, имя, умолч)


лид = store.get_lead(ЛИД)
print("лид %s — %s, ИНН %s, почта %s, ветка %s"
      % (ЛИД, п(лид, "company_name"), п(лид, "inn"), п(лид, "email"),
         п(лид, "thread_id")))

# ровно тот путь, которым живёт экран карточки
from sender.store import group_dialog_threads                   # noqa: E402
инн = п(лид, "inn")
элементы = store.dialog_thread_company(инн) if инн else []
охват = "company"
if not элементы:
    элементы = store.dialog_thread(п(лид, "recipient_id")) or []
    охват = "recipient"
диалог = {"thread": элементы, "threads": group_dialog_threads(элементы)}
print("охват: %s" % охват)
print("")
print("--- лента диалога: %d элементов ---" % len(элементы))
for э in элементы:
    тело = str(п(э, "body") or "")
    print("   %-12s %s  %s"
          % (п(э, "kind"), str(п(э, "ts"))[:16], str(п(э, "subject") or "")[:50]))
    print("       ящик %-34s %s" % (str(п(э, "mailbox_id") or "-"),
                                    str(п(э, "email") or "")))
    первая = " ".join(тело.split())[:110]
    print("       тело (%d знаков): %s" % (len(тело), первая))

if isinstance(диалог, dict) and диалог.get("threads"):
    print("")
    print("--- ветки ---")
    for в in диалог["threads"]:
        эл = п(в, "items") or []
        print("   ветка %s: %d писем, тема «%s»"
              % (п(в, "id"), len(эл), str(п(в, "subject") or "")[:50]))
print("")
print("=" * 74)
print("=== ДИАЛОГ КАРТОЧКИ %d ===" % ЛИД)
