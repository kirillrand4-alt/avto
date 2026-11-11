# -*- coding: utf-8 -*-
"""Перепроверка отсева газовых писем (владелец 11.11: «не подходит — проверь, что реально не проходят»).

Берёт из gaz-kc-sud.jsonl всех, кого модель НЕ пропустила (не подходит + брак фразы; конкурентов не трогаем),
и судит заново: модель С РАССУЖДЕНИЕМ, уточнённые правила для спорных случаев, видит причину первого отсева.
Пересуженных «да» дописывает в gaz-kc-sud.jsonl (последняя запись по ИНН главнее) с pereproverka=true —
генератор gen_gaz_kc.py подхватит их при следующем запуске (лесенка + карточки). Все решения перепроверки —
в gaz-kc-pereproverka.jsonl (fsync), резюмируемо. Итог и примеры — gaz-pereproverka.txt (+ копия на дроп).
    gaz_pereproverka.py --zapusk [--model=claude-opus-5-5] [--potokov=6]"""
import csv, io, json, os, re, shutil, subprocess, sys, threading, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "gaz-pereproverka.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaz_kanon as K      # noqa: E402
import gen_provider as GP  # noqa: E402
csv.field_size_limit(10 ** 9)
МОДЕЛЬ = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-5-5")
ПОТОКОВ = int(next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--potokov=")), "6"))
ЖУР_СУД = os.path.join(ОПС, "gaz-kc-sud.jsonl")
ЖУР_ПП = os.path.join(ОПС, "gaz-kc-pereproverka.jsonl")
_замок = threading.Lock()
ДРОП = r"C:\seostat\drop\drop-storage"


def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
def цифры(x): return re.sub(r"\D", "", str(x or ""))
def журнал(п):
    вых = []
    if os.path.exists(п):
        for с in io.open(п, encoding="utf-8"):
            try: вых.append(json.loads(с))
            except ValueError: pass
    return вых
def пиши(п, з):
    with _замок:
        with io.open(п, "a", encoding="utf-8") as ф:
            ф.write(json.dumps(з, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())


база = {}
for р in читать("CA-ENGER-ZALIVKA.csv") + читать("CA-ENGER-ZALIVKA-kompanii.csv"):
    и = цифры(р.get("ИНН"))
    if и and (и not in база or (not (база[и].get("Продукция") or "").strip() and (р.get("Продукция") or "").strip())):
        база[и] = р
САЙТ = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-BAZA-kompanii.csv")}
суд = {}
for з in журнал(ЖУР_СУД):
    суд[з["inn"]] = з
СТРОГО = "--strogo" in sys.argv
ЖУР_СТР = os.path.join(ОПС, "gaz-kc-strogo.jsonl")
сделано = {з["inn"] for з in журнал(ЖУР_ПП)}
if СТРОГО:
    # владелец 11.11 «проверь, что реально не проходят» + моя вычитка: перепроверка с «если сомневаешься — да» вернула
    # много додуманного (озонаторные блоки у фильтровщиков, «может применяться» у БАД/молока). Возвращённых судим строго.
    пп = {}
    for з in журнал(ЖУР_ПП): пп[з["inn"]] = з
    уже = {з["inn"] for з in журнал(ЖУР_СТР)}
    кого = [и for и, з in пп.items() if з.get("ok") and и in база and и not in уже]
else:
    кого = [и for и, з in суд.items() if not з.get("ok") and not з.get("konk") and и in база and и not in сделано]
if СТРОГО: print("СТРОГАЯ проверка возвращённых", flush=True)
print("на перепроверку: %d (уже перепроверено %d), модель %s с рассуждением" % (len(кого), len(сделано), МОДЕЛЬ), flush=True)

ЗАДАНИЕ = """Ты перепроверяешь отсев холодной рассылки поставщика азотных и кислородных станций (PSA, газ из сжатого воздуха прямо на заводе) и компрессоров. Первая проверка отсеяла компании ниже; часть отсеяна зря. Для КАЖДОЙ реши заново, подходит ли она как адресат письма про {gaz}.

Подходит (ok: true), если компания САМА производит или перерабатывает и в её процессе {gaz} типично применяется или реально может применяться. Уточнения, где первая проверка ошибалась:
- лазерная резка металла НА ЗАКАЗ (услуги резки, металлообработка, изготовление металлоконструкций) — подходит: режут на азоте;
- сады, производители и хранители яблок/груш/фруктов — подходят (хранение в регулируемой газовой среде), даже если РГС на сайте не названа;
- розлив питьевой и минеральной воды, напитков — подходит для кислорода (озонирование воды перед розливом) и для азота (продувка, розлив);
- водоканалы и станции водоподготовки — подходят для кислорода (озонирование), даже если озонирование на сайте не названо;
- обжарщики кофе с фасовкой (дрип-пакеты, капсулы, пачки) — подходят, размер не важен;
- кабельные заводы, приборостроение, производство электрооборудования с монтажом плат — подходят (азот при пайке, в линиях);
- заправка и торговля техническими газами в баллонах — подходит (может сама получать азот);
- фасованная пищевка (снеки, сухофрукты, специи, смеси, соусы в пакетах) — подходит, если продукт фасуется в упаковку.
НЕ подходит (ok: false): нет своего производства (торговля, дистрибуция, услуги не про обработку металла, IT, образование, туризм, ЖКХ-управление, медуслуги); продукция явно из другой сферы и газ там не нужен (книги, обувь, одежда, посуда, мебель, фанера); конкурент (сам делает газовые станции, генераторы газов, компрессоры).
Если сомневаешься, но производство профильное — ok: true.

Для ok: true дай фразу f: законченное предложение 10-22 слова о том, где в ИХ производстве нужен {gaz}, про их собственный продукт, без цифр и чисел (никаких процентов, граммов, объёмов), без «мы/наш», без названия компании, без длинного тире, не начинай с «На производстве», не упоминай вакуум.
{firmy}
Ответ СТРОГО JSON: {{"o": [{{"n": НОМЕР, "ok": true/false, "pochemu": "кратко, почему", "f": "..."}}]}}"""


ЗАДАНИЕ_СТРОГО = """Ты строгий редактор холодной рассылки поставщика азотных и кислородных станций и компрессоров. По каждой компании ниже другой проверяющий решил «подходит» и написал фразу о том, где у неё нужен {gaz}. Подтверди (ok: true) ТОЛЬКО если в её ПРОДУКЦИИ или ОБОРУДОВАНИИ есть ЯВНОЕ основание, что {gaz} у неё реально применяется:
- азот: лазерная резка металла (своя или на заказ), пайка плат/SMT, MAP- или газовая фасовка продуктов, которые так типично фасуют (колбасы, нарезка, сыры твёрдые/нарезанные, кофе обжаренный, орехи, сухофрукты, снеки, чипсы), инертизация реакторов и ёмкостей с горючими растворителями/маслами (ЛКМ, растворители, масложир), розлив вина/пива/напитков, хранение фруктов в РГС (сады, фруктохранилища), фарма с синтезом субстанций;
- кислород: озонирование воды (водоканалы, водоподготовка, розлив воды), рыбоводство (оксигенация бассейнов), цианирование руды на ЗИФ.
ОТКАЖИ (ok: false), если обоснование — общее «может применяться», «возможно», «как правило»; если фраза описывает процесс, которого НЕТ в их продукции/оборудовании (например, «испытание озонаторных блоков» у производителя фильтров или котельных, «пропеллент» у производителя шампуней без аэрозолей, «азот в лазере» у чайной компании); если продукция — БАД/витамины в капсулах, молоко/сметана/творог, корма, зерно/крупы, солод, спирт, тракторы/техника без резки металла, фильтры без резки.
{firmy}
Ответ СТРОГО JSON: {{"o": [{{"n": НОМЕР, "ok": true/false, "pochemu": "кратко"}}]}}"""


def зов(текст):
    for _п in range(15):
        try:
            м = GP._raw_stream([{"role": "user", "content": текст}], МОДЕЛЬ, 8000, thinking=True, effort="medium")
            т = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
            _м = list(re.finditer(r'\{\s*"o"\s*:', т))
            if not _м:
                raise ValueError("нет JSON: %r" % т[:150])
            return {int(x["n"]): x for x in json.JSONDecoder(strict=False).raw_decode(т[_м[-1].start():])[0].get("o", [])}
        except Exception as ex:  # noqa: BLE001
            print("модель: %s, повтор" % str(ex)[:120], flush=True)
            time.sleep(300 if "429" in str(ex) else 90 if "503" in str(ex) else 20)
    return None


итог = Counter()


def пачка(сп):
    з0 = (пп if СТРОГО else суд)[сп[0]]; отр, газ = з0.get("otr", ""), з0.get("gaz", "N2")
    строки = []
    for i, и in enumerate(сп, 1):
        р, с = база[и], САЙТ.get(и, {})
        if СТРОГО:
            строки.append(K.строка_для_модели(i, отр, р, с) + "; ФРАЗА ПРОВЕРЯЮЩЕГО: %s" % (пп[и].get("f") or "")[:200])
        else:
            строки.append(K.строка_для_модели(i, отр, р, с) + "; ПРИЧИНА ПЕРВОГО ОТСЕВА: %s" % (суд[и].get("pochemu") or суд[и].get("beda") or "")[:160])
    if СТРОГО:
        о = зов(ЗАДАНИЕ_СТРОГО.replace("{gaz}", "азот" if газ == "N2" else "кислород").replace("{firmy}", "\n".join(строки)).replace("{{", "{").replace("}}", "}"))
        if о is None:
            print("пачка не прошла (%s), вернёмся при перезапуске" % отр[:30], flush=True); return
        for i, и in enumerate(сп, 1):
            x = о.get(i) or {}
            ok = x.get("ok") is True
            з = {"inn": и, "otr": отр, "gaz": газ, "ok": ok, "pochemu": (x.get("pochemu") or "")[:200], "f": пп[и].get("f", ""), "model": МОДЕЛЬ,
                 "ts": datetime.now(timezone.utc).isoformat()}
            пиши(ЖУР_СТР, з)
            if not ok:   # перекрываем «да» перепроверки в журнале суда (последняя запись по ИНН главнее)
                пиши(ЖУР_СУД, {"inn": и, "ok": False, "konk": False, "model_ok": False, "pochemu": "строгая проверка: " + з["pochemu"], "f": "",
                               "beda": "", "otr": отр, "gaz": газ, "model": МОДЕЛЬ + "+strogo", "strogo": True, "ts": з["ts"]})
            with _замок:
                итог["строго: " + ("подтверждено" if ok else "отказ")] += 1
        return
    о = зов(ЗАДАНИЕ.replace("{gaz}", "азот" if газ == "N2" else "кислород").replace("{firmy}", "\n".join(строки)).replace("{{", "{").replace("}}", "}"))
    if о is None:
        print("пачка не прошла (%s), вернёмся при перезапуске" % отр[:30], flush=True); return
    for i, и in enumerate(сп, 1):
        x = о.get(i) or {}
        f, беда = K.фраза(x.get("f") or "", газ)
        ok = x.get("ok") is True and not беда
        было = "брак фразы" if суд[и].get("beda") else "не подходит"
        з = {"inn": и, "otr": отр, "gaz": газ, "bylo": было, "bylo_pochemu": (суд[и].get("pochemu") or суд[и].get("beda") or "")[:200],
             "ok": ok, "model_ok": x.get("ok") is True, "pochemu": (x.get("pochemu") or "")[:200], "f": f if ok else "", "beda": беда if x.get("ok") is True else "",
             "model": МОДЕЛЬ, "ts": datetime.now(timezone.utc).isoformat()}
        пиши(ЖУР_ПП, з)
        if ok:
            пиши(ЖУР_СУД, {"inn": и, "ok": True, "konk": False, "model_ok": True, "pochemu": з["pochemu"], "f": f, "beda": "", "otr": отр, "gaz": газ,
                           "model": МОДЕЛЬ + "+thinking", "pereproverka": True, "ts": з["ts"]})
        with _замок:
            итог["%s -> %s" % (было, "ПОДХОДИТ" if ok else ("брак фразы" if x.get("ok") is True else "не подходит"))] += 1


группы = defaultdict(list)
for и in кого:
    _з = пп[и] if СТРОГО else суд[и]
    группы[(_з.get("otr", ""), _з.get("gaz", "N2"))].append(и)
пачки = [сп[i:i + 8] for сп in группы.values() for i in range(0, len(сп), 8)]
print("пачек: %d" % len(пачки), flush=True)
from concurrent.futures import ThreadPoolExecutor   # noqa: E402
n = 0
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    for _ in пул.map(пачка, пачки):
        n += 1
        if n % 10 == 0:
            print("пачек %d/%d: %s" % (n, len(пачки), dict(итог)), flush=True)
# ---- отчёт
if СТРОГО:
    стр = журнал(ЖУР_СТР); по = defaultdict(Counter); прим = defaultdict(lambda: {"да": [], "нет": []})
    for з in стр:
        по[з["otr"]]["да" if з["ok"] else "нет"] += 1
        if len(прим[з["otr"]]["да" if з["ok"] else "нет"]) < 4: прим[з["otr"]]["да" if з["ok"] else "нет"].append(з)
    вых = io.open(os.path.join(ОПС, "gaz-strogo.txt"), "w", encoding="utf-8")
    вых.write("СТРОГАЯ ПРОВЕРКА ВОЗВРАЩЁННЫХ: %s\n" % dict(Counter("подтверждено" if з["ok"] else "отказ" for з in стр)))
    for отр, c in sorted(по.items(), key=lambda x: -x[1]["да"]):
        вых.write("\n## %s — подтверждено %d, отказ %d\n" % (отр[:70], c["да"], c["нет"]))
        for вид in ("да", "нет"):
            for з in прим[отр][вид]:
                р = база.get(з["inn"], {})
                вых.write("  %s %s | %s\n      %s\n" % ("+" if вид == "да" else "-", (р.get("Компания") or "")[:45], (р.get("Продукция") or "")[:110], з["pochemu"][:150]))
    вых.close()
    shutil.copy2(os.path.join(ОПС, "gaz-strogo.txt"), os.path.join(ДРОП, "gaz-strogo.txt"))
    print("ГОТОВО СТРОГО: %s" % dict(итог), flush=True); sys.exit(0)
все = журнал(ЖУР_ПП)
по_отр = defaultdict(Counter); примеры = defaultdict(list)
for з in все:
    по_отр[з["otr"]]["перевернуто" if з["ok"] else "отсев подтверждён"] += 1
    if з["ok"] and len(примеры[з["otr"]]) < 6:
        примеры[з["otr"]].append(з)
вых = io.open(os.path.join(ОПС, "gaz-pereproverka.txt"), "w", encoding="utf-8")
вых.write("ПЕРЕПРОВЕРКА ОТСЕВА (модель %s с рассуждением). Итог: %s\n" % (МОДЕЛЬ, dict(Counter("ПОДХОДИТ" if з["ok"] else "отсев подтверждён" for з in все))))
for отр, c in sorted(по_отр.items(), key=lambda x: -x[1]["перевернуто"]):
    вых.write("\n## %s — вернулись %d, отсев подтверждён %d\n" % (отр[:70], c["перевернуто"], c["отсев подтверждён"]))
    for з in примеры[отр]:
        р = база.get(з["inn"], {})
        вых.write("  + %s | %s\n      было: %s\n      стало: %s\n      фраза: %s\n" % ((р.get("Компания") or "")[:50], (р.get("Продукция") or "")[:140],
                                                                                 з["bylo_pochemu"][:140], з["pochemu"][:140], з["f"]))
вых.close()
shutil.copy2(os.path.join(ОПС, "gaz-pereproverka.txt"), os.path.join(ДРОП, "gaz-pereproverka.txt"))
print("ГОТОВО: %s" % dict(итог), flush=True)
