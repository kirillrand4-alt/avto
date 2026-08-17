# -*- coding: utf-8 -*-
"""Какая модель дешевле на боевом промпте письма.

16.08 письма делались на sonnet-5 и стоили $0.41-0.60 (raskladka-vyzovov).
17.08 на opus-4-8 - $1.90. Часть разницы просто в тарифе (sonnet $3/$15
против opus $6/$30), но часть - в объёме невидимого рассуждения, а он у
моделей разный. Меряем оба конца сразу: и токены, и деньги.

Тариф берём из карты ниже; если шлюз считает иначе, отношение всё равно
сохранится - сравнение относительное.

Ничего не ставим в очередь.
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ПОВТОРОВ = int(sys.argv[1]) if len(sys.argv) > 1 else 2
ПОТОЛОК = 4000
ГРУППА = "Партия 935"
ОТЧЁТ = r"C:\sender\_ops\MODELI-CENY.md"
БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")

# вход/выход за миллион токенов
ТАРИФ = {"claude-opus-4-8": (5.0, 25.0),
         "claude-sonnet-5": (3.0, 15.0),
         "claude-sonnet-4-6": (3.0, 15.0),
         "claude-haiku-4-5": (1.0, 5.0)}

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


def вызов(модель):
    тело = {"model": модель, "max_tokens": ПОТОЛОК, "stream": True,
            "messages": [{"role": "user", "content": ПРОМПТ}],
            "output_config": {"effort": "low"}}
    req = urllib.request.Request(БАЗА + "/v1/messages", method="POST",
                                 data=json.dumps(тело).encode(),
                                 headers=ЗАГОЛОВКИ)
    т0 = time.time()
    текст, вых, вх, стоп, первый = "", 0, 0, None, None
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
                    кус = (d.get("delta") or {}).get("text") or ""
                    if кус:
                        if первый is None:
                            первый = round(time.time() - т0, 1)
                        текст += кус
                elif т == "message_delta":
                    вых = int((d.get("usage") or {}).get("output_tokens") or вых)
                    стоп = (d.get("delta") or {}).get("stop_reason") or стоп
    except urllib.error.HTTPError as ex:
        try:
            ошибка = f"HTTP {ex.code}: {ex.read(160).decode('utf-8','replace')}"
        except Exception:                                      # noqa: BLE001
            ошибка = f"HTTP {ex.code}"
    except Exception as ex:                                    # noqa: BLE001
        ошибка = f"{type(ex).__name__}: {str(ex)[:110]}"
    a, b = ТАРИФ.get(модель, (5.0, 25.0))
    # разбирается ли ответ как JSON письма - иначе дешевизна ничего не стоит
    годен = False
    try:
        т = текст.strip()
        if т.startswith("```"):
            т = т.split("```")[1]
            т = т[4:] if т.lower().startswith("json") else т
        d = json.loads(т)
        годен = bool((d.get("letters") or [{}])[0].get("body"))
    except Exception:                                          # noqa: BLE001
        годен = False
    return {"сек": round(time.time() - т0, 1), "вых": вых, "вх": вх,
            "знаков": len(текст), "первый": первый, "стоп": стоп,
            "ошибка": ошибка, "годен": годен,
            "цена": вх / 1e6 * a + вых / 1e6 * b}


п("# Цена боевого вызова по моделям")
п()
п(f"промпт {len(ПРОМПТ)} знаков | потолок {ПОТОЛОК} | effort=low | "
  f"повторов {ПОВТОРОВ}")
п()
п("| модель | выход | текста | JSON письма | 1-й знак, с | сек | stop | $ |")
п("|---|---|---|---|---|---|---|---|")
итоги = {}
for модель in ("claude-opus-4-8", "claude-sonnet-5", "claude-sonnet-4-6",
               "claude-haiku-4-5"):
    ряд = []
    for _ in range(ПОВТОРОВ):
        x = вызов(модель)
        ряд.append(x)
        if x["ошибка"]:
            п(f"| {модель} | — | — | — | — | {x['сек']} | ОШИБКА | "
              f"{str(x['ошибка'])[:50]} |")
        else:
            п(f"| {модель} | {x['вых']} | {x['знаков']} | "
              f"{'да' if x['годен'] else 'НЕТ'} | {x['первый']} | "
              f"{x['сек']} | {x['стоп']} | {x['цена']:.4f} |")
    итоги[модель] = ряд

п()
п("## Свод")
п()
п("| модель | вызовов годных | средний выход | средняя цена | средние сек |")
п("|---|---|---|---|---|")
for м, ряд in итоги.items():
    год = [x for x in ряд if not x["ошибка"] and x["годен"]]
    if not год:
        п(f"| {м} | 0 | — | — | — |")
        continue
    п(f"| {м} | {len(год)}/{len(ряд)} | "
      f"{sum(x['вых'] for x in год) / len(год):.0f} | "
      f"${sum(x['цена'] for x in год) / len(год):.4f} | "
      f"{sum(x['сек'] for x in год) / len(год):.0f} |")

база = [x for x in итоги.get("claude-opus-4-8", [])
        if not x["ошибка"] and x["годен"]]
if база:
    цб = sum(x["цена"] for x in база) / len(база)
    п()
    п(f"opus-4-8 (то, что в бою сейчас): ${цб:.4f} за вызов")
    for м, ряд in итоги.items():
        if м == "claude-opus-4-8":
            continue
        год = [x for x in ряд if not x["ошибка"] and x["годен"]]
        if год:
            ц = sum(x["цена"] for x in год) / len(год)
            п(f"  {м}: ${ц:.4f} — в {цб / max(1e-9, ц):.1f} раза дешевле")

текст = "\n".join(СТРОКИ) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/MODELI-CENY.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: MODELI-CENY.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:160])
