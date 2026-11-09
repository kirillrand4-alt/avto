# -*- coding: utf-8 -*-
"""Калибровка правил разбора ответов (владелец 09.11: «откалибруем правила для панели… автоответы,
интересно и не интересно, нейтрально — по тем ответам, которые были уже»).

Берём все входящие ответы из events (reply / reply_auto), текст — detail.snippet (без цитаты, как
видит классификатор). По каждому:
  1) что говорят ТЕКУЩИЕ правила панели (sender.reply_classify.classify_reply) — вид и группа;
  2) что говорит модель через провайдерский шлюз (пачки по 20), вид и группа.
Разметка модели пишется в C:\\sender\\_ops\\kalibrovka-otvetov.jsonl (fsync, резюм по id события).
Ничего в базах панели не меняем.

Группы (для владельца):
  автоответ    = auto_reply
  интересно    = hot, interested, deferred
  не интересно = not_interested, unsub_request, objection_status_quo, competitor_in_place
  нейтрально   = neutral, redirect, wrong_contact, objection_tech

    kalibrovka_otvetov.py              посчитать
    kalibrovka_otvetov.py --zapusk     разметка моделью в фоне (лог _ops/kalibrovka-otvetov.log)
    kalibrovka_otvetov.py --otchet     сводка: правила против модели, примеры расхождений
"""
import io, json, os, re, sqlite3, subprocess, sys, time
from collections import Counter, defaultdict
if "--zapusk" in sys.argv:
    лог = io.open(r"C:\sender\_ops\kalibrovka-otvetov.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "--rabota"],
                         cwd=r"C:\sender", stdout=лог, stderr=лог, creationflags=0x00000008 | 0x00000200)
    time.sleep(8); print("запущен, pid %d, жив %s" % (п.pid, п.poll() is None)); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
from sender.reply_classify import classify_reply   # noqa: E402

ГРУППА = {"auto_reply": "автоответ",
          "hot": "интересно", "interested": "интересно", "deferred": "интересно",
          "not_interested": "не интересно", "unsub_request": "не интересно",
          "objection_status_quo": "не интересно", "competitor_in_place": "не интересно",
          "neutral": "нейтрально", "redirect": "нейтрально", "wrong_contact": "нейтрально",
          "objection_tech": "нейтрально"}
ЖУР = r"C:\sender\_ops\kalibrovka-otvetov.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
ответы = []
for eid, et, det in c.execute("SELECT id, event_type, detail_json FROM events WHERE event_type IN ('reply','reply_auto') ORDER BY id"):
    try: д = json.loads(det or "{}")
    except Exception: continue
    т = str(д.get("snippet") or "").strip()
    if not т: continue
    з = д.get("headers") if isinstance(д.get("headers"), dict) else {}
    тема = str(з.get("subject") or з.get("Subject") or д.get("subject") or "")
    try:
        с = classify_reply(тема, т, з or None)
        вид = с.kind
    except Exception as ex:  # noqa: BLE001
        вид = "ошибка: %s" % str(ex)[:40]
    ответы.append({"id": eid, "et": et, "tema": тема[:120], "t": т[:700], "pravila": вид})
готово = {}
if os.path.exists(ЖУР):
    for l in io.open(ЖУР, encoding="utf-8"):
        try: x = json.loads(l); готово[x["id"]] = x
        except Exception: pass
print("ответов с текстом: %d, размечено моделью: %d" % (len(ответы), len(готово)), flush=True)

ВИД = next((a.split("=",1)[1] for a in sys.argv if a.startswith("--vid=")), None)
if ВИД:
    а, б = ВИД.split(">")
    n = int(next((a.split("=",1)[1] for a in sys.argv if a.startswith("--n=")), "25"))
    k = 0
    for о in ответы:
        м = готово.get(о["id"])
        if м and о["pravila"] == а and м["model"] == б:
            k += 1
            if k <= n: print("#%s %s" % (о["id"], re.sub(r"\s+", " ", re.split(r"(?:-{4,}|_{4,}|>\s*>|Кому:|From:|От кого:)", о["t"])[0])[:260]))
    print("всего:", k); sys.exit(0)
