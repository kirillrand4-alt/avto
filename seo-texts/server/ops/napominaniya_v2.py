# -*- coding: utf-8 -*-
"""Напоминания Meyer, вторая партия — шаблоны редактора (владелец 02.11:
«давай в таком стиле их сделаем»; пункты 1-4 согласованы; на рентгене бесплатная
тестовая сортировка тоже есть).

Отбор — как в пилоте (napominaniya_pilot.py), компании пилота исключены.
Шаблон по адресу, на который ушло первое письмо:
  A — общая/ролевая почта (info@, office@…): передали ли обращение специалисту;
  B — именной/прочий адрес: «возможно, линии уже укомплектованы… если модернизация
      или сложности — подберу оборудование, бесплатная тестовая сортировка».
Род отправителя — по ящику; модель провайдера пересказывает каждое письмо
(смысл и порядок абзацев сохраняются), чтобы партия не была одинаковой.
Re: в ветку первого письма, с того же ящика; цитату первого письма панель
добавляет сама при отправке.

    napominaniya_v2.py --pokaz=10          показать, ничего не заводить
    napominaniya_v2.py --zavesti=300       завести карточки (kind=reply, pending)
Журнал: _ops/napominaniya-v2.jsonl; показ — на дроп napominaniya-v2-pokaz.txt (с --produkt: napominaniya-v2-produkt-pokaz.txt — их сырьё/продукция вместо общих слов)."""
import difflib
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import time
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
ЖУР = r"C:\sender\_ops\napominaniya-v2.jsonl"
ЖУР_ПИЛОТ = r"C:\sender\_ops\napominaniya-pilot.jsonl"
МОДЕЛЬ = _а.get("model", "claude-sonnet-4-6")
if not (ПОКАЗ or ЗАВЕСТИ):
    print(__doc__)
    sys.exit(0)
# отсоединённо (раннер режет задачу на 900 с): --zapusk + те же ключи; журнал — _ops/napominaniya-v2.log
if "--zapusk" in sys.argv:
    import subprocess
    import time
    л = io.open(r"C:\sender\_ops\napominaniya-v2%s.log" % ("-produkt" if "--produkt" in sys.argv else ""), "w", encoding="utf-8")
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


ШАБЛОН = {
    "A": ("Ранее направлял/направляла письмо о поставке оборудования Meyer для сортировки сырья и контроля пищевой продукции.\n"
          "Подскажите, пожалуйста, удалось ли передать моё обращение специалисту, который отвечает за контроль качества "
          "или закупку оборудования?\n"
          "Буду благодарен/благодарна за контакт ответственного коллеги, чтобы обсудить вопрос напрямую и не отвлекать вас "
          "дополнительными письмами.\nСпасибо!"),
    "B": ("Некоторое время назад направлял/направляла вам письмо об оборудовании Meyer для сортировки сырья и контроля "
          "продукции. Пока не получил/получила ответа, поэтому решил/решила ещё раз обратиться.\n\n"
          "Вполне возможно, что ваши линии уже укомплектованы фотосепараторами или рентген-детекторами и сейчас "
          "необходимости в новом оборудовании нет.\n\n"
          "Но если в перспективе планируете модернизацию или расширение производства, будем рады рассмотреть ваши задачи. "
          "Также можем быть полезны, если уже сейчас есть сложности с удалением примесей, дефектного продукта или "
          "выявлением посторонних включений. Я помогу с подбором оборудования под вашу продукцию и проведу бесплатную "
          "тестовую сортировку на ваших образцах.\n\n"
          "Буду благодарен/благодарна за короткую обратную связь."),
}


ПРОДУКТ = "--produkt" in sys.argv   # владелец 02.11: «если релевантно вставить их продукцию»


def собрать(шаблон, имя, жен, сл=None):
    привет = ("%s, добрый день!" % имя) if имя else "Добрый день!"
    т = ШАБЛОН[шаблон]
    if сл:
        # их сырьё/продукция вместо общих слов — только там, где модель уверена
        # жидкое «сырьё» не сортируют (показ 02.11: «сортировки молока» у мороженого)
        if сл.get("syrye_r") and not re.search(r"молок|сливк|вод|сок|масл|сироп|пив|вин|спирт|жидк", сл["syrye_r"], re.I):
            т = т.replace("для сортировки сырья", "для сортировки %s" % сл["syrye_r"])
        if сл.get("prod_r"):
            т = т.replace("контроля пищевой продукции", "контроля качества %s" % сл["prod_r"])
            т = т.replace("контроля продукции", "контроля качества %s" % сл["prod_r"])
    return привет + "\n\n" + м_ж(т, жен)


