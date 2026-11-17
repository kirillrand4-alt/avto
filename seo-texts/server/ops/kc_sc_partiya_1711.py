# -*- coding: utf-8 -*-
"""Письма КЦ «конец года» клиентам СЦ (успешные сделки сервис-центра: что-то у нас покупали). Владелец 17.11:
  1) убрать компании и контакты Алтайского края;
  2) выбрать наиболее логичный адрес (одно ФИО из Битрикса бывает проставлено на все почты компании — соотнести,
     кто похож на реального получателя);
  3) наиболее значимая роль; ФИО уверенно — с именем, не уверен — без имени;
  4) проба всех адресов;
  5) письма в каноне «КЦ ЦА конец года 17.11» (gen_9000_kc_kanon), карточки в «Подтвердить отправку».
Файл — дроп kc_sc_rassylka.csv (ИНН;Название компании;Почта;ФИО;Должность). В репозиторий НЕ кладётся.

ЭТАПЫ (журналы _ops, fsync, резюмируемо):
  1. выбор адреса моделью   kc-sc-vybor.jsonl     — порядок адресов (до 5) и имя для обращения по компании;
  2. лесенка + проба        kc-sc-lesenka.jsonl   — точная проба сверху вниз; «нет ящика», «нет MX», «неясно»,
                                                     «отказ пробе» — следующий адрес (владелец 17.11);
  3. письма                 kc-sc-kartochki.jsonl — кампания «КЦ СЦ клиенты 17.11», pending. Каждое 20-е — kc-sc-kazhdoe20.txt.
Отсев как в КЦ: стоп-лист, ответ/жалоба/отписка, активная сделка КЦ, КЦ писал на адрес < 15 дней, письмо компании в
очереди, адрес за другим ИНН. АВТООТПРАВКИ НЕТ.
    kc_sc_partiya_1711.py                 — сухой подсчёт
    kc_sc_partiya_1711.py --zapusk [--model=claude-opus-4-8] [--tolko-gotovye]   (--tolko-gotovye: письма без хвоста пробы)
    kc_sc_partiya_1711.py --hod"""
import csv, io, json, os, random, re, sqlite3, subprocess, sys, threading, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
ОПС = r"C:\sender\_ops"; ДР = r"C:\seostat\drop\drop-storage"
ЖУР_ВЫБ, ЖУР_ЛЕС, ЖУР_КАРТ = (os.path.join(ОПС, x) for x in ("kc-sc-vybor.jsonl", "kc-sc-lesenka.jsonl", "kc-sc-kartochki.jsonl"))
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "kc-sc.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--rabota"] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)


def читать_журнал(путь):
    з = {}
    if os.path.exists(путь):
        for с in io.open(путь, encoding="utf-8", errors="replace"):
            try: x = json.loads(с); з[x["kluch"]] = x
            except Exception: pass
    return з


if "--hod" in sys.argv:
    for и, п in (("выбор", ЖУР_ВЫБ), ("лесенка", ЖУР_ЛЕС), ("карточки", ЖУР_КАРТ)):
        з = читать_журнал(п).values()
        print(и, len(з), dict(Counter(x.get("status") or ("карточка" if x.get("karta") else str(x.get("otsev", "есть"))[:40]) for x in з)))
    try: print(io.open(os.path.join(ОПС, "kc-sc.log"), encoding="utf-8", errors="replace").read()[-900:])
    except Exception: pass
    sys.exit(0)

