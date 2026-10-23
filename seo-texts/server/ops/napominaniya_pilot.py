# -*- coding: utf-8 -*-
"""Пилот напоминаний Meyer в ту же ветку (владелец 23.10: заходы 4,5,6,8,9;
«покажи что в итоге получится сначала»).

Компания подходит (как napominaniya_podschet.py): последнее письмо Meyer
старше N дней, ни на какой её адрес не было ответа/автоответа/жалобы/отбивки/
лида, свежих писем любого направления, стоп-листа, приговора пробы.
Адрес — один, лучший: проба «есть» > «принимает всё» > нет вердикта (неясно/отказ
— мимо); именной > ролевой; потом свежее письмо. Re: в ветку письма на этот
адрес, с того же ящика (ящик должен быть в конфиге и не на паузе).

Текст собирается из утверждённых строк (email-assistant/NAPOMINANIYA.md):
приветствие + первая фраза (заход по кругу) + вторая фраза + запрос контакта.
Модель провайдера только заполняет слоты по первому письму (сырьё/продукция в
падежах, сортировка или рентген, зерно ли) — текст она не пишет.

    napominaniya_pilot.py --pokaz=10          показать, ничего не заводить
    napominaniya_pilot.py --zavesti=300       завести карточки (kind=reply, pending)
Журнал (резюм): _ops/napominaniya-pilot.jsonl; показ — на дроп napominaniya-pokaz.txt."""
import difflib
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.validation import _BASE_ROLE_PREFIXES as РОЛИ  # noqa: E402

_а = dict(a.lstrip("-").split("=", 1) for a in sys.argv[1:] if "=" in a)
ПОКАЗ = int(_а.get("pokaz", 0) or 0)
ЗАВЕСТИ = int(_а.get("zavesti", 0) or 0)
ДНЕЙ = int(_а.get("dney", 15))
ЖУР = r"C:\sender\_ops\napominaniya-pilot.jsonl"
МОДЕЛЬ = _а.get("model", "claude-sonnet-4-6")
if not (ПОКАЗ or ЗАВЕСТИ):
    print(__doc__)
    sys.exit(0)
