# -*- coding: utf-8 -*-
"""Как погасить невидимое рассуждение: перебор способов на боевом промпте.

Улика. На боевом промпте вызов отдаёт 7867-9668 токенов выхода при
max_tokens=4000 и stop_reason='end_turn'. Одиночный вызов не может превысить
потолок обычным текстом - значит это токены рассуждения: они тарифицируются
по ставке выхода, потолком не ограничены и в поток не отдаются. Молчание
длится 76-94 секунды, потом письмо приходит целиком за четыре секунды.
Поэтому обрыв потока бесполезен: рвать нечего, платёж уже случился.

Что в коде сейчас. gen_provider._raw_stream при thinking=False просто НЕ
КЛАДЁТ поле thinking в тело запроса. Отсутствие поля - не то же самое, что
явный запрет: апстрим вправе включить рассуждение по своему умолчанию.

Перебираем способы сказать «не рассуждай» и смотрим на выход. Побеждает тот,
где выход падает до размера письма (около 1000-1500 токенов на 1000 знаков).

Ничего не ставим в очередь. Аргумент - повторов на вариант.
"""
import io
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ПОВТОРОВ = int(sys.argv[1]) if len(sys.argv) > 1 else 1
МОДЕЛЬ = "claude-opus-4-8"
ПОТОЛОК = 4000
ГРУППА = "Партия 935"
ОТЧЁТ = r"C:\sender\_ops\GASIM-RASSUZHDENIE.md"
БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")

ЗАГОЛОВКИ = {"anthropic-version": "2023-06-01",
             "content-type": "application/json", "User-Agent": "curl/8.5.0",
             "x-api-key": os.environ["PROVIDER_API_KEY"]}
for h in ("X-Stainless-Lang", "X-Stainless-Package-Version", "X-Stainless-OS",
          "X-Stainless-Arch", "X-Stainless-Runtime",
          "X-Stainless-Runtime-Version", "X-Stainless-Retry-Count",
          "X-Stainless-Timeout"):
    ЗАГОЛОВКИ[h] = ""

СТРОКИ = []


def п(s=""):
    СТРОКИ.append(s)
    print(s)


cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
группы = store.recipient_groups().get("по_id") or {}
rid = sorted(r for r, gr in группы.items() if ГРУППА in gr)[0]
rec = store.get_recipient(rid)
req0 = q._request(rec)
div = str(req0.get("target_division") or "kc")
div = div if div in ("kc", "meyer") else "kc"
req0["target_division"] = div
ПРОМПТ = gen_prompt([req0], load_facts(division=div), div, angle_base=0)

# ВАРИАНТЫ. Первый - ровно то, что шлёт боевой код сегодня.
ВАРИАНТЫ = [
    ("как сейчас (поля thinking нет)", {"output_config": {"effort": "low"}}),
    ("thinking: disabled", {"thinking": {"type": "disabled"},
                            "output_config": {"effort": "low"}}),
    ("thinking: disabled, без output_config", {"thinking": {"type": "disabled"}}),
    ("thinking: enabled budget 1024", {"thinking": {"type": "enabled",
                                                    "budget_tokens": 1024}}),
    ("голый запрос (ни thinking, ни effort)", {}),
]


def вызов(доп):
    тело = {"model": МОДЕЛЬ, "max_tokens": ПОТОЛОК, "stream": True,
            "messages": [{"role": "user", "content": ПРОМПТ}]}
    тело.update(доп)
    req = urllib.request.Request(БАЗА + "/v1/messages", method="POST",
                                 data=json.dumps(тело).encode(),
                                 headers=ЗАГОЛОВКИ)
    т0 = time.time()
    текст, дум, вых, вх, стоп = "", "", 0, 0, None
    первый = None
    ошибка = None
    try:
        with urllib.request.urlopen(req, timeout=400) as r:
            for сырая in r:
                s = сырая.decode("utf-8", "replace").strip()
                if not s.startswith("data:"):
                    continue
                к = s[5:].strip()
                if к == "[DONE]":
                    break
                try:
                    d = json.loads(к)
                except Exception:                              # noqa: BLE001
                    continue
                т = d.get("type")
                if т == "message_start":
                    вх = int(((d.get("message") or {}).get("usage")
                              or {}).get("input_tokens") or 0)
                elif т == "content_block_delta":
                    dl = d.get("delta") or {}
                    if dl.get("text"):
                        if первый is None:
                            первый = round(time.time() - т0, 1)
                        текст += dl["text"]
                    if dl.get("thinking"):
                        дум += dl["thinking"]
                elif т == "message_delta":
                    вых = int((d.get("usage") or {}).get("output_tokens") or вых)
                    стоп = (d.get("delta") or {}).get("stop_reason") or стоп
    except urllib.error.HTTPError as ex:                       # noqa: F821
        try:
            ошибка = f"HTTP {ex.code}: {ex.read(200).decode('utf-8','replace')}"
        except Exception:                                      # noqa: BLE001
            ошибка = f"HTTP {ex.code}"
    except Exception as ex:                                    # noqa: BLE001
        ошибка = f"{type(ex).__name__}: {str(ex)[:120]}"
    return {"сек": round(time.time() - т0, 1), "вых": вых, "вх": вх,
            "знаков": len(текст), "думал": len(дум), "первый": первый,
            "стоп": стоп, "ошибка": ошибка,
            "цена": вх / 1e6 * 6 + вых / 1e6 * 30}


import urllib.error                                            # noqa: E402

п("# Как погасить невидимое рассуждение")
п()
п(f"боевой промпт {len(ПРОМПТ)} знаков | модель {МОДЕЛЬ} | потолок {ПОТОЛОК}")
п()
п("| вариант | выход | текста | думал | 1-й знак, с | сек | stop | $ |")
п("|---|---|---|---|---|---|---|---|")
итоги = {}
for имя, доп in ВАРИАНТЫ:
    ряд = []
    for _ in range(ПОВТОРОВ):
        x = вызов(доп)
        ряд.append(x)
        if x["ошибка"]:
            п(f"| {имя} | — | — | — | — | {x['сек']} | ОШИБКА | "
              f"{str(x['ошибка'])[:60]} |")
        else:
            п(f"| {имя} | {x['вых']} | {x['знаков']} | {x['думал']} | "
              f"{x['первый']} | {x['сек']} | {x['стоп']} | {x['цена']:.4f} |")
    итоги[имя] = ряд

п()
п("## Вывод")
п()
годные = {и: [x for x in р if not x["ошибка"] and x["знаков"] > 300]
          for и, р in итоги.items()}
лучший, лучшая_цена = None, None
for и, р in годные.items():
    if not р:
        continue
    ц = sum(x["цена"] for x in р) / len(р)
    в = sum(x["вых"] for x in р) / len(р)
    п(f"* {и}: средний выход {в:.0f} токенов, ${ц:.4f} за вызов")
    if лучшая_цена is None or ц < лучшая_цена:
        лучший, лучшая_цена = и, ц
if лучший:
    п()
    п(f"**Дешевле всех: «{лучший}» — ${лучшая_цена:.4f} за вызов.**")
    как_сейчас = годные.get("как сейчас (поля thinking нет)") or []
    if как_сейчас and лучшая_цена:
        сейчас = sum(x["цена"] for x in как_сейчас) / len(как_сейчас)
        if сейчас > 0:
            п(f"Против того, что в бою сейчас (${сейчас:.4f}): "
              f"в {сейчас / лучшая_цена:.1f} раза дешевле.")

текст = "\n".join(СТРОКИ) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/GASIM-RASSUZHDENIE.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: GASIM-RASSUZHDENIE.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:160])
