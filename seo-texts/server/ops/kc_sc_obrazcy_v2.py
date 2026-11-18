# -*- coding: utf-8 -*-
"""Образцы писем клиентам СЦ v2 (владелец 18.11: «покажи 3 примера, насколько уникализированы и антиспамные», «может
филологическую линзу поставим»): фраза по сделкам → письмо → пересказ моделью → линзы технолог/филолог/доверие
(ошибка → откат к исходнику и повтор линз). N писем по случайным компаниям с выбранным адресом; печатает уникальность
(шинглы по 4 слова без приветствия), вердикты линз и 3 примера. КАРТОЧЕК НЕ ЗАВОДИТ. Журнал _ops/kc-sc-obrazcy-v2.jsonl.
    kc_sc_obrazcy_v2.py [N=30]"""
import io, json, os, random, re, statistics, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server"); sys.path.insert(0, r"C:\sender\server\ops")
os.environ["PROVIDER_THINKING_FIELD"] = "omit"
import gen_provider as GP
import gen_9000_kc_kanon as KK
import kc_sc_sdelki_fraza as KF
import kc_sc_linzy as L
from sender.config import Config

# Образец руководителя продаж 18.11: «палиться — в первом абзаце: я из Компрессор Центра, тогда-то мы поставляли вам то-то.
# Во втором — пишу, потому что в конце года компании закладывают бюджет. Мы делаем проекты, такие-то».
ПОВОД_СЦ = ["Пишу, потому что в конце года компании закладывают бюджет на следующий год.",
            "Пишу сейчас, потому что в конце года многие компании закладывают бюджет на следующий год.",
            "Сейчас конец года, и многие предприятия планируют бюджет на следующий год, поэтому и пишу.",
            "Пишу в конце года, когда компании как раз закладывают бюджет и модернизацию на следующий год."]
ПОВОД = KK.ПОВОД + ["Пишу сейчас, пока многие производства составляют планы и бюджеты на следующий год.",
                    "Сейчас на многих предприятиях закладывают бюджет на следующий год, поэтому решил написать."]
ВОПРОС = ["Подскажите, есть ли в планах на ближайшие месяцы модернизация или расширение компрессорной?",
          "Скажите, планируете ли в ближайшие 4 месяца обновлять компрессорное оборудование или расширяться?",
          "Есть ли в планах на ближайшие месяцы обновление компрессорного парка или расширение?",
          "Подскажите, стоит ли в планах на следующие месяцы модернизация компрессорной?",
          "Скажите, рассматриваете ли на ближайшие месяцы обновление или расширение компрессорной?"]
ТЕМЫ = ["Компрессорная: планы на следующий год", "Вопрос по компрессорной на следующий год", "Сжатый воздух: планы на следующий год",
        "Планы по компрессорному оборудованию", "Вопрос о планах по компрессорной", "Модернизация компрессорной: планы"]


def зов(текст, ключ, система, макс):
    for п in range(8):
        try:
            м = GP._raw_stream([{"role": "user", "content": текст}], "claude-opus-4-8", макс, thinking=False, effort=None, system=система, cache_system=True)
            т = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
            мм = list(re.finditer(r'\{\s*"%s"\s*:' % ключ, т))
            if not мм: raise ValueError("нет JSON")
            return json.JSONDecoder(strict=False).raw_decode(т[мм[-1].start():])[0]
        except Exception as ex:  # noqa: BLE001
            print("модель: %s" % str(ex)[:100], flush=True); time.sleep(20)
    return None


