# -*- coding: utf-8 -*-
"""Механическая сверка писем партии вторых адресов: что могло сломаться при
копировании — обращение не к тому, следы прошлого адресата, битая метка."""
import io
import json
import re
import sqlite3
from collections import Counter, defaultdict

партия = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = (str(d["inn"]), d["email"].lower())
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партия))
строки = c.execute(
    "SELECT cr.id, cr.email, cr.subject, cr.body, cr.inn, cr.panel_json, "
    "       r.company_name, r.contact_name "
    "  FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.id IN (%s) AND cr.status='pending'" % зн, list(партия)).fetchall()
c.close()
print("писем в очереди: %d" % len(строки))

_ГРИТ = re.compile(r"(?i)^\s*(добрый день|здравствуйте|доброе утро|добрый вечер)"
                   r"\s*,\s*([^!\n]{2,60})!")
_ОТЧ = re.compile(r"(?i)(вич|вна|ична|инична)$")
ПОДОЗР = {
    "писали ранее": re.compile(r"(?i)(писал[аи]?\s+вам|ранее\s+обраща|повторно|"
                               r"моё\s+прошлое\s+письмо|напоминаю)"),
    "два приветствия": re.compile(r"(?i)(добрый день|здравствуйте)[^\n]*\n+\s*"
                                  r"(добрый день|здравствуйте)"),
    "осталась метка адреса": re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I),
}
сч = Counter()
беды = defaultdict(list)
for r in строки:
    тело = str(r["body"] or "")
    тема = str(r["subject"] or "")
    контакт = str(r["contact_name"] or "")
    п = {}
    try:
        п = (json.loads(r["panel_json"] or "{}") or {}).get("vtoroy_adres") or {}
    except Exception:                                            # noqa: BLE001
        pass
    первый = str(п.get("pervyy_adres") or "")

    if len(тело) < 300:
        сч["тело короче 300 знаков"] += 1
        беды["короткое"].append((r["id"], r["email"], str(len(тело))))
    if "ИМЯ_ОТПРАВИТЕЛЯ" in тело and not re.search(r"(?i)меня зовут", тело):
        сч["метка без «меня зовут»"] += 1
        беды["метка"].append((r["id"], r["email"], ""))
    if not re.search(r"(?i)с уважением", тело):
        сч["нет «с уважением» в конце"] += 1
        беды["подпись"].append((r["id"], r["email"], тело[-40:].replace("\n", "|")))
    # обращение по имени: сверяем с человеком, привязанным к НОВОМУ адресу
    м = _ГРИТ.match(тело)
    if м:
        обращение = м.group(2).strip()
        ток = [т.lower() for т in re.split(r"\s+", контакт) if т]
        нужно = [т.lower() for т in re.split(r"\s+", обращение) if т]
        if not контакт:
            сч["обращение по имени, а контакта нет"] += 1
            беды["имя без контакта"].append((r["id"], r["email"], обращение))
        elif not all(т in ток for т in нужно):
            сч["обращение НЕ совпадает с контактом"] += 1
            беды["чужое имя"].append((r["id"], r["email"],
                                      "%s <> %s" % (обращение, контакт)))
        else:
            сч["обращение по имени — сходится"] += 1
    else:
        сч["обращение обезличенное"] += 1
    # следы прошлого адресата
    if первый and первый.split("@")[0] and первый.split("@")[0] in тело:
        сч["в теле локальная часть первого адреса"] += 1
        беды["след адреса"].append((r["id"], r["email"], первый))
    for имя, рег in ПОДОЗР.items():
        if имя == "осталась метка адреса":
            найдено = [a for a in рег.findall(тело)
                       if not a.lower().endswith("prokompressor.ru")]
            if найдено:
                сч["в теле чей-то email"] += 1
                беды["email в теле"].append((r["id"], r["email"], найдено[0]))
            continue
        if рег.search(тело):
            сч[имя] += 1
            беды[имя].append((r["id"], r["email"], рег.search(тело).group(0)[:40]))
    # название компании в теме против карточки
    в_кав = re.findall(r"«([^»]{2,40})»", тема)
    if в_кав and r["company_name"]:
        н = lambda x: re.sub(r"[^а-яёa-z0-9]", "", str(x).lower())    # noqa: E731
        if not any(н(к)[:6] and н(к)[:6] in н(r["company_name"]) for к in в_кав):
            сч["название в теме не из карточки"] += 1
            беды["тема"].append((r["id"], в_кав[0], str(r["company_name"])[:34]))

print("")
for к, n in сч.most_common():
    print("   %-42s %5d" % (к, n))
for имя, сп in беды.items():
    if not сп:
        continue
    print("")
    print("=== %s (%d) ===" % (имя, len(сп)))
    for a, b, cc in сп[:4]:
        print("   rev %-6s %-30s %s" % (a, str(b)[:30], str(cc)[:52]))
