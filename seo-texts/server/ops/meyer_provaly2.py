# -*- coding: utf-8 -*-
"""Провалы Meyer, версия 2 (владелец 12.11 прислал полную выгрузку сделок Meyer: drop meyer-sdelki-vse.csv —
DEAL_ID, воронка, статус, DATE_CREATE, CLOSEDATE, COMPANY_ID, INN). Почты — из meyer-kontakty-sdelok.csv
(по DEAL_ID и COMPANY_ID). Файлы с контактами в git НЕ кладём.
Правило: у компании есть проваленная сделка Meyer; нет сделок Meyer в работе/успешных; последняя активность по
сделкам Meyer (создание/закрытие) старше года. Привлечение тоже берём (владелец 12.11).
Итог по компаниям — _ops/meyer-provaly2.jsonl.   meyer_provaly2.py"""
import csv, io, json, os, re, sqlite3
from collections import Counter, defaultdict
Д = r"C:\seostat\drop\drop-storage"; ОПС = r"C:\sender\_ops"; ГОД = "2025-11-12"
csv.field_size_limit(10 ** 9)
чит = lambda имя: list(csv.DictReader(io.open(os.path.join(Д, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
сд = {р["DEAL_ID"].strip(): р for р in чит("meyer-sdelki-vse.csv")}
кид_инн = defaultdict(Counter)
for р in сд.values():
    if р.get("INN", "").strip() and р.get("COMPANY_ID", "").strip(): кид_инн[р["COMPANY_ID"].strip()][р["INN"].strip()] += 1
for р in чит("kc-sc-sdelki-0910.csv"):
    if р.get("INN", "").strip() and р.get("COMPANY_ID", "").strip(): кид_инн[р["COMPANY_ID"].strip()][р["INN"].strip()] += 1
def инн_сделки(р):
    и = (р.get("INN") or "").strip()
    if и: return и, "реквизиты"
    к = (р.get("COMPANY_ID") or "").strip()
    if к in кид_инн: return кид_инн[к].most_common(1)[0][0], "компания Битрикса"
    return "", ""
# контакты
конт = чит("meyer-kontakty-sdelok.csv")
почты_сд, почты_к, ком_сд = defaultdict(set), defaultdict(set), {}
for р in конт:
    e = (р.get("EMAIL") or "").strip().lower()
    if e: почты_сд[р["DEAL_ID"].strip()].add(e)
    if e and (р.get("COMPANY_ID") or "").strip(): почты_к[р["COMPANY_ID"].strip()].add(e)
    п = р.get("ПРИЧИНА_ПРОВАЛА") or ""
    if "Комментарий:" in п: ком_сд[р["DEAL_ID"].strip()] = п.split("Комментарий:", 1)[1].strip()
# группировка по компании
комп = defaultdict(lambda: {"sd": [], "kid": set()}); путь = Counter()
for did, р in сд.items():
    и, как = инн_сделки(р); путь[как or "нет ИНН"] += 1
    ключ = и or ("cid:" + р["COMPANY_ID"].strip() if (р.get("COMPANY_ID") or "").strip() else "deal:" + did)
    комп[ключ]["sd"].append(did)
    if (р.get("COMPANY_ID") or "").strip(): комп[ключ]["kid"].add(р["COMPANY_ID"].strip())
print("сделок Meyer:", len(сд), "| ИНН сделки:", dict(путь), "| компаний:", len(комп))
vse = json.load(io.open(os.path.join(Д, "sdelki-vse-1410.json"), encoding="utf-8"))
cs = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
sup = {v[0] for v in cs.execute("SELECT lower(value) FROM suppression")}
писали = {}
for em, mb, t in cs.execute("SELECT lower(r.email), m.mailbox_id, substr(m.sent_at,1,10) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'"):
    if t > писали.get(em, ("",))[0]: писали[em] = (t, mb)
кат = Counter(); вых = []
for ключ, к in комп.items():
    рр = [сд[d] for d in к["sd"]]
    ст = Counter(р["СТАТУС"] for р in рр)
    посл = max(max(str(р.get("DATE_CREATE") or "")[:10], str(р.get("CLOSEDATE") or "")[:10]) for р in рр)
    if ст.get("В работе") or ст.get("Успешна"): к_ = "есть сделка Meyer в работе/успешная"
    elif not ст.get("Провалена"): к_ = "нет проваленных"
    elif посл >= ГОД: к_ = "последняя сделка Meyer моложе года"
    else: к_ = "ПОДХОДИТ"
    почты = set().union(*[почты_сд.get(d, set()) for d in к["sd"]], *[почты_к.get(x, set()) for x in к["kid"]])
    if к_ == "ПОДХОДИТ" and not почты: к_ = "подходит, но почты нет в файле контактов"
    кат[к_] += 1
    if к_ != "ПОДХОДИТ": continue
    инн = "" if ключ.startswith(("cid:", "deal:")) else ключ
    стоп = (инн and инн in sup) or any(e in sup or e.split("@")[-1] in sup for e in почты)
    свеж = sorted(e for e in почты if писали.get(e, ("",))[0] >= "2026-09-13")
    вор = Counter(р["ВОРОНКА"] for р in рр if р["СТАТУС"] == "Провалена")
    вых.append({"kluch": ключ, "inn": инн, "sdelki": к["sd"], "emails": sorted(почты), "posled": посл,
                "voronki": dict(вор), "prodazha": bool(вор.get("MEYER-Продажа")), "stop": bool(стоп), "pisali60": свеж,
                "drugie_napr": sorted({x[0] for x in vse.get(инн, []) if x[0] != "meyer"}) if инн else [],
                "aktiv_kc": any(x[0] == "kc" and x[1] == "В работе" for x in vse.get(инн, [])) if инн else False,
                "kommentarii": [ком_сд[d][:400] for d in к["sd"] if d in ком_сд],
                "nazvaniya": [сд[d].get("TITLE", "")[:120] for d in к["sd"]], "kompaniya": next((р.get("КОМПАНИЯ") for р in рр if р.get("КОМПАНИЯ")), "")})
with io.open(os.path.join(ОПС, "meyer-provaly2.jsonl"), "w", encoding="utf-8") as ф:
    for x in вых: ф.write(json.dumps(x, ensure_ascii=False) + "\n")
    ф.flush(); os.fsync(ф.fileno())
print("компании:"); [print("  %-50s %d" % (k, v)) for k, v in кат.most_common()]
print("ПОДХОДЯТ %d, адресов %d" % (len(вых), sum(len(x["emails"]) for x in вых)))
print("  с ИНН %d, без ИНН %d" % (sum(1 for x in вых if x["inn"]), sum(1 for x in вых if not x["inn"])))
print("  есть провал в Продаже %d, только Привлечение/прочее %d" % (sum(x["prodazha"] for x in вых), sum(not x["prodazha"] for x in вых)))
print("  год последней сделки:", sorted(Counter(x["posled"][:4] for x in вых).items()))
print("  в стоп-листе %d | на этот адрес писали за 60 дней %d компаний | активная сделка КЦ %d | есть дела КЦ/СЦ %d" % (
    sum(x["stop"] for x in вых), sum(bool(x["pisali60"]) for x in вых), sum(x["aktiv_kc"] for x in вых), sum(bool(x["drugie_napr"]) for x in вых)))
ж = [x for x in вых if any(len(re.sub(r"\[/?url[^\]]*\]|https?://\S+|\[/?[a-zA-Z]+\]|\s", "", t)) >= 8 for t in x["kommentarii"])]
print("  с живым комментарием %d (в Продаже %d)" % (len(ж), sum(x["prodazha"] for x in ж)))
чист = [x for x in вых if not x["stop"] and not x["pisali60"]]
print("ЧИСТЫХ (без стопа и без письма на тот же адрес за 60 дней): %d компаний, %d адресов; из них Продажа %d" % (len(чист), sum(len(x["emails"]) for x in чист), sum(x["prodazha"] for x in чист)))
