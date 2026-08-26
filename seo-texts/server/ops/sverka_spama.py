# -*- coding: utf-8 -*-
"""Ответы, улетевшие в «Спам», забираем в ленту лидов.

ЗАЧЕМ. Сторож читает только INBOX. 25.08 ООО «ВЗНО» ответило на наше
письмо, почтовик положил ответ в «Спам» — в базе его не было вовсе, и
продавец его не видел. Разбирать спам целиком нельзя (там мусор), поэтому
берём только письма ОТ НАШИХ ЖЕ получателей: адрес известен базе, значит
это ответ на нашу рассылку, а не чужая реклама.

Идемпотентно: лид заводится по ключу письма, повтор ничего не двоит.

    python sverka_spama.py            # показать
    python sverka_spama.py primenit   # завести лиды
"""
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "120"))
СПАМ = re.compile(r"spam|junk|спам|нежелат", re.I)
СВОИ = re.compile(r"kompressor|compressor-store|optic-sort|zernosort|"
                  r"sort-systems|meyer|prokompressor", re.I)
# Публичные почтовики: по домену компанию не опознать, берём только точное
# совпадение адреса.
ОБЩИЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru",
         "gmail.com", "rambler.ru", "outlook.com", "hotmail.com", "mail.com"}

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")
c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

найдено = []
for м in mb.mailboxes():
    яид = м["mailbox_id"] if isinstance(м, dict) else м
    try:
        папки = mb.folders(яид)
    except Exception:                                         # noqa: BLE001
        continue
    for п in папки:
        имя = п.get("name") if isinstance(п, dict) else str(п)
        показ = п.get("display") if isinstance(п, dict) else имя
        if not (СПАМ.search(str(имя or "")) or СПАМ.search(str(показ or ""))):
            continue
        try:
            д = mb.messages(яид, folder=имя, limit=СКОЛЬКО)
        except Exception:                                     # noqa: BLE001
            continue
        for пис in (д.get("messages") or []):
            отпр = str(пис.get("from_addr") or "").lower()
            if not отпр or СВОИ.search(отпр):
                continue
            дом = отпр.rsplit("@", 1)[-1]
            r = c.execute("SELECT id, company_name FROM recipients "
                          " WHERE email=?", (отпр,)).fetchone()
            if r is None and дом not in ОБЩИЕ:
                строки = c.execute(
                    "SELECT id, inn, company_name FROM recipients "
                    " WHERE lower(domain)=? OR lower(email) LIKE ?",
                    (дом, "%@" + дом)).fetchall()
                инны = {str(x["inn"] or "") for x in строки}
                инны.discard("")
                if строки and len(инны) <= 1:
                    r = строки[0]
            if r is None:
                continue
            # Уже знаем этот ответ?
            есть = c.execute(
                "SELECT 1 FROM events WHERE recipient_id=? "
                "   AND event_type IN ('reply','reply_auto') LIMIT 1",
                (r["id"],)).fetchone()
            найдено.append((яид, имя, пис, r, bool(есть)))

print("в спам-папках писем от наших компаний: %d" % len(найдено))
новых = [x for x in найдено if not x[4]]
print("из них ответ этой компании базе НЕ известен: %d" % len(новых))
for яид, папка, пис, r, _е in найдено:
    print("   %s | %-28s | %-30s | %s"
          % (str(пис.get("date_iso"))[:16], str(пис.get("from_addr"))[:28],
             str(r["company_name"])[:30], "новый" if not _е else "уже есть"))
    print("      %s" % str(пис.get("subject"))[:88])

if not ДЕЛАТЬ or not новых:
    print("\nвхолостую или нечего заводить. Завести — primenit")
    raise SystemExit(0)

from sender.leaddesk import LeadDesk                          # noqa: E402
from sender.store import Store                                # noqa: E402

store = Store(БАЗА)
десk = LeadDesk(cfg, store)
заведено = 0
for яид, папка, пис, r, _е in новых:
    try:
        полное = mb.message(яид, folder=папка, uid=пис["uid"])
    except Exception as ex:                                   # noqa: BLE001
        print("   тело не прочлось: %s" % str(ex)[:60])
        continue
    тело = " ".join(str(полное.get("body") or полное.get("text") or "").split())
    рек = store.get_recipient(int(r["id"]))
    if рек is None:
        continue
    if десk.push_warm_lead(рек, пис.get("message_id") or "",
                           "[reply] " + тело[:3000],
                           otvetil=str(пис.get("from_addr") or "")):
        заведено += 1
c.close()
print("\nзаведено лидов: %d" % заведено)