if "--sravnit" in sys.argv:
    # ЭТАЛОН: ручное решение владельца по лиду (последний ответ получателя), иначе — модель.
    import importlib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    К = importlib.import_module("reply_classify_kandidat")
    ВЛАД = {"not_interested": "не интересно", "in_bitrix": "интересно", "avtootvet": "автоответ", "v_otpuske": "автоответ"}
    рид = {eid: rid for eid, rid in c.execute("SELECT id, recipient_id FROM events WHERE event_type IN ('reply','reply_auto')")}
    последний = {}
    for о in ответы:
        r = рид.get(о["id"])
        if r: последний[r] = max(последний.get(r, 0), о["id"])
    сырые = {eid: (json.loads(det or "{}")) for eid, det in c.execute("SELECT id, detail_json FROM events WHERE event_type IN ('reply','reply_auto')")}
    ит = Counter(); мат = Counter(); ош = defaultdict(list); ист = Counter()
    for о in ответы:
        м = готово.get(о["id"])
        if not м: continue
        r = рид.get(о["id"]); эт = None
        if r and последний.get(r) == о["id"]:
            л = c.execute("SELECT status FROM leads WHERE recipient_id=? ORDER BY id DESC LIMIT 1", (r,)).fetchone()
            if л and л[0] in ВЛАД: эт = ВЛАД[л[0]]; ист["владелец"] += 1
        if эт is None: эт = ГРУППА.get(м["model"]); ист["модель"] += 1
        д = сырые.get(о["id"]) or {}
        з = д.get("headers") if isinstance(д.get("headers"), dict) else None
        try: кв = К.classify_reply(о["tema"], о["t"], з).kind
        except Exception as ex: кв = "ошибка"
        гб, гк = ГРУППА.get(о["pravila"], о["pravila"]), ГРУППА.get(кв, кв)
        ит["было верно"] += (гб == эт); ит["стало верно"] += (гк == эт); ит["всего"] += 1
        гм = ГРУППА.get(м["model"])
        ит["было=модель"] += (гб == гм); ит["стало=модель"] += (гк == гм)
        if эт != гм or ист.get("_") is None:
            pass
        влад = эт if (r and последний.get(r) == о["id"] and эт is not None and ист) else None
        ит["было=любой"] += (гб in (эт, гм)); ит["стало=любой"] += (гк in (эт, гм))
        мат[(гк, эт)] += 1
        if гк != эт and len(ош[(гк, эт)]) < 40:
            ош[(гк, эт)].append("#%s [%s] %s" % (о["id"], кв, re.sub(r"\s+", " ", re.split(r"(?:-{4,}|_{4,}|>\s*>|Кому:|From:|От кого:)", о["t"])[0])[:170]))
    print("эталон: %s" % dict(ист))
    n = ит["всего"]
    print("СОВПАДЕНИЕ С МОДЕЛЬЮ: было %.0f%%, стало %.0f%%" % (100.0 * ит["было=модель"] / n, 100.0 * ит["стало=модель"] / n))
    print("СОВПАДЕНИЕ ХОТЯ БЫ С ОДНИМ (владелец или модель): было %.0f%%, стало %.0f%%" % (100.0 * ит["было=любой"] / n, 100.0 * ит["стало=любой"] / n))
    print("ТОЧНОСТЬ ГРУПП (эталон: владелец, иначе модель): было %d/%d (%.0f%%), стало %d/%d (%.0f%%)" % (ит["было верно"], ит["всего"], 100.0 * ит["было верно"] / ит["всего"], ит["стало верно"], ит["всего"], 100.0 * ит["стало верно"] / ит["всего"]))
    гр = ["автоответ", "интересно", "не интересно", "нейтрально"]
    print("строки — новые правила, столбцы — эталон:")
    print("%-14s" % "" + "".join("%14s" % г for г in гр))
    for a in гр: print("%-14s" % a + "".join("%14d" % мат[(a, b)] for b in гр))
    if "--primery" in sys.argv:
        КЛ = next((a.split("=",1)[1] for a in sys.argv if a.startswith("--kletka=")), None)
        for к, сп in sorted(ош.items(), key=lambda x: -мат[x[0]]):
            if КЛ and "%s>%s" % к != КЛ: continue
            print("== правила «%s», эталон «%s» (%d)" % (к[0], к[1], мат[к]))
            for x in сп: print("   ", x)
    sys.exit(0)
