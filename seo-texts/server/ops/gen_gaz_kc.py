# -*- coding: utf-8 -*-
"""Газовые письма КЦ — боевая генерация (владелец 11.11: «после пробы запускай генерацию всех писем»).

Канон и проверки — gaz_kanon.py (тот же, что у образцов). Источники — дроп: CA-ENGER-ZALIVKA.csv (ЛПР),
CA-ENGER-ZALIVKA-kompanii.csv (почта компании), CA-ENGER-BAZA-kontakty.csv (все контакты — запас лесенки),
CA-ENGER-BAZA-kompanii.csv (поля сайта).

ПРАВИЛА ВЛАДЕЛЬЦА 11.11:
  * не пишем на АДРЕС, на который КЦ писал < 15 дней (Meyer не мешает, КЦ на другой адрес — не мешает);
  * компания в стопе — не пишем совсем: был ответ/жалоба/отписка (любое направление), конкурент (реестр
    «не наш», стоп-лист, код, модель), активная сделка КЦ (sdelki_napr);
  * резерв не берём; отсев кодом (gaz_kanon.отсев_кодом);
  * лесенка адресов: ЛПР тех-роли > руководитель > закупки > прочие с именем > общие > продажи;
    проба сверху вниз, пока не найдётся НЕ мёртвый (мёртв = «нет ящика»/«нет MX»; «принимает всё» и
    «неясно» — не приговор). Проба — на основном сервере (VPS не работает), темп как smtp_proba_vtoroe
    (крупные публичные — раз в 20 с на домен), вердикт сразу в три базы.
  * карточки — в «Подтвердить отправку» (в автоотправку только по команде владельца).

ЭТАПЫ (каждый резюмируем по своему журналу в C:\\sender\\_ops, fsync):
  1. суд модели   gaz-kc-sud.jsonl      — ok/конкурент/почему/фраза по каждой компании;
  2. лесенка      gaz-kc-lesenka.jsonl  — выбранный адрес (или «все мертвы»);
  3. карточки     gaz-kc-kartochki.jsonl — кампания «КЦ газ 11.11», карточка pending.

    gen_gaz_kc.py                  — сухой подсчёт (без модели, пробы и карточек)
    gen_gaz_kc.py --zapusk [--model=claude-opus-5-5] [--potokov=6]   — всё фоном
    ход: C:\\sender\\_ops\\gaz-kc-hod.json, лог gaz-kc.log"""
import csv, io, json, os, re, sqlite3, subprocess, sys, threading, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "gaz-kc.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--rabota"] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    io.open(os.path.join(ОПС, "gaz-kc.pid"), "w").write(str(п.pid))
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import random                                   # noqa: E402
from sender.config import Config               # noqa: E402
from sender.store import Store                 # noqa: E402
import gaz_kanon as K                          # noqa: E402
csv.field_size_limit(10 ** 9)
РАБОТА = "--rabota" in sys.argv
# владелец 11.11: «генерацию можешь запускать по тем, у кого проба прошла» — только карточки по готовым журналам
ТОЛЬКО_КАРТ = "--tolko-kartochki" in sys.argv
МОДЕЛЬ = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-5-5")
ПОТОКОВ = int(next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--potokov=")), "6"))
ИМЯ_КАМП = "КЦ газ 11.11"
ЖУР_СУД, ЖУР_ЛЕС, ЖУР_КАРТ = (os.path.join(ОПС, x) for x in ("gaz-kc-sud.jsonl", "gaz-kc-lesenka.jsonl", "gaz-kc-kartochki.jsonl"))
ХОД_ФАЙЛ = os.path.join(ОПС, "gaz-kc-hod.json")
МЁРТВ = ("нет ящика", "нет MX")
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru", "ya.ru", "yandex.by", "yandex.com",
           "narod.ru", "gmail.com", "rambler.ru"}
ПАУЗА_КРУПНЫХ = 20.0
_замок = threading.Lock()


