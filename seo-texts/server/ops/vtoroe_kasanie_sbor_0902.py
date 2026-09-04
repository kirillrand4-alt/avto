# -*- coding: utf-8 -*-
"""Второе касание: копия прежнего письма на другой адрес компании.

Что проверяем в каждом письме:
  * имя отправителя. В решении текст хранится с меткой ИМЯ_ОТПРАВИТЕЛЯ,
    её и копируем - движок подставит имя ТОГО ящика, с которого письмо
    реально уйдёт. Если в старом тексте метки нет, а имя менеджера в нём
    есть, метку возвращаем на место;
  * обращение. Прежний адресат - другой человек. Именное обращение
    заменяем на имя нового адресата, если оно известно, иначе на
    безымянное «Добрый день!».

argv: проба | делать
"""
import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                        # noqa: E402
from sender.store import Store, CampaignIn, RecipientIn  # noqa: E402

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
ИМЯ_КАМПАНИИ = "Второе касание — Meyer"
ГРУППА = "vtoroe-kasanie-0209"
МЕТКА = "ИМЯ_ОТПРАВИТЕЛЯ"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
граница = (utc - dt.timedelta(days=3)).isoformat()

ИМЕНА = {str(m.get("from_name", "")).split()[0] for m in cfg.get("mailboxes", [])
         if m.get("from_name")}
ПУБЛ = {"mail.ru", "gmail.com", "yandex.ru", "list.ru", "bk.ru", "inbox.ru", "ya.ru",
        "rambler.ru", "icloud.com", "yahoo.com", "outlook.com", "mail.com"}
ВРЕМЕННОЕ = ("вебинар", "августа", "завтра", "прошедш", "на следующей неделе")
РОЛЕВЫЕ = ("info", "office", "mail", "sale", "sales", "zakaz", "zakupki", "shop",
           "market", "secretar", "priemnaya", "post", "reception")


def дом(u):
    u = str(u or "").strip().lower()
    if not u:
        return ""
    u = re.sub(r"^https?://", "", u).split("/")[0].split("?")[0]
    return u[4:] if u.startswith("www.") else u


# ---------- отбор компаний ----------
писали = {}
for р in s.execute("SELECT r.inn, MAX(m.sent_at) п FROM messages m JOIN recipients r"
                   " ON r.id=m.recipient_id WHERE m.status='sent' AND m.campaign_id<>12"
                   " AND r.inn IS NOT NULL AND r.inn<>'' GROUP BY r.inn"):
    if str(р["п"]) <= граница:
        писали[р["inn"]] = р["п"]
ответили = {р["inn"] for р in s.execute(
    "SELECT DISTINCT r.inn FROM events ev JOIN recipients r ON r.id=ev.recipient_id"
    " WHERE ev.event_type IN ('reply','reply_auto') AND r.inn IS NOT NULL")}
канд = [i for i in писали if i not in ответили]
выр, див, сайты, паспорт = {}, {}, {}, {}
for i in range(0, len(канд), 800):
    к = канд[i:i + 800]
    q = ",".join("?" * len(к))
    for р in e.execute("SELECT inn, revenue_rub, site, cand_site, site_checko,"
                       " name FROM companies WHERE inn IN (%s)" % q, к):
        выр[р["inn"]] = (р["revenue_rub"], р["name"])
        сайты[р["inn"]] = {дом(р["site"]), дом(р["cand_site"]),
                           дом(р["site_checko"])} - {""}
    for р in o.execute("SELECT inn, division FROM obzvon WHERE inn IN (%s)" % q, к):
        див[р["inn"]] = р["division"] or ""
    for р in e.execute("SELECT inn, site FROM site_facts WHERE inn IN (%s)" % q, к):
        if р["site"]:
            паспорт[р["inn"]] = дом(р["site"])
цель = [i for i in канд
        if (выр.get(i, (0,))[0] or 0) >= 30_000_000 and "meyer" in (див.get(i) or "")]

# ---------- стоп-лист и уже написанные адреса ----------
стоп_инн = {str(р["value"]).lower() for р in s.execute(
    "SELECT value FROM suppression WHERE scope='inn'")}
стоп_почта = {str(р["value"]).lower() for р in s.execute(
    "SELECT value FROM suppression WHERE scope='email'")}
писали_адреса = {str(р["e"]).lower() for р in s.execute(
    "SELECT DISTINCT LOWER(r.email) e FROM messages m JOIN recipients r"
    " ON r.id=m.recipient_id WHERE m.status='sent'")}

# ---------- выбор адреса ----------
адреса = {}
for i in range(0, len(цель), 800):
    к = цель[i:i + 800]
    q = ",".join("?" * len(к))
    for р in e.execute("SELECT inn, email, source, source_url, person, imya_ok"
                       " FROM emails WHERE inn IN (%s)" % q, к):
        адреса.setdefault(р["inn"], []).append(dict(р))


