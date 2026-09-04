# -*- coding: utf-8 -*-
"""Только чтение: сколько компаний годятся под второе касание.

Условия владельца:
  1) контакту писали больше 3 дней назад и НЕ по вебинару;
  2) выручка компании от 30 млн;
  3) направление meyer;
  4) компания нам не ответила;
  5) у компании есть ЕЩЁ адрес — снятый с сайта либо на домене сайта,
     откуда собран паспорт.
"""
import datetime as dt
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row

utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
граница = (utc - dt.timedelta(days=3)).isoformat()
print("колонки emails: %s"
      % ", ".join(r["name"] for r in e.execute("PRAGMA table_info(emails)")))

# --- 1. кому писали давно и не по вебинару ---
писали = {}
for р in s.execute("SELECT r.inn, r.email, MAX(m.sent_at) посл FROM messages m"
                   " JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.status='sent' AND m.campaign_id<>12"
                   " AND r.inn IS NOT NULL AND r.inn<>''"
                   " GROUP BY r.inn"):
    if str(р["посл"]) <= граница:
        писали[р["inn"]] = р["посл"]
print("\n1) компаний, кому писали не по вебинару и раньше чем 3 дня назад: %d"
      % len(писали))

# --- 2. ответившие ---
ответили = set()
for р in s.execute("SELECT DISTINCT r.inn FROM events ev"
                   " JOIN recipients r ON r.id=ev.recipient_id"
                   " WHERE ev.event_type IN ('reply','reply_auto')"
                   " AND r.inn IS NOT NULL AND r.inn<>''"):
    ответили.add(р["inn"])
шаг2 = {i: t for i, t in писали.items() if i not in ответили}
print("2) из них компания нам не ответила: %d" % len(шаг2))

# --- 3. выручка и направление ---
инн = list(шаг2)
выручка, дивизион = {}, {}
for i in range(0, len(инн), 800):
    к = инн[i:i + 800]
    q = ",".join("?" * len(к))
    for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE inn IN (%s)" % q, к):
        выручка[р["inn"]] = р["revenue_rub"]
    for р in o.execute("SELECT inn, division FROM obzvon WHERE inn IN (%s)" % q, к):
        дивизион[р["inn"]] = р["division"] or ""
шаг3 = [i for i in шаг2 if (выручка.get(i) or 0) >= 30_000_000]
print("3) из них выручка от 30 млн: %d" % len(шаг3))
шаг4 = [i for i in шаг3 if "meyer" in (дивизион.get(i) or "")]
print("4) из них направление meyer: %d" % len(шаг4))

# --- 5. есть ли ещё адрес ---
уже_писали_адреса = set()
for р in s.execute("SELECT DISTINCT LOWER(r.email) e FROM messages m"
                   " JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'"):
    уже_писали_адреса.add(р["e"])

паспорт_домен = {}
годных, всего_адресов = [], 0
чужая_ссылка = [0]
for i in range(0, len(шаг4), 800):
    к = шаг4[i:i + 800]
    q = ",".join("?" * len(к))
    for р in e.execute("SELECT inn, site FROM site_facts WHERE inn IN (%s)" % q, к):
        if р["site"]:
            паспорт_домен[р["inn"]] = str(р["site"]).lower().replace("www.", "")
для_инн, свои_сайты = {}, {}


def _дом(u):
    import re as _re
    u = str(u or "").strip().lower()
    if not u:
        return ""
    u = _re.sub(r"^https?://", "", u).split("/")[0].split("?")[0]
    return u[4:] if u.startswith("www.") else u

for i in range(0, len(шаг4), 800):
    к = шаг4[i:i + 800]
    q = ",".join("?" * len(к))
    for р in e.execute("SELECT inn, email, source, source_url FROM emails"
                       " WHERE inn IN (%s)" % q, к):
        для_инн.setdefault(р["inn"], []).append((str(р["email"]).lower(),
                                                 str(р["source"] or ""),
                                                 str(р["source_url"] or "")))
    for р in e.execute("SELECT inn, site, cand_site, site_checko FROM companies"
                       " WHERE inn IN (%s)" % q, к):
        свои_сайты[р["inn"]] = {_дом(р["site"]), _дом(р["cand_site"]),
                                _дом(р["site_checko"])} - {""}
for inn in шаг4:
    пд = паспорт_домен.get(inn)
    свежие = []
    for адрес, ист, ссылка in для_инн.get(inn, []):
        if адрес in уже_писали_адреса:
            continue
        домен = адрес.partition("@")[2]
        свои = свои_сайты.get(inn) or set()
        ссылка_своя = (not ссылка) or (not свои) or (_дом(ссылка) in свои)
        с_сайта = (ист in ("own-site", "обзвон-сайт", "сайт:справочник")
                   and ссылка_своя)
        if ист == "own-site" and ссылка and свои and _дом(ссылка) not in свои:
            чужая_ссылка[0] += 1
            continue
        на_домене_паспорта = bool(пд) and домен == пд
        if с_сайта or на_домене_паспорта:
            свежие.append(адрес)
    if свежие:
        годных.append((inn, свежие))
        всего_адресов += len(свежие)

print("   отброшено адресов с чужой ссылкой (агрегаторы): %d" % чужая_ссылка[0])
print("5) из них есть ещё адрес с сайта или на домене паспорта: %d" % len(годных))

# --- 6. стоп-лист: сделки, отписки, отбивки ---
стоп_инн, стоп_почта = set(), set()
for р in s.execute("SELECT scope, value FROM suppression"):
    v = str(р["value"] or "").strip().lower()
    if р["scope"] == "inn":
        стоп_инн.add(v)
    elif р["scope"] == "email":
        стоп_почта.add(v)
чистые = []
адресов_чистых = 0
for inn, ад in годных:
    if str(inn).lower() in стоп_инн:
        continue
    св = [a for a in ад if a not in стоп_почта]
    if св:
        чистые.append((inn, св))
        адресов_чистых += len(св)
print("6) после стоп-листа (сделки, отписки, отбивки): %d" % len(чистые))
годных, всего_адресов = чистые, адресов_чистых
print("\n=== ИТОГ ===")
print("  компаний под второе касание: %d" % len(годных))
print("  всего свободных адресов у них: %d" % всего_адресов)
print("  если писать по одному адресу на компанию: %d писем" % len(годных))
print("\n=== ПРИМЕРЫ ===")
for inn, ад in годных[:8]:
    print("  %-12s выручка %5.0f млн  адреса: %s"
          % (inn, (выручка.get(inn) or 0) / 1e6, ", ".join(ад[:3])[:60]))
