# -*- coding: utf-8 -*-
"""Сколько ещё вторых адресов можно достать под те же критерии.

Владелец 28.08: «сколько мы ещё можем достать писем под те же критерии?
(писали 3 дня назад, с учётом того что уже следующий день, паспорт и почта с
одного сайта либо домен почты и паспорт совпадает?)»

Уже поставленные адреса выпадают сами: они теперь заведены получателями.
"""
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender\sender")
ДНЕЙ = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))
ПОЧТОВИКИ = {
    "mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru", "yandex.ru",
    "ya.ru", "yandex.com", "narod.ru", "gmail.com", "googlemail.com",
    "rambler.ru", "outlook.com", "hotmail.com", "live.com", "icloud.com",
    "me.com", "yahoo.com", "tut.by", "mail.by", "lenta.ru", "autorambler.ru",
    "ro.ru", "myrambler.ru", "bigmir.net", "ukr.net", "i.ua",
}
ПРИГОВОР = {"нет ящика", "нет MX"}
НЕЛЬЗЯ_РОЛЬ = {"кадры", "бухгалтерия"}
СЛУЖЕБНЫЕ = {"gosuslugi", "buh", "buhgalter", "kadry", "kadri", "kadr", "ok",
             "hr", "vacancy", "rabota", "job", "press", "pr", "smi", "edo",
             "diadoc", "sbis", "nalog", "fss", "pfr", "noreply", "no-reply",
             "postmaster", "abuse", "spam", "rassylka", "news",
             # 28.08: в первой партии проскочили resume@ и cv@ — ящики для
             # резюме. Набор был собран по ролям обогащения, а эти приходят
             # с сайта и роли не имеют вовсе.
             "resume", "rezume", "cv", "personal", "otdelkadrov", "kadrovik",
             "vakans", "vakansiya", "career", "careers", "recruit",
             "recruiting", "hrm", "hrd", "praktika", "sekretariat"}
ВЕС = {"снабжение/закупки": 0, "продажи": 1, "директор": 2,
       "нач.производства": 3, "нач.цеха": 3, "гл.инженер": 3,
       "гл.конструктор": 4, "инженер (не главный)": 4, "техконтакт": 5,
       "общий": 6, "приёмная": 7, "свой": 8}
_ЦИФ = re.compile(r"\d+$")
порог = (datetime.now(timezone.utc) - timedelta(days=ДНЕЙ)).strftime("%Y-%m-%d")
print("сегодня %s, берём компании с письмом не позже %s"
      % (datetime.now(timezone.utc).strftime("%Y-%m-%d"), порог))


def дом(u):
    u = str(u or "").strip().lower()
    м = re.search(r"//([^/]+)", u)
    d = м.group(1) if м else u.split("/")[0]
    d = d[4:] if d.startswith("www.") else d
    return d if "." in d else ""


s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
s.row_factory = sqlite3.Row
послано, давность = {}, {}
for r in s.execute(
        "SELECT m.recipient_id rid, r.inn, r.email, MAX(m.sent_at) kogda "
        "  FROM messages m JOIN recipients r ON r.id = m.recipient_id "
        " WHERE m.status='sent' AND m.sent_at IS NOT NULL GROUP BY m.recipient_id"):
    if r["inn"]:
        послано[int(r["rid"])] = (str(r["inn"]), (r["email"] or "").lower())
        давность[int(r["rid"])] = str(r["kogda"])[:10]
ответили = {int(r[0]) for r in s.execute(
    "SELECT DISTINCT recipient_id FROM events "
    " WHERE event_type IN ('reply','reply_auto') AND recipient_id IS NOT NULL")}
инн_отв = {послано[rid][0] for rid in ответили if rid in послано}
свежие = {rid for rid, д in давность.items() if д > порог}
молч = {}
for rid, (инн, почта) in послано.items():
    if инн in инн_отв or rid in свежие:
        continue
    молч.setdefault(инн, set()).add(почта)
print("получателей с письмом: %d, ответили: %d компаний, свежих: %d"
      % (len(послано), len(инн_отв), len(свежие)))
print("компаний-кандидатов: %d" % len(молч))
уже = {(r[0] or "").lower() for r in s.execute(
    "SELECT email FROM recipients WHERE email IS NOT NULL")}
стоп = {(r[0] or "").lower() for r in s.execute(
    "SELECT value FROM suppression WHERE scope IN ('email','address')")}
инны = sorted(молч)
зн = ",".join("?" * len(инны))
не_покуп = {str(r[0]) for r in s.execute(
    "SELECT inn FROM target_verdicts WHERE verdict='не покупатель' "
    "  AND inn IN (%s)" % зн, инны)}