# ------------------------------------------------------------- отбор ------
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
ящики = {}
for mb in cfg.mailboxes():
    s = st.get_mailbox_state(mb.mailbox_id)
    if mb.division == "meyer" and ("--vklyuchaya-pauzu" in sys.argv or not (s and getattr(s, "paused", False))):
        ящики[mb.mailbox_id] = mb.from_name
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
сейчас = datetime.now(timezone.utc)
порог = (сейчас - timedelta(days=ДНЕЙ)).strftime("%Y-%m-%dT%H:%M:%S")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
мк = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
оквэд = {r[0]: str(r[1] or "")[:90] for r in c.execute("SELECT id, okved FROM recipients")}
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
for _ж in (ЖУР, ЖУР_ПИЛОТ, r"C:\sender\_ops\napominaniya-v2-ne-profil.jsonl"):   # не наш профиль — второй раз модель не гоняем
    if not os.path.exists(_ж):
        continue
    for s in io.open(_ж, encoding="utf-8"):
        try:
            уже.add(json.loads(s)["inn"])
        except (ValueError, KeyError):
            pass
# у компании уже стоит письмо (второе касание и т.п.) — напоминание не шлём
for (инн,) in c.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                        "WHERE m.status IN ('pending_review','scheduled','sending') AND r.inn IS NOT NULL"):
    уже.add(str(инн))
for (инн,) in c.execute("SELECT DISTINCT inn FROM confirm_reviews WHERE status='pending' AND inn IS NOT NULL"):
    уже.add(str(инн))
кандидаты = []
for инн, сп in отпр.items():
    # вебинар — не письмо об оборудовании: в его ветку напоминание «направлял письмо
    # об оборудовании Meyer» не ложится (показ 02.11: два письма ушли бы в ветку вебинара)
    мей = [x for x in сп if x["cid"] in мк and "вебинар" not in str(кам.get(x["cid"], "")).lower()
           and not re.search(r"вебинар|\bИИ\b", x["subj"], re.I)]
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
        if re.match(r"(hr|kadr|buh|rezume|resume|job|vakans|personal|personnel|otdelkadrov)", лок):
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
if "--tolko-schet" in sys.argv:   # 09.11: только посчитать, без модели и записи
    from collections import Counter as _C
    print("ящики в отборе: %d; по ящикам первого письма:" % len(ящики), _C(x[2]["mb"] for x in кандидаты).most_common())
    print("по давности последнего письма:", _C(x[0][:10] for x in кандидаты).most_common(8))
    sys.exit(0)

# --------------------------------------------------------- слоты моделью --
import gen_provider as GP  # noqa: E402

_сырой = GP._raw_stream


def _с_ожиданием(*a, **k):
    """429 шлюза («Short request limit… paused») — ждём 5 мин и повторяем (02.11)."""
    for _п in range(8):
        try:
            return _сырой(*a, **k)
        except Exception as ex:  # noqa: BLE001
            if "429" not in str(ex) or _п == 7:
                raise
            print("шлюз 429, жду 5 мин", flush=True)
            time.sleep(300)


GP._raw_stream = _с_ожиданием