N = int(next((a for a in sys.argv[1:] if a.isdigit()), "30"))
лес = {}
for с in io.open(r"C:\sender\_ops\kc-sc-lesenka.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if x.get("status") == "выбран": лес[x["kluch"]] = x
кл = [k for k in лес if not k.startswith("имя:")]; random.seed(1812); random.shuffle(кл); кл = кл[:N]
cfg = Config.load(r"C:\sender\sender.yaml")
ящики = [m for m in cfg.mailboxes() if str(getattr(m, "division", "")) == "kc"]
фр = KF.frazy([(k, k) for k in кл], зов)


def одно(k):
    л_ = лес[k]; обр = л_.get("imya") or ""
    mb = random.choice(ящики); менеджер = (str(mb.from_name or "").split(",")[0].split() or ["Сергей"])[0]
    з = random.sample(KK.ЗАК, 3)
    прив = (обр + ", добрый день!") if обр else "Добрый день!"
    исх = ["Меня зовут " + менеджер + ", я из Компрессор Центра. " + фр[k]["f"],
           random.choice(ПОВОД_СЦ) + " " + KF.o_nas() + " " + random.choice(KK.ЗАК_ФР).format(z=", ".join(з[:-1]) + " и " + з[-1], zt=", ".join(KK.ЗАК_ТВ[x] for x in з[:-1]) + " и " + KK.ЗАК_ТВ[з[-1]]),
           random.choice(ВОПРОС)]
    тема = random.choice(ТЕМЫ); сд = KF.sdelki(k)
    нов = L.perefraz(исх, сд, зов)
    if нов and менеджер not in нов[0]: нов = None
    текст = lambda аа: "\n\n".join([прив + " " + аа[0]] + list(аа[1:]))
    письмо = текст(нов or исх); вер = L.linzy(письмо, тема, сд, зов); откат = False
    if нов and L.oshibka(вер):
        письмо = текст(исх); вер = L.linzy(письмо, тема, сд, зов); откат = True
    з_ = {"kluch": k, "perefraz": bool(нов) and not откат, "otkat": откат, "ist": фр[k]["ist"], "tema": тема, "pismo": письмо, "ishodnik": текст(исх),
          "linzy": вер, "status": "ошибка" if L.oshibka(вер) else "ок", "sdelki": [x["t"][:80] for x in сд[:3]]}
    with io.open(r"C:\sender\_ops\kc-sc-obrazcy-v2.jsonl", "a", encoding="utf-8") as ф:
        ф.write(json.dumps(з_, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
    return з_


with ThreadPoolExecutor(6) as пул: вс = list(пул.map(одно, кл))


def тело(т):
    п = т.split("\n\n"); п[0] = re.sub(r"^.*?добрый день!\s*", "", п[0]); return " ".join(п)


Ш = [{tuple(w[i:i + 4]) for w in [re.findall(r"\w+", тело(x["pismo"]).lower())] for i in range(len(w) - 3)} for x in вс]
мх = sorted(max(len(Ш[i] & Ш[j]) / len(Ш[i] | Ш[j]) for j in range(len(Ш)) if j != i) for i in range(len(Ш)))
print("писем %d | статусы %s | пересказ %d, откат %d | фраза: %s" % (len(вс), dict(Counter(x["status"] for x in вс)), sum(x["perefraz"] for x in вс),
      sum(x["otkat"] for x in вс), dict(Counter(x["ist"] for x in вс))))
print("сходство с ближайшим: медиана %.0f%%, 90%% ниже %.0f%%, макс %.0f%%; пар >50%%: %d" % (statistics.median(мх) * 100, мх[int(len(мх) * .9)] * 100, мх[-1] * 100, sum(1 for v in мх if v > .5)))
for к in ("tehnolog", "filolog", "doverie"): print("  линза %s: %s" % (к, dict(Counter(x["linzy"][к].get("verdict") for x in вс))))
for x in вс:
    for к in ("tehnolog", "filolog", "doverie"):
        if x["linzy"][к].get("verdict") in ("ошибка", "сомнительно"): print("   [%s %s] %s" % (к, x["linzy"][к]["verdict"], x["linzy"][к].get("pochemu", "")[:150]))
ок = [x for x in вс if x["status"] == "ок" and x["perefraz"]]
for x in (ок[:1] + [y for y in ок if y["ist"] == "запас"][:1] + ок[1:2])[:3]:
    print("\n=== ИСХОДНИК:\n%s\n--- ПОСЛЕ ПЕРЕСКАЗА (тема: %s):\n%s\n   сделки: %s" % (x["ishodnik"], x["tema"], x["pismo"], " / ".join(x["sdelki"])))