РАБОТА = "--rabota" in sys.argv
МОДЕЛЬ = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-4-8")
ИМЯ_КАМП = "КЦ СЦ клиенты 17.11"
os.environ["PROVIDER_THINKING_FIELD"] = "omit"
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server"); sys.path.insert(0, r"C:\sender\server\ops")
if РАБОТА:
    import msvcrt  # noqa: E402
    _зф = open(os.path.join(ОПС, "kc-sc.lock"), "a+")
    try: msvcrt.locking(_зф.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError: print("уже идёт другая копия — выхожу", flush=True); sys.exit(0)
from sender.config import Config               # noqa: E402
from sender.store import Store                 # noqa: E402
from sender.sdelki_napr import blok as сделка_блок   # noqa: E402
import gaz_kanon as K                          # noqa: E402
ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
_з = threading.Lock()


def пиши(путь, запись):
    with _з, io.open(путь, "a", encoding="utf-8") as ф:
        ф.write(json.dumps(запись, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())


# ---------------- 0. файл, Алтайский край, явный мусор ----------------
строки = list(csv.DictReader(io.open(os.path.join(ДР, "kc_sc_rassylka.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
к = store._conn
e = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=60)
o = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True, timeout=60)
РЕГ = {}
for i, р in o.execute("SELECT inn, region FROM obzvon WHERE region IS NOT NULL"): РЕГ.setdefault(ц(i), str(р))
for i, р in e.execute("SELECT inn, region FROM companies WHERE region IS NOT NULL AND region<>''"): РЕГ.setdefault(ц(i), str(р))
АЛТ_ИМЯ = re.compile(r"(?i)барнаул|бийск|рубцовск|новоалтайск|заринск|славгород|алтайск\w* кра|алейск|камень-на-оби")
НАШИ_ДОМЕНЫ = re.compile(r"(?i)@(prokompressor|rusprom|kompressor-center|compressor-center|meyer-corp|usort|vsefotoseparatory)\.|compressor-air-expert|compressor-pro|kompressor-pro|optic-sort|sort-systems|sorting-systems|food-sort|rentgen-")
МУСОР_ФИО = re.compile(r"(?i)больше не работает|не работает|уволил|наш менеджер|служба безопасности|бухгалт|^контакты$|автоответ")
сч0 = Counter(); КОМП = defaultdict(list); ИМЯ_К = {}
for р in строки:
    инн = ц(р.get("ИНН")); имя = (р.get("Название компании") or "").strip(); кл = инн or "имя:" + имя.lower()
    em = (р.get("Почта") or "").strip().lower(); fio = (р.get("ФИО") or "").strip(); дол = (р.get("Должность") or "").strip()
    рег = РЕГ.get(инн, "")
    if инн.startswith("22") or "алтайский" in рег.lower() or АЛТ_ИМЯ.search(имя) or АЛТ_ИМЯ.search(fio):
        сч0["Алтайский край"] += 1; continue
    if not em or "@" not in em or not K.адрес_годен(em): сч0["плохой адрес"] += 1; continue
    if "autoreply" in em or НАШИ_ДОМЕНЫ.search(em): сч0["автоответ / наш адрес"] += 1; continue
    if МУСОР_ФИО.search(fio + " " + дол): сч0["не получатель (уволен, наш менеджер, СБ, бухгалтерия)"] += 1; continue
    КОМП[кл].append({"email": em, "fio": fio, "dolzhn": дол}); ИМЯ_К[кл] = имя
print("строк %d, компаний после чистки %d | отсев строк %s" % (len(строки), len(КОМП), dict(сч0)), flush=True)

# ---------------- 1. правила КЦ ----------------
стоп = {str(v).strip().lower() for _, v in к.execute("SELECT scope, value FROM suppression")}
мёртв = {r[0].lower() for r in к.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
ответ = {ц(r[0]) for r in к.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
кам = {i: н for i, н in к.execute("SELECT id, name FROM campaigns")}
кц_к = {i for i, н in кам.items() if re.search(r"(?i)кц|компрессор|\bkc\b", н or "") and not re.search(r"(?i)meyer|мейер|фса|рентген|сепарат", н or "")}
кц_15 = {r[0].lower() for r in к.execute("SELECT email, campaign_id FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days')") if r[1] in кц_к}
в_очереди = set()
for em, inn in к.execute("SELECT lower(r.email), r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','sending','pending_review')"):
    в_очереди.add("@" + em); в_очереди.add(ц(inn))
чей = {r[0].lower(): ц(r[1]) for r in к.execute("SELECT email, inn FROM recipients WHERE email IS NOT NULL")}
try:
    sys.path.insert(0, r"C:\sender\sender")
    from sender.ne_nash import build_ne_nash
    не_наш = {ц(x) for x in (build_ne_nash().набор(None) or [])}
except Exception as ex:  # noqa: BLE001
    print("реестр «не наш» не прочитан: %s" % ex, flush=True); не_наш = set()
# 17.11 вычитка выбора: в сделках СЦ есть компрессорные сервисы и дилеры (покупали запчасти) — это конкуренты, не пишем
КОНК_ИМЯ = re.compile(r"(?i)компрессор|kompres|compres|пневмо|фильтрамакс|filtramax|\bсц\b|сервисн\w* центр компр")
сч1 = Counter(); ГОДН = {}; КОНК = []
for кл, ад in КОМП.items():
    инн = кл if not кл.startswith("имя:") else ""
    if (инн and инн in не_наш) or КОНК_ИМЯ.search(ИМЯ_К[кл]) or any(re.search(r"(?i)\bсц\)", а["fio"] or "") for а in ад):
        сч1["конкурент / компрессорный сервис / «не наш»"] += 1; КОНК.append(ИМЯ_К[кл] + (" [реестр]" if инн in не_наш else "")); continue
    if инн and (инн in стоп): сч1["компания в стоп-листе"] += 1; continue
    if инн and инн in ответ: сч1["был ответ/жалоба/отписка"] += 1; continue
    if инн and инн in в_очереди: сч1["письмо компании в очереди"] += 1; continue
    if инн and сделка_блок(к, инн, "kc"): сч1["активная сделка КЦ"] += 1; continue
    ост = []
    for а in ад:
        em = а["email"]
        if em in стоп or em.split("@")[-1] in стоп: сч1["адрес: стоп-лист"] += 1; continue
        if em in мёртв: сч1["адрес: мёртв по пробе"] += 1; continue
        if em in кц_15: сч1["адрес: КЦ писал < 15 дней"] += 1; continue
        if ("@" + em) in в_очереди: сч1["адрес: письмо в очереди"] += 1; continue
        if чей.get(em) and инн and чей[em] != инн: сч1["адрес: за другим ИНН"] += 1; continue
        if em not in {x["email"] for x in ост}: ост.append(а)
    if not ост: сч1["не осталось адреса"] += 1; continue
    ГОДН[кл] = ост
print("правила КЦ: компаний дальше %d | %s" % (len(ГОДН), dict(сч1)), flush=True)
print("конкуренты/компрессорные сервисы:", КОНК[:60], flush=True)
if not РАБОТА:
    print("сухой прогон: модель, проба и карточки не запускались. Боевой — --zapusk"); sys.exit(0)

# ---------------- 2. выбор адреса и имени моделью ----------------
import gen_provider as GP                         # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402


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


ВЫБОР = """Ты готовишь холодное письмо поставщика компрессоров (Компрессор Центр) бывшим клиентам сервиса. По каждой компании
даны контакты из Битрикса: почта | ФИО | должность. ФИО и должность в Битриксе грязные: одно ФИО менеджеры часто
проставляли на ВСЕ почты компании, в поле ФИО бывают роль, отдел, название компании, пометки.
Задача по каждой компании:
1) order — почты по убыванию логичности получателя письма про компрессорную (до 5). Выше: главный инженер, главный
   механик, энергетик, техдиректор, производство, сервис/эксплуатация оборудования, кто запрашивал компрессор; затем
   руководитель (директор, ген. директор); затем снабжение/закупки; затем общие адреса (info@, office@). Ниже всего:
   продажи, бухгалтерия, HR, личные почты непонятно чьи. Именная почта (фамилия/имя в адресе) человека с подходящей
   ролью — выше общей.
2) Для каждой почты из order: imya — обращение, ТОЛЬКО если ты уверен, что эта почта принадлежит человеку из ФИО:
   «Имя Отчество», если в ФИО есть имя и отчество, иначе «Имя». Уверен = ФИО стоит только на этой почте компании,
   ИЛИ имя/фамилия/инициалы совпадают с адресом (a.ivanov@ ↔ Иванов Андрей). Если одно ФИО стоит на нескольких почтах и
   адрес с ним не совпадает, если в ФИО отдел, роль, название компании или непонятно — imya пустое.
   rol — кто это коротко (гл.инженер, директор, снабжение, общий адрес, ...). teh — true, если это тех. служба
   (инженер, механик, энергетик, техдиректор, производство, сервис оборудования).
Не выдумывай почт, бери только данные. Ответ СТРОГО JSON:
{"k": [{"n": НОМЕР, "order": [{"email": "...", "imya": "", "rol": "", "teh": false}]}]}"""
ВЫБ = читать_журнал(ЖУР_ВЫБ)


def пачка_выбор(кусок):
    блоки = []
    for н, кл in enumerate(кусок, 1):
        блоки.append("%d. %s\n%s" % (н, ИМЯ_К[кл], "\n".join("   %s | %s | %s" % (а["email"], а["fio"] or "-", а["dolzhn"] or "-") for а in ГОДН[кл])))
    д = зов("\n\n".join(блоки), "k", ВЫБОР, 4000)
    if not д: return
    for x in д.get("k") or []:
        try: кл = кусок[int(x["n"]) - 1]
        except Exception: continue
        есть = {а["email"]: а for а in ГОДН[кл]}; пор = []
        for у in x.get("order") or []:
            em = str(у.get("email") or "").strip().lower()
            if em not in есть or em in {p["email"] for p in пор}: continue
            им = str(у.get("imya") or "").strip()
            fio = есть[em]["fio"].lower().replace("ё", "е")
            # имя должно реально быть в ФИО этого контакта и быть именем (а не фамилией/ролью)
            if им and not (all(сл.lower().replace("ё", "е") in fio for сл in им.split()) and им.split()[0].lower() in K.ИМЕНА and len(им.split()) <= 2):
                им = ""
            пор.append({"email": em, "imya": им, "rol": str(у.get("rol") or "")[:40], "teh": bool(у.get("teh")), "fio": есть[em]["fio"], "dolzhn": есть[em]["dolzhn"]})
        if пор:
            з = {"kluch": кл, "order": пор, "ts": datetime.now(timezone.utc).isoformat()}; пиши(ЖУР_ВЫБ, з); ВЫБ[кл] = з


к_выб = [кл for кл in ГОДН if кл not in ВЫБ]
print("выбор адреса: к модели %d (уже %d)" % (len(к_выб), len(ГОДН) - len(к_выб)), flush=True)
with ThreadPoolExecutor(6) as пул:
    list(пул.map(пачка_выбор, [к_выб[i:i + 10] for i in range(0, len(к_выб), 10)]))
print("выбор готов: %d компаний, с именем на первой ступени %d" % (len([кл for кл in ГОДН if кл in ВЫБ]), sum(1 for кл in ГОДН if кл in ВЫБ and ВЫБ[кл]["order"][0]["imya"])), flush=True)

# ---------------- 3. лесенка проб ----------------
from sender.addr_probe import build_addr_probe   # noqa: E402
import proba_tochnaya as P                          # noqa: E402
_петля = build_addr_probe(store, cfg)
проба = getattr(_петля, "probe", None) or getattr(_петля, "probe_")
проба.per_domain = 10 ** 6
НЕ_БРАТЬ = ("нет ящика", "нет MX", "неясно", "отказ пробе")
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru", "ya.ru", "yandex.by", "yandex.com", "narod.ru", "gmail.com", "rambler.ru"}
ЛЕС = читать_журнал(ЖУР_ЛЕС)
шаг = {кл: 0 for кл in ГОДН if кл in ВЫБ and кл not in ЛЕС}
if "--tolko-gotovye" in sys.argv:   # владелец 17.11: «начинай письма» — письма по уже пробованным, хвост пробы позже
    print("хвост пробы отложен: %d компаний" % len(шаг), flush=True); шаг = {}
посл = {}; сп = Counter()
print("лесенка: к пробе %d" % len(шаг), flush=True)
while шаг:
    двиг = False
    for кл in list(шаг):
        пор = ВЫБ[кл]["order"]; i = шаг[кл]
        if i >= len(пор):
            з = {"kluch": кл, "status": "все мертвы", "ts": datetime.now(timezone.utc).isoformat()}; пиши(ЖУР_ЛЕС, з); ЛЕС[кл] = з; del шаг[кл]; двиг = True; continue
        адрес = пор[i]["email"]
        есть = проба.cached(адрес)
        if есть and str(есть.get("verdict") or "") == "неясно": есть = None
        if есть:
            вер = str(есть.get("verdict") or "неясно")
        else:
            дом = адрес.rsplit("@", 1)[-1]
            if дом in КРУПНЫЕ and time.monotonic() - посл.get(дом, -1e9) < 20.0: continue
            посл[дом] = time.monotonic()
            try: вер, _к, _о, _м = P.проба(адрес)
            except Exception as ex:  # noqa: BLE001
                вер, _к, _о, _м = "неясно", None, str(ex)[:200], ""
            P.в_базы(адрес, вер, _к, _о, _м); сп[вер] += 1
        двиг = True
        if вер in НЕ_БРАТЬ: шаг[кл] = i + 1; continue
        з = dict(пор[i], kluch=кл, status="выбран", verdict=вер, stupen=i, ts=datetime.now(timezone.utc).isoformat()); пиши(ЖУР_ЛЕС, з); ЛЕС[кл] = з; del шаг[кл]
        if sum(сп.values()) % 50 == 0: print("проба: %s, осталось %d" % (dict(сп), len(шаг)), flush=True)
    if not двиг: time.sleep(3)
живые = [кл for кл in ГОДН if ЛЕС.get(кл, {}).get("status") == "выбран"]
print("лесенка готова: проб %s; живой адрес у %d, все мертвы у %d" % (dict(сп), len(живые), sum(1 for кл in ГОДН if ЛЕС.get(кл, {}).get("status") == "все мертвы")), flush=True)

# ---------------- 4. письма по канону и карточки ----------------
from sender.ai_quota import build_ai_quota   # noqa: E402
import gen_9000_kc_kanon as KK               # noqa: E402
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
список = [кл for кл in живые if кл not in КАРТ]
print("письма: к генерации %d" % len(список), flush=True)
ГЛАЗ = io.open(os.path.join(ОПС, "kc-sc-kazhdoe20.txt"), "a", encoding="utf-8")


def о_компании(кл):
    инн = кл if not кл.startswith("имя:") else ""
    r_ = e.execute("SELECT name, okved, substr(COALESCE(activity,''),1,300) FROM companies WHERE inn=?", (инн,)).fetchone() if инн else None
    ок = (r_[1] if r_ else "") or ((o.execute("SELECT okved_main FROM obzvon WHERE inn=? LIMIT 1", (инн,)).fetchone() or [""])[0] if инн else "")
    прод = ""
    if инн:
        ф = e.execute("SELECT facts_json FROM site_facts WHERE inn=?", (инн,)).fetchone()
        try: прод = "; ".join(map(str, (json.loads(ф[0]) or {}).get("продукция") or []))[:300] if ф else ""
        except Exception: прод = ""
    return "%s; ОКВЭД %s; %s" % (ИМЯ_К[кл], ок or "-", прод or (r_[2] if r_ else "") or "-")


_ТР = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a","b","v","g","d","e","e","zh","z","i","y","k","l","m","n","o","p","r","s","t","u","f","kh","ts","ch","sh","sch","","y","","e","yu","ya"]))
def _лат(с): return "".join(_ТР.get(ч, ч) for ч in с.lower())
def _вар(с):
    л = _лат(с); return {л, л.replace("kh", "h"), л.replace("y", "i"), л.replace("ts", "c"), л.replace("zh", "j")}


def имя_уверено(кл, em, imya, fio):
    """Владелец 17.11: одно ФИО на нескольких почтах компании — имя только если адрес совпадает с именем/фамилией."""
    лок0 = em.split("@")[0].lower().replace(".", "").replace("_", "").replace("-", "")
    if not imya:
        обр = K.обращение(fio or "")
        слова = [сл for сл in re.findall(r"[А-Яа-яЁё]{4,}", fio or "") if сл.lower() not in K.ИМЕНА and not re.search(r"(?i)(вич|вна|ична)$", сл)]
        if обр and слова and any(в[:5] in лок0 for сл in слова for в in _вар(сл) if len(в) >= 5): return обр
        return ""
    сколько = sum(1 for а in КОМП.get(кл, []) if (а["fio"] or "").strip() == (fio or "").strip())
    if сколько <= 1: return imya
    лок = em.split("@")[0].lower().replace(".", "").replace("_", "").replace("-", "")
    for сл in re.findall(r"[А-Яа-яЁё]{3,}", fio or ""):
        if any(в[:4] in лок for в in _вар(сл) if len(в) >= 4): return imya
    return ""


заведено = 0; отсев = Counter()
for п0 in range(0, len(список), 20):
    пачка = список[п0:п0 + 20]
    д = зов(KK.ЗАДАНИЕ.replace("{firmy}", "\n".join("%d. %s" % (i, о_компании(кл)) for i, кл in enumerate(пачка, 1))).replace("{{", "{").replace("}}", "}"), "f", None, 3000)
    if not д: print("пачка %d: модель не дала фраз" % (п0 // 20 + 1), flush=True); continue
    фразы = {int(x["n"]): x["t"] for x in д.get("f", []) if str(x.get("n", "")).isdigit()}
    for i, кл in enumerate(пачка, 1):
        лз = ЛЕС[кл]; em = лз["email"]; инн = кл if not кл.startswith("имя:") else ""
        ф = (фразы.get(i) or "").strip().replace("—", "-")
        запись = {"kluch": кл, "inn": инн, "email": em, "imya": лз.get("imya"), "rol": лз.get("rol"), "ts": datetime.now(timezone.utc).isoformat()}
        if not KK.фраза_годна(ф):
            запись["otsev"] = "фраза модели: %r" % ф[:120]; пиши(ЖУР_КАРТ, запись); отсев["фраза не прошла"] += 1; continue
        обр = имя_уверено(кл, em, лз.get("imya") or "", лз.get("fio") or "")
        if (лз.get("imya") or "") and not обр: отсев["имя снято: одно ФИО на нескольких почтах"] += 1
        if not (лз.get("imya") or "") and обр: отсев["имя добавлено: фамилия в адресе"] += 1
        _им = обр.split()[:1]
        mb = random.choice([m for m in ящики if str(getattr(m, "from_name", "") or "").split()[:1] != _им] or ящики)
        менеджер = (str(getattr(mb, "from_name", "") or "").split(",")[0].split() or ["Сергей"])[0]
        з = random.sample(KK.ЗАК, 3)
        абз = [((обр + ", добрый день!") if обр else "Добрый день!") + " Меня зовут " + менеджер + ", я из Компрессор Центра. " + random.choice(KK.ПОВОД),
               ф + " " + random.choice(KK.ОХВАТ) + " " + random.choice(KK.ЗАК_ФР).format(z=", ".join(з[:-1]) + " и " + з[-1], zt=", ".join(KK.ЗАК_ТВ[x] for x in з[:-1]) + " и " + KK.ЗАК_ТВ[з[-1]]) + " " + random.choice(KK.СЕРВИС),
               random.choice(KK.ВОПРОС) + ("" if лз.get("teh") else " " + random.choice(KK.ПЕРЕСЛАТЬ))]
        тело = "\n\n".join(абз); тема = random.choice(KK.ТЕМЫ)
        есть = к.execute("SELECT id, inn FROM recipients WHERE lower(email)=?", (em,)).fetchone()
        if есть and есть[1] and инн and ц(есть[1]) != инн:
            запись["otsev"] = "адрес за другим ИНН %s" % есть[1]; пиши(ЖУР_КАРТ, запись); отсев["адрес за другим ИНН"] += 1; continue
        сейчас = datetime.now(timezone.utc).isoformat()
        if есть:
            rid = есть[0]
        else:
            with store._lock:
                rid = к.execute("INSERT INTO recipients (email, company_name, inn, segment, domain, tz, contact_name, source, extra_json, created_at, updated_at) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (em, ИМЯ_К[кл], инн or None, "кц", em.split("@")[-1], "Europe/Moscow", лз.get("fio") or "", "kc-sc-1711",
                                json.dumps({"target_division": "kc", "stupen": лз.get("rol"), "sc_klient": True}, ensure_ascii=False), сейчас, сейчас)).lastrowid
                к.commit()
        ключ = "%s|%s|%d" % (инн or кл, em, КАМП)
        if к.execute("SELECT 1 FROM confirm_reviews WHERE dedup_key=?", (ключ,)).fetchone(): отсев["карточка уже есть"] += 1; continue
        mid, _ш, почему = q._ensure_message(КАМП, int(rid))
        if not mid:
            запись["otsev"] = "сообщение не завелось: %s" % почему; пиши(ЖУР_КАРТ, запись); отсев["сообщение не завелось"] += 1; continue
        панель = json.dumps({"letter_division": "kc", "mailbox_id": mb.mailbox_id, "vruchnuyu": ИМЯ_КАМП, "company": {"name": ИМЯ_К[кл]}}, ensure_ascii=False)
        with store._lock:
            к.execute("UPDATE messages SET mailbox_id=? WHERE id=?", (mb.mailbox_id, mid))
            кид = к.execute("INSERT INTO confirm_reviews (dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, panel_json, status, kind, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,'pending','outbound',?,?)", (ключ, КАМП, rid, mid, инн, em, тема, тело, панель, сейчас, сейчас)).lastrowid
            к.commit()
        заведено += 1
        запись.update({"karta": кид, "mailbox": mb.mailbox_id, "tema": тема, "telo": тело}); пиши(ЖУР_КАРТ, запись)
        if i == 1:
            ГЛАЗ.write("=== #%d %s | %s (%s) | %s | %s\nТема: %s\n\n%s\n\n" % (кид, ИМЯ_К[кл], лз.get("fio"), лз.get("rol"), em, mb.mailbox_id, тема, тело)); ГЛАЗ.flush()
    print("пачка %d: карточек %d, отсев %s" % (п0 // 20 + 1, заведено, dict(отсев)), flush=True)
print("ГОТОВО: кампания %d «%s», карточек %d, отсев %s" % (КАМП, ИМЯ_КАМП, заведено, dict(отсев)), flush=True)
