# -*- coding: utf-8 -*-
"""Анализ файла контактов сделок Meyer (владелец 12.11, drop: meyer-kontakty-sdelok.csv, в git НЕ кладём):
кому можно писать письма «провалена сделка больше года назад, больше сделок/привлечений не было».
ИНН в файле нет — берём: DEAL_ID → ИНН (sdelki-napr-1410), почта → ИНН (enrich.emails, sender.recipients),
название компании → ИНН (по тем же сделкам). Даты и прочие сделки компании — sdelki-vse-1410 (ИНН → все сделки).
Результат по компаниям — _ops/meyer-provaly.jsonl (+ сводка). Контакты в вывод не печатаем.
    meyer_provaly_analiz.py [--tolko-prodazha]"""
import csv, io, json, os, re, sqlite3
from collections import Counter, defaultdict
from datetime import date
Д = r"C:\seostat\drop\drop-storage"; ОПС = r"C:\sender\_ops"
ГОД_НАЗАД = "2025-11-12"
import sys
ТОЛЬКО_ПРОДАЖА = "--tolko-prodazha" in sys.argv   # владелец 12.11: сначала «только продажа», затем «привлечение тоже берём»
def норм(к):
    к = (к or "").lower().replace("ё", "е")
    к = re.sub(r"(?i)\b(ооо|оао|зао|пао|ао|ип|кфх|сппк|спк|ск|тд|гк|нпо|нпп|фгуп|муп|гуп|ооо\.|llc|ltd)\b", " ", к)
    return re.sub(r"[^a-zа-я0-9]+", "", к)
