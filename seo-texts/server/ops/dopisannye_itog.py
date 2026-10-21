# -*- coding: utf-8 -*-
"""Итог починки забракованных писем КЦ-1 (_ops/dopisannye-kc1.jsonl): сколько в
очереди, сколько снова забраковано и почему."""
import io
import json
from collections import Counter
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\dopisannye-kc1.jsonl", encoding="utf-8")]
ок = [x for x in з if not x.get("гейт")]
print("записей:", len(з), "| без замечаний гейта:", len(ок), "| с карточкой в очереди:", sum(1 for x in з if x.get("review_id")))
print("снова забраковано:", Counter(str((x.get("гейт") or [""])[0])[:60] for x in з if x.get("гейт")).most_common(10))
