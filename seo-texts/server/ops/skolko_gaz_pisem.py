# -*- coding: utf-8 -*-
"""Сколько газовых писем КЦ можно сделать (владелец 11.11). Только чтение. Те же детерминированные фильтры,
что в gaz_obrazcy.py (резерв, реестр «не наш», стоп-лист, адрес, конкуренты кодом, обязательные признаки
отраслей, золото, аэрозоли, вендинг) + мёртвые адреса пробы, писали < 15 дней, был ответ/жалоба/отписка.
Одна компания = одно письмо (ЛПР по имени, если есть, иначе почта компании). Решение модели о
соответствии отрасли здесь НЕ применяется — по образцам проходит ~половина, это отдельная оценка."""
import csv, io, os, re, sqlite3, sys
from collections import Counter, defaultdict
csv.field_size_limit(10 ** 9)
ДРОП = r"C:\seostat\drop\drop-storage"
def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
лпр, комп = читать("CA-ENGER-ZALIVKA.csv"), читать("CA-ENGER-ZALIVKA-kompanii.csv")
САЙТ = {str(р.get("ИНН") or "").strip(): р for р in читать("CA-ENGER-BAZA-kompanii.csv")}
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
стоп = {str(v).strip().lower() for _, v in s.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in s.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
недавно = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days') AND inn IS NOT NULL")}
когда_либо = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND inn IS NOT NULL")}
ответ = {str(r[0]) for r in s.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
try:
    sys.path.insert(0, r"C:\sender\sender"); sys.path.insert(0, r"C:\sender")
    from sender.ne_nash import build_ne_nash
    не_наш = {str(x) for x in (build_ne_nash().набор(None) or [])}
except Exception:  # noqa: BLE001
    не_наш = set()
ПЛОХ = re.compile(r"(?i)@(site|example|test)\.(ru|com)$|\.(ua|by|kz|uz|am|ge|az|md)$")
def адрес_годен(em):
    em = (em or "").strip().lower()
    return bool(re.match(r"^[\w.+-]+@[\w.-]+\.(ru|рф|su|com|org|net|pro|biz|info)$", em)) and not ПЛОХ.search(em)
КОНК = re.compile(r"(?i)адсорбцион|получени\w* (газ|азот|кислород)|генератор\w* (азот|кислород|газ)|(азотн|кислородн|газоразделит)\w* (станц|установ|оборуд)|воздухоразделит|мембранн\w* (установ|блок)|(производ|выпуск)\w* компрессор|компрессорн\w* (станц|оборуд|установ)|винтов\w* компрессор|осушител\w* (воздух|газ)")
ОБЯЗ = [(r"(?i)фруктохран|ргс", r"(?i)фрукт|яблок|груш|сад|плод|ягод"),
        (r"(?i)сухое молоко", r"(?i)сух\w* молок|сухих? смес|молочн\w* смес|казеин|детск\w* (питан|смес)"),
        (r"(?i)озонирован", r"(?i)вод|озон"),
        (r"(?i)аэрозол", r"(?i)аэрозол|спрей|баллон|пропеллент|airless|дезодорант|лак для волос|пена")]
ТЕХ = re.compile(r"(?i)техн\w* директор|главн\w* (инженер|технолог|энергетик|механик)|производств|технолог|энергетик|механик|начальник цеха")
def причина(р):
    inn = re.sub(r"\D", "", str(р.get("ИНН") or "")); em = (р.get("Почта") or "").strip().lower()
    отр = (р.get("Отрасль основная") or р.get("Отрасль") or "")
    с = САЙТ.get(inn, {})
    тут = " ".join([р.get("Продукция") or "", с.get("Продукция") or "", с.get("Оборудование, линии") or "", р.get("Компания") or ""])
    if "резерв" in (р.get("Статус отрасли") or "").lower(): return "резерв"
    if inn in не_наш or inn in стоп or em in стоп: return "реестр/стоп-лист"
    if not адрес_годен(em): return "плохой адрес"
    if em in мёртв: return "мёртвый адрес (проба)"
    if КОНК.search(" ".join([р.get("Продукция") or "", с.get("Продукция") or "", с.get("Газы (паспорт)") or ""])): return "конкурент (код)"
    for о, к in ОБЯЗ:
        if re.search(о, отр) and not re.search(к, тут): return "нет признаков отрасли"
    if re.search(r"(?i)золот", отр) and (re.search(r"(?i)россыпн", тут) or not re.search(r"(?i)руд|фабрик|зиф|цианир|обогат|кучн|выщелач|cil|cip", тут)): return "золото без ЗИФ"
    if re.search(r"(?i)кофе", отр) and re.search(r"(?i)вендинг|автомат\w*\s+(unicum|necta|saeco|jettino)|парк оборудования|кофемашин|кофейн", тут): return "вендинг"
    if not (р.get("Продукция") or "").strip(): return "нет продукции"
    if inn in ответ: return "уже был ответ/отписка"
    if inn in недавно: return "писали < 15 дней"
    return ""
итог = defaultdict(lambda: Counter()); отсев = Counter(); готово = {}
for р in лпр:   # по имени: одна лучшая строка на ИНН
    inn = re.sub(r"\D", "", str(р.get("ИНН") or ""))
    if ";" in (р.get("ФИО") or ""): continue
    п = причина(р)
    if п: отсев[п] += 1; continue
    if inn not in готово or (ТЕХ.search(р.get("Должность") or "") and not ТЕХ.search(готово[inn][1].get("Должность") or "")):
        готово[inn] = ("имя", р)
for р in комп:
    inn = re.sub(r"\D", "", str(р.get("ИНН") or ""))
    if inn in готово: continue
    п = причина(р)
    if п: отсев[п] += 1; continue
    готово[inn] = ("без", р)
for inn, (вид, р) in готово.items():
    отр = (р.get("Отрасль основная") or р.get("Отрасль") or "")[:55]
    итог[отр][вид] += 1
    if inn in когда_либо: итог[отр]["писали_раньше"] += 1
print("ОТСЕВ (строк):", dict(отсев.most_common()))
print("%-55s %6s %6s %6s %8s" % ("отрасль", "имя", "без", "всего", "писали>15д"))
вс = Counter()
for отр, c in sorted(итог.items(), key=lambda x: -(x[1]["имя"] + x[1]["без"])):
    print("%-55s %6d %6d %6d %8d" % (отр, c["имя"], c["без"], c["имя"] + c["без"], c["писали_раньше"]))
    вс.update(c)
print("%-55s %6d %6d %6d %8d" % ("ИТОГО компаний", вс["имя"], вс["без"], вс["имя"] + вс["без"], вс["писали_раньше"]))
