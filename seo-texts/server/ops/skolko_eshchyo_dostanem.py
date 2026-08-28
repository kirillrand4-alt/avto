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
# ШКАЛА РОЛЕЙ. Продажи стояли вторыми после снабжения — ошибка: отдел
# продаж ничего не покупает, он продаёт. Владелец 28.08 показал ответ
# территориального представителя по продажам: «я не занимаюсь вопросами
# производства, направляйте в соответствующие службы». Директор и даже
# общий ящик перекинут вопрос о закупке скорее, чем продажник, поэтому
# продажи опущены в самый низ.
ВЕС = {"снабжение/закупки": 0,
       "нач.производства": 1, "нач.цеха": 1, "гл.инженер": 1,
       "гл.конструктор": 2, "инженер (не главный)": 2,
       "техконтакт": 3, "директор": 4,
       "общий": 5, "приёмная": 6, "свой": 7,
       "продажи": 8}
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
# ИСКЛЮЧАЕМ ТОЛЬКО ТЕХ, КОМУ РЕАЛЬНО ПИСАЛИ. Раньше здесь стоял список ВСЕХ
# заведённых получателей, и адрес выпадал по факту существования строки —
# даже если письма по ней ни разу не уходило. Так у «Инкаба» выпала
# m.gorbunova@ (снабжение, вердикт «есть»): строка была заведена инжектом
# новостей под другим ИНН группы, письмо по ней осталось skipped, а лучший
# контакт компании мы потеряли и написали в продажи.
уже = {(r[0] or "").lower() for r in s.execute(
    "SELECT LOWER(rc.email) FROM messages m "
    "  JOIN recipients rc ON rc.id = m.recipient_id "
    " WHERE m.status = 'sent' AND rc.email IS NOT NULL")}
# плюс те, кому письмо уже стоит в очереди: иначе поставим второе
уже |= {(r[0] or "").lower() for r in s.execute(
    "SELECT LOWER(rc.email) FROM messages m "
    "  JOIN recipients rc ON rc.id = m.recipient_id "
    " WHERE m.status IN ('scheduled','sending','pending_review') "
    "   AND rc.email IS NOT NULL")}
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

# АДРЕСА БЕРЁМ ПО ДОМЕНУ КОМПАНИИ, А НЕ ТОЛЬКО ПО СТРОКЕ ИНН. Один ящик
# живёт в обогащении под несколькими ИНН группы, и роли у копий расходятся:
# 13595 адресов (6.3%) числятся под двумя и более юрлицами, 3427 (1.6%) с
# разными ролями. У «Инкаба» под нужным ИНН нашлось всего два адреса, а на
# домене их двенадцать. Домен, который делят ДВЕ наши компании-кандидата,
# не расширяем: там непонятно, кому засчитывать адрес.
_дом_компании = {}
for _инн in инны:
    for _a in молч[_инн]:
        if "@" in _a:
            _d = _a.split("@", 1)[1]
            if _d and _d not in ПОЧТОВИКИ:
                _дом_компании.setdefault(_d, set()).add(_инн)
_свой_домен = {и: д for д, набор in _дом_компании.items()
               if len(набор) == 1 for и in набор}
_по_домену = {д: и for и, д in _свой_домен.items()}
print("доменов, расширяемых на всю компанию: %d" % len(_по_домену))

этап = Counter()
годные = defaultdict(list)
_видели = set()
_домены = sorted(_по_домену)
for i in range(0, len(_домены), 200):
    к = _домены[i:i + 200]; з = ",".join("?" * len(к))
    for r in e.execute(
            "SELECT inn, email, role, person, probe_verdict, mx_ok, source_url "
            "  FROM emails "
            " WHERE substr(email, instr(email,'@') + 1) IN (%s)" % з, к):
        _почта = (r["email"] or "").lower().strip()
        if "@" not in _почта:
            continue
        _хозяин = _по_домену.get(_почта.split("@", 1)[1])
        if not _хозяин or (_хозяин, _почта) in _видели:
            continue
        _видели.add((_хозяин, _почта))
        инн = _хозяин
        почта = _почта
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
