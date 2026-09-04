# -*- coding: utf-8 -*-
"""Сколько адресов «кэш-добора» пришло из служебного кода, а не из контактов.

Признаки служебного происхождения ищем по самому адресу и по компании:
 - адрес на ЧУЖОМ домене (не совпадает с сайтом компании) — личная почта,
   какие обычно и попадают в скрипты;
 - бесплатные почтовики у компании со своим доменом;
 - адреса-ловушки (noreply, example, test, sentry, wixpress и т.п.);
 - домены сервисов конструкторов сайтов (tilda, wix, bitrix и пр.).
Это не приговор, а разметка: точный ответ даёт только просмотр страниц.
"""
import re
import sqlite3
from collections import Counter

БЕСПЛАТНЫЕ = ("mail.ru", "yandex.ru", "ya.ru", "gmail.com", "bk.ru",
              "inbox.ru", "list.ru", "rambler.ru", "yahoo.com", "icloud.com",
              "outlook.com", "hotmail.com", "internet.ru", "mail.by",
              "tut.by", "ukr.net")
СЛУЖЕБНЫЕ = ("noreply", "no-reply", "example", "test@", "sentry",
             "wixpress", "tilda", "sitemap", "webmaster", "postmaster",
             "abuse@", "hostmaster", "@sentry", "donotreply", "bitrix",
             "yourdomain", "domain.com", "email@", "mail@mail")

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=180)
c.row_factory = sqlite3.Row
сайты = {}
for и, s1, s2 in c.execute("SELECT inn, site, cand_site FROM companies"):
    д = str(s1 or s2 or "").lower()
    д = re.sub(r"^https?://", "", д).split("/")[0].replace("www.", "")
    if д:
        сайты[str(и)] = д

ряды = [dict(r) for r in c.execute(
    "SELECT inn, email, source, source_url, pometka, role FROM emails "
    " WHERE COALESCE(pometka,'') LIKE '%кэш-добор%'")]
c.close()

счёт = Counter()
примеры = {}
for р in ряды:
    поч = str(р.get("email") or "").lower()
    дом = поч.split("@")[-1]
    сайт = сайты.get(str(р.get("inn")), "")
    если = None
    if any(x in поч for x in СЛУЖЕБНЫЕ):
        если = "служебный/технический адрес"
    elif дом in БЕСПЛАТНЫЕ and сайт and сайт not in БЕСПЛАТНЫЕ:
        если = "бесплатный ящик у компании со своим доменом"
    elif сайт and дом and дом != сайт and not дом.endswith("." + сайт) \
            and not сайт.endswith("." + дом) and дом not in БЕСПЛАТНЫЕ:
        если = "ЧУЖОЙ домен (не сайт компании)"
    elif дом in БЕСПЛАТНЫЕ:
        если = "бесплатный ящик, своего домена у компании нет"
    else:
        если = "на своём домене компании"
    счёт[если] += 1
    примеры.setdefault(если, []).append(
        "%-34s сайт: %-24s роль: %s"
        % (поч[:34], (сайт or "—")[:24], str(р.get("role") or "—")[:12]))

итог = sum(счёт.values())
print("=" * 84)
print("=== СВОДКА: АДРЕСА «КЭШ-ДОБОРА» ===")
print("всего адресов с этой пометкой: %d" % итог)
print("")
for к, в in счёт.most_common():
    print("   %-46s %6d  (%4.1f%%)"
          % (к, в, 100.0 * в / итог if итог else 0))
print("")
print("=== ПРИМЕРЫ (по три) ===")
for к, спис in счёт.most_common():
    print("--- %s" % к[:60])
    for с in примеры[к][:3]:
        print("      " + с[:96])

# пересечение со сбором по Чеко
c2 = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                     timeout=180)
из_сбора = {str(r[0]) for r in c2.execute(
    "SELECT inn FROM requisites WHERE src='checko-sbor-agro'")}
c2.close()
наши_инн = {str(р.get("inn")) for р in ряды}
пересеч = наши_инн & из_сбора

print("")
print("=" * 84)
print("=== СВОДКА КОРОТКО ===")
print("адресов с пометкой «кэш-добор»: %d, у %d компаний"
      % (итог, len(наши_инн)))
for к, в in счёт.most_common():
    print("   %-46s %6d  (%4.1f%%)" % (к, в, 100.0 * в / итог if итог else 0))
print("")
print("компаний свежего сбора Чеко: %d" % len(из_сбора))
print("пересечение с «кэш-добором»: %d" % len(пересеч))
print("   -> это %s"
      % ("РАЗНЫЕ наборы, кэш-добор к сбору Чеко отношения не имеет"
         if len(пересеч) < 50 else "заметно пересекающиеся наборы"))
