# -*- coding: utf-8 -*-
"""Собрать публичную страницу лида и показать её текстом — без рестарта."""
import re
import sys
sys.path.insert(0, r"C:\sender")
ЛИД = int(sys.argv[1]) if len(sys.argv) > 1 else 253
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
from sender.leaddesk import LeadDesk                                  # noqa: E402
from sender import lid_ssylka as LS                                # noqa: E402
from sender import lid_stranica as LST                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
desk = LeadDesk(cfg, store)
lead = desk.get(ЛИД)
л = {"id": lead.id, "email": lead.email, "company_name": lead.company_name,
     "inn": lead.inn, "status": lead.status, "reply_kind": lead.reply_kind,
     "phone": lead.phone, "need": lead.need}
нить = store.dialog_thread_company(lead.inn) if lead.inn else []
контакты = {"karta": LS.karta_kompanii(lead.inn, л)}
html = LST.sobrat(л, нить, контакты,
                  (LS.bez_podpisi, LS.bez_adresov, LS.bez_citaty,
                   LS.bez_nashey_podpisi))
т = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
т = re.sub(r"</(div|p|tr|h1|h2)>", "\n", т)
т = re.sub(r"<br\s*/?>", "\n", т)
т = re.sub(r"</td>", " | ", т)
т = re.sub(r"<[^>]+>", "", т)
import html as _h
т = _h.unescape(т)
т = re.sub(r"[ \t]+", " ", т)
т = re.sub(r"\n\s*\n+", "\n", т)
print("=" * 70)
for стр in т.strip().split("\n"):
    if стр.strip():
        print(стр.strip())
print("=" * 70)
print("размер страницы: %d знаков, блоков переписки: %d" % (len(html), len(нить)))
