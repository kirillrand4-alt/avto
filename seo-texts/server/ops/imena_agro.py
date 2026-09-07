# -*- coding: utf-8 -*-
"""Привести названия агро-хозяйств к виду, годному для письма.

Зачем модель. В реестре имена записаны прописными и с юридической формой:
«ООО "КРЕСТЬЯНСКОЕ ХОЗЯЙСТВО ПОПЮК"», «СПК ИМ.М.ГОРЬКОГО», «ООО СХП "ЮГ"».
Правилами это не разбирается: чтобы получить «Крестьянское хозяйство Попюк»,
надо знать, что Попюк - фамилия, а хозяйство - нарицательное. Дешёвая
модель это знает, а регулярка нет.

Это НЕ генерация писем (владелец 07.09: «не надо ничего генерировать») -
письмо утверждено и подставляется как есть. Здесь разбирается только
название компании, пачками по 60 штук, через провайдерский API.

Результат durable: C:\\sender\\_ops\\agro-imena.jsonl (одна строка на имя,
fsync). Прогон резюмируется - разобранные пачки заново не оплачиваются.

    python imena_agro.py            # разобрать все неразобранные
    python imena_agro.py предел=120
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider                                            # noqa: E402
from sender.store import Store                                 # noqa: E402

ГРУППА = "Агро зерно 2026"
ЖУРНАЛ = r"C:\sender\_ops\agro-imena.jsonl"
ПАЧКА = 60
МОДЕЛЬ = os.environ.get("GEN_NAME_MODEL", "claude-fable-5")
ПРЕДЕЛ = None
for а in sys.argv[1:]:
    if а.startswith(("предел=", "predel=")):
        try:
            ПРЕДЕЛ = int(а.split("=", 1)[1])
        except ValueError:
            pass

ЗАДАЧА = """Ты приводишь названия российских сельхозпредприятий из ЕГРЮЛ к виду, в котором их можно подставить в деловое письмо.

Правила:
1. Убери организационно-правовую форму: ООО, АО, ЗАО, ПАО, СПК, КФХ, КХ, СХП, СХПК, ТНВ, АФ, ПЗ и подобные. Но если без формы остаётся бессмыслица (например «ИМ. ЛЕНИНА»), оставь родовое слово: «Колхоз им. Ленина».
2. Регистр как в обычном тексте: первое слово с заглавной, нарицательные слова строчными, имена собственные и фамилии с заглавной. «КРЕСТЬЯНСКОЕ ХОЗЯЙСТВО ПОПЮК» → «Крестьянское хозяйство Попюк». «ДОНДУКОВСКИЙ ЭЛЕВАТОР» → «Дондуковский элеватор».
3. Настоящие аббревиатуры оставляй прописными: ВТГ, МИК, АПК, МТС.
4. «ИМ.» разворачивай в «им.» с пробелами: «СПК ИМ.М.ГОРЬКОГО» → «Колхоз им. М. Горького».
5. Если название - фамилия с инициалами («КФХ ВОРОБЬЕВА А.И.»), верни «Воробьева А.И.» и пометь его как имя человека.
6. Ничего не выдумывай и не переводи. Слова не меняй, только форму записи.

Верни СТРОГО JSON-массив без пояснений, по объекту на каждое входное название, в том же порядке:
[{"n": 1, "imya": "Крестьянское хозяйство Попюк", "chelovek": false}, ...]
где n - номер из входа, imya - готовое название, chelovek - true если это фамилия человека."""


def _в_журнал(записи):
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
        for з in записи:
            f.write(json.dumps(з, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


разобрано = {}
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if z.get("сыро") and z.get("имя"):
            разобрано[z["сыро"]] = z

store = Store(r"C:\sender\sender.db")
группы = store.recipient_groups().get("по_id") or {}
сырые = []
видели = set()
for rid, g in группы.items():
    if ГРУППА not in (g or []):
        continue
    rec = store.get_recipient(rid)
    имя = " ".join(str(getattr(rec, "company_name", "") or "").split())
    if имя and имя not in видели:
        видели.add(имя)
        сырые.append(имя)
сырые.sort()
надо = [и for и in сырые if и not in разобрано]
if ПРЕДЕЛ:
    надо = надо[:ПРЕДЕЛ]

print("названий в группе: %d; уже разобрано: %d; к разбору: %d"
      % (len(сырые), len(сырые) - len([и for и in сырые if и not in разобрано]),
         len(надо)), flush=True)

client = gen_provider.make_client()
ЧИСЛО = re.compile(r"\[.*\]", re.S)
сделано = сбоев = 0
for нач in range(0, len(надо), ПАЧКА):
    кусок = надо[нач:нач + ПАЧКА]
    вход = "\n".join("%d. %s" % (i + 1, н) for i, н in enumerate(кусок))
    try:
        ответ = gen_provider.call(
            client, [{"role": "user",
                      "content": ЗАДАЧА + "\n\nНазвания:\n" + вход}],
            model=МОДЕЛЬ, attempts=4, thinking=False)
    except Exception as ex:                                    # noqa: BLE001
        print("   пачка %d: провайдер отказал: %s" % (нач, str(ex)[:100]),
              flush=True)
        сбоев += 1
        continue
    # call() возвращает объект сообщения, а не строку: текст лежит в
    # последнем блоке content (перед ним может стоять блок рассуждения).
    if isinstance(ответ, str):
        текст = ответ
    else:
        текст = "".join(getattr(b, "text", "") or ""
                        for b in (getattr(ответ, "content", None) or [])
                        if getattr(b, "type", "") == "text")
    м = ЧИСЛО.search(текст)
    if not м:
        print("   пачка %d: не JSON: %s" % (нач, текст[:120]), flush=True)
        сбоев += 1
        continue
    try:
        разбор = json.loads(м.group(0))
    except Exception as ex:                                    # noqa: BLE001
        print("   пачка %d: JSON битый: %s" % (нач, str(ex)[:90]), flush=True)
        сбоев += 1
        continue
    строки = []
    for о in разбор:
        try:
            i = int(о.get("n") or 0) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(кусок)):
            continue
        имя = " ".join(str(о.get("imya") or "").split())
        if not имя:
            continue
        строки.append({"сыро": кусок[i], "имя": имя,
                       "человек": bool(о.get("chelovek")),
                       "модель": МОДЕЛЬ, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _в_журнал(строки)
    сделано += len(строки)
    print("   разобрано %d из %d" % (сделано, len(надо)), flush=True)

print("=" * 70)
print("=== РАЗБОР НАЗВАНИЙ ===")
print("разобрано за прогон: %d; пачек с ошибкой: %d" % (сделано, сбоев))
итого = {}
for с in (io.open(ЖУРНАЛ, encoding="utf-8", errors="replace")
          if os.path.exists(ЖУРНАЛ) else []):
    с = с.strip()
    if с:
        try:
            z = json.loads(с)
            итого[z["сыро"]] = z
        except Exception:                                      # noqa: BLE001
            pass
print("всего в журнале: %d" % len(итого))
print("")
for с in сырые[:25]:
    z = итого.get(с)
    print("   %-38s → %s%s" % (с[:38], (z or {}).get("имя", "—"),
                               "  [человек]" if (z or {}).get("человек") else ""))
