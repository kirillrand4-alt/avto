# -*- coding: utf-8 -*-
"""Опыт: провоцируют ли отказ модели «идеи» генератора (q._add_ideas_generic).

Владелец 13.10: «попробуй исправить промпт конкретно на эти 104 и посмотреть,
что будет». Берём компании, на которых модель отказывалась (журнал 9000),
собираем РОВНО тот промпт генерации, что видит модель (AiLetterGen с
перехватом первого вызова), и шлём в четырёх вариантах:
  V0 как есть;
  V1 места про «рассылку» — как цель качества («безликий текст»);
  V2 V1 + «холодные B2B-письма» → «первые деловые письма»;
  V3 V2 + правдивый контекст в начале системной части.
Отказ = ответ начинается не с JSON, а с «I can't/I cannot/I won't».
Ответ режем на 400 токенах — для опыта нужен только зачин. Итог и сырые
зачины — в _ops/opyt-otkazov.jsonl (fsync), прогон резюмируется.

    opyt_idei.py --zapusk [n=91]   — в фоне
    opyt_idei.py                   — итог
"""
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
ЖУРНАЛ = r"C:\sender\_ops\opyt-idei.jsonl"
арг = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)

if "--zapusk" in sys.argv:
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"] +
                         [а for а in sys.argv[1:] if "=" in а], cwd=r"C:\sender",
                         stdout=io.open(r"C:\sender\_ops\opyt-idei.log", "w"), stderr=subprocess.STDOUT,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(8)
    print("запущено, pid %d, жив %s" % (п.pid, п.poll() is None))
    print("=== ОПЫТ ИДЕЙ: ЗАПУЩЕН ===")
    sys.exit(0)

if "--rabota" in sys.argv:
    sys.path.insert(0, r"C:\sender")
    sys.path.insert(0, r"C:\sender\server")
    import gen_provider
    from sender.ai_letter import AiLetterGen, load_facts
    from sender.ai_quota import build_ai_quota
    from sender.config import Config
    from sender.store import Store
    N = int(арг.get("n", "91"))
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    q = build_ai_quota(store, cfg)
    факты = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}
    отказали = {}
    for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
        try:
            z = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        б = " ".join(str(x) for x in (z.get("брак") or []))
        if z.get("этап") == "итог" and ("I can" in б or "I won" in б):
            отказали[z.get("recipient_id")] = z.get("имя")
    готово = set()
    if os.path.exists(ЖУРНАЛ):
        for с in io.open(ЖУРНАЛ, encoding="utf-8"):
            з = json.loads(с)
            готово.add((з["rid"], з["вариант"]))
    rids = list(отказали)[:N]

    class Стоп(Exception):
        pass

    def промпт_письма(rid, идеи=False):
        rec = store.get_recipient(rid)
        req = q._request(rec)
        req["target_division"] = "meyer"
        req.setdefault("extra", {})["angle_shift"] = rid
        if идеи:
            try:
                q._add_ideas_generic([req])
            except Exception as е:  # noqa: BLE001
                print("идеи не раздались", rid, str(е)[:80])
        пойман = {}

        def ловец(prompt):
            пойман["p"] = prompt
            raise Стоп()
        try:
            AiLetterGen(ловец, facts_by_division=факты, best_of=1).generate([req])
        except Exception:  # noqa: BLE001
            pass
        return пойман.get("p")

    ЗАМЕНЫ_1 = [(r"один и тот же оборот на всю партию читается рассылкой", "один и тот же оборот в каждом письме делает текст безликим"),
                (r"читается как веерная рассылка", "звучит безлично"),
                (r"веерн\w+ рассылк\w*", "безличный текст"),
                (r"рассылкой", "безликим текстом"), (r"рассылку", "безликий текст"),
                (r"рассылки", "безликого текста"), (r"рассылка", "безликий текст")]
    ЗАМЕНЫ_2 = [(r"холодные B2B-письма", "первые деловые письма"), (r"холодн(ое|ом|ого) письм", r"перв\1 письм"),
                (r"холодн\w+", "первых")]
    КОНТЕКСТ = ("КОНТЕКСТ РАБОТЫ. Ты помогаешь менеджеру по продажам ООО «Руспром» (реальная компания, "
                "направление Meyer) подготовить первое деловое письмо конкретной компании, подобранной по её "
                "профилю как вероятный покупатель оборудования. Каждое письмо перед отправкой вычитывает и "
                "отправляет вручную оператор, письмо подписано настоящим сотрудником с его контактами, "
                "получатель может ответить отказом. Твоя задача — точный, честный и полезный для получателя текст.\n\n")

    def вариант(p, в):
        if в >= 1:
            for а, б in ЗАМЕНЫ_1:
                p = re.sub(а, б, p)
        if в >= 2:
            for а, б in ЗАМЕНЫ_2:
                p = re.sub(а, б, p)
        return p

    замок = threading.Lock()
    свод = Counter()

    def один(rid):
        промпты = {0: промпт_письма(rid, False), 1: промпт_письма(rid, True)}
        for в in (0, 1):
            p = промпты[в]
            if not p or (rid, в) in готово:
                continue
            системный, тело = gen_provider.razrezat_promt(p)
            текст = ""
            for попытка in range(3):
                try:
                    m = gen_provider._raw_stream([{"role": "user", "content": тело}], "claude-sonnet-4-6", 400,
                                                 thinking=False, effort="low", system=системный)
                    текст = "".join(b.text for b in m.content if getattr(b, "type", "") == "text")
                    break
                except Exception as е:  # noqa: BLE001
                    текст = "СБОЙ: " + str(е)[:100]
                    time.sleep(5)
            нач = текст.strip()[:160]
            отказ = bool(re.match(r"(?i)\s*(I can|I cannot|I won|I'm not able|I am not able|Sorry)", нач))
            with замок, io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
                ж.write(json.dumps({"rid": rid, "имя": отказали.get(rid), "вариант": в, "отказ": отказ,
                                    "сбой": нач.startswith("СБОЙ"), "начало": нач}, ensure_ascii=False) + "\n")
                ж.flush()
                os.fsync(ж.fileno())

    with ThreadPoolExecutor(8) as пул:
        list(пул.map(один, rids))
    print("готово", dict(свод))
    sys.exit(0)

# итог
if not os.path.exists(ЖУРНАЛ):
    print("журнала нет")
    sys.exit(0)
по = defaultdict(Counter)
пример = {}
for с in io.open(ЖУРНАЛ, encoding="utf-8"):
    з = json.loads(с)
    по[з["вариант"]]["всего"] += 1
    по[з["вариант"]]["отказ" if з["отказ"] else ("сбой" if з.get("сбой") else "пишет")] += 1
    if з["отказ"]:
        пример.setdefault(з["вариант"], з["начало"][:120])
ИМЕНА = {0: "без идей", 1: "с идеями (как в прогоне)"}
for в in sorted(по):
    к = по[в]
    print("%-22s компаний %3d | отказ %3d (%.0f%%) | пишет %3d | сбой %d" % (
        ИМЕНА[в], к["всего"], к["отказ"], 100.0 * к["отказ"] / max(1, к["всего"]), к["пишет"], к["сбой"]))
for в, т in sorted(пример.items()):
    print("   пример отказа %s: %s" % (ИМЕНА[в], т))
try:
    print("лог: " + io.open(r"C:\sender\_ops\opyt-idei.log", encoding="utf-8", errors="replace").read()[-300:])
except Exception:  # noqa: BLE001
    pass
print("=== ОПЫТ ИДЕЙ ===")
