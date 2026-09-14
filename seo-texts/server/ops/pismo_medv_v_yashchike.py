# -*- coding: utf-8 -*-
"""Лежит ли ответ Медведовского ЗПП в самом ящике: обход всех папок по IMAP.

Вопрос владельца: письмо было в ленте лидов? По базе — нет. Здесь смотрим
живьём в почте: есть ли вообще это входящее, в какой папке, прочитано ли,
и что в теле. Если письмо в ящике есть, а лида нет — значит сборщик его
не взял (или взял и выбросил), и лид надо завести руками.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.mailbrowser import MailBrowser  # noqa: E402

ЯЩИК = "i.boyarkin@zernosort.ru"
ИСКАТЬ = "krimck1600"

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)

строки = []
найдено = []
try:
    папки = mb.folders(ЯЩИК)
except Exception as ex:                                         # noqa: BLE001
    папки = []
    строки.append("папки не прочитались: %s" % str(ex)[:140])

строки.append("папок в ящике %s: %d" % (ЯЩИК, len(папки)))
for п in папки:
    имя = п.get("name") if isinstance(п, dict) else str(п)
    титул = п.get("title") if isinstance(п, dict) else имя
    роль = п.get("role") if isinstance(п, dict) else "?"
    try:
        рез = mb.messages(ЯЩИК, folder=имя, limit=25, search=ИСКАТЬ)
    except Exception as ex:                                     # noqa: BLE001
        строки.append("   %-28s %-8s ОШИБКА: %s" % (титул, роль, str(ex)[:60]))
        continue
    всего = int(рез.get("total") or 0)
    строки.append("   %-28s %-8s совпадений: %d" % (титул, роль, всего))
    for м in рез.get("messages") or []:
        найдено.append((имя, титул, м))

строки.append("")
строки.append("--- найденные письма ---")
for имя, титул, м in найдено:
    строки.append("   папка %s | uid=%s | %s | прочитано=%s"
                  % (титул, м.get("uid"), str(м.get("date"))[:30],
                     м.get("seen")))
    строки.append("      от:   %s %s" % (str(м.get("from_name"))[:40],
                                          str(м.get("from_addr"))[:50]))
    строки.append("      кому: %s" % str(м.get("to_addr"))[:90])
    строки.append("      тема: %s" % str(м.get("subject"))[:90])
    строки.append("      msgid: %s" % str(м.get("message_id"))[:90])

# тело первого входящего от клиента
for имя, титул, м in найдено:
    отпр = str(м.get("from_addr") or "").lower()
    if ИСКАТЬ not in отпр:
        continue
    try:
        целиком = mb.message(ЯЩИК, folder=имя, uid=str(м.get("uid")))
    except Exception as ex:                                     # noqa: BLE001
        строки.append("   тело не прочиталось: %s" % str(ex)[:100])
        break
    строки.append("")
    строки.append("--- тело входящего (uid=%s) ---" % м.get("uid"))
    тело = str(целиком.get("body") or "")[:1800]
    for с in тело.splitlines()[:45]:
        строки.append("      " + с[:150])
    break

print("\n".join(строки))
print("")
print("=" * 74)
print("=== ПИСЬМО МЕДВЕДОВСКОГО В ЯЩИКЕ ===")
