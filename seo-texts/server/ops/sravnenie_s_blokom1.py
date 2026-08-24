# -*- coding: utf-8 -*-
"""Механическое письмо против опусового: слепое сравнение на блоке 1.

Блок 1 дал 242 готовых мейеровских письма. Компании и паспорта те же, так
что платить за опусовую половину второй раз не нужно — берём её из журнала.

Сравниваем тремя способами:
  1. проходимость механического гейта (у опуса она известна: 242 из 250);
  2. слепой суд канона редактора — тот же judge_prompt, что выбирает лучший
     вариант в самой генерации; порядок вариантов ЧЕРЕДУЕМ, иначе судья
     выберет первый по позиции, а не по качеству;
  3. три пары текстом — глазами.

Судит sonnet-4-6, по вызову на пару.
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                             # noqa: E402
from sender.ai_letter import (gate, judge_prompt, load_facts,   # noqa: E402
                              короткое_имя)
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
МОДЕЛЬ = "claude-sonnet-4-6"
ПАР = int(next((a for a in sys.argv[1:] if a.isdigit()), "30"))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
ФАКТЫ = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}


def _без_чисел(т):
    т = re.sub(r"\d[\d\s.,-]*", "", str(т))
    return re.sub(r"\s{2,}", " ", т).strip(" ,;-")


def _первый(v, сколько=2):
    if not v:
        return ""
    сп = v if isinstance(v, list) else [x.strip() for x in str(v).split(";")]
    куски = [_без_чисел(x) for x in сп if str(x).strip()]
    return ", ".join([к for к in куски if len(к) > 3][:сколько]).lower()


def собрать(rec, паспорт, div):
    имя = короткое_имя(getattr(rec, "company_name", "")) or "вашей компании"
    продукция = _первый(паспорт.get("продукция"), 2)
    линии = _первый(паспорт.get("оборудование_линии"), 1)
    мощности = _первый(паспорт.get("мощности"), 1)
    сырьё = _первый(паспорт.get("сырьё"), 2)
    набл = []
    if продукция:
        набл.append(f"Смотрел, что выпускает «{имя}»: {продукция}.")
    if линии:
        набл.append(f"На производстве {линии}.")
    elif мощности:
        набл.append(f"Заявленные мощности - {мощности}.")
    первый = " ".join(набл)
    if div == "kc":
        предст = ("Я веду направление компрессорного оборудования в "
                  "Компрессор Центре - подбираю машины под конкретные "
                  "задачи производства.")
        связка = ("Такое производство обычно завязано на сжатом воздухе: "
                  "пневмоприводы, обдув, подача инструмента. Винтовая пара "
                  "со временем изнашивается - падает производительность и "
                  "растёт расход электроэнергии при той же выработке.")
        вопрос = ("Подскажите, актуален ли для вас вопрос обновления или "
                  "расширения компрессорного парка? Если да - под какие "
                  "участки?")
        тема = f"Вопрос по компрессорному парку в «{имя}»"
    else:
        предст = ("Меня зовут ИМЯ_ОТПРАВИТЕЛЯ, я веду направление "
                  "рентген-инспекции и фотосепарации в Meyer - подбираю "
                  "решения под конкретную линию.")
        связка = ("В таком производстве инородное включение, попавшее в "
                  "готовый продукт, обходится дорого. Рентген-инспекция "
                  "видит их внутри упакованной продукции, фотосепаратор "
                  "снимает посторонние фракции на потоке сырья.")
        if сырьё:
            связка = f"Работаете с сырьём: {сырьё}. " + связка
        вопрос = ("Подскажите, как сейчас закрыт контроль включений - на "
                  "сырье, на готовой продукции или нигде?")
        тема = f"Вопрос по контролю включений в «{имя}»"
    переслать = ("Если этот вопрос ведёт кто-то другой, буду признателен, "
                 "если перешлёте письмо коллеге.")
    тело = "\n\n".join(x for x in ("Добрый день!", предст, первый, связка,
                                   вопрос, переслать, "С уважением,") if x)
    return тема, тело


# --- письма блока 1 из журнала ------------------------------------------- #
опус = {}
for с in io.open(ЖУРНАЛ, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("этап") == "итог" and з.get("ок") and з.get("тело") \
            and з.get("направление") == "meyer":
        опус[str(з.get("inn"))] = з
пары_ключи = list(опус.items())[-ПАР * 2:]
print("мейеровских писем опуса в журнале: %d, берём последние %d"
      % (len(опус), ПАР))

ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб",
        "мощности")
пары = []
for inn, з in reversed(пары_ключи):
    rid = з.get("recipient_id")
    rec = store.get_recipient(rid) if rid else None
    if not rec:
        continue
    try:
        п = q._site_facts(inn) or {}
    except Exception:  # noqa: BLE001
        continue
    if sum(1 for к in ПОЛЯ if п.get(к)) < 2:
        continue
    т2, б2 = собрать(rec, п, "meyer")
    пары.append((rec, з, т2, б2))
    if len(пары) >= ПАР:
        break
print("пар собрано: %d\n" % len(пары))

# --- 3. три пары глазами -------------------------------------------------- #
print("\n=== ТРИ ПАРЫ ТЕКСТОМ ===")
for rec, з, т2, б2 in пары[:3]:
    print("\n" + "=" * 78)
    print("%s" % str(getattr(rec, "company_name", ""))[:60])
    print("-" * 78)
    print("ОПУС ($0.67):  %s" % з.get("тема"))
    print(str(з.get("тело"))[:900])
    print("-" * 78)
    print("МЕХАНИКА ($0): %s" % т2)
    print(б2)


# --- 1. гейт ------------------------------------------------------------- #
чисто_мех = чисто_опус = 0
причины = Counter()
for rec, з, т2, б2 in пары:
    доп = {"company_name": getattr(rec, "company_name", "")}
    п1 = gate(str(з.get("тема")), str(з.get("тело")), mode="GENERIC",
              extra=доп, facts=ФАКТЫ["meyer"], division="meyer")
    п2 = gate(т2, б2, mode="GENERIC", extra=доп,
              facts=ФАКТЫ["meyer"], division="meyer")
    чисто_опус += 0 if п1 else 1
    чисто_мех += 0 if п2 else 1
    for x in п2:
        причины[str(x).split(":")[0][:52]] += 1
print("=== ГЕЙТ ===")
print("  опус:     %d из %d чисто" % (чисто_опус, len(пары)))
print("  механика: %d из %d чисто" % (чисто_мех, len(пары)))
if причины:
    print("  механику бракует за:")
    for к, н in причины.most_common(6):
        print("    %-54s %d" % (к, н))

# --- 2. слепой суд ------------------------------------------------------- #
print("\n=== СЛЕПОЙ СУД КАНОНА РЕДАКТОРА (%s) ===" % МОДЕЛЬ)
голоса = Counter()
цена = 0.0
for i, (rec, з, т2, б2) in enumerate(пары):
    # чередуем позиции: чётные - опус первым, нечётные - механика первой
    мех_первый = bool(i % 2)
    варианты = ([{"subject": т2, "body": б2},
                 {"subject": з.get("тема"), "body": з.get("тело")}]
                if мех_первый else
                [{"subject": з.get("тема"), "body": з.get("тело")},
                 {"subject": т2, "body": б2}])
    промпт = judge_prompt([(0, варианты)], "meyer")
    сис, тело_п = gen_provider.razrezat_promt(промпт)
    try:
        m = gen_provider._raw_stream([{"role": "user", "content": тело_п}],
                                     МОДЕЛЬ, 300, thinking=False,
                                     effort="low", system=сис)
        т = "".join(b.text for b in m.content
                    if getattr(b, "type", "") == "text")
        u = getattr(m, "usage", None)
        цена += ((int(getattr(u, "input_tokens", 0) or 0)
                  + 1.25 * int(getattr(u, "cache_creation_input_tokens", 0) or 0)
                  + 0.1 * int(getattr(u, "cache_read_input_tokens", 0) or 0))
                 / 1e6 * 3.0
                 + int(getattr(u, "output_tokens", 0) or 0) / 1e6 * 15.0)
        м = re.search(r'"pick"\s*:\s*(\d+)', т)
        if not м:
            голоса["судья не ответил"] += 1
            continue
        pick = int(м.group(1))
        победа_механики = (pick == 0) if мех_первый else (pick == 1)
        голоса["механика" if победа_механики else "опус"] += 1
    except Exception as e:  # noqa: BLE001
        голоса["сбой: %s" % type(e).__name__] += 1

for к, н in голоса.most_common():
    print("  %-22s %d" % (к, н))
print("  потрачено: $%.3f" % цена)



# durable: итог на сервер, а не только в срезаемый stdout
import os
_отчёт = r"C:\sender\_ops\sravnenie-blok1.jsonl"
with io.open(_отчёт, "a", encoding="utf-8") as _ф:
    _ф.write(json.dumps({"пар": len(пары), "гейт_опус": чисто_опус,
                         "гейт_механика": чисто_мех,
                         "голоса": dict(голоса), "цена_$": round(цена, 3)},
                        ensure_ascii=False) + "\n")
    _ф.flush()
    os.fsync(_ф.fileno())
print("\nитог записан в %s" % _отчёт)
