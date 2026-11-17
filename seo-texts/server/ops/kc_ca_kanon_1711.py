# -*- coding: utf-8 -*-
"""Письма КЦ «конец года» (канон «по имени», как КЦ Россия 9000: заход «ноябрь–декабрь, бюджеты», фраза модели где
нужен сжатый воздух, РУСАЛ/РЖД/Северсталь/Алроса, сервис, вопрос про 4 месяца, просьба переслать механику/энергетику)
по запасу ЦА с паспортом (владелец 17.11). Запас: CA-ENGER-ZALIVKA-kompanii + CA-ENGER-BAZA-kompanii, без карточки КЦ,
без ответа/жалобы, модель газа их не смотрела, паспорт есть (≥3 полей сайта в CA или site_facts вес ≥8) — 2333 фирмы.

ПРАВИЛА ВЛАДЕЛЬЦА 17.11 «проверь что этим компаниям мы не писали, если писали то на другой ящик и прошло больше
30 дней»: письмо нашей рассылки (любое направление) компании за последние 30 дней — компанию не берём; адрес, на
который мы писали хоть раз, — не берём (берём другой адрес из лесенки). Плюс обычное: стоп-лист, реестр «не наш»,
активная сделка КЦ, мёртвые адреса, письмо в очереди.

ЭТАПЫ (журналы в C:\\sender\\_ops, fsync, резюмируемо):
  1. лесенка + проба   kc-ca-lesenka.jsonl   — точная проба сверху вниз до живого (вердикты в три базы);
  2. предфильтр        kc-ca-predklass.jsonl — предклассификатор партии (_ПРЕДКЛАСС_СИСТЕМА из partiya_gen.py,
                                               проверен судьёй 13.10): дальше только «кц» и «оба»;
  3. генерация         kc-ca-kartochki.jsonl — фраза модели (пачка 20) + канон, карточка pending в кампании
                                               «КЦ ЦА конец года 17.11» (клон КЦ-1). Каждое 20-е — kc-ca-kazhdoe20.txt.
АВТООТПРАВКИ НЕТ — только «Подтвердить отправку».
    kc_ca_kanon_1711.py                 — сухой подсчёт (без пробы, модели, карточек)
    kc_ca_kanon_1711.py --zapusk [--model=claude-opus-4-8] [--limit=N]   — всё фоном, лог kc-ca.log
    kc_ca_kanon_1711.py --hod           — ход по журналам"""
import csv, io, json, os, random, re, sqlite3, subprocess, sys, threading, time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
ОПС = r"C:\sender\_ops"; ДР = r"C:\seostat\drop\drop-storage"
ЖУР_ЛЕС, ЖУР_ПК, ЖУР_КАРТ = (os.path.join(ОПС, x) for x in ("kc-ca-lesenka.jsonl", "kc-ca-predklass.jsonl", "kc-ca-kartochki.jsonl"))
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "kc-ca.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--rabota"] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)


def читать_журнал(путь):
    з = {}
    if os.path.exists(путь):
        for с in io.open(путь, encoding="utf-8", errors="replace"):
            try: x = json.loads(с); з[x["inn"]] = x
            except Exception: pass
    return з


if "--hod" in sys.argv:
    for и, п in (("лесенка", ЖУР_ЛЕС), ("предфильтр", ЖУР_ПК), ("карточки", ЖУР_КАРТ)):
        з = читать_журнал(п).values()
        print(и, len(з), dict(Counter(x.get("status") or x.get("napr") or ("карточка" if x.get("karta") else x.get("otsev", "?")[:40]) for x in з)))
    try: print(io.open(os.path.join(ОПС, "kc-ca.log"), encoding="utf-8", errors="replace").read()[-700:])
    except Exception: pass
    sys.exit(0)

