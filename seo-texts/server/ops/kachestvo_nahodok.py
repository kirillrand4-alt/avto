# -*- coding: utf-8 -*-
"""Осмысленные ли кандидаты: сверяем имя компании с найденным доменом."""
import io
import json
import re
import unicodedata
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\sayty_dlya_celey.jsonl"

ТР = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
      "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
      "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
      "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
      "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}


def латиница(с):
    return "".join(ТР.get(ч, ч) for ч in str(с or "").lower())


# ТОЛЬКО СВОИ ЦЕЛИ. В журнале 316 записей от прежних прогонов по другому
# списку — там Россети, РусГидро, водоканалы. Если считать по всему
# журналу, качество МОЕГО поиска не измеришь вовсе: первая же выборка
# показала энергетиков и приняла их за агро.
ЦЕЛИ = r"C:\seostat\drop\celi_meyer_30mln.jsonl"
свои = set()
for с in io.open(ЦЕЛИ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if с:
        try:
            свои.add(str(json.loads(с).get("inn") or ""))
        except Exception:  # noqa: BLE001
            pass

записи = []
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
        if str(z.get("инн") or "") in свои:
            записи.append(z)
    except Exception:                                          # noqa: BLE001
        pass

кандидаты = [z for z in записи
             if z.get("сайт") and str(z.get("инн_на_странице")) not in
             ("True", "true", "1")]

счёт = Counter()
показ = []
for z in кандидаты:
    имя = str(z.get("имя") or "")
    домен = re.sub(r"^https?://", "", str(z.get("сайт") or "")).split("/")[0]
    ядро = re.sub(r"^(ООО|АО|ЗАО|ПАО|ОАО|СПК|КФХ|СХПК|ПО|КХ)\s+", "", имя)
    ядро = re.sub(r"[^А-Яа-яA-Za-z]", "", ядро).lower()
    лат = re.sub(r"[^a-z]", "", латиница(ядро))
    домен_ядро = re.sub(r"[^a-z]", "", домен.split(".")[0].lower())
    похоже = bool(лат) and (лат[:5] in домен_ядро or домен_ядро[:5] in лат)
    счёт["имя похоже на домен" if похоже else "имя НЕ похоже"] += 1
    if len(показ) < 14:
        показ.append("%-34s -> %-28s %s"
                     % (имя[:34], домен[:28], "похоже" if похоже else "—"))

print("=" * 80)
print("=== СВОДКА: КАЧЕСТВО КАНДИДАТОВ ===")
print("записей ПО МОИМ ЦЕЛЯМ: %d, из них кандидатов: %d" % (len(записи),
                                                        len(кандидаты)))
for к, в in счёт.most_common():
    print("   %-24s %5d  (%4.1f%%)"
          % (к, в, 100.0 * в / len(кандидаты) if кандидаты else 0))
print("")
print("выборка:")
for с in показ:
    print("   " + с)
