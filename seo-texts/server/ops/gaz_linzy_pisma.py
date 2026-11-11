# -*- coding: utf-8 -*-
"""Три линзы по письму целиком (владелец 11.11): «продажник» (хочется ли купить/ответить), «филолог» (язык, стиль),
«доверие» (вызывает ли доверие, не похоже ли на спам). Выборка 60 случайных pending-карточек кампании 22, пачки по
10 писем на линзу (модель с рассуждением). По каждому письму: оценка 1-10, проблемы, одно предложение; по пачке —
общие замечания к канону. Журнал _ops/gaz-linzy-pisma.jsonl, отчёт gaz-linzy-pisma.txt + дроп. Ничего не меняет.
    gaz_linzy_pisma.py --zapusk [--n=60] [--model=claude-opus-5-5]"""
import io, json, os, random, re, shutil, sqlite3, subprocess, sys, threading, time
from collections import defaultdict
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "gaz-linzy-pisma.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402
МОДЕЛЬ = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-5-5")
N = int(next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--n=")), "60"))
ЖУР = os.path.join(ОПС, "gaz-linzy-pisma.jsonl")
_замок = threading.Lock()
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
ряды = c.execute("SELECT id, subject, COALESCE(edited_body, body), panel_json FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall()
random.seed(1112)
выб = random.sample(ряды, min(N, len(ряды)))
ПИСЬМА = []
for кид, тема, тело, pj in выб:
    д = json.loads(pj or "{}"); комп = д.get("company") or {}
    ПИСЬМА.append({"id": кид, "tema": тема, "telo": тело, "komp": "%s; продукция: %s" % (комп.get("name", ""), (комп.get("activity") or "")[:200])})
ОБЩЕЕ = ("Контекст: холодное B2B-письмо от «Компрессор Центра» (ООО «Руспром») производственной компании — предложение азотных/кислородных "
         "станций и компрессоров. Письма собраны по канону: общие блоки + одна фраза про производство адресата. Подпись с юр.лицом "
         "добавляется при отправке. Оцени каждое письмо и дай общие замечания к канону (повторяющиеся блоки). Пиши по-русски, коротко и по делу.")
ЛИНЗЫ = {
    "продажник": "Ты опытный B2B-продажник промышленного оборудования. Главный вопрос: захочется ли главному инженеру/директору завода "
                 "ответить на это письмо или хотя бы переслать его? Чего не хватает, чтобы зацепило; что лишнее; сильный ли вопрос в конце.",
    "филолог": "Ты редактор-филолог деловой переписки. Оцени язык: канцелярит, штампы, тавтологии, ритм, длину фраз, стыки между абзацами, "
               "естественность, грамматику и согласование. Укажи конкретные неудачные места и как переписать.",
    "доверие": "Ты скептичный главный инженер, которому каждый день пишут поставщики. Вызывает ли письмо доверие: похоже ли на шаблонный "
               "спам, есть ли конкретика и подтверждения, не преувеличено ли, правдоподобно ли, что отправитель понимает наше производство?",
}
ЗАДАНИЕ = """{rol}
{obshchee}
{pisma}
Ответ СТРОГО JSON: {{"o": [{{"n": НОМЕР, "ball": 1-10, "problemy": ["...", "..."], "predlozhenie": "..."}}], "kanon": ["общее замечание 1", "общее замечание 2", "..."]}}"""


def зов(текст):
    for _п in range(12):
        try:
            м = GP._raw_stream([{"role": "user", "content": текст}], МОДЕЛЬ, 12000, thinking=True, effort="medium")
            т = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
            _м = list(re.finditer(r'\{\s*"o"\s*:', т))
            if not _м: raise ValueError("нет JSON: %r" % т[:150])
            return json.JSONDecoder(strict=False).raw_decode(т[_м[-1].start():])[0]
        except Exception as ex:  # noqa: BLE001
            print("модель: %s, повтор" % str(ex)[:120], flush=True); time.sleep(90 if "503" in str(ex) else 20)
    return None


def задача(args):
    линза, пачка = args
    блок = "\n\n".join("=== ПИСЬМО %d (адресат: %s)\nТема: %s\n%s" % (i, п["komp"], п["tema"], п["telo"]) for i, п in enumerate(пачка, 1))
    о = зов(ЗАДАНИЕ.replace("{rol}", ЛИНЗЫ[линза]).replace("{obshchee}", ОБЩЕЕ).replace("{pisma}", блок).replace("{{", "{").replace("}}", "}"))
    if not о: print("линза %s: пачка не прошла" % линза, flush=True); return
    with _замок:
        with io.open(ЖУР, "a", encoding="utf-8") as ф:
            for x in о.get("o", []):
                i = int(x.get("n", 0))
                if 1 <= i <= len(пачка):
                    ф.write(json.dumps({"linza": линза, "karta": пачка[i - 1]["id"], "ball": x.get("ball"), "problemy": x.get("problemy"),
                                        "predlozhenie": x.get("predlozhenie")}, ensure_ascii=False) + "\n")
            ф.write(json.dumps({"linza": линза, "kanon": о.get("kanon", [])}, ensure_ascii=False) + "\n")
            ф.flush(); os.fsync(ф.fileno())
    print("линза %s: пачка готова" % линза, flush=True)


if os.path.exists(ЖУР): os.rename(ЖУР, ЖУР + ".%d" % int(time.time()))
пачки = [ПИСЬМА[i:i + 10] for i in range(0, len(ПИСЬМА), 10)]
from concurrent.futures import ThreadPoolExecutor   # noqa: E402
with ThreadPoolExecutor(max_workers=6) as пул:
    list(пул.map(задача, [(л, п) for л in ЛИНЗЫ for п in пачки]))
# ---- отчёт
баллы = defaultdict(list); канон = defaultdict(list); по_письму = defaultdict(dict)
for с in io.open(ЖУР, encoding="utf-8"):
    з = json.loads(с)
    if "kanon" in з: канон[з["linza"]] += з["kanon"] or []
    else:
        try: баллы[з["linza"]].append(float(з["ball"]))
        except (TypeError, ValueError): pass
        по_письму[з["karta"]][з["linza"]] = з
вых = io.open(os.path.join(ОПС, "gaz-linzy-pisma.txt"), "w", encoding="utf-8")
вых.write("ТРИ ЛИНЗЫ ПО ПИСЬМУ ЦЕЛИКОМ: выборка %d писем кампании 22, модель %s\n" % (len(ПИСЬМА), МОДЕЛЬ))
for л in ЛИНЗЫ:
    б = баллы[л]
    вых.write("\n######## %s: средний балл %.1f (мин %s, макс %s, писем %d)\n" % (л, sum(б) / max(1, len(б)), min(б) if б else "-", max(б) if б else "-", len(б)))
    вых.write("ОБЩИЕ ЗАМЕЧАНИЯ К КАНОНУ:\n" + "\n".join("  - " + str(x) for x in канон[л]) + "\n")
вых.write("\n######## ПРИМЕРЫ ПО ПИСЬМАМ (5 худших по сумме баллов)\n")
сумма = sorted(по_письму.items(), key=lambda x: sum(float(v.get("ball") or 0) for v in x[1].values()))
пис = {п["id"]: п for п in ПИСЬМА}
for кид, л in сумма[:5]:
    вых.write("\n=== #%s | %s\n%s\n" % (кид, пис[кид]["komp"][:80], пис[кид]["telo"]))
    for имя, з in л.items():
        вых.write("  [%s %s] %s | → %s\n" % (имя, з.get("ball"), "; ".join(з.get("problemy") or [])[:300], (з.get("predlozhenie") or "")[:300]))
вых.close()
shutil.copy2(os.path.join(ОПС, "gaz-linzy-pisma.txt"), os.path.join(r"C:\seostat\drop\drop-storage", "gaz-linzy-pisma.txt"))
print("ГОТОВО ЛИНЗЫ ПИСЬМА", flush=True)
