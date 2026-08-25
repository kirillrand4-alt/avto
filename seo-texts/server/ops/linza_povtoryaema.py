# -*- coding: utf-8 -*-
"""Даёт ли линза один и тот же ответ на один и тот же текст.

Она забраковала 457 писем, которые сама же пропустила внутри конвейера. Две
причины возможны: письма плохи (но они не менялись) или линза шумит. Прежде
чем снимать 457 писем, гоняем сорок забракованных ЕЩЁ ДВА раза и смотрим,
совпадает ли вердикт.
"""
import json
import re
import sqlite3
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import vf_prompt                        # noqa: E402

МОДЕЛЬ = "claude-sonnet-4-6"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=20, check_same_thread=False)
c.row_factory = sqlite3.Row
замок = threading.Lock()


def вердикт(тема, тело, напр, кц):
    п = vf_prompt([(0, тема, тело)], напр)
    сис, т = gen_provider.razrezat_promt(п)
    m = gen_provider._raw_stream([{"role": "user", "content": т}], МОДЕЛЬ,
                                 900, thinking=False, effort="low", system=сис)
    txt = "".join(b.text for b in m.content if getattr(b, "type", "") == "text")
    мм = re.search(r"\{.*\}", txt, re.S)
    if not мм:
        return None, "не JSON"
    try:
        д = json.loads(мм.group(0))
    except Exception:  # noqa: BLE001
        return None, "не разобрался"
    спис = д.get("verdicts") or []
    з = спис[0] if спис else д
    беды = з.get("problems") or []
    беды = беды if isinstance(беды, list) else [беды]
    if кц:
        беды = [b for b in беды
                if not (re.search(r"(?i)правил\w*\s*2", str(b))
                        and re.search(r"(?i)отказ", str(b)))]
    ок = bool(з.get("ok")) or not беды
    return ок, "; ".join(str(x) for x in беды)[:90]


строки = c.execute(
    "SELECT cr.id, cr.subject, cr.body, m.campaign_id FROM confirm_reviews cr "
    "  JOIN messages m ON m.id=cr.message_id "
    " WHERE m.status IN ('pending_review','scheduled') "
    "   AND COALESCE(cr.body,'')<>'' ORDER BY RANDOM() LIMIT 40").fetchall()
print("проверяем %d писем по два раза" % len(строки))

итог = Counter()
расхождения = []


def проба(р):
    напр = "meyer" if р["campaign_id"] == 11 else "kc"
    ответы = []
    for _ in range(2):
        try:
            о, поч = вердикт(str(р["subject"]), str(р["body"]), напр,
                             напр == "kc")
        except Exception as e:  # noqa: BLE001
            о, поч = None, "сбой: %s" % type(e).__name__
        ответы.append((о, поч))
    with замок:
        а, б = ответы[0][0], ответы[1][0]
        if а is None or б is None:
            итог["не разобрался хотя бы раз"] += 1
        elif а == б:
            итог["совпало: годно" if а else "совпало: брак"] += 1
        else:
            итог["РАЗОШЛОСЬ"] += 1
            расхождения.append((р["id"], ответы))


with ThreadPoolExecutor(max_workers=6) as пул:
    list(пул.map(проба, строки))

print("\n=== ПОВТОРЯЕМОСТЬ ===")
for к, н in итог.most_common():
    print("  %-30s %d" % (к, н))
разошлось = итог["РАЗОШЛОСЬ"]
всего = sum(итог.values()) or 1
print("\n  вердикт нестабилен у %d из %d (%.0f%%)"
      % (разошлось, всего, 100.0 * разошлось / всего))
for rid, о in расхождения[:6]:
    print("  #%s: 1) %s %s | 2) %s %s"
          % (rid, "годно" if о[0][0] else "брак", о[0][1][:50],
             "годно" if о[1][0] else "брак", о[1][1][:50]))
