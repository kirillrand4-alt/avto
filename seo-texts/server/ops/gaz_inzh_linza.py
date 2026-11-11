# -*- coding: utf-8 -*-
"""Инженерная линза по фразам газовых писем (владелец 11.11: «с инженерной согласен линзой»).

Канон письма написан нами; модель пишет ОДНУ фразу — где у компании нужен газ. Линза читает эту фразу
(второй абзац до «Под такие задачи…/Для этого…/Как раз…/Под резку…/Под такие процессы…») вместе с
продукцией компании и решает: технически верно ли и про ИХ ли продукт. НИЧЕГО НЕ СНИМАЕТ — только отмечает
и предлагает исправленную фразу. Журнал gaz-kc-linza.jsonl (fsync, резюмируемо), отчёт gaz-linza.txt + дроп.
    gaz_inzh_linza.py --zapusk [--model=claude-opus-5-5] [--potokov=6]"""
import csv, io, json, os, re, shutil, sqlite3, subprocess, sys, threading, time
from collections import Counter
from datetime import datetime, timezone
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "gaz-linza.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402
csv.field_size_limit(10 ** 9)
МОДЕЛЬ = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-5-5")
ПОТОКОВ = int(next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--potokov=")), "6"))
ЖУР = os.path.join(ОПС, "gaz-kc-linza.jsonl")
ДРОП = r"C:\seostat\drop\drop-storage"
_замок = threading.Lock()


def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
def цифры(x): return re.sub(r"\D", "", str(x or ""))
база = {}
for р in читать("CA-ENGER-ZALIVKA.csv") + читать("CA-ENGER-ZALIVKA-kompanii.csv"):
    и = цифры(р.get("ИНН"))
    if и and (и not in база or not (база[и].get("Продукция") or "").strip()):
        база[и] = р
сайт = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-BAZA-kompanii.csv")}
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
карт = c.execute("SELECT id, inn, body FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall()
СВЯЗКА = re.compile(r"\s(Под такие задачи|Для этого как раз|Как раз под такие процессы|Под резку как раз|Под такие процессы)\b")
уже = set()
if os.path.exists(ЖУР):
    for с in io.open(ЖУР, encoding="utf-8"):
        try: уже.add(json.loads(с)["karta"])
        except (ValueError, KeyError): pass
задачи = []
for кид, inn, тело in карт:
    if кид in уже: continue
    абз = (тело or "").split("\n\n")
    if len(абз) < 2: continue
    м = СВЯЗКА.search(абз[1])
    фраза = абз[1][:м.start()].strip() if м else абз[1].split(". ")[0] + "."
    газ = "кислород" if "кислородн" in абз[1] else "азот"
    задачи.append((кид, цифры(inn), фраза, газ))
print("карточек pending: %d, к проверке: %d (уже %d), модель %s" % (len(карт), len(задачи), len(уже), МОДЕЛЬ), flush=True)

ЗАДАНИЕ = """Ты инженер по промышленным газам (азот и кислород из PSA-станций, азот 95-99,999 %, кислород около 93 %). Проверь фразы из писем: каждая говорит, где у компании нужен газ. Для КАЖДОЙ реши:
ok: true — фраза технически верна (газ так реально применяется) И говорит про продукцию/процессы ЭТОЙ компании (по её продукции и оборудованию).
ok: false — если есть техническая ошибка (газ так не применяют; азот при вакуумной упаковке; кислород 93 % для резки металла или заправки баллонов; «азот убивает микробы»; азот как пропеллент у того, кто не делает аэрозолей и т.п.), неверный газ, выдуманный процесс, которого нет у компании, или фраза про другой продукт, не их.
Для ok: false дай problem (кратко) и fix — исправленную фразу 10-22 слова про ИХ продукт, технически верную, без цифр, без «мы», без длинного тире; если верной фразы для этой компании нет (газ им не нужен) — fix: "".
{firmy}
Ответ СТРОГО JSON: {{"o": [{{"n": НОМЕР, "ok": true/false, "problem": "...", "fix": "..."}}]}}"""


def зов(текст):
    for _п in range(15):
        try:
            м = GP._raw_stream([{"role": "user", "content": текст}], МОДЕЛЬ, 9000, thinking=True, effort="medium")
            т = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
            _м = list(re.finditer(r'\{\s*"o"\s*:', т))
            if not _м: raise ValueError("нет JSON: %r" % т[:150])
            return {int(x["n"]): x for x in json.JSONDecoder(strict=False).raw_decode(т[_м[-1].start():])[0].get("o", [])}
        except Exception as ex:  # noqa: BLE001
            print("модель: %s, повтор" % str(ex)[:120], flush=True)
            time.sleep(300 if "429" in str(ex) else 90 if "503" in str(ex) else 20)
    return None


итог = Counter()


def пачка(сп):
    строки = []
    for i, (кид, inn, фраза, газ) in enumerate(сп, 1):
        р, с = база.get(inn, {}), сайт.get(inn, {})
        строки.append("%d) газ: %s; отрасль: %s; продукция: %s; оборудование: %s; ФРАЗА: %s" % (
            i, газ, (р.get("Отрасль основная") or р.get("Отрасль") or "")[:60], (р.get("Продукция") or "")[:250],
            (с.get("Оборудование, линии") or "нет данных")[:150], фраза))
    о = зов(ЗАДАНИЕ.replace("{firmy}", "\n".join(строки)).replace("{{", "{").replace("}}", "}"))
    if о is None:
        print("пачка не прошла, вернёмся при перезапуске", flush=True); return
    for i, (кид, inn, фраза, газ) in enumerate(сп, 1):
        x = о.get(i) or {}
        if "ok" not in x: continue
        з = {"karta": кид, "inn": inn, "gaz": газ, "fraza": фраза, "ok": x.get("ok") is True, "problem": (x.get("problem") or "")[:200],
             "fix": (x.get("fix") or "")[:300], "model": МОДЕЛЬ, "ts": datetime.now(timezone.utc).isoformat()}
        with _замок:
            with io.open(ЖУР, "a", encoding="utf-8") as ф:
                ф.write(json.dumps(з, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
            итог["ok" if з["ok"] else "замечание"] += 1


пачки = [задачи[i:i + 15] for i in range(0, len(задачи), 15)]
from concurrent.futures import ThreadPoolExecutor   # noqa: E402
n = 0
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    for _ in пул.map(пачка, пачки):
        n += 1
        if n % 10 == 0: print("пачек %d/%d: %s" % (n, len(пачки), dict(итог)), flush=True)
все = []
for с in io.open(ЖУР, encoding="utf-8"):
    try: все.append(json.loads(с))
    except ValueError: pass
вых = io.open(os.path.join(ОПС, "gaz-linza.txt"), "w", encoding="utf-8")
вых.write("ИНЖЕНЕРНАЯ ЛИНЗА по фразам кампании 22: %s (НИЧЕГО НЕ СНЯТО)\n" % dict(Counter("ok" if з["ok"] else "замечание" for з in все)))
for з in [з for з in все if not з["ok"]]:
    р = база.get(з["inn"], {})
    вых.write("#%s | %s | %s\n   фраза: %s\n   проблема: %s\n   исправить: %s\n" % (з["karta"], (р.get("Компания") or "")[:45], (р.get("Продукция") or "")[:100],
                                                                          з["fraza"], з["problem"], з["fix"] or "(газ им не нужен — снять)"))
вых.close()
shutil.copy2(os.path.join(ОПС, "gaz-linza.txt"), os.path.join(ДРОП, "gaz-linza.txt"))
print("ГОТОВО ЛИНЗА: %s" % dict(итог), flush=True)