def пиши(путь, запись):
    with _замок:
        with io.open(путь, "a", encoding="utf-8") as ф:
            ф.write(json.dumps(запись, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())


def читать_журнал(путь):
    if not os.path.exists(путь):
        return []
    вых = []
    for стр in io.open(путь, encoding="utf-8"):
        try:
            вых.append(json.loads(стр))
        except ValueError:
            pass
    return вых


ХОД = {"старт": datetime.now().strftime("%d.%m %H:%M"), "этап": "подготовка"}


def ход(**kw):
    ХОД.update(kw)
    with _замок:
        with io.open(ХОД_ФАЙЛ, "w", encoding="utf-8") as ф:
            json.dump(ХОД, ф, ensure_ascii=False); ф.flush(); os.fsync(ф.fileno())


def с_повтором(fn, *a, **k):
    for п in range(12):
        try:
            return fn(*a, **k)
        except sqlite3.OperationalError as ex:
            if "locked" not in str(ex) or п == 11:
                raise
            time.sleep(10)


def цифры(x):
    return re.sub(r"\D", "", str(x or ""))


# ---------------- данные ----------------
ДРОП = r"C:\seostat\drop\drop-storage"
def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
лпр, комп = читать("CA-ENGER-ZALIVKA.csv"), читать("CA-ENGER-ZALIVKA-kompanii.csv")
САЙТ = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-BAZA-kompanii.csv")}
нужные = {цифры(р.get("ИНН")) for р in лпр + комп}
КОНТ = defaultdict(list)
for р in читать("CA-ENGER-BAZA-kontakty.csv"):
    и = цифры(р.get("ИНН"))
    if и in нужные:
        КОНТ[и].append(р)
print("файлы: ЛПР %d, компаний %d, контактов по нашим ИНН %d" % (len(лпр), len(комп), sum(len(v) for v in КОНТ.values())), flush=True)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
к = store._conn
стоп = {str(v).strip().lower() for _, v in к.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in к.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
ответ = {цифры(r[0]) for r in к.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id "
                                          "WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
кц_камп = {i for i, н in к.execute("SELECT id, name FROM campaigns") if re.search(r"(?i)кц|компрессор|\bkc\b", н or "")
           and not re.search(r"(?i)meyer|мейер|фса|рентген|сепарат", н or "")}
кц_15 = {r[0].lower() for r in к.execute("SELECT email, campaign_id FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days')")
         if r[1] in кц_камп}
в_очереди = {r[0].lower() for r in к.execute("SELECT DISTINCT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                               "WHERE m.status IN ('scheduled','sending','pending_review')")}
чей_адрес = {r[0].lower(): цифры(r[1]) for r in к.execute("SELECT email, inn FROM recipients WHERE email IS NOT NULL")}
try:
    sys.path.insert(0, r"C:\sender\sender")
    from sender.ne_nash import build_ne_nash
    не_наш = {цифры(x) for x in (build_ne_nash().набор(None) or [])}
except Exception as ex:  # noqa: BLE001
    print("реестр «не наш» не прочитан: %s" % ex, flush=True); не_наш = set()
from sender.sdelki_napr import blok as сделка_блок   # noqa: E402
# АДРЕС ЗА ДРУГИМ ИНН (владелец 11.11: «54 за другим доменом выпиши для другой сессии, остальным больше верю ЦА»):
# берём по привязке ЦА, КРОМЕ домена = сайт другой компании, и если та, другая, компания сама в стопе.
_en = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=60)
САЙТ_ИНН = {цифры(i): (с or "") for i, с in _en.execute("SELECT inn, site FROM companies WHERE site IS NOT NULL AND site<>''")}
def _домен_сайта(с):
    с = str(с or "").lower().split("//")[-1].split("/")[0]
    return с[4:] if с.startswith("www.") else с
def _домен_совпал(дом, сайт):
    сайт = _домен_сайта(сайт)
    return bool(сайт) and (дом == сайт or дом.endswith("." + сайт) or сайт.endswith("." + дом))
def в_стопе(и):
    return и in не_наш or и in стоп or и in ответ or bool(сделка_блок(к, и, "kc"))
print("стоп-лист %d, мёртвых %d, ответивших ИНН %d, кампаний КЦ %d, адресов КЦ<15д %d, не наш %d"
      % (len(стоп), len(мёртв), len(ответ), len(кц_камп), len(кц_15), len(не_наш)), flush=True)

# ---------------- компании и лесенки ----------------
база = {}
for р in лпр + комп:
    и = цифры(р.get("ИНН"))
    if и and (и not in база or (not (база[и].get("Продукция") or "").strip() and (р.get("Продукция") or "").strip())):
        база[и] = р


def ранг_адреса(fio, должн, тип):
    имя = K.обращение(fio) if fio and ";" not in fio else None
    т = (тип or "").lower()
    if "продаж" in т:
        return 7, None
    if имя:
        return K.ранг(должн or ""), имя      # 0 тех, 1 руководитель, 2 закупки, 3 прочие
    return (5 if "общ" in т or not т else 6), None


def лесенка(и):
    кандидаты = {}
    for р in ЛПР_ПО_ИНН.get(и, []) + КОНТ.get(и, []) + ([база[и]] if и in база else []):
        em = (р.get("Почта") or "").strip().lower()
        if not em:
            continue
        for e1 in re.split(r"[,;\s]+", em):
            if "@" not in e1:
                continue
            fio, должн = (р.get("ФИО") or "").strip(), (р.get("Должность") or "").strip()
            ранг, имя = ранг_адреса(fio, должн, р.get("Тип почты"))
            if re.match(r"(?i)(sales|zakaz|order|opt|shop|market|reklama|pr|hr|job|resume|buh)@", e1):
                ранг = max(ранг, 7)
            if e1 not in кандидаты or ранг < кандидаты[e1]["ранг"]:
                кандидаты[e1] = {"email": e1, "ранг": ранг, "имя": имя, "fio": fio if имя else "", "должн": должн if имя else ""}
    вых, почему = [], Counter()
    for к1 in sorted(кандидаты.values(), key=lambda x: (x["ранг"], x["email"])):
        e1 = к1["email"]
        if not K.адрес_годен(e1): почему["плохой адрес"] += 1; continue
        if e1 in стоп: почему["адрес в стоп-листе"] += 1; continue
        if e1 in мёртв: почему["мёртв по пробе"] += 1; continue
        if e1 in кц_15: почему["КЦ писал < 15 дней"] += 1; continue
        if e1 in в_очереди: почему["уже в очереди"] += 1; continue
        _др = чей_адрес.get(e1)
        if _др and _др != и:
            if в_стопе(_др): почему["адрес за другим ИНН, та компания в стопе"] += 1; continue
            _дом = e1.rsplit("@", 1)[-1]
            _наш_сайт = (база.get(и, {}).get("Сайт") or САЙТ.get(и, {}).get("Сайт") or САЙТ_ИНН.get(и, ""))
            if _домен_совпал(_дом, САЙТ_ИНН.get(_др, "")) and not _домен_совпал(_дом, _наш_сайт):
                почему["домен = сайт другой компании"] += 1; continue
            к1 = dict(к1, drugoy_inn=_др); почему["за другим ИНН, берём по ЦА"] += 1
        вых.append(к1)
    return вых[:6], почему


ЛПР_ПО_ИНН = defaultdict(list)
for р in лпр:
    ЛПР_ПО_ИНН[цифры(р.get("ИНН"))].append(р)

ОТСЕВ = Counter(); АДР_ОТСЕВ = Counter(); КОМПАНИИ = {}
for и, р in база.items():
    отр = (р.get("Отрасль основная") or р.get("Отрасль") or "").strip()
    с = САЙТ.get(и, {})
    if "резерв" in (р.get("Статус отрасли") or "").lower(): ОТСЕВ["резерв"] += 1; continue
    if и in не_наш or и in стоп: ОТСЕВ["реестр «не наш»/стоп-лист"] += 1; continue
    if и in ответ: ОТСЕВ["был ответ/жалоба/отписка"] += 1; continue
    if сделка_блок(к, и, "kc"): ОТСЕВ["активная сделка КЦ"] += 1; continue
    п = K.отсев_кодом(р, отр, с)
    if п: ОТСЕВ[п.split(" (")[0]] += 1; continue
    лес, поч = лесенка(и)
    АДР_ОТСЕВ.update(поч)
    if not лес: ОТСЕВ["нет годного адреса"] += 1; continue
    газ = "N2" if "Азот" in (р.get("Газ") or "") else "O2"
    КОМПАНИИ[и] = {"р": р, "отр": отр, "газ": газ, "лес": лес}
print("отсев компаний:", dict(ОТСЕВ.most_common()), flush=True)
print("отсев адресов в лесенках:", dict(АДР_ОТСЕВ.most_common()), flush=True)
print("к суду модели: %d компаний; глубина лесенки: %s" % (len(КОМПАНИИ), dict(Counter(len(x["лес"]) for x in КОМПАНИИ.values()))), flush=True)
ход(этап="подготовка", компаний=len(КОМПАНИИ), отсев=dict(ОТСЕВ))
if not РАБОТА:
    print("сухой прогон: модель, проба и карточки не запускались. Боевой — --zapusk"); sys.exit(0)

# ---------------- 1. суд модели ----------------
import gen_provider as GP   # noqa: E402
СУД = {з["inn"]: з for з in читать_журнал(ЖУР_СУД)}


def зов(текст):
    for _п in range(20):
        try:
            м = GP._raw_stream([{"role": "user", "content": текст}], МОДЕЛЬ, 4000, thinking=False, effort="low")
            т = м if isinstance(м, str) else "".join(getattr(b, "text", "") for b in getattr(м, "content", []) or [])
            _м = list(re.finditer(r'\{\s*"o"\s*:', т))
            if not _м:
                raise ValueError("нет JSON в ответе: %r" % т[:200])
            return {int(x["n"]): x for x in json.JSONDecoder(strict=False).raw_decode(т[_м[-1].start():])[0].get("o", [])}
        except Exception as ex:  # noqa: BLE001
            print("модель: %s, повтор" % str(ex)[:120], flush=True)
            time.sleep(300 if "429" in str(ex) else 90 if "503" in str(ex) else 20)
    return None


def пачка_суда(пачка):
    отр, газ = КОМПАНИИ[пачка[0]]["отр"], КОМПАНИИ[пачка[0]]["газ"]
    строки = [K.строка_для_модели(i, отр, КОМПАНИИ[и]["р"], САЙТ.get(и, {})) for i, и in enumerate(пачка, 1)]
    о = зов(K.задание(газ, строки))
    if о is None:
        print("пачка не судилась (%s), вернёмся при перезапуске" % отр[:30], flush=True); return 0
    n = 0
    for i, и in enumerate(пачка, 1):
        x = о.get(i) or {}
        f, беда = K.фраза(x.get("f") or "", газ)
        ok = x.get("ok") is True and x.get("konk") is not True and not беда
        з = {"inn": и, "ok": ok, "konk": x.get("konk") is True, "model_ok": x.get("ok") is True, "pochemu": (x.get("pochemu") or "")[:200],
             "f": f if ok else "", "beda": беда if x.get("ok") is True else "", "otr": отр, "gaz": газ, "model": МОДЕЛЬ,
             "ts": datetime.now(timezone.utc).isoformat()}
        if not x:
            з["beda"] = "нет ответа модели"
        пиши(ЖУР_СУД, з); СУД[и] = з; n += 1
    return n


ждут = [] if ТОЛЬКО_КАРТ else [и for и in КОМПАНИИ if и not in СУД]
группы = defaultdict(list)
for и in ждут:
    группы[(КОМПАНИИ[и]["отр"], КОМПАНИИ[и]["газ"])].append(и)
пачки = [сп[i:i + 10] for сп in группы.values() for i in range(0, len(сп), 10)]
ход(этап="суд модели", пачек=len(пачки), уже_судили=len(КОМПАНИИ) - len(ждут))
print("суд: компаний %d, уже в журнале %d, пачек %d, модель %s, потоков %d" % (len(КОМПАНИИ), len(КОМПАНИИ) - len(ждут), len(пачки), МОДЕЛЬ, ПОТОКОВ), flush=True)
from concurrent.futures import ThreadPoolExecutor   # noqa: E402
готово_пачек = 0
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    for _n in пул.map(пачка_суда, пачки):
        готово_пачек += 1
        if готово_пачек % 10 == 0:
            ход(суд_пачек_готово=готово_пачек)
            print("суд: пачек %d/%d" % (готово_пачек, len(пачки)), flush=True)
прошли = [и for и in КОМПАНИИ if СУД.get(и, {}).get("ok")]
итог_суда = Counter("ok" if з.get("ok") else ("конкурент" if з.get("konk") else ("брак фразы" if з.get("beda") else "не подходит")) for и, з in СУД.items() if и in КОМПАНИИ)
print("суд готов:", dict(итог_суда), flush=True)
ход(этап="лесенка", суд=dict(итог_суда))

# ---------------- 2. лесенка проб ----------------
from sender.addr_probe import build_addr_probe   # noqa: E402
_петля = build_addr_probe(store, cfg)
проба = getattr(_петля, "probe", None) or getattr(_петля, "probe_")
проба.per_domain = 10 ** 6          # темп держим сами
ЛЕС = {з["inn"]: з for з in читать_журнал(ЖУР_ЛЕС)}
буфер_обзвона = []


def слить_обзвон():
    if not буфер_обзвона:
        return
    try:
        ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
        ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, source TEXT, answer TEXT, ts INTEGER)")
        ox.executemany("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                       "verdict=excluded.verdict, answer=excluded.answer, ts=excluded.ts", буфер_обзвона)
        ox.commit(); ox.close(); del буфер_обзвона[:]
    except Exception as ex:  # noqa: BLE001
        print("обзвон: не слилось (%s), повторим" % str(ex)[:80], flush=True)


def в_базы(адрес, вер, ответ_):
    ts = int(time.time())
    try:
        cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
        cx.execute("PRAGMA busy_timeout=60000")
        cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? WHERE lower(email)=?", (вер, ts, str(ответ_)[:300], адрес))
        cx.commit(); cx.close()
    except Exception as ex:  # noqa: BLE001
        print("enrich: %s" % str(ex)[:80], flush=True)
    буфер_обзвона.append((адрес, вер, "smtp-server", str(ответ_)[:300], ts))
    if len(буфер_обзвона) >= 100:
        слить_обзвон()


шаг = {} if ТОЛЬКО_КАРТ else {и: 0 for и in прошли if и not in ЛЕС}
посл_домен = {}
сч_проб = Counter()
print("лесенка: компаний %d (уже решено %d)" % (len(шаг), len([и for и in прошли if и in ЛЕС])), flush=True)
while шаг:
    продвинулись = False
    for и in list(шаг):
        лес = КОМПАНИИ[и]["лес"]; i = шаг[и]
        if i >= len(лес):
            з = {"inn": и, "status": "все мертвы", "ts": datetime.now(timezone.utc).isoformat()}
            пиши(ЖУР_ЛЕС, з); ЛЕС[и] = з; del шаг[и]; продвинулись = True; continue
        адрес = лес[i]["email"]
        есть = проба.cached(адрес)
        if есть:
            вер = str(есть.get("verdict") or "неясно")
        else:
            домен = адрес.rsplit("@", 1)[-1]
            if домен in КРУПНЫЕ and time.monotonic() - посл_домен.get(домен, -1e9) < ПАУЗА_КРУПНЫХ:
                continue
            посл_домен[домен] = time.monotonic()
            try:
                рез = проба.probe(адрес)
            except Exception as ex:  # noqa: BLE001
                рез = {"verdict": "неясно", "answer": str(ex)[:200]}
            вер = str(рез.get("verdict") or "неясно")
            в_базы(адрес, вер, рез.get("answer") or "")
            сч_проб[вер] += 1
        продвинулись = True
        if вер in МЁРТВ:
            шаг[и] = i + 1
            continue
        з = {"inn": и, "status": "выбран", "email": адрес, "verdict": вер, "stupen": i, "ts": datetime.now(timezone.utc).isoformat()}
        пиши(ЖУР_ЛЕС, з); ЛЕС[и] = з; del шаг[и]
        if sum(сч_проб.values()) % 25 == 0:
            ход(проб=dict(сч_проб), осталось_компаний=len(шаг))
    if not продвинулись:
        time.sleep(3)
    ход(проб=dict(сч_проб), осталось_компаний=len(шаг))
слить_обзвон()
выбраны = [и for и in прошли if ЛЕС.get(и, {}).get("status") == "выбран"]
print("лесенка готова: проб %s; выбран адрес у %d, все мертвы у %d" % (dict(сч_проб), len(выбраны), len([и for и in прошли if ЛЕС.get(и, {}).get("status") == "все мертвы"])), flush=True)
ход(этап="карточки", выбрано=len(выбраны))

# ---------------- 3. карточки ----------------
from sender.ai_quota import build_ai_quota   # noqa: E402
r = к.execute("SELECT id FROM campaigns WHERE name=?", (ИМЯ_КАМП,)).fetchone()
if r:
    КАМП = r[0]
else:
    б = к.execute("SELECT status, legal_entity, legal_inn, provider_pool, config_json FROM campaigns WHERE id=17").fetchone()
    сейчас = datetime.now(timezone.utc).isoformat()

    def _завести():
        with store._lock:
            ид = к.execute("INSERT INTO campaigns (name, status, legal_entity, legal_inn, provider_pool, config_json, created_at, updated_at) "
                           "VALUES (?,?,?,?,?,?,?,?)", (ИМЯ_КАМП, б[0], б[1], б[2], б[3], б[4], сейчас, сейчас)).lastrowid
            шк = [x[1] for x in к.execute("PRAGMA table_info(sequence_steps)") if x[1] != "id"]
            for row in к.execute("SELECT %s FROM sequence_steps WHERE campaign_id=17" % ",".join(шк)).fetchall():
                д = dict(zip(шк, row)); д["campaign_id"] = ид
                к.execute("INSERT INTO sequence_steps (%s) VALUES (%s)" % (",".join(д), ",".join("?" * len(д))), list(д.values()))
            к.commit()
        return ид
    КАМП = с_повтором(_завести)
    print("заведена кампания", КАМП, ИМЯ_КАМП, flush=True)
q = build_ai_quota(store, cfg)
ящики = [m for m in cfg.mailboxes() if str(getattr(m, "division", "")) == "kc"]
КАРТ = {з["inn"] for з in читать_журнал(ЖУР_КАРТ) if з.get("karta")}
в_кампании = {цифры(x[0]) for x in к.execute("SELECT inn FROM confirm_reviews WHERE campaign_id=?", (КАМП,))}
заведено, пропущено = 0, Counter()
for и in выбраны:
    if и in КАРТ or и in в_кампании:
        continue
    ком = КОМПАНИИ[и]; р = ком["р"]; суд = СУД[и]; em = ЛЕС[и]["email"]
    ступ = next(x for x in ком["лес"] if x["email"] == em)
    имя, fio, должн = ступ["имя"], ступ["fio"], ступ["должн"]
    _им = (имя or "").split()[:1]
    mb = random.choice([m for m in ящики if str(getattr(m, "from_name", "") or "").split()[:1] != _им] or ящики)
    менеджер = (str(getattr(mb, "from_name", "") or "").split(",")[0].split() or ["Сергей"])[0]
    тема, тело = K.письмо(имя, менеджер, должн, суд["f"], ком["отр"], ком["газ"], р)
    имя_комп = (р.get("Компания") or "").strip()
    запись = {"inn": и, "email": em, "fio": fio, "post": должн, "otr": ком["отр"], "gaz": ком["газ"], "stupen": ЛЕС[и].get("stupen"),
              "verdict": ЛЕС[и].get("verdict"), "ts": datetime.now(timezone.utc).isoformat()}
    сейчас = datetime.now(timezone.utc).isoformat()
    есть = к.execute("SELECT id, inn FROM recipients WHERE lower(email)=?", (em,)).fetchone()
    if есть and есть[1] and цифры(есть[1]) != и:
        запись["drugoy_inn"] = цифры(есть[1])     # по привязке ЦА (владелец 11.11); получатель в панели остаётся как был
    if есть:
        rid = есть[0]
    else:
        def _получатель():
            with store._lock:
                ид = к.execute("INSERT INTO recipients (email, company_name, inn, segment, domain, tz, contact_name, source, extra_json, created_at, updated_at) "
                               "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (em, имя_комп, и, "кц", em.split("@")[-1], "Europe/Moscow", fio, "gaz-kc-1111",
                                                                   json.dumps({"target_division": "kc", "stupen": должн, "gaz": ком["газ"]}, ensure_ascii=False),
                                                                   сейчас, сейчас)).lastrowid
                к.commit()
            return ид
        rid = с_повтором(_получатель)
    mid, _шаг, почему = с_повтором(q._ensure_message, КАМП, int(rid))
    if not mid:
        запись["otsev"] = "сообщение не завелось: %s" % почему; пиши(ЖУР_КАРТ, запись); пропущено["сообщение не завелось"] += 1; continue
    панель = json.dumps({"letter_division": "kc", "mailbox_id": mb.mailbox_id, "vruchnuyu": ИМЯ_КАМП, "company": {"name": имя_комп},
                         **({"adres_za_drugim_inn": запись["drugoy_inn"]} if запись.get("drugoy_inn") else {})}, ensure_ascii=False)
    ключ = "%s|%s|%d" % (и, em, КАМП)
    if к.execute("SELECT 1 FROM confirm_reviews WHERE dedup_key=?", (ключ,)).fetchone():
        пропущено["карточка уже есть"] += 1; continue

    def _карточка():
        with store._lock:
            к.execute("UPDATE messages SET mailbox_id=? WHERE id=?", (mb.mailbox_id, mid))
            ид = к.execute("INSERT INTO confirm_reviews (dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, panel_json, status, kind, created_at, updated_at) "
                           "VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)", (ключ, КАМП, rid, mid, и, em, тема, тело, панель, сейчас, сейчас)).lastrowid
            к.commit()
        return ид
    кид = с_повтором(_карточка)
    заведено += 1
    запись.update({"karta": кид, "mailbox": mb.mailbox_id, "tema": тема, "telo": тело})
    пиши(ЖУР_КАРТ, запись)
    if заведено % 25 == 0:
        ход(карточек=заведено); print("карточек: %d" % заведено, flush=True)
ход(этап="готово", карточек=заведено, пропущено=dict(пропущено))
print("ИТОГ: кампания %d «%s», карточек заведено %d, пропущено %s" % (КАМП, ИМЯ_КАМП, заведено, dict(пропущено)), flush=True)