# отсоединённо (раннер режет задачу на 900 с): --zapusk + те же ключи; журнал — _ops/napominaniya-pilot.log
if "--zapusk" in sys.argv:
    import subprocess
    import time
    л = io.open(r"C:\sender\_ops\napominaniya-pilot.log", "w", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [a for a in sys.argv[1:] if a != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(10)
    print("запущен, pid %d, жив %s" % (п.pid, п.poll() is None))
    sys.exit(0)

# ----------------------------------------------------------------- строки --
ЖЕН_ИСКЛ = {"никита", "илья", "кузьма", "фома", "лука", "савва", "данила"}


def м_ж(т, жен):
    """«Писал/Писала» -> по полу отправителя."""
    return re.sub(r"(\w+)/(\w+)", lambda m: m.group(2) if жен else m.group(1), т)


# заход -> (первая фраза сортировка, вторая фраза сортировка, первая рентген, вторая рентген)
ЗАХОДЫ = {
    4: ("Что больше мешает в {П}: камни, сор или {ЗЕРНО}?",
        "Спрашиваю в продолжение своего письма про фотосепараторы Meyer, оно могло затеряться. "
        "Если пришлёте образец, бесплатно прогоним его на тестовой сортировке и покажем, что уберёт машина.",
        None, None),
    5: ("Чем сейчас убираете брак из {Р}: {ЧЕМ}?",
        "Писал/Писала вам недавно про фотосепараторы и хочу понять, есть ли смысл что-то предлагать. "
        "Можем и просто бесплатно проверить ваш образец на тестовой сортировке.",
        None, None),
    6: ("Бывают ли претензии покупателей по посторонним включениям в {ПРОД_П}?",
        "Возвращаюсь к своему письму про контроль качества: фотосепаратор убирает такие включения ещё на входе. "
        "Образец можем бесплатно проверить на тестовой сортировке.",
        "Бывают ли претензии покупателей по посторонним включениям в {ПРОД_П}?",
        "Возвращаюсь к своему письму про рентген-инспекцию: она находит стекло, камень и металл уже в готовой упаковке."),
    8: ("Коротко по прошлому письму о сортировке {Р}: одно уточнение.",
        "Можем бесплатно прогнать ваш образец на тестовой сортировке и показать результат, "
        "даже если покупать оборудование пока не планируете.",
        "Коротко по прошлому письму о контроле качества {ПРОД_Р}: одно уточнение.",
        "Как сейчас проверяете готовую продукцию на посторонние включения: визуально, металлодетектором или уже стоит рентген?"),
    9: ("Сколько {Р} уходит в отсев при {ОЧИСТКЕ}? Можно вернуть часть.",
        "Писал/Писала об этом недавно, письмо могло затеряться. Пришлите образец: бесплатно прогоним "
        "на тестовой сортировке и покажем, сколько годного можно вернуть из отсева.",
        None, None),
}
КОНТАКТ = [
    "Кто в вашей компании отвечает за качество {Р} на входе? Перешлю ему коротко, с вариантом бесплатной пробы.",
    "Если удобно, можем коротко созвониться с тем, кто отвечает за качество {Р}, минут на 10.",
    "Может, проще обсудить голосом? Подскажите, с кем можно созвониться по сортировке {Р} и когда удобно.",
    "Буду рад/рада короткому звонку с вашим технологом или главным инженером. Подскажите контакт или удобное время.",
    "Можно просто прислать номер того, кто занимается очисткой {Р}, сам/сама наберу в удобное время.",
]
КОНТАКТ_РЕНТГЕН = [
    "Кто в вашей компании отвечает за контроль качества {ПРОД_Р}? Перешлю ему коротко.",
    "Если удобно, можем коротко созвониться с тем, кто отвечает за качество {ПРОД_Р}, минут на 10.",
    "Буду рад/рада короткому звонку с вашим технологом или главным инженером. Подскажите контакт или удобное время.",
    "Можно просто прислать номер того, кто отвечает за контроль продукции, сам/сама наберу в удобное время.",
]


def собрать(сл, заход, к_номер, имя, жен):
    рентген = сл.get("tip") == "rentgen"
    з = ЗАХОДЫ[заход]
    if рентген:
        if not з[2]:
            return None
        п1, п2 = з[2], з[3]
        контакт = КОНТАКТ_РЕНТГЕН[к_номер % len(КОНТАКТ_РЕНТГЕН)]
    else:
        п1, п2 = з[0], з[1]
        контакт = КОНТАКТ[к_номер % len(КОНТАКТ)]
    зерно = bool(сл.get("zerno"))
    подст = {
        "{Р}": сл.get("syrye_r") or "сырья", "{П}": сл.get("syrye_p") or "сырье",
        "{ПРОД_Р}": сл.get("prod_r") or "продукции", "{ПРОД_П}": сл.get("prod_p") or "продукции",
        "{ЗЕРНО}": "битое зерно" if зерно else "посторонние включения",
        "{ЧЕМ}": "триером, ситами или вручную" if зерно else "ситами, вручную или уже стоит оптика",
        "{ОЧИСТКЕ}": "очистке" if зерно else "сортировке",
    }
    т = []
    for ч in (п1, п2, контакт):
        for к, в in подст.items():
            ч = ч.replace(к, в)
        т.append(м_ж(ч, жен))
    привет = ("%s, добрый день!" % имя) if имя else "Добрый день!"
    return привет + "\n\n" + т[0] + " " + т[1] + "\n\n" + т[2]


# ------------------------------------------------------------- отбор ------
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
ящики = {}
for mb in cfg.mailboxes():
    s = st.get_mailbox_state(mb.mailbox_id)
    if mb.division == "meyer" and not (s and getattr(s, "paused", False)):
        ящики[mb.mailbox_id] = mb.from_name
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
сейчас = datetime.now(timezone.utc)
порог = (сейчас - timedelta(days=ДНЕЙ)).strftime("%Y-%m-%dT%H:%M:%S")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
мк = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
пол = {r[0]: (str(r[1] or "") or "rid%d" % r[0], (r[2] or "").lower(), r[3] or "") for r in
       c.execute("SELECT id, inn, email, company_name FROM recipients")}
отпр = {}
for mid, rid, cid, sent, mb, rfc, thr, subj in c.execute(
        "SELECT id, recipient_id, campaign_id, sent_at, mailbox_id, rfc_message_id, thread_id, subject "
        "FROM messages WHERE status='sent' AND sent_at IS NOT NULL"):
    инн = пол.get(rid, ("rid%d" % rid,))[0]
    отпр.setdefault(инн, []).append(dict(mid=mid, rid=rid, cid=cid, sent=sent, mb=mb, rfc=rfc, thr=thr, subj=subj or ""))
плохие = set()
for (rid,) in c.execute("SELECT DISTINCT recipient_id FROM events WHERE event_type IN ('reply','reply_auto','complaint','dsn','bounce')"):
    if rid in пол:
        плохие.add(пол[rid][0])
try:
    for (rid,) in c.execute("SELECT DISTINCT recipient_id FROM leads"):
        if rid in пол:
            плохие.add(пол[rid][0])
except sqlite3.Error:
    pass
стоп = {(s, v.lower()) for s, v in c.execute("SELECT scope, value FROM suppression")}
проба = {r[0].lower(): r[1] for r in c.execute("SELECT email, verdict FROM addr_probe")}
уже = set()
if os.path.exists(ЖУР):
    for s in io.open(ЖУР, encoding="utf-8"):
        try:
            уже.add(json.loads(s)["inn"])
        except (ValueError, KeyError):
            pass
кандидаты = []
for инн, сп in отпр.items():
    мей = [x for x in сп if x["cid"] in мк]
    if not мей or инн in плохие or инн in уже:
        continue
    if max(x["sent"] for x in сп) >= порог:
        continue
    лучшие = []
    for x in мей:
        if x["rid"] not in пол:
            continue
        em = пол[x["rid"]][1]
        в = проба.get(em, "")
        if в in ("нет ящика", "нет MX") or (в and в not in ("есть", "принимает всё")):
            continue
        if ("email", em) in стоп or ("domain", em.split("@")[-1]) in стоп:
            continue
        if x["mb"] not in ящики or not x["rfc"]:
            continue
        лок = em.split("@")[0]
        # отдел кадров и бухгалтерия про сортировку сырья не решают — мимо
        if re.match(r"(hr|kadr|buh|rezume|resume|job|vakans)", лок):
            continue
        роль = лок.split(".")[0].split("_")[0] in РОЛИ
        лучшие.append(((0 if в == "есть" else 1 if в == "принимает всё" else 2), 1 if роль else 0, "~" + x["sent"], x))
    if not лучшие:
        continue
    лучший = sorted(лучшие, key=lambda t: (t[0], t[1], t[2]))[0][3]
    # для порядка — давность последнего письма компании (старые вперёд)
    кандидаты.append((max(x["sent"] for x in мей), инн, лучший))
кандидаты.sort()
НАДО = ПОКАЗ or ЗАВЕСТИ
print("подходит компаний: %d, берём %d" % (len(кандидаты), НАДО), flush=True)

# --------------------------------------------------------- слоты моделью --
import gen_provider as GP  # noqa: E402

ЗАДАНИЕ = """Ниже — наши первые письма компаниям (направление Meyer: фотосепараторы и
рентген-инспекция). По каждому письму определи:
- tip: "sortirovka" если письмо про фотосепараторы/сортировку сырья, "rentgen" если про рентген-инспекцию готовой продукции;
- zerno: true, если сырьё компании - зерно/крупа/бобовые/семена (там есть «битое зерно»), иначе false;
- syrye_r: сырьё компании в родительном падеже, 1-3 слова, без «вашего» (пшеницы; подсолнечника; орехов; пластика). Нет ясности - "";
- syrye_p: то же в предложном падеже без предлога (пшенице; подсолнечнике; орехах). Нет ясности - "";
- prod_r: продукция компании в родительном падеже, 1-3 слова (муки; растительного масла; готовой продукции). Нет ясности - "";
- prod_p: то же в предложном без предлога (муке; растительном масле). Нет ясности - "".
Бери только то, что прямо есть в письме. Ничего не выдумывай. Несколько культур - назови главную или общее слово (зерна).

{pisma}

Ответ - СТРОГО JSON: {{"firmy": [{{"n": 1, "tip": "...", "zerno": true, "syrye_r": "...", "syrye_p": "...", "prod_r": "...", "prod_p": "..."}}]}}"""


def слоты(пачка):
    тексты = []
    for i, (инн, x, тело) in enumerate(пачка, 1):
        тексты.append("ПИСЬМО %d (компания: %s)\n%s" % (i, пол[x["rid"]][2][:80], тело[:1500]))
    m = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ.replace("{pisma}", "\n\n---\n\n".join(тексты))
                         .replace("{{", "{").replace("}}", "}")}], МОДЕЛЬ, 3000, thinking=False, effort="low")
    т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
    д, _ = json.JSONDecoder(strict=False).raw_decode(т[т.find("{"):])
    out = {}
    for f in д.get("firmy") or []:
        try:
            out[int(f.get("n"))] = f
        except (TypeError, ValueError):
            pass
    return out


