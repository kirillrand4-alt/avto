# -*- coding: utf-8 -*-
"""Насколько точно предклассификатор отсекает не покупателей (непищевые отрасли).

1) По журналу: из ПРОПУЩЕННЫХ им компаний (пластик, стекло, вторсырьё,
   горнодобыча) — сколько генератор потом всё равно забраковал как «не
   покупатель» (пропущенный мусор = ошибка «пропустил»).
2) Выборка: по N снятых и N пропущенных — независимый судья (opus через
   провайдера) по тем же паспортам и правилам владельца. Сравнение →
   «снял зря» / «пропустил зря». Итог и ответы судьи — в _ops/tochnost-predklassa.json.

    tochnost_predklassa.py [n=12]
"""
import io
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.review_lenses import default_caller  # noqa: E402

N = int(dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а).get("n", "12"))
ОТРАСЛИ = {"Пластик и полимеры", "Стекло", "Вторсырьё и лом", "Горнодобыча, нерудные", "Химия, удобрения"}
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сег_инн = {}
for inn, сег in c.execute("SELECT inn, segment FROM recipients WHERE inn IS NOT NULL"):
    if сег in ОТРАСЛИ:
        сег_инн[str(inn)] = сег
снятые, пропущенные = {}, {}
итог_пропущенных = defaultdict(list)
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    инн = str(z.get("inn") or "")
    if инн not in сег_инн:
        continue
    if z.get("этап") == "предкласс_отсев":
        снятые[инн] = z.get("имя")
    elif z.get("этап") == "итог" and str(z.get("день") or "") >= "2026-10-12":
        пропущенные[инн] = z.get("имя")
        б = " ".join(str(x) for x in (z.get("брак") or []))
        итог_пропущенных[инн].append("ok" if z.get("ок") else ("не покупатель" if "НЕ ПОКУПАТЕЛЬ" in б else "другой брак"))
пропущенные = {к: v for к, v in пропущенные.items() if к not in снятые}
print("в непищевых отраслях: снято предклассом %d компаний, пропущено и сгенерировано %d" % (len(снятые), len(пропущенные)))
итоги = Counter(("ok" if "ok" in v else "не покупатель" if "не покупатель" in v else "другой брак") for v in итог_пропущенных.values())
print("исход пропущенных: %s" % dict(итоги))
по_отр = defaultdict(Counter)
for инн, v in итог_пропущенных.items():
    по_отр[сег_инн[инн]]["ok" if "ok" in v else "не покупатель" if "не покупатель" in v else "другой брак"] += 1
for о, к in по_отр.items():
    print("   %-24s пропущено %3d: %s | снято %d" % (о[:24], sum(к.values()), dict(к), sum(1 for i in снятые if сег_инн[i] == о)))

random.seed(13)
выборка = [(i, "снял") for i in random.sample(sorted(снятые), min(N, len(снятые)))] + \
          [(i, "пропустил") for i in random.sample(sorted(пропущенные), min(N, len(пропущенные)))]
блоки = []
for k, (инн, реш) in enumerate(выборка):
    try:
        d = q._site_facts(инн) or {}
    except Exception:  # noqa: BLE001
        d = {}
    п = "; ".join("%s: %s" % (кл, (v if isinstance(v, str) else ", ".join(map(str, v)))[:200])
                  for кл, v in d.items() if v and кл in ("продукция", "сырьё", "оборудование_линии", "масштаб", "цитата"))
    имя = снятые.get(инн) or пропущенные.get(инн)
    блоки.append("=== %d | %s | отрасль книги: %s\n%s" % (k, имя, сег_инн[инн], п[:900] or "(паспорта нет)"))
ПРОМПТ = """Ты технолог-продавец оборудования Meyer: фотосепараторы (оптическая сортировка
сыпучего потока по цвету/форме/материалу) и рентген-инспекция пищевой упаковки.
Правила владельца, кто ПОКУПАТЕЛЬ фотосепаратора вне пищёвки:
- переработчики пластика (дробление, флекс, гранула из вторсырья) — да; производитель
  изделий из первичного пластика (трубы, плёнка, тара) — НЕТ, если нет переработки;
- вторсырьё: сортировка/переработка смешанного потока (пластик, стеклобой, лом цветных) — да;
  чистая торговля/заготовка без переработки — нет;
- стеклобой и производство стекла из стеклобоя — да; стекольная мастерская/стеклопакеты — нет;
- нерудные карьеры (песок, щебень, кварц, известняк) — да; горная техника/услуги — нет;
- химия: сыпучие гранулы/порошки, которые сортируют по цвету (удобрения, соль, полимерные
  гранулы) — возможно; жидкая химия, растворы — нет.
По паспорту каждой компании ответь: покупатель ли она фотосепаратора Meyer.
Ответ строго JSON: {"r":[{"id":N,"pokupatel":"да|нет|сомнительно","pochemu":"до 12 слов"}]}

"""
ответ, _м = default_caller(ПРОМПТ + "\n\n".join(блоки), max_tokens=4000, model="claude-opus-4-8")
д = json.loads(re.search(r"\{.*\}", ответ, re.S).group(0))
св = Counter()
строки = []
for р in д.get("r") or []:
    инн, реш = выборка[int(р["id"])]
    суд = р.get("pokupatel")
    если = ("снял верно" if реш == "снял" and суд == "нет" else
            "СНЯЛ ЗРЯ" if реш == "снял" and суд == "да" else
            "пропустил верно" if реш == "пропустил" and суд == "да" else
            "ПРОПУСТИЛ ЗРЯ" if реш == "пропустил" and суд == "нет" else "сомнительно (%s)" % реш)
    св[если] += 1
    строки.append({"inn": инн, "имя": снятые.get(инн) or пропущенные.get(инн), "отрасль": сег_инн[инн],
                   "предкласс": реш, "судья": суд, "почему": р.get("pochemu"), "итог": если})
json.dump(строки, io.open(r"C:\sender\_ops\tochnost-predklassa.json", "w", encoding="utf-8"), ensure_ascii=False)
print("выборка %d снятых + %d пропущенных, судья opus: %s" % (min(N, len(снятые)), min(N, len(пропущенные)), dict(св)))
for с in строки:
    if с["итог"] in ("СНЯЛ ЗРЯ", "ПРОПУСТИЛ ЗРЯ"):
        print("   %s: %s [%s] — %s" % (с["итог"], str(с["имя"])[:30], с["отрасль"][:12], с["почему"]))
print("=== ТОЧНОСТЬ ПРЕДКЛАССА ===")
