# -*- coding: utf-8 -*-
"""Насколько письма Meyer шаблонные и что в них реально от сайта компании.

Прошлый счёт мерил не то: наличие подтверждённого сайта В КАРТОЧКЕ, а не
использование сайта В ТЕКСТЕ. Здесь три честных замера:

  А. был ли у письма повод (signal) или это холодный заход по шаблону;
  Б. описание деятельности — текст с сайта или просто расшифровка ОКВЭДа;
  В. сколько у писем разных текстов: шаблон виден по числу повторов.
"""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)

повод = Counter()
описание = Counter()
скелеты = Counter()
тексты = Counter()
по_кампаниям = {}
писем = 0


def скелет(т: str) -> str:
    """Текст без того, что меняется от компании к компании."""
    s = str(т or "")
    s = re.sub(r"[«\"'][^»\"']{2,60}[»\"']", "«X»", s)      # названия в кавычках
    s = re.sub(r"\d[\d  ]*", "N", s)                         # любые числа
    s = re.sub(r"\b(ООО|АО|ЗАО|ПАО|ИП|СХП|КФХ)\b[^,.\n]{0,40}", "ЮЛ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


with store._lock:
    c = store._conn
    for р in c.execute(
            "SELECT m.id, m.campaign_id, m.body_rendered, cr.panel_json "
            "  FROM messages m "
            "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
            " WHERE m.status='sent' AND (%s)" % усл):
        писем += 1
        к = р["campaign_id"]
        д = {}
        if р["panel_json"]:
            try:
                д = json.loads(р["panel_json"])
            except Exception:                                   # noqa: BLE001
                д = {}
        с = (д.get("signal") or {})
        метка = str(с.get("label") or "")
        есть = bool(с.get("present"))
        повод["повод есть" if есть else (метка or "карточки нет")] += 1

        полно = д.get("company_full") or {}
        акт = " ".join(str(полно.get("activity") or "").split())
        оквэд = " ".join(str(полно.get("okved_main_name") or "").split())
        код = str((д.get("company") or {}).get("okved") or "")
        голый = акт.replace(код, "").strip(" .,")
        if not акт:
            описание["описания нет"] += 1
        elif оквэд and (голый == оквэд or голый.startswith(оквэд)):
            описание["только расшифровка ОКВЭДа"] += 1
        elif полно.get("activity_verified"):
            описание["текст с подтверждённого сайта"] += 1
        else:
            описание["текст сверх ОКВЭДа, сайт не сверен"] += 1

        тело = str(р["body_rendered"] or "")
        if тело:
            тексты[тело] += 1
            ск = скелет(тело)
            скелеты[ск] += 1
            d = по_кампаниям.setdefault(к, {"писем": 0, "скелеты": Counter()})
            d["писем"] += 1
            d["скелеты"][ск] += 1

print("--- А. был ли повод (signal в карточке) ---")
for к, n in повод.most_common():
    print("   %-40s %6d  (%.1f%%)" % (к[:40], n, 100.0 * n / писем))

print("")
print("--- Б. откуда описание деятельности ---")
for к, n in описание.most_common():
    print("   %-40s %6d  (%.1f%%)" % (к[:40], n, 100.0 * n / писем))

print("")
print("--- В. сколько разных текстов по кампаниям ---")
with store._lock:
    for к in sorted(по_кампаниям):
        имя = store._conn.execute("SELECT name FROM campaigns WHERE id=?",
                                  (к,)).fetchone()
        d = по_кампаниям[к]
        топ = d["скелеты"].most_common(1)
        print("   кампания %-4s %-26s писем %5d, скелетов %5d, "
              "самый частый повторён %4d раз"
              % (к, str(имя["name"] if имя else "")[:26], d["писем"],
                 len(d["скелеты"]), топ[0][1] if топ else 0))

print("")
print("=" * 74)
print("=== НАСКОЛЬКО ПИСЬМА ШАБЛОННЫЕ ===")
print("   писем всего:                %6d" % писем)
print("   разных текстов дословно:    %6d" % len(тексты))
print("   разных скелетов:            %6d" % len(скелеты))