def выбрать(inn):
    """Один адрес на компанию: корпоративный и именной ценнее ролевого."""
    лучший, лучший_вес = None, -1
    for a in адреса.get(inn, []):
        почта = str(a["email"]).lower()
        if почта in писали_адреса or почта in стоп_почта:
            continue
        д = почта.partition("@")[2]
        ссылка = дом(a["source_url"])
        свои = сайты.get(inn) or set()
        if a["source"] == "own-site" and ссылка and свои and ссылка not in свои:
            continue          # адрес снят не с сайта компании
        с_сайта = a["source"] in ("own-site", "обзвон-сайт", "сайт:справочник")
        на_паспорте = bool(паспорт.get(inn)) and д == паспорт.get(inn)
        if not (с_сайта or на_паспорте):
            continue
        вес = 0
        if д not in ПУБЛ:
            вес += 4
        if a.get("person") and a.get("imya_ok") == 1:
            вес += 3
        if not any(почта.startswith(x) for x in РОЛЕВЫЕ):
            вес += 2
        if на_паспорте:
            вес += 1
        if вес > лучший_вес:
            лучший, лучший_вес = a, вес
    return лучший


def имя_из(person):
    ч = str(person or "").strip().split()
    if len(ч) >= 2 and re.match(r"^[А-ЯЁ][а-яё]{2,}$", ч[1]):
        return ч[1]                       # «Хачатрян Гоар Аветисовна» -> Гоар
    if len(ч) == 1 and re.match(r"^[А-ЯЁ][а-яё]{2,}$", ч[0]):
        return ч[0]
    return None


def починить(тело, имя_адресата):
    """Вернуть метку отправителя и поправить обращение."""
    прав = []
    т = тело
    if МЕТКА not in т:
        for им in ИМЕНА:
            if им and re.search(r"Меня зовут %s\b" % re.escape(им), т):
                т = re.sub(r"(Меня зовут )%s\b" % re.escape(им), r"\1" + МЕТКА, т)
                прав.append("вернул метку вместо «%s»" % им)
                break
    стр = т.splitlines()
    п = стр[0] if стр else ""
    было_имя = bool(re.match(r"^[А-ЯЁ][а-яё]+(\s[А-ЯЁ][а-яё]+)?,\s*(добрый день"
                             r"|здравствуйте)", п, re.I))
    if было_имя:
        нов = ("%s, добрый день!" % имя_адресата) if имя_адресата else "Добрый день!"
        стр[0] = нов
        т = "\n".join(стр)
        прав.append("обращение: «%s» -> «%s»" % (п[:24], нов))
    elif имя_адресата and re.match(r"^(добрый день|здравствуйте)", п, re.I):
        стр[0] = "%s, добрый день!" % имя_адресата
        т = "\n".join(стр)
        прав.append("добавил имя адресата")
    return т, прав


# ---------- сборка ----------
занятые_адреса = set()
письма, ст = [], {"нет адреса": 0, "адрес уже в партии": 0, "стоп-лист": 0, "нет исходника": 0,
                  "метка возвращена": 0, "обращение поправлено": 0,
                  "имя адресата известно": 0, "имени менеджера в тексте нет": 0}
for inn in цель:
    if str(inn).lower() in стоп_инн:
        ст["стоп-лист"] += 1
        continue
    a = выбрать(inn)
    if not a:
        ст["нет адреса"] += 1
        continue
    # Письмо про уже прошедшее событие копировать нельзя: приглашение на
    # вебинар 28 августа, отправленное в сентябре, выглядит как небрежность.
    # Берём самое свежее письмо БЕЗ привязки ко времени; нет такого - пропуск.
    ист = None
    for кан in s.execute(
            "SELECT cr.body, cr.subject FROM messages m JOIN recipients r"
            " ON r.id=m.recipient_id JOIN confirm_reviews cr ON cr.message_id=m.id"
            " WHERE m.status='sent' AND m.campaign_id<>12 AND r.inn=? AND cr.body<>''"
            " ORDER BY m.sent_at DESC LIMIT 6", (inn,)):
        т = (str(кан["body"]) + " " + str(кан["subject"] or "")).lower()
        if any(сл in т for сл in ВРЕМЕННОЕ):
            continue
        ист = кан
        break
    if not ист:
        ст["исходник привязан ко времени"] = ст.get("исходник привязан ко времени", 0) + 1
        continue
    п_почта = str(a["email"]).lower()
    имя = имя_из(a.get("person")) if a.get("imya_ok") == 1 else None
    if имя:
        ст["имя адресата известно"] += 1
    тело, прав = починить(str(ист["body"]), имя)
    for p in прав:
        if "метку" in p:
            ст["метка возвращена"] += 1
        if "бращение" in p or "имя адресата" in p:
            ст["обращение поправлено"] += 1
    if МЕТКА not in тело:
        ст["имени менеджера в тексте нет"] += 1
    if п_почта in занятые_адреса:
        ст["адрес уже в партии"] += 1
        continue
    занятые_адреса.add(п_почта)
    письма.append({"inn": inn, "email": str(a["email"]).lower(),
                   "компания": (выр.get(inn) or (0, ""))[1],
                   "тема": ист["subject"], "тело": тело,
                   "имя": имя, "правки": прав})