# --- файл
ряды = list(csv.DictReader(io.open(os.path.join(Д, "meyer-kontakty-sdelok.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";"))
сделки = defaultdict(lambda: {"emails": set(), "fio": set()})
for р in ряды:
    с = сделки[р["DEAL_ID"]]
    for k in ("СТАТУС", "ВОРОНКА", "СТАДИЯ", "ПРИЧИНА_ПРОВАЛА", "КОМПАНИЯ", "COMPANY_ID", "НАЗВАНИЕ_СДЕЛКИ"):
        if р.get(k) and not с.get(k): с[k] = р[k].strip()
    if р.get("EMAIL"): с["emails"].add(р["EMAIL"].strip().lower())
    if р.get("ФИО"): с["fio"].add(р["ФИО"].strip())
print("строк %d, сделок %d" % (len(ряды), len(сделки)))
print("статусы сделок:", Counter(с.get("СТАТУС") for с in сделки.values()))
# --- источники ИНН
napr = json.load(io.open(os.path.join(Д, "sdelki-napr-1410.json"), encoding="utf-8"))
ид_инн, имя_инн = {}, defaultdict(set)
for инн, по in napr.items():
    for напр, сп in по.items():
        for x in сп or []:
            ид_инн[str(x.get("id"))] = инн
            if x.get("k"): имя_инн[норм(x["k"])].add(инн)
почта_инн = {}
try:
    cx = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True)
    for em, инн in cx.execute("SELECT lower(email), inn FROM emails WHERE COALESCE(inn,'')<>''"): почта_инн.setdefault(em, инн)
except Exception as ex: print("enrich:", ex)
try:
    cs = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
    for em, инн in cs.execute("SELECT lower(email), inn FROM recipients WHERE COALESCE(inn,'')<>''"): почта_инн.setdefault(em, инн)
except Exception as ex: print("recipients:", ex)
кид_инн = defaultdict(Counter)
csv.field_size_limit(10 ** 9)
for р in csv.DictReader(io.open(os.path.join(Д, "kc-sc-sdelki-0910.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";"):
    if (р.get("INN") or "").strip() and р.get("COMPANY_ID"): кид_инн[р["COMPANY_ID"].strip()][р["INN"].strip()] += 1
    if (р.get("INN") or "").strip() and р.get("DEAL_ID"): ид_инн.setdefault(р["DEAL_ID"].strip(), р["INN"].strip())
print("компания Битрикса → ИНН (kc-sc-sdelki-0910):", len(кид_инн))
ид_дата = []
for р in csv.DictReader(io.open(os.path.join(Д, "kc-sc-sdelki-0910.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";"):
    try: ид_дата.append((int(р["DEAL_ID"]), str(р.get("DATE_CREATE") or "")[:10]))
    except (ValueError, TypeError): pass
ид_дата.sort()
import bisect
_ключи = [x[0] for x in ид_дата]
def дата_по_id(did):
    try: i = bisect.bisect_right(_ключи, int(did)) - 1
    except ValueError: return ""
    return ид_дата[i][1] if i >= 0 else ""
print("ID→дата: опорных сделок", len(ид_дата), "| пример:", дата_по_id(125094), дата_по_id(155855))
print("справочники: сделка→ИНН %d, имя→ИНН %d, почта→ИНН %d" % (len(ид_инн), len(имя_инн), len(почта_инн)))
# --- сопоставление сделок → ИНН
путь = Counter()
for did, с in сделки.items():
    инн, как = ид_инн.get(did), "сделка"
    if not инн and с.get("COMPANY_ID") in кид_инн:
        инн, как = кид_инн[с["COMPANY_ID"]].most_common(1)[0][0], "компания Битрикса"
    if not инн:
        вар = Counter(почта_инн[e] for e in с["emails"] if e in почта_инн)
        if вар: инн, как = вар.most_common(1)[0][0], "почта"
    if not инн:
        к = имя_инн.get(норм(с.get("КОМПАНИЯ")))
        if к and len(к) == 1: инн, как = next(iter(к)), "название"
    с["inn"] = инн; путь[как if инн else "не найден"] += 1
print("сделки → ИНН:", dict(путь))
# доклеиваем ИНН по COMPANY_ID внутри файла (у одной компании Битрикса один ИНН)
комп_инн = defaultdict(Counter)
for с in сделки.values():
    if с.get("inn") and с.get("COMPANY_ID"): комп_инн[с["COMPANY_ID"]][с["inn"]] += 1
доп = 0
for с in сделки.values():
    if not с.get("inn") and с.get("COMPANY_ID") in комп_инн: с["inn"] = комп_инн[с["COMPANY_ID"]].most_common(1)[0][0]; доп += 1
print("доклеено по COMPANY_ID:", доп)
# --- по компаниям
vse = json.load(io.open(os.path.join(Д, "sdelki-vse-1410.json"), encoding="utf-8"))
комп = defaultdict(lambda: {"sdelki": [], "emails": set()})
for did, с in сделки.items():
    ключ = с.get("inn") or ("cid:" + с["COMPANY_ID"] if с.get("COMPANY_ID") else "deal:" + did)
    комп[ключ]["sdelki"].append(did); комп[ключ]["emails"] |= с["emails"]
итог = Counter(); причины = Counter(); вых = []
for ключ, к in комп.items():
    сд = [сделки[d] for d in к["sdelki"]]
    ст = Counter(с.get("СТАТУС") for с in сд)
    инн = ключ if not ключ.startswith(("cid:", "deal:")) else ""
    все = vse.get(инн, []) if инн else []
    meyer = [x for x in все if x[0] == "meyer"]
    послед_свод = max([str(x[3] or x[2] or "") for x in meyer] or [""])
    послед_ид = max([дата_по_id(d) for d in к["sdelki"]] or [""])
    послед = max(послед_свод, послед_ид)
    if ст.get("В работе") or ст.get("Успешна") or any(x[1] in ("В работе", "Успешна") for x in meyer):
        кат = "есть живая/успешная сделка Meyer"
    elif not ст.get("Провалена"):
        кат = "нет проваленных"
    elif ТОЛЬКО_ПРОДАЖА and not any(с.get("СТАТУС") == "Провалена" and с.get("ВОРОНКА") == "MEYER-Продажа" for с in сд):
        кат = "провалы только в Привлечении/СЦ — не трогаем"
    elif послед >= ГОД_НАЗАД or (not послед_свод and послед_ид >= "2025-09-12"):
        кат = "провал моложе года"
    elif not послед:
        кат = "провал, дату не определить"
    elif not инн:
        кат = "ПОДХОДИТ (ИНН не найден, дата по номеру сделки)"
    elif not послед_свод:
        кат = "ПОДХОДИТ (дата по номеру сделки)"
    elif False:
        кат = "провал моложе года"
    else:
        кат = "ПОДХОДИТ: провал > года, других сделок Meyer нет"
    if кат.startswith("ПОДХОДИТ"): кат_общ = "ПОДХОДИТ"
    итог[кат] += 1
    if кат.startswith("ПОДХОДИТ"):
        for с in сд:
            if с.get("ПРИЧИНА_ПРОВАЛА"): причины[с["ПРИЧИНА_ПРОВАЛА"][:70]] += 1
    вых.append({"kluch": ключ, "inn": инн, "kat": кат, "sdelki": к["sdelki"], "n_email": len(к["emails"]), "posled_meyer": послед,
                "drugie_napr": sorted({x[0] for x in все if x[0] != "meyer"}),
                "prichiny": [сделки[d].get("ПРИЧИНА_ПРОВАЛА", "")[:200] for d in к["sdelki"] if сделки[d].get("ПРИЧИНА_ПРОВАЛА")],
                "voronki": sorted({сделки[d].get("ВОРОНКА", "") for d in к["sdelki"]}), "emails": sorted(к["emails"])})
with io.open(os.path.join(ОПС, "meyer-provaly.jsonl"), "w", encoding="utf-8") as ф:
    for x in вых: ф.write(json.dumps(x, ensure_ascii=False) + "\n")
    ф.flush(); os.fsync(ф.fileno())
print("компаний:", len(комп)); [print("  %-55s %d" % (k, v)) for k, v in итог.most_common()]
под = [x for x in вых if x["kat"].startswith("ПОДХОДИТ")]
print("ПОДХОДИТ всего:", len(под))
print("подходящие: с почтой %d, адресов всего %d, с делами КЦ/СЦ %d" % (sum(1 for x in под if x["n_email"]), sum(x["n_email"] for x in под), sum(1 for x in под if x["drugie_napr"])))
print("год последней сделки Meyer у подходящих:", sorted(Counter(x["posled_meyer"][:4] for x in под).items()))
# --- стопы у подходящих: стоп-лист, писали ли Meyer/КЦ недавно, ответы
sup = set()
try:
    for v in cs.execute("SELECT lower(value) FROM suppression"): sup.add(v[0])
except Exception as ex: print("suppression:", ex)
писали = defaultdict(list)
for инн, mb, t in cs.execute("SELECT r.inn, m.mailbox_id, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' AND COALESCE(r.inn,'')<>''"):
    писали[инн].append((str(t)[:10], mb))
писали_почта = {}
for em, mb, t in cs.execute("SELECT lower(r.email), m.mailbox_id, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'"):
    if str(t)[:10] > писали_почта.get(em, ("",))[0]: писали_почта[em] = (str(t)[:10], mb)
ст = Counter()
for x in под:
    стоп = x["inn"] in sup or any(e in sup or e.split("@")[-1] in sup for e in x["emails"])
    п = sorted(писали.get(x["inn"], []))
    x["stop"] = стоп; x["pisali"] = п[-1][0] if п else ""
    if not x["inn"]:
        п = sorted(писали_почта.get(e, ("", ""))[0:2] for e in x["emails"] if e in писали_почта)
        п = [y for y in п if y[0]]
        x["pisali"] = п[-1][0] if п else ""
    напр = ("Meyer" if п and re.search(r"sort|rentgen|inspection|optic", п[-1][1]) else "КЦ") if п else ""
    x["pisali_napr"] = напр
    ст["в стоп-листе" if стоп else ("писали за 60 дней (%s)" % напр if п and п[-1][0] >= "2026-09-13" else ("писали раньше" if п else "не писали"))] += 1
print("подходящие — стопы/история писем:", dict(ст))
with io.open(os.path.join(ОПС, "meyer-provaly.jsonl"), "w", encoding="utf-8") as ф:
    for x in вых: ф.write(json.dumps(x, ensure_ascii=False, default=list) + "\n")
    ф.flush(); os.fsync(ф.fileno())
print("воронки проваленных сделок у подходящих:", Counter(v for x in под for v in x["voronki"]))
print("с комментарием менеджера:", sum(1 for x in под if any("Комментарий:" in p for p in x["prichiny"])))
print("топ-50 причин провала у подходящих:"); [print("  %4d  %s" % (v, k)) for k, v in причины.most_common(50)]