s.close()
print("из них гейт назвал «не покупатель»: %d" % len(не_покуп))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
паспорт = defaultdict(set)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; з = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, site, sources_json FROM site_facts "
                       " WHERE inn IN (%s) AND COALESCE(facts_json,'')<>''" % з, к):
        for д in [дом(r["site"])] + [дом(u) for u in re.findall(
                r"https?://[^\s\"']+", str(r["sources_json"] or ""))[:20]]:
            if д:
                паспорт[str(r["inn"])].add(д)
выр = {}
ob = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True, timeout=60)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; з = ",".join("?" * len(к))
    for r in ob.execute("SELECT inn, revenue_rub FROM obzvon WHERE inn IN (%s)" % з, к):
        try:
            в = float(r[1])
        except Exception:                                       # noqa: BLE001
            continue
        if в > 0:
            выр.setdefault(str(r[0]), в)
ob.close()
нетв = [и for и in инны if и not in выр]
for i in range(0, len(нетв), 400):
    к = нетв[i:i + 400]; з = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, revenue_rub FROM companies WHERE inn IN (%s)" % з, к):
        try:
            в = float(r[1])
        except Exception:                                       # noqa: BLE001
            continue
        if в > 0:
            выр.setdefault(str(r[0]), в)

этап = Counter()
годные = defaultdict(list)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; з = ",".join("?" * len(к))
    for r in e.execute(
            "SELECT inn, email, role, person, probe_verdict, mx_ok, source_url "
            "  FROM emails WHERE inn IN (%s)" % з, к):
        инн = str(r["inn"])
        почта = (r["email"] or "").lower().strip()
        if "@" not in почта:
            continue
        д_почты = почта.split("@", 1)[1]
        этап["адресов у кандидатов"] += 1
        if инн in не_покуп:
            этап["гейт: не покупатель"] += 1; continue
        родной = {d.split("@", 1)[1] for d in молч[инн] if "@" in d} - ПОЧТОВИКИ
        if д_почты in ПОЧТОВИКИ or д_почты not in (родной | паспорт[инн]):
            этап["не домен компании"] += 1; continue
        if почта in молч[инн]:
            этап["тот же адрес"] += 1; continue
        if почта in уже:
            этап["уже заведён получателем"] += 1; continue
        if почта in стоп:
            этап["в стоп-листе"] += 1; continue
        if (r["probe_verdict"] or "") in ПРИГОВОР or r["mx_ok"] == 0:
            этап["приговор пробы"] += 1; continue
        if (r["role"] or "").strip() in НЕЛЬЗЯ_РОЛЬ:
            этап["кадры/бухгалтерия"] += 1; continue
        if _ЦИФ.sub("", почта.split("@", 1)[0]) in СЛУЖЕБНЫЕ:
            этап["служебный ящик"] += 1; continue
        # ПРАВИЛО ПАСПОРТА
        пас = паспорт.get(инн) or set()
        д_ист = дом(r["source_url"])
        if not пас:
            этап["паспорта сайта нет"] += 1; continue
        if not (д_почты in пас or (д_ист and (д_ист in пас or д_ист == д_почты))):
            этап["домен почты не из паспорта"] += 1; continue
        этап["ГОДЕН"] += 1
        годные[инн].append((ВЕС.get((r["role"] or "").strip(), 9),
                            0 if r["person"] else 1, почта,
                            (r["role"] or "—"), r["person"] or ""))
e.close()
print("")
print("=== отсев ===")
for к, n in этап.most_common():
    print("   %-30s %7d" % (к, n))
выбор = {и: sorted(v)[0] for и, v in годные.items()}
с_выр = {и: v for и, v in выбор.items() if выр.get(и, 0) >= 30e6}
print("")
print("=== СКОЛЬКО ЕЩЁ ДОСТАНЕМ (1 адрес на компанию) ===")
print("   всего:                       %d" % len(выбор))
print("   из них с выручкой от 30 млн: %d" % len(с_выр))
print("   выручка неизвестна:          %d"
      % sum(1 for и in выбор if и not in выр))
print("")
print("=== роли ===")
for к, n in Counter(v[3] for v in выбор.values()).most_common(8):
    print("   %-24s %5d" % (к, n))
print("")
print("=== примеры ===")
for и, v in list(sorted(выбор.items()))[:6]:
    print("   %-13s %-32s %-18s %s" % (и, v[2][:32], v[3][:18], v[4][:22]))
