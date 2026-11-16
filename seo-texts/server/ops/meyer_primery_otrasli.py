# -*- coding: utf-8 -*-
"""Банк примеров «под отрасль» для писем провалов Meyer (владелец 16.11: «проверку по тем же канонам, что основные
письма Meyer (935 / Россия 9000)»; «чтобы не было зерна навалом для рентгенов»).
  1) продукты из разметки meyer-provaly-klass.jsonl → группы продуктов (модель), у каждой группы: сыпучий поток /
     упакованный-штучный, станок по правилу канона (сыпучее — фотосепаратор до фасовки; рентген — только упакованный
     или штучный ПИЩЕВОЙ продукт; оба станка — только если оба этапа явны);
  2) по группе 2 варианта фразы примера ТОЛЬКО из канона: meyer-facts.json, meyer_glossary.json, эталоны редактора
     для непищевых (ai_letter._ЭТАЛОН_НЕПИЩЕВЫМ);
  3) каждую фразу — линзы боевого генератора Meyer: технолог (_TEH_LENS_TEHNOLOG_MEYER) и скептик
     (_TEH_LENS_SKEPTIK_MEYER). Годна — только «верно» у обеих. Ничего не отправляет и карточек не заводит.
Журналы (fsync, резюмируемо): _ops/meyer-produkt-gruppa.jsonl, _ops/meyer-primery.jsonl; отчёт _ops/meyer-primery.txt.
    meyer_primery_otrasli.py --zapusk [--model=claude-opus-5-5]"""
