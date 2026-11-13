# -*- coding: utf-8 -*-
"""Разметка подходящих компаний «провалы Meyer» по шаблонам редактора + продукт для подстановки (модель провайдера).
Вход: _ops/meyer-provaly2.jsonl (не стоп) + причины drop meyer-kontakty-prichiny.csv. Журнал _ops/meyer-provaly-klass.jsonl
(резюмируемо, fsync). Решения владельца 13.11: резкие отказы («нет и не надо») — писать (шаблон «задач не было»);
«Привлечение: не выходит на связь» — шаблон «задач не было» БЕЗ фразы про коллегу.
    meyer_provaly_klass.py --zapusk [--model=claude-opus-4-7] [--potokov=4]"""
import csv, io, json, os, re, subprocess, sys, threading, time
ОПС = r"C:\sender\_ops"
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "meyer-provaly-klass.log"), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, r"C:\sender"); sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402
МОДЕЛЬ = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--model=")), "claude-opus-4-7")
ПОТОКОВ = int(next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--potokov=")), "4"))
ЖУР = os.path.join(ОПС, "meyer-provaly-klass.jsonl"); _з = threading.Lock()
csv.field_size_limit(10 ** 9)
пп, пр = {}, {}
for р in csv.DictReader(io.open(r"C:\seostat\drop\drop-storage\meyer-kontakty-prichiny.csv", encoding="utf-8-sig", errors="replace"), delimiter=";"):
    d = р["DEAL_ID"].strip()
    if (р.get("ПРОДАЖА_ПРИЧИНА") or "").strip(): пп[d] = р["ПРОДАЖА_ПРИЧИНА"].strip()
    if (р.get("ПРИВЛЕЧЕНИЕ_ПРИЧИНА") or "").strip(): пр[d] = р["ПРИВЛЕЧЕНИЕ_ПРИЧИНА"].strip()
готово = set()
if os.path.exists(ЖУР):
    for с in io.open(ЖУР, encoding="utf-8"):
        try: готово.add(json.loads(с)["kluch"])
        except (ValueError, KeyError): pass
комп = []
for с in io.open(os.path.join(ОПС, "meyer-provaly2.jsonl"), encoding="utf-8"):
    x = json.loads(с)
    if x.get("stop") or x["kluch"] in готово: continue
    x["pp"] = [пп[d] for d in x["sdelki"] if d in пп]; x["pr"] = [пр[d][:300] for d in x["sdelki"] if d in пр]
    комп.append(x)
print("к разметке:", len(комп), "уже размечено:", len(готово), flush=True)
ЗАДАНИЕ = """Ты помогаешь отделу продаж Meyer (оптические сортировщики/фотосепараторы и рентген-детекторы для пищевых и
сырьевых производств) подготовить письма компаниям, с которыми сделка провалилась больше года назад. По каждой компании
выбери шаблон письма и продукт.

Шаблоны:
 K_ZNAYU — компания купила оборудование у конкурента (в «Привлечении»: «купили Сисорт/PETKUS/Зоркий», «стоит фотосепаратор»).
 K_OBSUZHDALI — в «Продаже» причина «купили у конкурентов» (было обсуждение с нашим менеджером, потом купили у других).
 OTLOZHILI — в «Продаже» «отложили сделку», «не выходит на связь», «нет бюджета», «позже» (проект обсуждали и отложили).
 NET_ZADACH — отказ по сути: «нет и не надо», «не нужен ФТС», «не интересно», «отпала потребность», «не предвидится» и т.п.
              (был разговор с компанией). Резкие отказы — тоже сюда.
 NET_ZADACH_BEZ — то же, но разговора по сути не было: «не выходит на связь», «не дозвониться», «нет информации» в
              Привлечении, причина пустая или непонятная (консультация, слабая компания…).
 NE_PISAT — дубль, банкротство/ликвидация, не наш клиент/не наша сфера, спам, компания закрыта.
Если есть причина в Продаже — она главнее причины в Привлечении.

Продукт — что они сортируют/производят, коротко в РОДИТЕЛЬНОМ падеже для фразы «оборудование для сортировки ___»
(«зерна», «подсолнечника», «орехов», «пластика»), из причин, комментариев, названий сделок и названия компании.
Не уверен — пустая строка. Оборудование: «фотосепаратор» или «рентген» — что им предлагали/что у них стоит (если ясно).
Конкурент — марка, если названа (Сисорт, CSort, PETKUS, Зоркий, Bühler…), иначе пусто.

Компании:
{spisok}

Ответ СТРОГО JSON: {{"o": [{{"n": НОМЕР, "shablon": "...", "produkt": "...", "oborud": "фотосепаратор|рентген|", "konkurent": "...", "pochemu": "кратко"}}]}}"""


def зов(т):
    for _п in range(10):
        try:
            м = GP._raw_stream([{"role": "user", "content": т}], МОДЕЛЬ, 8000, thinking=False, effort="medium")
            тт = м if isinstance(м, str) else "".join(getattr(b, "text", "") or "" for b in getattr(м, "content", []) or [])
            мм = list(re.finditer(r'\{\s*"o"\s*:', тт))
            if not мм: raise ValueError("нет JSON")
            return json.JSONDecoder(strict=False).raw_decode(тт[мм[-1].start():])[0]
        except Exception as ex:  # noqa: BLE001
            print("модель: %s, повтор" % str(ex)[:100], flush=True); time.sleep(60 if "503" in str(ex) else 15)
    return None


def пачка(п):
    стр = "\n".join("%d. %s | Продажа: %s | Привлечение: %s | комментарии: %s | сделки: %s" % (
        i, x.get("kompaniya", "")[:80], "; ".join(x["pp"]) or "-", "; ".join(x["pr"]) or "-",
        " / ".join(x.get("kommentarii") or [])[:400] or "-", "; ".join(x.get("nazvaniya") or [])[:200]) for i, x in enumerate(п, 1))
    о = зов(ЗАДАНИЕ.replace("{spisok}", стр).replace("{{", "{").replace("}}", "}"))
    if not о: print("пачка не прошла", flush=True); return
    with _з:
        with io.open(ЖУР, "a", encoding="utf-8") as ф:
            for r in о.get("o", []):
                i = int(r.get("n", 0))
                if 1 <= i <= len(п):
                    x = п[i - 1]
                    ф.write(json.dumps({"kluch": x["kluch"], "inn": x["inn"], "shablon": r.get("shablon"), "produkt": r.get("produkt", ""),
                                        "oborud": r.get("oborud", ""), "konkurent": r.get("konkurent", ""), "pochemu": r.get("pochemu", ""),
                                        "pp": x["pp"], "pr": x["pr"][:3]}, ensure_ascii=False) + "\n")
            ф.flush(); os.fsync(ф.fileno())
    print("пачка готова", flush=True)


from concurrent.futures import ThreadPoolExecutor   # noqa: E402
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(пачка, [комп[i:i + 20] for i in range(0, len(комп), 20)]))
from collections import Counter   # noqa: E402
ит = Counter(json.loads(с)["shablon"] for с in io.open(ЖУР, encoding="utf-8"))
print("ГОТОВО РАЗМЕТКА:", dict(ит), flush=True)