ПЕРЕСКАЗ = """Ниже - черновики коротких напоминаний (Re: в ветку нашего прошлого письма,
ответа не было). Перепиши КАЖДЫЙ своими словами так, чтобы все письма пачки
звучали по-разному: разные слова, порядок, длина фраз, разное начало. Пишет живой
менеджер Meyer (фотосепараторы, рентген-инспекция), не робот.

ЖЁСТКО:
- смысл каждой части сохранить: первая фраза (сразу после приветствия) - тот же
  вопрос или предложение, она видна в превью и должна цеплять; дальше - отсылка к
  прошлому письму и то же предложение; в конце - та же просьба о контакте/звонке;
- приветствие: «{{Имя}}, добрый день!», «Добрый день!» или «Здравствуйте!» (имя - только если оно есть в черновике);
- ничего не добавлять: никаких фактов о компании, цифр, цен, сроков, ссылок, обещаний;
  «бесплатно» - только если оно есть в черновике;
- не писать «без обязательств», «надеюсь, у вас всё хорошо», «хотел бы предложить»;
- род отправителя как в черновике (писал/писала, рад/рада);
- без длинного тире, только дефис или запятая; 2-4 предложения плюс приветствие;
- без подписи.

{pisma}

Ответ - СТРОГО JSON: {{"pisma": [{{"n": 1, "tekst": "..."}}]}}"""