print("=== СОБРАНО ===")
print("  компаний в отборе: %d" % len(цель))
for k, v in ст.items():
    print("  %-28s %d" % (k, v))
print("  ПИСЕМ К ОТПРАВКЕ: %d" % len(письма))

плохо = [п for п in письма
         if МЕТКА not in п["тело"] and any(re.search(r"Меня зовут %s\b" % re.escape(и),
                                                     п["тело"]) for и in ИМЕНА if и)]
print("\n  писем с чужим именем менеджера в тексте: %d (должно быть 0)" % len(плохо))
одинак = len(письма) - len({п["email"] for п in письма})
print("  повторов адреса внутри партии: %d" % одинак)
поинн = len(письма) - len({п["inn"] for п in письма})
print("  повторов компании внутри партии: %d" % поинн)

if not ДЕЛАТЬ:
    print("\n=== ТРИ ПРИМЕРА ===")
    for п in письма[:3]:
        print("\n  --- %s | %s ---" % (п["компания"][:40], п["email"]))
        print("  тема: %s" % п["тема"])
        print("  правки: %s" % ("; ".join(п["правки"]) or "не потребовались"))
        print("  " + "\n  ".join(п["тело"].splitlines()[:5]))
    print("\nничего не изменено (режим пробы)")
    raise SystemExit(0)

# ---------- заливка ----------
кид = None
for к in store.list_campaigns():
    if getattr(к, "name", None) == ИМЯ_КАМПАНИИ:
        кид = к.id
if кид is None:
    кид = store.create_campaign(CampaignIn(
        name=ИМЯ_КАМПАНИИ, legal_entity="ООО «Руспром»", legal_inn="2221239841",
        provider_pool=None,
        config={"segment": "meyer", "division": "meyer", "letter_mode": "kopiya",
                "ai_mode": "off", "gruppa": ГРУППА,
                "opisanie": "второе касание: копия письма на другой адрес компании"}))
print("кампания: id=%s" % кид)

вышло = {"новых": 0, "было": 0, "в очередь": 0, "стоп": 0, "ошибка": 0}
for п in письма:
    домен = п["email"].partition("@")[2]
    сущ = store.find_recipient_by_email(п["email"])
    доп = {}
    if сущ:
        вышло["было"] += 1
        try:
            доп = json.loads(сущ.get("extra_json") or "{}")
        except Exception:
            доп = {}
    else:
        вышло["новых"] += 1
    гр = list(доп.get("gruppy") or [])
    if ГРУППА not in гр:
        гр.append(ГРУППА)
    доп.update({"gruppy": гр, "volna": ГРУППА, "rol": "второй контакт компании",
                "zachem": "первому контакту писали, компания не ответила"})
    рид = store.upsert_recipient(RecipientIn(
        email=п["email"], domain=домен, inn=п["inn"],
        company_name=п["компания"] or None, okved=(сущ or {}).get("okved"),
        segment="meyer", bitrix_id=(сущ or {}).get("bitrix_id"),
        contact_name=п["имя"] or (сущ or {}).get("contact_name"),
        source="второе касание 02.09",
        priority_max=(сущ or {}).get("priority_max"),
        priority_total=(сущ or {}).get("priority_total"),
        pxr=(сущ or {}).get("pxr"), region=(сущ or {}).get("region"),
        tz=(сущ or {}).get("tz"), extra=доп))
    панель = {"actions": {"confirm_hold": False}, "ai": False,
              "letter_division": "meyer",
              "letter_division_reason": "второе касание, дивизион meyer",
              "company": {"name": п["компания"] or "", "inn": п["inn"]},
              "contact": {"name": п["имя"] or "", "email": п["email"]},
              "vtoroe_kasanie": {"gruppa": ГРУППА, "pravki": п["правки"]}}
    try:
        рев, новый = store.confirm_submit(
            email=п["email"], subject=п["тема"], body=п["тело"], inn=п["inn"],
            campaign_id=кид, recipient_id=рид, panel=панель, status="pending",
            reason="повтор разрешён: второй контакт компании, первому писали"
                   " и ответа нет")
        если = store.confirm_get(рев) or {}
        if если.get("status") == "skipped":
            вышло["стоп"] += 1
        elif новый:
            вышло["в очередь"] += 1
    except Exception as ex:
        вышло["ошибка"] += 1
        if вышло["ошибка"] <= 3:
            print("  ошибка на %s: %s" % (п["email"], str(ex)[:120]))

print("\n=== ЗАЛИТО ===")
for k, v in вышло.items():
    print("  %-12s %d" % (k, v))
print("  очередь подтверждений: %s"
      % json.dumps(store.confirm_counts(), ensure_ascii=False)[:180])