ЗАДАНИЕ = """Ниже — наши первые письма компаниям (направление Meyer: фотосепараторы и
рентген-инспекция). По каждому письму определи:
- tip: "sortirovka" если письмо про фотосепараторы/сортировку сырья, "rentgen" если про рентген-инспекцию готовой продукции;
- zerno: true, если сырьё компании - зерно/крупа/бобовые/семена (там есть «битое зерно»), иначе false;
- syrye_r: сырьё компании в родительном падеже, 1-3 слова, без «вашего» (пшеницы; подсолнечника; орехов; пластика). Нет ясности - "";
- syrye_p: то же в предложном падеже без предлога (пшенице; подсолнечнике; орехах). Нет ясности - "";
- prod_r: продукция компании в родительном падеже, 1-3 слова (муки; растительного масла; готовой продукции). Нет ясности - "";
- prod_p: то же в предложном без предлога (муке; растительном масле). Нет ясности - "".
- nuzhen: true ТОЛЬКО если компании точно нужен фотосепаратор (сортировка сыпучего пищевого
  или с/х сырья: зерно, крупы, бобовые, семена, орехи, сухофрукты, ягоды, кофе, специи,
  чай, замороженные овощи/фрукты, рыба/морепродукты сыпучие, переработка пластика)
  ИЛИ рентген-инспекция (упакованные пищевые продукты: мясо, колбасы, птица, рыба,
  молочка, сыры, кондитерка, снеки, выпечка, полуфабрикаты, консервы, детское питание,
  корма в упаковке). false - руды, горная добыча, щебень, песок, гипс, стройматериалы,
  напитки (вода, соки, пиво, лимонады, алкоголь), торговля/дистрибуция без своего
  производства, услуги, непищевое (химия, металл, косметика), и любые сомнения;
- pochemu: 3-8 слов, почему так решил.
Бери только то, что прямо есть в письме. Ничего не выдумывай. Несколько культур - назови главную или общее слово (зерна).

{pisma}

Ответ - СТРОГО JSON: {{"firmy": [{{"n": 1, "tip": "...", "zerno": true, "syrye_r": "...", "syrye_p": "...", "prod_r": "...", "prod_p": "...", "nuzhen": true, "pochemu": "..."}}]}}"""


def слоты(пачка):
    тексты = []
    for i, (инн, x, тело) in enumerate(пачка, 1):
        тексты.append("ПИСЬМО %d (компания: %s; ОКВЭД: %s)\n%s" % (i, пол[x["rid"]][2][:80], оквэд.get(x["rid"], ""), тело[:1500]))
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


ПЕРЕСКАЗ = """Ниже - черновики вежливых напоминаний (Re: в ветку нашего прошлого письма).
Тексты утверждены редактором. Перепиши КАЖДЫЙ немного своими словами, чтобы письма
пачки не были одинаковыми для спам-фильтра: другие синонимы, порядок слов внутри
фраз, иногда объединить или разбить предложение. Пишет живой менеджер Meyer.

ЖЁСТКО:
- смысл, порядок абзацев и число абзацев - как в черновике; каждая мысль черновика
  остаётся, новых мыслей нет;
- приветствие как в черновике («Добрый день!» можно заменить на «Здравствуйте!»; имя оставить);
- ничего не добавлять: никаких фактов о компании, цифр, цен, сроков, ссылок, обещаний;
- тон вежливый и мягкий, на «вы»; никаких повелительных «Дайте», «Скиньте», «Давайте»;
- не писать «без обязательств», «надеюсь, у вас всё хорошо»;
- род отправителя как в черновике (направлял/направляла, благодарен/благодарна);
- без длинного тире, только дефис или запятая;
- срок не уточнять: первое письмо было давно - только «ранее», «некоторое время назад»;
  НЕ «недавно», «на днях», «несколько дней назад»;
- вопрос в шаблоне A - с «Подскажите, пожалуйста, удалось ли…» или «…ли удалось…»,
  не голое «Моё обращение удалось передать…?»;
- без подписи.

{pisma}

Ответ - СТРОГО JSON: {{"pisma": [{{"n": 1, "tekst": "..."}}]}}"""


def пересказ(черновики):
    тексты = ["ЧЕРНОВИК %d (отправитель - %s)\n%s" % (i, "женщина" if ж else "мужчина", т)
              for i, (т, ж) in enumerate(черновики, 1)]
    m = GP._raw_stream([{"role": "user", "content": ПЕРЕСКАЗ.replace("{pisma}", "\n\n---\n\n".join(тексты))
                         .replace("{{", "{").replace("}}", "}")}], МОДЕЛЬ, 8000, thinking=False, effort="low")
    т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
    with io.open(r"C:\sender\_ops\napominaniya-syroy.txt", "a", encoding="utf-8") as сф:
        сф.write("\n\n======== %s\n%s" % (time.strftime("%H:%M:%S"), т))
    # модель рассуждает вслух и переписывает образец формата — берём ПОСЛЕДНИЙ JSON
    # JSON бывает с отступами: «{\n  "pisma"» — ищем последний такой, а не только слитный
    вх = [m.start() for m in re.finditer(r'\{\s*"pisma"', т)]
    нач = вх[-1] if вх else -1
    д, _ = json.JSONDecoder(strict=False).raw_decode(т[нач:])
    out = {}
    for f in д.get("pisma") or []:
        try:
            out[int(f.get("n"))] = str(f.get("tekst") or "").strip()
        except (TypeError, ValueError):
            pass
    return out