def пересказ(черновики):
    тексты = ["ЧЕРНОВИК %d (отправитель - %s)\n%s" % (i, "женщина" if ж else "мужчина", т)
              for i, (т, ж) in enumerate(черновики, 1)]
    m = GP._raw_stream([{"role": "user", "content": ПЕРЕСКАЗ.replace("{pisma}", "\n\n---\n\n".join(тексты))
                         .replace("{{", "{").replace("}}", "}")}], МОДЕЛЬ, 4000, thinking=False, effort="low")
    т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
    нач = т.find('{"pisma"')
    if нач < 0:
        нач = т.find("{\n")
    д, _ = json.JSONDecoder(strict=False).raw_decode(т[нач:])
    out = {}
    for f in д.get("pisma") or []:
        try:
            out[int(f.get("n"))] = str(f.get("tekst") or "").strip()
        except (TypeError, ValueError):
            pass
    return out


ЗАПРЕТ = re.compile(r"—|без обязательств|http|www\.|надеюсь", re.I)


def годен(нов, черн):
    if not нов or ЗАПРЕТ.search(нов) or len(нов) > len(черн) * 1.4 or len(нов) < len(черн) * 0.5:
        return False
    if not set(re.findall(r"\d+", нов)) <= set(re.findall(r"\d+", черн)):
        return False
    if "бесплатн" in нов.lower() and "бесплатн" not in черн.lower():
        return False
    return True


def чисто(в):
    в = str(в or "").strip().strip(".,;").lower()
    return в if (в and len(в) <= 40 and not re.search(r"[\d\"«»—]", в)) else ""


ИМЯ_ИЗ_ПИСЬМА = re.compile(r"^\s*([А-ЯЁ][а-яё]+)(?:\s+[А-ЯЁ][а-яё]+)?,\s*(?:добрый|здравствуйте)", re.M)
ПОДПИСЬ_ИМЯ = re.compile(r"Меня зовут\s+([А-ЯЁ][а-яё]+)")
from collections import Counter  # noqa: E402
отсев = Counter()
готово, номер = [], 0
ж = io.open(ЖУР, "a", encoding="utf-8") if ЗАВЕСТИ else None
cs = None
if ЗАВЕСТИ:
    from sender.wiring import build_deps    # noqa: E402
    cs = build_deps(cfg, st, dry_run=True).confirm
