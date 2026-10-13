# -*- coding: utf-8 -*-
"""Отнесённые предклассификатором к «кц» (вся база 13.10): по отраслям + выборка
на независимого судью (opus) с правилами владельца — подходит ли Meyer на самом деле.

    proverka_kc_predklassa.py [n=40]
"""
import io
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter
os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.review_lenses import default_caller  # noqa: E402
N = int(dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а).get("n", "40"))
кц = [json.loads(с)["inn"] for с in io.open(r"C:\sender\_ops\predklass-vsey-bazy.jsonl", encoding="utf-8")
      if json.loads(с)["napr"] == "кц"]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сег, имя = {}, {}
for inn, s, n in c.execute("SELECT inn, segment, company_name FROM recipients WHERE inn IS NOT NULL"):
    сег[str(inn)] = s
    имя[str(inn)] = n
print("отнесено к кц: %d; по отраслям: %s" % (len(кц), dict(Counter(сег.get(i, "?") for i in кц).most_common(16))))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
random.seed(5)
выборка = random.sample(кц, min(N, len(кц)))
блоки = []
for k, инн in enumerate(выборка):
    d = q._site_facts(инн) or {}
    п = "; ".join("%s: %s" % (кл, (v if isinstance(v, str) else ", ".join(map(str, v)))[:200])
                  for кл, v in d.items() if v and кл in ("продукция", "сырьё", "оборудование_линии", "упаковка_фасовка"))
    блоки.append("=== %d | %s | отрасль книги: %s\n%s" % (k, имя.get(инн), сег.get(инн), п[:700] or "(паспорта нет)"))
правила = io.open(r"C:\sender\server\ops\partiya_gen.py", encoding="utf-8").read()
правила = правила[правила.index("МЕЙЕР - два станка"):правила.index('Ответ: "кц" | "мейер"')]
ПРОМПТ = ("Ты технолог Meyer. Meyer продаёт фотосепараторы и рентген-инспекцию. Правила, кому Meyer подходит:\n"
          + правила + "\nПо паспорту каждой компании ответь, подходит ли ей Meyer (хоть один станок). "
          "Ответ строго JSON: {\"r\":[{\"id\":N,\"meyer\":\"да|нет|сомнительно\",\"pochemu\":\"до 12 слов\"}]}\n\n")
ответ, _м = default_caller(ПРОМПТ + "\n\n".join(блоки), max_tokens=5000, model="claude-opus-4-8")
д = json.loads(re.search(r"\{.*\}", ответ, re.S).group(0))
св = Counter(р.get("meyer") for р in д.get("r") or [])
print("судья opus по %d «кц»: %s" % (len(выборка), dict(св)))
for р in д.get("r") or []:
    if р.get("meyer") == "да":
        инн = выборка[int(р["id"])]
        print("   ЗРЯ в КЦ: %s [%s] — %s" % (str(имя.get(инн))[:34], str(сег.get(инн))[:20], р.get("pochemu")))
print("=== ПРОВЕРКА КЦ ===")