ЗАПРЕТ = re.compile(r"—|без обязательств|http|www\.|надеюсь|недавн|на днях|несколько дней", re.I)
МОЁ_УДОБНО = re.compile(r"(?:перезвон|позвон|набер|свяж)\w*[^.?!]{0,30}?когда (?:будет )?удобно(?! (?:вам|ему|ей|им))", re.I)
СЛАБОЕ_НАЧАЛО = re.compile(r"^\s*(?:возвраща|напомина|вопрос по прошлому|по прошлому письму|уточн|пишу)", re.I)


def годен(нов, черн):
    """'' — годен, иначе причина отсева."""
    if not нов:
        return "пусто"
    з = ЗАПРЕТ.search(нов)
    if з:
        return "запрет: " + з.group(0)
    if "{" in нов or "}" in нов:
        return "заглушка в тексте"
    if re.search(r"удобн\w* (?:звонок|разговор)|связь могла не|обращение удалось ли|письмо удалось ли|признательн\w* буду|благодарн\w* буду", нов, re.I):
        return "кривая фраза"
    if re.search(r"(?:^|[.!?]\s+|\n)(?:дайте|скиньте|отправьте|давайте)\b|\bскин\w+|визуал\b", нов, re.I):
        return "грубо"
    if re.search(r"(?:^|[.!?]\s+|\n)пришлите\b", нов, re.I) and "пожалуйста" not in нов.lower():
        return "грубо"
    if МОЁ_УДОБНО.search(нов):
        return "«когда удобно» без «вам»"
    первая = (нов.split("\n", 1)[1] if "\n" in нов else нов).strip()
    if len(нов) > len(черн) * 1.25:
        return "длиннее черновика"
    if len(нов) < len(черн) * 0.75:
        return "короче черновика"
    if not set(re.findall(r"\d+", нов)) <= set(re.findall(r"\d+", черн)):
        return "новые цифры"
    if "бесплатн" in нов.lower() and "бесплатн" not in черн.lower():
        return "добавлено «бесплатно»"
    return ""


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
    while len(пачка) < 5 and i < len(кандидаты):
        _, инн, x = кандидаты[i]
        i += 1
        тело = (c.execute("SELECT body_rendered FROM messages WHERE id=?", (x["mid"],)).fetchone() or [""])[0] or ""
        if len(тело) < 200:
            continue
        пачка.append((инн, x, тело))
    if not пачка:
        continue
    # предклассификатор (владелец 02.11: «руды, стройку, напитки уберём полностью…
    # оставим только те где нужен точно фсп или рентген»): нет ответа модели — пачку мимо
    try:
        сл_пачки = слоты(пачка)
    except Exception as ex:  # noqa: BLE001
        print("слоты не пришли:", str(ex)[:150], flush=True)
        continue
    черн_пачки = []
    for n, (инн, x, тело) in enumerate(пачка, 1):
        ф = сл_пачки.get(n) or {}
        if ф.get("nuzhen") is not True:
            отсев["не наш профиль"] += 1
            with io.open(r"C:\sender\_ops\napominaniya-v2-ne-profil.jsonl", "a", encoding="utf-8") as нп:
                нп.write(json.dumps({"inn": инн, "imya": пол[x["rid"]][2], "okved": оквэд.get(x["rid"], ""),
                                     "pochemu": ф.get("pochemu")}, ensure_ascii=False) + "\n")
            continue
        им = ИМЯ_ИЗ_ПИСЬМА.search(тело)
        имя = им.group(1) if им and им.group(1) not in ("Добрый", "Здравствуйте", "Уважаемый", "Уважаемая") else ""
        отпр_имя = (ПОДПИСЬ_ИМЯ.search(тело) or [None, (ящики.get(x["mb"]) or "").split(" ")[0]])[1] or ""
        жен = отпр_имя.lower().endswith(("а", "я")) and отпр_имя.lower() not in ЖЕН_ИСКЛ
        лок = пол[x["rid"]][1].split("@")[0]
        заход = "A" if лок.split(".")[0].split("_")[0].split("-")[0] in РОЛИ else "B"
        сл = {k: чисто((сл_пачки.get(n) or {}).get(k)) for k in ("syrye_r", "prod_r")} if ПРОДУКТ else None
        # сырьё в «для сортировки …» — только если первое письмо было про сортировку;
        # у рентгена сырьё — это то, из чего делают продукт (молоко у мороженого), его не сортируют
        if сл and (str(ф.get("tip")) == "rentgen" or "рентген" in x["subj"].lower()):
            сл["syrye_r"] = ""
        текст = собрать(заход, имя, жен, сл)
        номер += 1
        if not текст:
            continue
        тема = "Re: " + re.sub(r"^(?:re:\s*)+", "", x["subj"], flags=re.I)  # владелец 03.11: все с Re:
        em = пол[x["rid"]][1]
        запись = dict(inn=инн, email=em, mailbox=x["mb"], v_otvet_na=x["mid"], zahod=заход,
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
        # 10.11: длинное тире не повод выбрасывать письмо — меняем на дефис, как в ручных письмах владельца
        т = re.sub(r"\s*—\s*", " - ", т) if т else т
        причина = годен(т, запись["telo"])
        if причина:
            отсев[причина] += 1
            if отсев[причина] <= 2:
                print("  отсев (%s): %r" % (причина, т[:300]), flush=True)
            continue
        if any(difflib.SequenceMatcher(None, т, г["telo"]).ratio() > 0.85 for г in готово[-200:]):
            отсев["слишком похоже на готовое"] += 1
            continue
        запись["chernovik"], запись["telo"] = запись["telo"], т
        if ЗАВЕСТИ:
            for _з in range(12):   # 09.11: «database is locked» уронил прогон на 18-й карточке — ждём и повторяем
                try:
                    р = cs.submit_reply(reply_to=запись["email"], subject=запись["tema"], body=т, in_reply_to=x["rfc"],
                                        thread_id=x["thr"], recipient_id=x["rid"], inn=запись["inn"],
                                        panel={"mailbox_id": x["mb"], "napominanie": запись["zahod"],
                                               "vruchnuyu": "напоминания v2 (шаблоны редактора) 02.11"})
                    break
                except sqlite3.OperationalError as _ex:
                    if "locked" not in str(_ex) or _з == 11:
                        raise
                    print("база занята, жду 10 с", flush=True)
                    time.sleep(10)
            запись["karta"] = getattr(р, "review_id", None)
            запись["status"] = getattr(р, "status", "")
            if not getattr(р, "created", True) or запись["status"] != "pending":
                # карточка на этот адрес уже была или её снял заслон — не в счёт
                отсев["карточка: %s" % ("уже была" if not getattr(р, "created", True) else запись["status"])] += 1
                ж.write(json.dumps(запись, ensure_ascii=False) + "\n")
                ж.flush()
                os.fsync(ж.fileno())
                continue
            ж.write(json.dumps(запись, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())
        готово.append(запись)
    print("готово %d, отсев %s" % (len(готово), dict(отсев)), flush=True)

вых = []
for з in готово:
    вых.append("=" * 70 + "\nШаблон %s | %s | %s | первое письмо %s | от %s (%s)\nТема: %s\n\n%s" % (
        з["zahod"], пол.get(next((x["rid"] for x in отпр[з["inn"]] if x["mid"] == з["v_otvet_na"]), 0), ("", "", ""))[2][:60],
        з["email"], з["pervoe"], з["mailbox"], з["otpravitel"], з["tema"], з["telo"]))
текст = "\n\n".join(вых) + "\n"
io.open(r"C:\sender\_ops\napominaniya-v2%s-pokaz.txt" % ("-produkt" if ПРОДУКТ else ""), "w", encoding="utf-8").write(текст)
try:
    requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/napominaniya-v2%s-pokaz.txt" % ("-produkt" if ПРОДУКТ else ""),
                 data=текст.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
except Exception as ex:  # noqa: BLE001
    print("на дроп не ушло:", ex)
print("отсев:", dict(отсев))
print("итог: %d напоминаний%s" % (len(готово), ", карточки заведены" if ЗАВЕСТИ else " (показ, ничего не заведено)"))
