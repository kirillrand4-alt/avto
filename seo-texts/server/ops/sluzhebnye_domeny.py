# -*- coding: utf-8 -*-
"""Адреса хостеров, регистраторов и аутсорсеров, попавшие в базу как контакты."""
import re
import sqlite3

СЛУЖЕБНЫЕ = (
    "sweb.ru", "reg.ru", "timeweb.ru", "timeweb.com", "nic.ru", "beget.ru",
    "beget.com", "masterhost.ru", "jino.ru", "ihc.ru", "hostland.ru",
    "netangels.ru", "firstvds.ru", "ispserver.ru", "rucenter.ru", "r01.ru",
    "webnames.ru", "hc.ru", "spaceweb.ru", "fastvps.ru", "selectel.ru",
    "hostinger.ru", "mchost.ru", "agava.ru", "eurobyte.ru", "adminvps.ru",
    "wix.com", "tilda.cc", "tilda.ws", "ukit.com", "nethouse.ru",
    "1c-bitrix.ru", "bitrix24.ru", "sendpulse.com", "unisender.com",
    "mailchimp.com", "yandex.team", "kontur.ru", "sbis.ru", "diadoc.ru",
    "1cbo.ru", "moedelo.org", "nalog.ru", "gosuslugi.ru",
)
РОЛЬ = re.compile(r"^(support|help|noreply|no-reply|abuse|billing|hostmaster|"
                  r"postmaster|webmaster|admin|robot|bot|mailer)@", re.I)

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
ряды = c.execute("SELECT id, inn, email, company_name, domain FROM recipients "
                 " WHERE email IS NOT NULL AND email <> ''").fetchall()
служебные, ролевые_чужие = [], []
for r in ряды:
    почта = str(r["email"]).strip().lower()
    дом = почта.rsplit("@", 1)[-1]
    if дом in СЛУЖЕБНЫЕ:
        служебные.append(r)
    elif РОЛЬ.match(почта) and дом not in ("mail.ru", "yandex.ru", "bk.ru",
                                           "list.ru", "inbox.ru", "gmail.com"):
        ролевые_чужие.append(r)

print("контактов на домене хостера/сервиса: %d" % len(служебные))
for r in служебные[:20]:
    print("   %-34s %-46s ИНН %s" % (r["email"][:34],
                                     str(r["company_name"])[:46], r["inn"]))
print("")
print("служебные ящики (support@, noreply@ и т.п.) на своём домене: %d"
      % len(ролевые_чужие))
for r in ролевые_чужие[:10]:
    print("   %-34s %s" % (r["email"][:34], str(r["company_name"])[:50]))

print("")
print("=== конкурент: ищем по адресу из письма ===")
for r in c.execute("SELECT id, inn, email, company_name, domain, okved "
                   "  FROM recipients WHERE email LIKE 'avaditex%'"):
    print("   #%s %s (ИНН %s) | %s | ОКВЭД %s"
          % (r["id"], r["company_name"], r["inn"], r["email"], r["okved"]))
    for cr in c.execute("SELECT id, status, created_at, substr(subject,1,60) s "
                        "  FROM confirm_reviews WHERE recipient_id=? "
                        " ORDER BY id DESC LIMIT 3", (r["id"],)):
        print("      карточка #%s %-9s %s | %s"
              % (cr["id"], cr["status"], str(cr["created_at"])[:19], cr["s"]))
c.close()