i = 0
while len(готово) < НАДО and i < len(кандидаты):
    пачка = []
    while len(пачка) < 10 and i < len(кандидаты):
        _, инн, x = кандидаты[i]
        i += 1
        тело = (c.execute("SELECT body_rendered FROM messages WHERE id=?", (x["mid"],)).fetchone() or [""])[0] or ""
        if len(тело) < 200:
            continue
        пачка.append((инн, x, тело))
    if not пачка:
        continue
    try:
        сл = слоты(пачка)
    except Exception as ex:  # noqa: BLE001
        print("слоты не пришли:", str(ex)[:150], flush=True)
        continue
    черн_пачки = []
    for n, (инн, x, тело) in enumerate(пачка, 1):
        с = сл.get(n) or {}
        с = {**{k: чисто(с.get(k)) for k in ("syrye_r", "syrye_p", "prod_r", "prod_p")},
             "tip": "rentgen" if str(с.get("tip")) == "rentgen" else "sortirovka", "zerno": bool(с.get("zerno"))}
        # тема первого письма сильнее модели: «рентген» в теме — значит рентген
        if "рентген" in x["subj"].lower():
            с["tip"] = "rentgen"
        elif re.search(r"сырь|сортир|зерн", x["subj"].lower()):
            с["tip"] = "sortirovka"
        if bool(с["syrye_r"]) != bool(с["syrye_p"]):
            с["syrye_r"] = с["syrye_p"] = ""
        if bool(с["prod_r"]) != bool(с["prod_p"]):
            с["prod_r"] = с["prod_p"] = ""
        им = ИМЯ_ИЗ_ПИСЬМА.search(тело)
        имя = им.group(1) if им and им.group(1) not in ("Добрый", "Здравствуйте", "Уважаемый", "Уважаемая") else ""
        отпр_имя = (ПОДПИСЬ_ИМЯ.search(тело) or [None, (ящики.get(x["mb"]) or "").split(" ")[0]])[1] or ""
        жен = отпр_имя.lower().endswith(("а", "я")) and отпр_имя.lower() not in ЖЕН_ИСКЛ
        варианты = [4, 5, 6, 8, 9] if с["tip"] != "rentgen" else [6, 8]
        заход = варианты[номер % len(варианты)]
        # строка контакта — своя у каждой компании (по ИНН), независимо от захода:
        # раньше менялась раз в пять писем, и в показе до номера не доходило
        к_номер = int(hashlib.md5(str(инн).encode()).hexdigest(), 16)
        текст = собрать(с, заход, к_номер, имя, жен)
        номер += 1
        if not текст:
            continue
        тема = x["subj"] if x["subj"].lower().startswith("re:") else "Re: " + x["subj"]
        em = пол[x["rid"]][1]
        запись = dict(inn=инн, email=em, mailbox=x["mb"], v_otvet_na=x["mid"], zahod=заход, sloty=с,
                      tema=тема, telo=текст, imya=имя, otpravitel=отпр_имя, zhen=жен, pervoe=x["sent"][:10])
        черн_пачки.append((запись, x))
    # 300 писем из одних строк — шаблон для спам-фильтра (владелец 23.10:
    # «слишком одинаково, в спам улетим»): модель пересказывает каждое,
    # смысл утверждённых строк остаётся; похожие на уже готовые — мимо.
    try:
        нов = пересказ([(з["telo"], з["zhen"]) for з, _ in черн_пачки]) if черн_пачки else {}
    except Exception as ex:  # noqa: BLE001
        print("пересказ не пришёл:", str(ex)[:150], flush=True)
        нов = {}
    for n, (запись, x) in enumerate(черн_пачки, 1):
        if len(готово) >= НАДО:
            break
        т = нов.get(n, "")
        if not годен(т, запись["telo"]):
            отсев["пересказ не прошёл проверку"] += 1
            continue
        if any(difflib.SequenceMatcher(None, т, г["telo"]).ratio() > 0.6 for г in готово[-200:]):
            отсев["слишком похоже на готовое"] += 1
            continue
        запись["chernovik"], запись["telo"] = запись["telo"], т
        if ЗАВЕСТИ:
            р = cs.submit_reply(reply_to=запись["email"], subject=запись["tema"], body=т, in_reply_to=x["rfc"],
                                thread_id=x["thr"], recipient_id=x["rid"], inn=запись["inn"],
                                panel={"mailbox_id": x["mb"], "napominanie": запись["zahod"],
                                       "vruchnuyu": "пилот напоминаний 23.10"})
            запись["karta"] = getattr(р, "review_id", None) or str(р)
            ж.write(json.dumps(запись, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())
        готово.append(запись)
    print("готово %d, отсев %s" % (len(готово), dict(отсев)), flush=True)

вых = []
for з in готово:
    вых.append("=" * 70 + "\nЗаход %s | %s | %s | первое письмо %s | от %s (%s)\nТема: %s\n\n%s" % (
        з["zahod"], пол.get(next((x["rid"] for x in отпр[з["inn"]] if x["mid"] == з["v_otvet_na"]), 0), ("", "", ""))[2][:60],
        з["email"], з["pervoe"], з["mailbox"], з["otpravitel"], з["tema"], з["telo"]))
текст = "\n\n".join(вых) + "\n"
io.open(r"C:\sender\_ops\napominaniya-pokaz.txt", "w", encoding="utf-8").write(текст)
try:
    requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/napominaniya-pokaz.txt",
                 data=текст.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
except Exception as ex:  # noqa: BLE001
    print("на дроп не ушло:", ex)
print("отсев:", dict(отсев))
print("итог: %d напоминаний%s" % (len(готово), ", карточки заведены" if ЗАВЕСТИ else " (показ, ничего не заведено)"))
