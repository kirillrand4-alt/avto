# -*- coding: utf-8 -*-
"""Пачка писем со сверкой утверждений по САЙТУ КОМПАНИИ. Решает человек.

Владелец: «100 штук посмотри глазами, с проверкой источника, и перекати в
автоотправку если там всё нормально».

Глазами смотреть сто писем можно только так: механику - скрипту, суждение -
себе. Скрипт по каждому письму:
  * достаёт слова-утверждения О КОМПАНИИ (длиной от шести букв, за вычетом
    нашего продуктового словаря - компрессоры, азот, Руспром и прочее: их на
    сайте получателя и быть не должно);
  * открывает сайт компании С СЕРВЕРА и, если надо, внутренние страницы
    услуг/производства - урок письма #2130, где одной главной было мало;
  * говорит, какие слова на сайте НАШЛИСЬ, а какие нет;
  * прогоняет механику: направление письма против карточки, концовка КЦ,
    именное приветствие против ящика, длинное тире, объём, марки, реклама.

Вывод - таблица на письмо. Что с ней делать, решаю я, а не скрипт: он не
ставит вердиктов «годно/негодно».

    python zapusk_svoego_skripta.py ops/sto_pisem_do_istochnika.py 25 0
"""
import gzip
import io
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import (_imennoe_privetstvie,             # noqa: E402
                              _imya_soglasuetsya_s_yashchikom,
                              _prosba_perenapravit, форма_захода)
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 else 25
ДО_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
ПРОПУСК = ДО_ID  # для имени файла
ИМЯ = f"STO-PISEM-{ПРОПУСК}.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
ОТКАЗ = "в дальнейшем вас не отвлекать"
# Наш словарь: этих слов на сайте получателя быть не обязано, сверять их
# бессмысленно.
НАШИ = ('компрессор', 'пневмо', 'воздух', 'азот', 'кислород', 'руспром',
        'фотосепаратор', 'рентген', 'сортировк', 'инспекц', 'оборудован',
        'подскажит', 'актуален', 'актуальн', 'неактуальн', 'признател',
        'отвлекать', 'уважением', 'напишите', 'обращаюсь', 'занимаюсь',
        'направлен', 'производств', 'предприят', 'подобрать', 'подбор',
        'пневмоаудит', 'вопрос', 'задач', 'участк', 'сейчас', 'который',
        'котор', 'работает', 'работа', 'станци', 'парка', 'парк')
МАРКИ = ('atlas copco', 'kaeser', 'ремеза', 'enger', 'remeza', 'abac',
         'fini', 'ceccato', 'ingersoll', 'boge', 'alup', 'далгакиран')
РЕКЛАМА = (r'(?i)\bпредлага', r'(?i)\bскидк', r'(?i)\bлучш(ая|ий|ие)\b',
           r'(?i)\bуникальн', r'(?i)\bбесплатн', r'(?i)\bгарантируем\b')

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def взять(url, таймаут=40):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=таймаут) as o:
            b = o.read(3_000_000)
            if o.headers.get("Content-Encoding") == "gzip":
                b = gzip.decompress(b)
            return b.decode("utf-8", "replace")
    except Exception:                                           # noqa: BLE001
        return ""


def текст_сайта(база):
    """Главная плюс до шести внутренних страниц про услуги и производство."""
    сырое = взять(база)
    if not сырое:
        for схема in ("https://", "http://"):
            if not база.startswith(схема):
                сырое = взять(схема + база.split("://")[-1])
                if сырое:
                    база = схема + база.split("://")[-1]
                    break
    if not сырое:
        return "", 0
    дом = re.match(r"https?://[^/]+", база)
    дом = дом.group(0) if дом else база
    ссылки = set()
    for m in re.finditer(r'href="([^"]+)"', сырое):
        u = m.group(1)
        if u.startswith("/"):
            u = дом + u
        if u.startswith(дом) and re.search(
                r"(?i)(uslug|servic|produkc|product|proizvod|about|company|"
                r"katalog|catalog|tehn|oborud)", u):
            ссылки.add(u.split("#")[0])
    куски = [сырое]
    for u in sorted(ссылки)[:6]:
        куски.append(взять(u, 25))
    т = " ".join(куски)
    т = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", т)
    т = re.sub(r"<[^>]+>", " ", т)
    return re.sub(r"\s+", " ", т), len(ссылки)


