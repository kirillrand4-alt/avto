# -*- coding: utf-8 -*-
"""Аудит станка в годных письмах Meyer за день: тот ли станок, нужен ли второй.

Владелец 12.10: «часто встречается? надо бы исправить не тот станок или не
предложен второй, когда нужно 2». Судья (sonnet через провайдера) видит
карточку и письмо и отвечает: какие станки нужны компании, какие предложены.
Каждая пачка — сразу в _ops/audit-stanka.jsonl (fsync), повтор продолжает.

    audit_stanka.py [день=2026-10-12] [potokov=6]
"""
import io
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.review_lenses import default_caller  # noqa: E402

арг = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
ДЕНЬ = арг.get("den", "2026-10-12")
ПОТОКОВ = int(арг.get("potokov", "6"))
ВЫХОД = r"C:\sender\_ops\audit-stanka.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

готово = set()
if os.path.exists(ВЫХОД):
    for с in io.open(ВЫХОД, encoding="utf-8"):
        try:
            готово.add(int(json.loads(с)["rid"]))
        except Exception:  # noqa: BLE001
            pass
письма = {}
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if z.get("ок") and z.get("тело") and z.get("день") == ДЕНЬ and z.get("направление") == "meyer":
        письма[int(z["recipient_id"])] = z
задачи = []
for rid, z in письма.items():
    if rid in готово:
        continue
    rec = store.get_recipient(rid)
    if not rec:
        continue
    req = q._request(rec)
    ex = req.get("extra") or {}
    пасп = ex.get("site_facts") or {}
    карточка = "отрасль: %s | ОКВЭД: %s | профиль: %s" % (
        req.get("segment"), req.get("okved"), str(req.get("activity") or "")[:700])
    if isinstance(пасп, dict):
        for к in ("продукция", "сырьё", "упаковка_фасовка"):
            if пасп.get(к):
                карточка += " | %s: %s" % (к, str(пасп.get(к))[:300])
    задачи.append({"rid": rid, "имя": z.get("имя"), "отрасль": req.get("segment"),
                   "станок_партии": ex.get("meyer_gradaciya"), "карточка": карточка,
                   "тело": str(z.get("тело")).split("С уважением")[0]})
print("годных писем за %s: %d, уже проверено %d, к проверке %d"
      % (ДЕНЬ, len(письма), len(готово), len(задачи)))

ПРОМПТ = """Ты технолог по оборудованию Meyer. У Meyer два станка:
ФОТО — фотосепаратор: сортирует СЫПУЧИЙ ПОТОК по поверхности (цвет, форма,
размер): зерно, крупа, семена, орехи, сухофрукты, ягоды, овощи, кофе, специи,
щепа и опил, вторсырьё (флекс, гранула), руда, щебень, стеклобой.
РЕНТГЕН — рентген-инспекция: ищет плотные включения (металл, стекло, камень,
керамика) в ПИЩЕВОМ продукте, обычно готовом или упакованном: мясо, молочка,
кондитерка, консервы, фасованные продукты, корма в упаковке.
ОБА нужны, только если у компании есть И сыпучее сырьё для сортировки, И
готовый пищевой продукт для инспекции (кондитер с орехами, мясо с комбикормом,
кофе: зерно на входе и фасовка на выходе). Непищевым отраслям рентген не нужен.

Для каждого письма по карточке реши, что нужно компании, и что предложено в
письме. Ответ строго JSON без текста вокруг:
{"r":[{"id":N,"нужно":"фото|рентген|оба|ничего","предложено":"фото|рентген|оба|ничего",
"вердикт":"верно|не тот станок|нужен второй|лишний второй|не покупатель",
"почему":"до 15 слов"}]}

"""
замок = threading.Lock()


def пачка(куски):
    текст = ПРОМПТ + "\n\n".join(
        "=== ПИСЬМО %d\nКАРТОЧКА: %s\nПИСЬМО:\n%s" % (i, к["карточка"], к["тело"])
        for i, к in enumerate(куски))
    ответ, _м = default_caller(текст, max_tokens=3000, model="claude-sonnet-4-6")
    м = re.search(r"\{.*\}", ответ or "", re.S)
    д = json.loads(м.group(0))
    with замок, io.open(ВЫХОД, "a", encoding="utf-8") as ф:
        for р in д.get("r") or []:
            к = куски[int(р["id"])]
            ф.write(json.dumps({"rid": к["rid"], "имя": к["имя"], "отрасль": к["отрасль"],
                                "станок_партии": к["станок_партии"], **р},
                               ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())


пачки = [задачи[i:i + 6] for i in range(0, len(задачи), 6)]
with ThreadPoolExecutor(ПОТОКОВ) as пул:
    for ф in [пул.submit(пачка, п) for п in пачки]:
        try:
            ф.result()
        except Exception as е:  # noqa: BLE001
            print("пачка упала: %s" % str(е)[:120])

from collections import Counter  # noqa: E402
все = [json.loads(с) for с in io.open(ВЫХОД, encoding="utf-8")]
все = [x for x in все if x["rid"] in письма]
св = Counter(x["вердикт"] for x in все)
print("проверено %d: %s" % (len(все), dict(св.most_common())))
по_отр = Counter((x.get("отрасль") or "?", x["вердикт"]) for x in все if x["вердикт"] != "верно")
for (о, в), n in по_отр.most_common(14):
    print("   %-32s %-16s %d" % (о[:32], в, n))
for x in [x for x in все if x["вердикт"] != "верно"][:14]:
    print("   - %s | %s | нужно %s, предложено %s | %s" % (x["имя"][:28], x["вердикт"],
          x["нужно"], x["предложено"], x["почему"]))
print("=== АУДИТ СТАНКА ===")