if "--lidy" in sys.argv:
    # что стало с лидами по ответам, где модель видит интерес, а правила — нет
    рид = {eid: rid for eid, rid in c.execute("SELECT id, recipient_id FROM events WHERE event_type IN ('reply','reply_auto')")}
    ст = Counter(); прим = []
    for о in ответы:
        м = готово.get(о["id"])
        if not м or ГРУППА.get(м["model"]) != "интересно" or ГРУППА.get(о["pravila"]) == "интересно": continue
        л = c.execute("SELECT id, status, reply_kind, bitrix_lead_id FROM leads WHERE recipient_id=? ORDER BY id DESC LIMIT 1", (рид.get(о["id"]),)).fetchone()
        к = (м["model"], л[1] if л else "лида нет", "в битриксе" if л and л[3] else "")
        ст[к] += 1
        if (not л or л[1] in ("not_interested", "closed", "avtootvet", "deleted")) and len(прим) < 25:
            прим.append("#%s лид %s %s | %s" % (о["id"], л[0] if л else "-", л[1] if л else "-", re.sub(r"\s+", " ", о["t"])[:150]))
    for k, n in ст.most_common(): print("  %4d  %s" % (n, k))
    for x in прим: print("   ", x)
    sys.exit(0)
if "--otchet" in sys.argv:
    мат = Counter(); вид_мат = Counter(); прим = defaultdict(list)
    for о in ответы:
        м = готово.get(о["id"])
        if not м: continue
        гп, гм = ГРУППА.get(о["pravila"], о["pravila"]), ГРУППА.get(м["model"], м["model"])
        мат[(гп, гм)] += 1; вид_мат[(о["pravila"], м["model"])] += 1
        if гп != гм and len(прим[(гп, гм)]) < 6:
            прим[(гп, гм)].append("#%s [%s→%s] %s" % (о["id"], о["pravila"], м["model"], re.sub(r"\s+", " ", о["t"])[:230]))
    вс = sum(мат.values()); сход = sum(n for (a, b), n in мат.items() if a == b)
    print("СОВПАДЕНИЕ ГРУПП: %d из %d (%.0f%%)" % (сход, вс, 100.0 * сход / max(вс, 1)))
    гр = ["автоответ", "интересно", "не интересно", "нейтрально"]
    print("строки — правила панели, столбцы — модель:")
    print("%-14s" % "" + "".join("%14s" % г for г in гр))
    for a in гр: print("%-14s" % a + "".join("%14d" % мат[(a, b)] for b in гр))
    print("\nчастые расхождения по видам (правила → модель):")
    for (a, b), n in вид_мат.most_common(40):
        if ГРУППА.get(a, a) != ГРУППА.get(b, b): print("  %4d  %s → %s" % (n, a, b))
    if "--kratko" in sys.argv: sys.exit(0)
    print("\nПРИМЕРЫ:")
    for к, сп in sorted(прим.items(), key=lambda x: -мат[x[0]]):
        print("== правила «%s», модель «%s» (%d)" % (к[0], к[1], мат[к]))
        for s in сп: print("   ", s)
    sys.exit(0)
if "--rabota" not in sys.argv:
    print("правила сейчас:", Counter(ГРУППА.get(о["pravila"], о["pravila"]) for о in ответы).most_common())
    print("сухой прогон. Разметка — --zapusk"); sys.exit(0)