РАБОТА = "--rabota" in sys.argv
МОДЕЛЬ = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-4-8")
ЛИМИТ = int(next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--limit=")), "0"))
ИМЯ_КАМП = "КЦ ЦА конец года 17.11"
os.environ["PROVIDER_THINKING_FIELD"] = "omit"     # канал включает рассуждение при любом поле thinking — дорого
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server"); sys.path.insert(0, r"C:\sender\server\ops")
if РАБОТА:
    import msvcrt  # noqa: E402 — вторая копия (повторный запуск при обрыве связи) сразу выходит
    _замок_ф = open(os.path.join(ОПС, "kc-ca.lock"), "a+")
    try: msvcrt.locking(_замок_ф.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError: print("уже идёт другая копия — выхожу", flush=True); sys.exit(0)
from sender.config import Config               # noqa: E402
from sender.store import Store                 # noqa: E402
from sender.sdelki_napr import blok as сделка_блок   # noqa: E402
import gaz_kanon as K                          # noqa: E402
csv.field_size_limit(10 ** 9)
ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
_з = threading.Lock()


def пиши(путь, запись):
    with _з, io.open(путь, "a", encoding="utf-8") as ф:
        ф.write(json.dumps(запись, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())


def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДР, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))


# ---------------- 0. запас: ЦА с паспортом ----------------
ПОЛЯ = ["Продукция", "Оборудование, линии", "Мощности", "Сырьё", "Упаковка, фасовка", "Контроль качества", "Масштаб",
        "Год основания", "Экспорт", "География поставок", "Клиенты", "Энергохозяйство", "Газы (паспорт)", "Расширение"]
лпр, зал, баз = читать("CA-ENGER-ZALIVKA.csv"), читать("CA-ENGER-ZALIVKA-kompanii.csv"), читать("CA-ENGER-BAZA-kompanii.csv")
БАЗА = {ц(р["ИНН"]): р for р in баз}
for р in зал: БАЗА.setdefault(ц(р["ИНН"]), р)
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
к = store._conn
e = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=60)
кам = {i: н for i, н in к.execute("SELECT id, name FROM campaigns")}
кц_к = {i for i, н in кам.items() if re.search(r"(?i)кц|компрессор|\bkc\b", н or "") and not re.search(r"(?i)meyer|мейер|фса|рентген|сепарат", н or "")}
карт_кц = {ц(i) for i, кид in к.execute("SELECT inn, campaign_id FROM confirm_reviews") if кид in кц_к}
ответ = {ц(r[0]) for r in к.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
суд_газ = set(читать_журнал(os.path.join(ОПС, "gaz-kc-sud.jsonl")))


def вес_sf(f):
    n = 0
    for k_ in ("продукция", "сырьё", "упаковка_фасовка", "мощности", "контроль_качества", "экспорт", "оборудование_линии", "география_поставок", "масштаб", "год_основания"):
        v = f.get(k_); n += len(v) if isinstance(v, (list, tuple)) else (1 if v else 0)
    return n


SF = {}
for i, fj in e.execute("SELECT inn, facts_json FROM site_facts"):
    try: f = json.loads(fj or "{}")
    except Exception: continue
    if isinstance(f, dict): SF[ц(i)] = f
запас = []
for и in ({ц(р["ИНН"]) for р in зал} | {ц(р["ИНН"]) for р in баз}) - карт_кц - ответ - суд_газ - {""}:
    р = БАЗА.get(и, {}); n = sum(1 for п in ПОЛЯ if (р.get(п) or "").strip())
    if n >= 3 or вес_sf(SF.get(и, {})) >= 8: запас.append(и)
print("запас ЦА с паспортом: %d" % len(запас), flush=True)

# ---------------- 1. «мы не писали»: 30 дней на компанию, адрес — ни разу ----------------
стоп = {str(v).strip().lower() for _, v in к.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in к.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
порог30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()[:19]
писали_адрес, писали_инн_30, в_очереди = set(), set(), set()
for em, inn, st, ts in к.execute("SELECT lower(r.email), r.inn, m.status, COALESCE(m.sent_at, m.updated_at, '') FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                 "WHERE m.status IN ('sent','sending','scheduled','pending_review')"):
    if st in ('sent', 'sending'):
        писали_адрес.add(em)
        if str(ts)[:19] >= порог30: писали_инн_30.add(ц(inn)); писали_инн_30.add("@" + em)
    else:
        в_очереди.add(ц(inn)); в_очереди.add("@" + em)
for em, ts in к.execute("SELECT lower(email), ts FROM send_log WHERE outcome='sent'"):
    писали_адрес.add(em)
    if str(ts)[:19] >= порог30: писали_инн_30.add("@" + em)
чей_адрес = {r[0].lower(): ц(r[1]) for r in к.execute("SELECT email, inn FROM recipients WHERE email IS NOT NULL")}
try:
    sys.path.insert(0, r"C:\sender\sender")
    from sender.ne_nash import build_ne_nash
    не_наш = {ц(x) for x in (build_ne_nash().набор(None) or [])}
except Exception as ex:  # noqa: BLE001
    print("реестр «не наш» не прочитан: %s" % ex, flush=True); не_наш = set()

КОНТ = defaultdict(list)
for р in лпр: КОНТ[ц(р.get("ИНН"))].append(р)
_запас = set(запас)
for р in читать("CA-ENGER-BAZA-kontakty.csv"):
    и = ц(р.get("ИНН"))
    if и in _запас: КОНТ[и].append(р)
for и, em, person, role in e.execute("SELECT inn, lower(email), COALESCE(person,''), COALESCE(role,'') FROM emails WHERE email LIKE '%@%'"):
    и = ц(и)
    if и in _запас: КОНТ[и].append({"Почта": em, "ФИО": person, "Должность": role, "Тип почты": "именная" if person else ""})


def ранг_адреса(fio, должн, тип):
    имя = K.обращение(fio) if fio and ";" not in fio else None
    т = (тип or "").lower()
    if "продаж" in т: return 7, None
    if имя: return K.ранг(должн or ""), имя
    return (5 if "общ" in т or not т else 6), None


def лесенка(и):
    кандидаты = {}
    р0 = БАЗА.get(и, {})
    for р in КОНТ.get(и, []) + [{"Почта": р0.get("Почты (все)") or р0.get("Почта") or "", "Тип почты": "общая"}]:
        for e1 in re.split(r"[,;\s]+", (р.get("Почта") or "").strip().lower()):
            if "@" not in e1: continue
            fio, должн = (р.get("ФИО") or "").strip(), (р.get("Должность") or "").strip()
            ранг, имя = ранг_адреса(fio, должн, р.get("Тип почты"))
            if re.match(r"(?i)(sales|zakaz|order|opt|shop|market|reklama|pr|hr|job|resume|buh)@", e1): ранг = max(ранг, 7)
            if e1 not in кандидаты or ранг < кандидаты[e1]["ранг"]:
                кандидаты[e1] = {"email": e1, "ранг": ранг, "имя": имя, "fio": fio if имя else "", "должн": должн if имя else ""}
    вых, почему = [], Counter()
    for к1 in sorted(кандидаты.values(), key=lambda x: (x["ранг"], x["email"])):
        e1 = к1["email"]
        if not K.адрес_годен(e1): почему["плохой адрес"] += 1; continue
        if e1 in стоп or e1.split("@")[-1] in стоп: почему["стоп-лист"] += 1; continue
        if e1 in мёртв: почему["мёртв по пробе"] += 1; continue
        if e1 in писали_адрес: почему["на адрес уже писали"] += 1; continue
        _др = чей_адрес.get(e1)
        if _др and _др != и: почему["адрес за другим ИНН"] += 1; continue
        вых.append(к1)
    return вых[:6], почему


ОТСЕВ, АДР = Counter(), Counter(); КОМП = {}
for и in sorted(запас):
    if и in не_наш or и in стоп: ОТСЕВ["реестр «не наш»/стоп"] += 1; continue
    if и in писали_инн_30: ОТСЕВ["писали компании < 30 дней"] += 1; continue
    if и in в_очереди: ОТСЕВ["письмо компании в очереди"] += 1; continue
    if сделка_блок(к, и, "kc"): ОТСЕВ["активная сделка КЦ"] += 1; continue
    лес, поч = лесенка(и); АДР.update(поч)
    if any(("@" + x["email"]) in писали_инн_30 or ("@" + x["email"]) in в_очереди for x in лес):
        ОТСЕВ["писали компании < 30 дней (по адресу)"] += 1; continue
    if not лес: ОТСЕВ["нет годного адреса"] += 1; continue
    КОМП[и] = лес
print("отсев компаний:", dict(ОТСЕВ), flush=True)
print("отсев адресов:", dict(АДР), flush=True)
print("к пробе: %d компаний; глубина лесенки %s" % (len(КОМП), dict(Counter(len(x) for x in КОМП.values()))), flush=True)
if ЛИМИТ:
    _к = sorted(КОМП); random.seed(1711); random.shuffle(_к); КОМП = {и: КОМП[и] for и in _к[:ЛИМИТ]}
if not РАБОТА:
    print("сухой прогон: проба, модель и карточки не запускались. Боевой — --zapusk"); sys.exit(0)

# ---------------- 2. лесенка проб ----------------
from sender.addr_probe import build_addr_probe   # noqa: E402
import proba_tochnaya as P                          # noqa: E402
_петля = build_addr_probe(store, cfg)
проба = getattr(_петля, "probe", None) or getattr(_петля, "probe_")
проба.per_domain = 10 ** 6
МЁРТВ = ("нет ящика", "нет MX")
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru", "ya.ru", "yandex.by", "yandex.com", "narod.ru", "gmail.com", "rambler.ru"}
ЛЕС = читать_журнал(ЖУР_ЛЕС)
шаг = {и: 0 for и in КОМП if и not in ЛЕС}
посл_домен = {}; сч_проб = Counter()
print("лесенка: к пробе %d (уже решено %d)" % (len(шаг), len([и for и in КОМП if и in ЛЕС])), flush=True)
while шаг:
    двиг = False
    for и in list(шаг):
        лес = КОМП[и]; i = шаг[и]
        if i >= len(лес):
            з = {"inn": и, "status": "все мертвы", "ts": datetime.now(timezone.utc).isoformat()}
            пиши(ЖУР_ЛЕС, з); ЛЕС[и] = з; del шаг[и]; двиг = True; continue
        адрес = лес[i]["email"]
        есть = проба.cached(адрес)
        if есть and str(есть.get("verdict") or "") == "неясно": есть = None
        if есть:
            вер = str(есть.get("verdict") or "неясно")
        else:
            дом = адрес.rsplit("@", 1)[-1]
            if дом in КРУПНЫЕ and time.monotonic() - посл_домен.get(дом, -1e9) < 20.0: continue
            посл_домен[дом] = time.monotonic()
            try: вер, _код, _отв, _мх = P.проба(адрес)
            except Exception as ex:  # noqa: BLE001
                вер, _код, _отв, _мх = "неясно", None, str(ex)[:200], ""
            P.в_базы(адрес, вер, _код, _отв, _мх); сч_проб[вер] += 1
        двиг = True
        if вер in МЁРТВ: шаг[и] = i + 1; continue
        з = {"inn": и, "status": "выбран", "email": адрес, "verdict": вер, "stupen": i, "fio": лес[i]["fio"], "dolzhn": лес[i]["должн"],
             "ts": datetime.now(timezone.utc).isoformat()}
        пиши(ЖУР_ЛЕС, з); ЛЕС[и] = з; del шаг[и]
        if sum(сч_проб.values()) % 50 == 0: print("проба: %s, осталось компаний %d" % (dict(сч_проб), len(шаг)), flush=True)
    if not двиг: time.sleep(3)
живые = [и for и in КОМП if ЛЕС.get(и, {}).get("status") == "выбран"]
print("лесенка готова: проб %s; живой адрес у %d, все мертвы у %d" % (dict(сч_проб), len(живые), len([и for и in КОМП if ЛЕС.get(и, {}).get("status") == "все мертвы"])), flush=True)

# ---------------- 3. предфильтр: предклассификатор ----------------
import ast                                        # noqa: E402
import gen_provider as GP                         # noqa: E402
import verdikty_v_bazy as вб                      # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
_исх = io.open(r"C:\sender\server\ops\partiya_gen.py", encoding="utf-8").read()
ПК_СИСТЕМА = next(ast.literal_eval(у.value) for у in ast.parse(_исх).body if isinstance(у, ast.Assign) and getattr(у.targets[0], "id", "") == "_ПРЕДКЛАСС_СИСТЕМА")


def паспорт(и):
    куски = []
    f = SF.get(и, {})
    for k_ in ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб", "мощности"):
        v = f.get(k_)
        if v: куски.append(f"{k_}: " + (v if isinstance(v, str) else "; ".join(map(str, v))[:260]))
    р = БАЗА.get(и, {})
    for п in ("ОКВЭД основной", "Отрасль", "Продукция", "Оборудование, линии", "Сырьё", "Мощности"):
        if (р.get(п) or "").strip(): куски.append("%s: %s" % (п, р[п].strip()[:260]))
    return "\n".join(куски)[:1500]


def зов(текст, ключ, система, макс):
    for п in range(10):
        try:
            м = GP._raw_stream([{"role": "user", "content": текст}], МОДЕЛЬ, макс, thinking=False, effort=None, system=система, cache_system=bool(система))
            т = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
            мм = list(re.finditer(r'\{\s*"%s"\s*:' % ключ, т))
            if not мм: raise ValueError("нет JSON")
            return json.JSONDecoder(strict=False).raw_decode(т[мм[-1].start():])[0]
        except Exception as ex:  # noqa: BLE001
            print("модель: %s" % str(ex)[:120], flush=True); time.sleep(30 if "503" in str(ex) or "429" in str(ex) else 10)
    return None


ПК = читать_журнал(ЖУР_ПК)


def пачка_пк(кусок):
    блоки = ["ИНН %s · %s\n%s" % (и, (БАЗА.get(и, {}).get("Компания") or ""), паспорт(и)) for и in кусок]
    д = зов("Компании:\n\n" + "\n\n".join(блоки), "firmy", ПК_СИСТЕМА, 3000)
    if not д: return
    записи = []
    for v in д.get("firmy") or []:
        и = ц(v.get("inn")); н = str(v.get("napravlenie") or "").strip().lower()
        if и in кусок and н: записи.append({"inn": и, "napr": н})
    try:
        вб.obnovit([{"inn": з["inn"], "napr": з["napr"], "istochnik": "предкласс", "rusprom": "не покупатель" if з["napr"] == "никуда" else None,
                     "pochemu": "предклассификатор по паспорту (КЦ ЦА 17.11)"} for з in записи])
    except Exception as ex:  # noqa: BLE001
        print("вердикты в базы: %s" % str(ex)[:100], flush=True)
    for з in записи:
        з["ts"] = datetime.now(timezone.utc).isoformat(); пиши(ЖУР_ПК, з); ПК[з["inn"]] = з


к_пк = [и for и in живые if и not in ПК]
print("предфильтр: к решению %d (уже решено %d)" % (len(к_пк), len(живые) - len(к_пк)), flush=True)
with ThreadPoolExecutor(6) as пул:
    list(пул.map(пачка_пк, [к_пк[i:i + 12] for i in range(0, len(к_пк), 12)]))
прошли = [и for и in живые if ПК.get(и, {}).get("napr") in ("кц", "оба")]
print("предфильтр готов: %s; дальше %d" % (dict(Counter(ПК.get(и, {}).get("napr", "нет ответа") for и in живые)), len(прошли)), flush=True)

# ---------------- 4. генерация по канону и карточки ----------------
from sender.ai_quota import build_ai_quota   # noqa: E402
import gen_9000_kc_kanon as KK               # noqa: E402  — тексты канона из gen_9000_kc.py (без побочных действий)
r = к.execute("SELECT id FROM campaigns WHERE name=?", (ИМЯ_КАМП,)).fetchone()
if r:
    КАМП = r[0]
else:
    б = к.execute("SELECT status, legal_entity, legal_inn, provider_pool, config_json FROM campaigns WHERE id=17").fetchone()
    сейчас = datetime.now(timezone.utc).isoformat()
    with store._lock:
        КАМП = к.execute("INSERT INTO campaigns (name, status, legal_entity, legal_inn, provider_pool, config_json, created_at, updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?)", (ИМЯ_КАМП, б[0], б[1], б[2], б[3], б[4], сейчас, сейчас)).lastrowid
        шк = [x[1] for x in к.execute("PRAGMA table_info(sequence_steps)") if x[1] != "id"]
        for row in к.execute("SELECT %s FROM sequence_steps WHERE campaign_id=17" % ",".join(шк)).fetchall():
            д = dict(zip(шк, row)); д["campaign_id"] = КАМП
            к.execute("INSERT INTO sequence_steps (%s) VALUES (%s)" % (",".join(д), ",".join("?" * len(д))), list(д.values()))
        к.commit()
    print("заведена кампания", КАМП, ИМЯ_КАМП, flush=True)
q = build_ai_quota(store, cfg)
пауз = {r[0] for r in к.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
ящики = [m for m in cfg.mailboxes() if str(getattr(m, "division", "")) == "kc" and m.mailbox_id not in пауз]
КАРТ = читать_журнал(ЖУР_КАРТ)
в_камп = {ц(x[0]) for x in к.execute("SELECT inn FROM confirm_reviews WHERE campaign_id=?", (КАМП,))}
список = [и for и in прошли if и not in КАРТ and и not in в_камп]
print("генерация: к письмам %d" % len(список), flush=True)
ГЛАЗ = io.open(os.path.join(ОПС, "kc-ca-kazhdoe20.txt"), "a", encoding="utf-8")
заведено = 0; отсев = Counter()
for п0 in range(0, len(список), 20):
    пачка = список[п0:п0 + 20]
    строки = []
    for i, и in enumerate(пачка, 1):
        р = БАЗА.get(и, {}); f = SF.get(и, {})
        прод = (р.get("Продукция") or "").strip() or "; ".join(map(str, f.get("продукция") or []))
        строки.append("%d. %s; ОКВЭД %s; продукция: %s" % (i, р.get("Компания") or "", р.get("ОКВЭД основной") or "", прод[:300] or "-"))
    д = зов(KK.ЗАДАНИЕ.replace("{firmy}", "\n".join(строки)).replace("{{", "{").replace("}}", "}"), "f", None, 3000)
    if not д: print("пачка %d: модель не дала фраз" % (п0 // 20 + 1), flush=True); continue
    фразы = {int(x["n"]): x["t"] for x in д.get("f", []) if str(x.get("n", "")).isdigit()}
    for i, и in enumerate(пачка, 1):
        лз = ЛЕС[и]; em, fio, должн = лз["email"], лз.get("fio") or "", лз.get("dolzhn") or ""
        тех = bool(re.search(KK.ТЕХ, должн, re.I)) if должн else False
        ф = (фразы.get(i) or "").strip().replace("—", "-")
        запись = {"inn": и, "email": em, "fio": fio, "post": должн, "ts": datetime.now(timezone.utc).isoformat()}
        if not KK.фраза_годна(ф):
            запись["otsev"] = "фраза модели: %r" % ф[:120]; пиши(ЖУР_КАРТ, запись); отсев["фраза не прошла"] += 1; continue
        имя_комп = (БАЗА.get(и, {}).get("Компания") or "").strip()
        обр = K.обращение(fio) if fio else None
        _им = (обр or "").split()[:1]
        mb = random.choice([m for m in ящики if str(getattr(m, "from_name", "") or "").split()[:1] != _им] or ящики)
        менеджер = (str(getattr(mb, "from_name", "") or "").split(",")[0].split() or ["Сергей"])[0]
        з = random.sample(KK.ЗАК, 3)
        абз = [((обр + ", добрый день!") if обр else "Добрый день!") + " Меня зовут " + менеджер + ", я из Компрессор Центра. " + random.choice(KK.ПОВОД),
               ф + " " + random.choice(KK.ОХВАТ) + " " + random.choice(KK.ЗАК_ФР).format(z=", ".join(з[:-1]) + " и " + з[-1], zt=", ".join(KK.ЗАК_ТВ[x] for x in з[:-1]) + " и " + KK.ЗАК_ТВ[з[-1]]) + " " + random.choice(KK.СЕРВИС),
               random.choice(KK.ВОПРОС) + ("" if тех else " " + random.choice(KK.ПЕРЕСЛАТЬ))]
        тело = "\n\n".join(абз)
        тема = random.choice(KK.ТЕМЫ)
        есть = к.execute("SELECT id, inn FROM recipients WHERE lower(email)=?", (em,)).fetchone()
        if есть and есть[1] and ц(есть[1]) != и:
            запись["otsev"] = "адрес закреплён за другим ИНН %s" % есть[1]; пиши(ЖУР_КАРТ, запись); отсев["адрес за другим ИНН"] += 1; continue
        сейчас = datetime.now(timezone.utc).isoformat()
        if есть:
            rid = есть[0]
        else:
            with store._lock:
                rid = к.execute("INSERT INTO recipients (email, company_name, inn, segment, domain, tz, contact_name, source, extra_json, created_at, updated_at) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (em, имя_комп, и, "кц", em.split("@")[-1], "Europe/Moscow", fio, "kc-ca-1711",
                                json.dumps({"target_division": "kc", "stupen": должн}, ensure_ascii=False), сейчас, сейчас)).lastrowid
                к.commit()
        ключ = "%s|%s|%d" % (и, em, КАМП)
        if к.execute("SELECT 1 FROM confirm_reviews WHERE dedup_key=?", (ключ,)).fetchone():
            отсев["карточка уже есть"] += 1; continue
        mid, _шаг, почему = q._ensure_message(КАМП, int(rid))
        if not mid:
            запись["otsev"] = "сообщение не завелось: %s" % почему; пиши(ЖУР_КАРТ, запись); отсев["сообщение не завелось"] += 1; continue
        панель = json.dumps({"letter_division": "kc", "mailbox_id": mb.mailbox_id, "vruchnuyu": ИМЯ_КАМП, "company": {"name": имя_комп}}, ensure_ascii=False)
        with store._lock:
            к.execute("UPDATE messages SET mailbox_id=? WHERE id=?", (mb.mailbox_id, mid))
            кид = к.execute("INSERT INTO confirm_reviews (dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, panel_json, status, kind, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)", (ключ, КАМП, rid, mid, и, em, тема, тело, панель, сейчас, сейчас)).lastrowid
            к.commit()
        заведено += 1
        запись.update({"karta": кид, "mailbox": mb.mailbox_id, "tema": тема, "telo": тело}); пиши(ЖУР_КАРТ, запись)
        if i == 1:
            ГЛАЗ.write("=== #%d %s | %s (%s) | %s | %s\nТема: %s\n\n%s\n\n" % (кид, имя_комп, fio, должн, em, mb.mailbox_id, тема, тело)); ГЛАЗ.flush()
    print("пачка %d: карточек %d, отсев %s" % (п0 // 20 + 1, заведено, dict(отсев)), flush=True)
print("ГОТОВО: кампания %d «%s», карточек %d, отсев %s" % (КАМП, ИМЯ_КАМП, заведено, dict(отсев)), flush=True)