def разбор(row):
    rid, camp, email, inn, subj, body, pj, статус, recip = row
    body = str(body or "")
    try:
        panel = json.loads(pj or "{}")
    except Exception:                                           # noqa: BLE001
        panel = {}
    comp = panel.get("company") if isinstance(panel.get("company"), dict) else {}
    full = panel.get("company_full") if isinstance(
        panel.get("company_full"), dict) else {}
    enr = (full.get("enrich") or {}) if isinstance(full.get("enrich"), dict) else {}
    ec = (enr.get("company") or {}) if isinstance(enr.get("company"), dict) else {}
    cont = panel.get("contact") if isinstance(panel.get("contact"), dict) else {}

    сайт = str(ec.get("site") or ec.get("domain") or comp.get("site") or "")
    сайт = сайт.strip()
    if сайт and not сайт.startswith("http"):
        сайт = "http://" + сайт
    текст, стр = (текст_сайта(сайт) if сайт else ("", 0))

    слова = set()
    for w in re.findall(r"[А-Яа-яЁё]{6,}", body):
        wl = w.lower()
        if any(wl.startswith(н) or н in wl for н in НАШИ):
            continue
        слова.add(wl)
    нашлись, нет = [], []
    for w in sorted(слова):
        корень = w[:-2] if len(w) > 7 else w
        (нашлись if re.search(re.escape(корень), текст, re.I) else нет).append(w)

    беды = []
    напр = str(panel.get("letter_division") or "")
    карт = str(comp.get("division") or "")
    if напр and карт and карт not in ("kc+meyer", "meyer+kc") and напр != карт:
        беды.append(f"направление письма {напр} против карточки {карт}")
    if напр == "kc" and ОТКАЗ not in body:
        беды.append("нет концовки КЦ")
    if "—" in body or "–" in body:
        беды.append("длинное тире")
    n = len([x for x in re.split(r"\s+", body) if x.strip()])
    if not (45 <= n <= 140):
        беды.append(f"объём {n}")
    for м in МАРКИ:
        if м in body.lower():
            беды.append(f"марка {м}")
    for rx in РЕКЛАМА:
        m = re.search(rx, body)
        if m:
            беды.append(f"реклама «{m.group(0)}»")
    имя = str(cont.get("person") or "")
    if _imennoe_privetstvie(body):
        if not имя:
            беды.append("здоровается по имени, а имени в карточке нет")
        elif not _imya_soglasuetsya_s_yashchikom(имя, email):
            беды.append(f"имя «{имя}» ящиком не подтверждено")
    elif not _prosba_perenapravit(body) and not имя:
        pass
    return {
        "id": rid, "email": email, "фирма": (comp.get("name") or "")[:44],
        "напр": напр, "сайт": сайт, "страниц": стр,
        "знаков_сайта": len(текст), "нашлись": нашлись, "нет": нет,
        "беды": беды, "заход": форма_захода(body), "слов": n,
        "статус": статус, "тема": subj or "", "тело": body,
        "оквэд": str(comp.get("okved") or ""),
        "деятельность": str(ec.get("activity") or ""),
        "контакт": имя, "роль": str(cont.get("role") or "")}


with store._lock:
    строки = store._conn.execute(
        "SELECT id, campaign_id, email, inn, subject, body, panel_json, "
        "status, recipient_id FROM confirm_reviews WHERE campaign_id=10 "
        "AND status='pending' AND id < ? ORDER BY id DESC LIMIT ?",
        (ДО_ID, СКОЛЬКО)).fetchall()

with ThreadPoolExecutor(max_workers=8) as pool:
    итоги = list(pool.map(разбор, строки))

С = [f"# Письма со сверкой по сайту компании ({len(итоги)} шт, пропуск {ПРОПУСК})",
     "", "Читать глазами: под каждым письмом - карточка, что подтвердил сайт",
     "и что на сайте НЕ нашлось.", ""]
for и in итоги:
    С.append(f"## #{и['id']} · {и['фирма']} · направление {и['напр']}")
    С.append("")
    С.append(f"ящик {и['email']} · роль {и['роль'] or 'не указана'} · "
             f"контакт {и['контакт'] or 'нет имени'}")
    С.append(f"ОКВЭД {и['оквэд']} · {и['деятельность'][:110] or 'деятельности нет'}")
    С.append(f"сайт: {и['сайт'] or 'НЕТ В КАРТОЧКЕ'} "
             f"({'открыт, ' + str(и['знаков_сайта']) + ' знаков, +' + str(и['страниц']) + ' стр' if и['знаков_сайта'] else 'НЕ ОТКРЫЛСЯ'})")
    С.append("")
    С.append(f"**{и['тема']}**")
    С.append("")
    С.append("```")
    for s in str(и["тело"]).splitlines():
        С.append(s)
    С.append("```")
    С.append("")
    С.append(f"- механика: {'; '.join(и['беды']) or 'чисто'} · объём {и['слов']} · заход «{и['заход']}»")
    С.append(f"- сайт подтвердил ({len(и['нашлись'])}): {', '.join(и['нашлись'][:18]) or '-'}")
    С.append(f"- на сайте НЕ нашлось ({len(и['нет'])}): {', '.join(и['нет'][:18]) or '-'}")
    С.append("")
текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                         # noqa: BLE001
    print("на дроп не уехал:", str(ex)[:160])

for и in итоги:
    print(f"#{и['id']} {и['фирма'][:34]:<36} сайт:{'+' if и['знаков_сайта'] else '-'} "
          f"подтв {len(и['нашлись']):>2} нет {len(и['нет']):>2} | "
          f"{'; '.join(и['беды'])[:70] or 'чисто'}")