import gen_provider as GP   # noqa: E402
_сырой = GP._raw_stream
def _с_ожиданием(*a, **k):
    for _п in range(8):
        try:
            return _сырой(*a, **k)
        except Exception as ex:  # noqa: BLE001
            if "429" not in str(ex) or _п == 7: raise
            print("шлюз 429, жду 5 мин", flush=True); time.sleep(300)
ЗАДАНИЕ = """Ты разбираешь ответы компаний на холодное письмо поставщика промышленного оборудования (компрессоры; рентген-инспекция и фотосепараторы). Для КАЖДОГО ответа выбери ОДИН вид:
auto_reply — автоответ: отпуск, вне офиса, «письмо получено/зарегистрировано», робот, смена адреса без человека;
unsub_request — просят не писать / удалить из рассылки / отписать;
not_interested — отказ: не нужно, нет потребности, не наш профиль, уже есть оборудование, нас всё устраивает, работаем с другими;
hot — явный запрос: прислать КП/цену/счёт, позвонить, конкретная потребность с параметрами;
interested — интерес без конкретики: вопросы по делу, «расскажите подробнее», «пришлите каталог», готовы рассмотреть;
deferred — интерес, но позже: «вернёмся в следующем году», «напишите через месяц», «пока нет бюджета, но планируем»;
redirect — переадресация: «пишите на такой-то адрес / такому-то человеку», «переслали в отдел», без отказа;
wrong_contact — не тот адресат без переадресации: «я тут не работаю», «это не к нам», ошибся адресом;
neutral — прочее: «вы кто?», «откуда у вас адрес», благодарность без сути, непонятно.
Если в ответе и отказ, и просьба писать другому — это redirect. Если отказ от одного направления, но интерес к другому — по интересу.
{otvety}
Ответ СТРОГО JSON: {{"o": [{{"n": НОМЕР, "v": "ВИД"}}]}} для КАЖДОГО номера."""
ВИДЫ = set(ГРУППА)
жур = io.open(ЖУР, "a", encoding="utf-8")
надо = [о for о in ответы if о["id"] not in готово]
print("к разметке: %d" % len(надо), flush=True)
сделано = 0
for п0 in range(0, len(надо), 20):
    пачка = надо[п0:п0 + 20]
    строки = "\n\n".join("%d) Тема: %s\n%s" % (i, о["tema"], re.sub(r"\s+", " ", о["t"])[:600]) for i, о in enumerate(пачка, 1))
    метки = None
    for _попытка in range(4):
        try:
            м = _с_ожиданием([{"role": "user", "content": ЗАДАНИЕ.replace("{otvety}", строки).replace("{{", "{").replace("}}", "}")}],
                             "claude-sonnet-4-6", 1500, thinking=False, effort="low")
            т = м if isinstance(м, str) else "".join(getattr(b, "text", "") for b in getattr(м, "content", []) or [])
            _п = max(т.rfind('{"o"'), т.rfind('{ "o"'))
            метки = {int(x["n"]): str(x["v"]).strip() for x in json.JSONDecoder(strict=False).raw_decode(т[_п:])[0].get("o", [])}
            break
        except Exception as ex:  # noqa: BLE001
            print("пачка %d: нет разметки (попытка %d): %s" % (п0 // 20 + 1, _попытка + 1, str(ex)[:120]), flush=True); time.sleep(30)
    if метки is None: continue
    for i, о in enumerate(пачка, 1):
        v = метки.get(i)
        if v not in ВИДЫ: continue
        жур.write(json.dumps({"id": о["id"], "model": v, "pravila": о["pravila"]}, ensure_ascii=False) + "\n"); сделано += 1
    жур.flush(); os.fsync(жур.fileno())
    print("пачка %d: размечено всего %d" % (п0 // 20 + 1, сделано), flush=True)
print("итог: размечено %d" % сделано, flush=True)