import io, json, os, re, subprocess, sys, time
from collections import Counter
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "meyer-primery.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402
import sender.ai_letter as AL  # noqa: E402
МОДЕЛИ = [next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-5-5"), "claude-opus-5", "claude-opus-4-8"]
ТЕХНОЛОГ, СКЕПТИК = AL._TEH_LENS_TEHNOLOG_MEYER, AL._TEH_LENS_SKEPTIK_MEYER
ЭТАЛОНЫ = "\n".join(т for _, т in getattr(AL, "_ЭТАЛОН_НЕПИЩЕВЫМ", ()))
ФАКТЫ = json.load(io.open(r"C:\sender\meyer-facts.json", encoding="utf-8"))
СЛОВАРЬ = json.load(io.open(r"C:\sender\meyer_glossary.json", encoding="utf-8"))
ЖГ, ЖП = os.path.join(ОПС, "meyer-produkt-gruppa.jsonl"), os.path.join(ОПС, "meyer-primery.jsonl")


def зов(т, ключ):
    for п in range(12):
        м_ = МОДЕЛИ[min(п // 2, len(МОДЕЛИ) - 1)]
        try:
            м = GP._raw_stream([{"role": "user", "content": т}], м_, 8000, thinking=False, effort="medium")
            тт = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
            мм = list(re.finditer(r'\{\s*"%s"\s*:' % ключ, тт))
            if not мм: raise ValueError("нет JSON")
            return json.JSONDecoder(strict=False).raw_decode(тт[мм[-1].start():])[0]
        except Exception as ex:  # noqa: BLE001
            print("модель %s: %s, повтор" % (м_, str(ex)[:100]), flush=True); time.sleep(30 if "503" in str(ex) else 10)
    return None


def записать(путь, з):
    with io.open(путь, "a", encoding="utf-8") as ф:
        ф.write(json.dumps(з, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())


КАНОН = ("ФАКТЫ MEYER (только из них):\n" + json.dumps({к: ФАКТЫ.get(к) for к in ("industries_typical", "pains_typical", "proof_points")}, ensure_ascii=False, indent=0)
         + "\n\nСЛОВАРЬ СТАНКОВ:\n" + "\n".join("- %s: %s" % (к, в) for к, в in СЛОВАРЬ.items())
         + "\n\nЭТАЛОНЫ РЕДАКТОРА ДЛЯ НЕПИЩЕВЫХ:\n" + ЭТАЛОНЫ)
ПРАВИЛА = """ПРАВИЛА СТАНКА (канон Meyer, нарушать нельзя):
- Сыпучий поток (зерно, крупа, семечка, орех, бобовые, кофе-зерно, гранулы, хлопья, стеклобой, минеральное сырьё) сортирует
  ФОТОСЕПАРАТОР до фасовки: по цвету, форме, размеру, дефекту. Рентген для сыпучего продукта навалом НЕ называть.
- Рентген — только упакованный или штучный ПИЩЕВОЙ продукт (мясо, полуфабрикаты, кондитерка, молочка, фасовка): ищет плотные
  включения — металл, стекло, камень, керамику, силикон и прочие плотные включения. Волос, дерево, перчатки, кость не обещать.
- В непищевых отраслях (пластик, стекло, химия, минералы, вторсырьё, лес) — только фотосепаратор.
- Оптика не видит металл внутри и включения под упаковкой; рентген не различает цвет.
- Оба станка в одной фразе — только если у группы явно два этапа (сырьё навалом на входе И фасованный продукт на выходе)."""

# 1. группы продуктов
кл = [json.loads(с) for с in io.open(os.path.join(ОПС, "meyer-provaly-klass.jsonl"), encoding="utf-8")]
кл = [x for x in кл if x.get("shablon") != "NE_PISAT"]
сч = Counter((x.get("produkt") or "").strip().lower() for x in кл if (x.get("produkt") or "").strip())
print("компаний к письму: %d, с продуктом: %d, разных продуктов: %d" % (len(кл), sum(сч.values()), len(сч)), flush=True)
отнесено = {}
if os.path.exists(ЖГ):
    for с in io.open(ЖГ, encoding="utf-8"):
        з = json.loads(с); отнесено[з["produkt"]] = з
групп_файл = os.path.join(ОПС, "meyer-gruppy.json")
if os.path.exists(групп_файл):
    группы = json.load(io.open(групп_файл, encoding="utf-8"))
else:
    о = зов("""Ниже продукты компаний-переработчиков (в родительном падеже, с частотой). Сведи их в 15-35 групп продуктов так, чтобы
у группы была ОДНА понятная задача сортировки/контроля. Для каждой группы: короткое имя, род. падеж для фразы «для ___»,
"vid": "сыпучее" | "упакованное" | "оба_этапа" | "непищевое_сыпучее", "stanok": "фотосепаратор" | "рентген" | "оба".
""" + ПРАВИЛА + "\n\nПродукты:\n" + "\n".join("%s (%d)" % (п, н) for п, н in сч.most_common(400)) +
            '\n\nОтвет СТРОГО JSON: {"g": [{"imya": "...", "rod": "...", "vid": "...", "stanok": "...", "primery_produktov": ["..."]}]}', "g")
    группы = (о or {}).get("g") or []
    if not группы: print("группы не получены"); sys.exit(1)
    json.dump(группы, io.open(групп_файл, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("групп:", len(группы), flush=True)
имена = [г["imya"] for г in группы]
ост = [п for п in сч if п not in отнесено]
for i in range(0, len(ост), 150):
    кус = ост[i:i + 150]
    о = зов("Отнеси каждый продукт к одной из групп (точное имя группы) или \"нет\", если ни одна не подходит.\nГруппы: "
            + "; ".join(имена) + "\n\nПродукты:\n" + "\n".join("%d. %s" % (j, п) for j, п in enumerate(кус, 1))
            + '\n\nОтвет СТРОГО JSON: {"o": [{"n": НОМЕР, "gruppa": "..."}]}', "o")
    for r in (о or {}).get("o", []):
        j = int(r.get("n", 0))
        if 1 <= j <= len(кус):
            з = {"produkt": кус[j - 1], "gruppa": r.get("gruppa") or "нет", "kompaniy": сч[кус[j - 1]]}
            отнесено[з["produkt"]] = з; записать(ЖГ, з)
    print("продукты отнесены: %d/%d" % (min(i + 150, len(ост)), len(ост)), flush=True)

# 2-3. фразы и линзы
готово = {json.loads(с)["gruppa"] for с in io.open(ЖП, encoding="utf-8")} if os.path.exists(ЖП) else set()
for г in группы:
    if г["imya"] in готово: continue
    о = зов("""Напиши 2 варианта ОДНОЙ фразы-примера для письма Meyer бывшему контакту: что оборудование Meyer делает именно для
этой группы продукции. Форма: «Для <род. падеж> фотосепараторы Meyer …» или «На упакованной <…> рентген-детекторы Meyer …».
Одна фраза до 25 слов, деловой тон, без цифр, без длинного тире, без «бесплатно», без обещаний, которых нет в каноне ниже.
Группа: %s (род.: %s), вид: %s, станок: %s. Примеры продуктов: %s
%s

%s

Ответ СТРОГО JSON: {"f": ["вариант 1", "вариант 2"]}""" % (г["imya"], г.get("rod"), г.get("vid"), г.get("stanok"),
                                                         ", ".join(г.get("primery_produktov") or [])[:300], ПРАВИЛА, КАНОН), "f")
    for фраза in ((о or {}).get("f") or [])[:2]:
        вер = {}
        for имя, линза in (("tehnolog", ТЕХНОЛОГ), ("skeptik", СКЕПТИК)):
            р = зов(линза + "\n\nПрофиль производства получателя: переработка/производство «%s» (%s).\nФраза из письма: «%s»\n\n"
                    'Ответ СТРОГО JSON: {"verdict": "верно|сомнительно|ошибка", "pochemu": "кратко"}' % (г["imya"], ", ".join(г.get("primery_produktov") or [])[:200], фраза), "verdict")
            вер[имя] = р or {"verdict": "нет ответа", "pochemu": ""}
        годна = all(в.get("verdict") == "верно" for в in вер.values())
        записать(ЖП, {"gruppa": г["imya"], "rod": г.get("rod"), "vid": г.get("vid"), "stanok": г.get("stanok"), "fraza": фраза,
                      "tehnolog": вер["tehnolog"], "skeptik": вер["skeptik"], "godna": годна})
    print("группа готова:", г["imya"], flush=True)

# отчёт
пр = [json.loads(с) for с in io.open(ЖП, encoding="utf-8")]
покр = Counter()
for з in отнесено.values(): покр[з["gruppa"]] += з["kompaniy"]
with io.open(os.path.join(ОПС, "meyer-primery.txt"), "w", encoding="utf-8") as ф:
    ф.write("Фраз: %d, годных (обе линзы «верно»): %d\n\n" % (len(пр), sum(1 for з in пр if з["godna"])))
    for г in группы:
        ф.write("== %s | %s | %s | компаний: %d\n" % (г["imya"], г.get("vid"), г.get("stanok"), покр.get(г["imya"], 0)))
        for з in [з for з in пр if з["gruppa"] == г["imya"]]:
            ф.write("  [%s] %s\n     технолог: %s — %s\n     скептик: %s — %s\n" % ("ГОДНА" if з["godna"] else "СНЯТЬ", з["fraza"],
                    з["tehnolog"].get("verdict"), з["tehnolog"].get("pochemu", "")[:160], з["skeptik"].get("verdict"), з["skeptik"].get("pochemu", "")[:160]))
    ф.write("\nбез группы: %d компаний\n" % покр.get("нет", 0))
print("ГОТОВО: фраз %d, годных %d" % (len(пр), sum(1 for з in пр if з["godna"])), flush=True)
