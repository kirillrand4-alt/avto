# -*- coding: utf-8 -*-
"""Списывает ли шлюз деньги за ОБОРВАННЫЙ поток. По его собственному счётчику.

Зачем. 86% цены письма - срывы: вызов жжёт 4-13 тысяч токенов выхода ради
тысячи знаков текста. Напрашивается «рвать поток пораньше». Но кадр
message_delta с usage приходит В КОНЦЕ, и оборвав поток, мы его не получаем:
наш собственный учёт покажет ноль токенов выхода. То есть после такой правки
журнал отрапортует «подешевело вчетверо» независимо от того, подешевело ли.
Это не проверка, а самообман - ровно тот класс ошибки, за который владелец
уже ловил («число брал из головы»).

Поэтому меряем по СТОРОННЕМУ счёту: у шлюза есть
GET /dashboard/billing/usage (авторизация Bearer), отдаёт монотонный
total_usage. Читаем до и после, разница и есть настоящий расход.

Порядок:
  1. тишина: два чтения подряд с паузой - убедиться, что счётчик не бежит
     сам по себе (иначе чужой прогон испортит замер);
  2. калибровка: один короткий вызов с известным usage -> сколько единиц
     счётчика приходится на доллар;
  3. N вызовов боевым промптом ДО КОНЦА -> расход;
  4. N вызовов тем же промптом с ОБРЫВОМ по тишине -> расход.

Если пункт 4 дешевле пункта 3 - обрыв работает, и это правка. Если нет -
обрыв только прячет расход от нашего учёта, и предложение неверно.
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

ПОВТОРОВ = int(sys.argv[1]) if len(sys.argv) > 1 else 2
ТИШИНА_СЕК = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
МОДЕЛЬ = "claude-opus-4-8"
ПОТОЛОК = 4000
ГРУППА = "Партия 935"
ОТЧЁТ = r"C:\sender\_ops\SCHET-OBRYVA.md"

БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
КЛЮЧ = os.environ["PROVIDER_API_KEY"]

ЗАГОЛОВКИ = {"anthropic-version": "2023-06-01",
             "content-type": "application/json",
             "User-Agent": "curl/8.5.0", "x-api-key": КЛЮЧ}
for h in ("X-Stainless-Lang", "X-Stainless-Package-Version", "X-Stainless-OS",
          "X-Stainless-Arch", "X-Stainless-Runtime",
          "X-Stainless-Runtime-Version", "X-Stainless-Retry-Count",
          "X-Stainless-Timeout"):
    ЗАГОЛОВКИ[h] = ""

СТРОКИ = []


def п(s=""):
    СТРОКИ.append(s)
    print(s)


def счёт():
    """total_usage шлюза. None, если недоступен."""
    req = urllib.request.Request(
        БАЗА + "/dashboard/billing/usage",
        headers={"Authorization": "Bearer " + КЛЮЧ, "User-Agent": "curl/8.5.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return float(json.loads(r.read()).get("total_usage"))
    except Exception as ex:                                    # noqa: BLE001
        п(f"счётчик не прочитался: {str(ex)[:120]}")
        return None


def вызов(промпт, обрывать):
    """Один вызов. обрывать=True - рвём поток после ТИШИНА_СЕК без текста."""
    тело = {"model": МОДЕЛЬ, "max_tokens": ПОТОЛОК, "stream": True,
            "messages": [{"role": "user", "content": промпт}],
            "output_config": {"effort": "low"}}
    req = urllib.request.Request(БАЗА + "/v1/messages", method="POST",
                                 data=json.dumps(тело).encode(),
                                 headers=ЗАГОЛОВКИ)
    т0 = time.time()
    текст, вых, вх = "", 0, 0
    посл = т0
    оборван = False
    r = urllib.request.urlopen(req, timeout=400)
    try:
        for сырая in r:
            сейчас = time.time()
            s = сырая.decode("utf-8", "replace").strip()
            if s.startswith("data:"):
                к = s[5:].strip()
                if к == "[DONE]":
                    break
                try:
                    d = json.loads(к)
                except Exception:                              # noqa: BLE001
                    d = {}
                т = d.get("type")
                if т == "message_start":
                    вх = int(((d.get("message") or {}).get("usage")
                              or {}).get("input_tokens") or 0)
                elif т == "content_block_delta":
                    кус = (d.get("delta") or {}).get("text") or ""
                    if кус:
                        текст += кус
                        посл = сейчас
                elif т == "message_delta":
                    вых = int((d.get("usage") or {}).get("output_tokens") or вых)
            # ОБРЫВ ПО ТИШИНЕ, а не по числу токенов: срыв 17.08 отдавал
            # готовое письмо в 942-1164 знака, и порог по объёму зарубил бы
            # его. Тишина - другое дело: пока модель молчит, текста не
            # прибавляется, а счётчик выхода растёт.
            if обрывать and текст and (сейчас - посл) > ТИШИНА_СЕК:
                оборван = True
                break
    finally:
        try:
            r.close()
        except Exception:                                      # noqa: BLE001
            pass
    return {"сек": round(time.time() - т0, 1), "знаков": len(текст),
            "вых": вых, "вх": вх, "оборван": оборван}


# --- боевой промпт -------------------------------------------------------
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

п("# Счёт за оборванный поток")
п()
п(f"боевой промпт {len(ПРОМПТ)} знаков | модель {МОДЕЛЬ} | потолок "
  f"{ПОТОЛОК} | обрыв по тишине {ТИШИНА_СЕК} с | повторов {ПОВТОРОВ}")
п()

# --- 1. тишина счётчика --------------------------------------------------
а = счёт()
time.sleep(20)
б = счёт()
п(f"счётчик в покое: {а} -> {б} за 20 с (дрейф {None if а is None else б - а})")
if а is None:
    п("**счётчик недоступен - замер невозможен**")
    raise SystemExit(1)
if б - а > 0:
    п("ВНИМАНИЕ: счётчик бежит сам - кто-то ещё жжёт провайдера, "
      "числа ниже будут завышены на этот фон")

# --- 2. калибровка -------------------------------------------------------
до = счёт()
мал = вызов("Ответь одним словом: готово.", False)
time.sleep(8)
после = счёт()
ед = после - до
п()
п(f"калибровка: вход {мал['вх']}, выход {мал['вых']} -> счётчик +{ед}")
цена_мал = мал["вх"] / 1e6 * 6 + мал["вых"] / 1e6 * 30
if цена_мал > 0:
    п(f"  по тарифу это ${цена_мал:.5f}, то есть 1 доллар ≈ "
      f"{ед / цена_мал:.0f} единиц счётчика")

# --- 3. до конца ---------------------------------------------------------
п()
п("## Вызовы ДО КОНЦА")
п()
до = счёт()
полные = []
for i in range(ПОВТОРОВ):
    x = вызов(ПРОМПТ, False)
    полные.append(x)
    п(f"  #{i+1} вход {x['вх']} выход {x['вых']} текста {x['знаков']} "
      f"{x['сек']}с")
time.sleep(10)
после = счёт()
расход_полных = после - до
п(f"**счётчик: +{расход_полных} на {ПОВТОРОВ} вызова**")

# --- 4. с обрывом --------------------------------------------------------
п()
п("## Вызовы С ОБРЫВОМ по тишине")
п()
до = счёт()
рваные = []
for i in range(ПОВТОРОВ):
    x = вызов(ПРОМПТ, True)
    рваные.append(x)
    п(f"  #{i+1} вход {x['вх']} выход {x['вых']} текста {x['знаков']} "
      f"{x['сек']}с оборван={x['оборван']}")
time.sleep(10)
после = счёт()
расход_рваных = после - до
п(f"**счётчик: +{расход_рваных} на {ПОВТОРОВ} вызова**")

# --- вывод ---------------------------------------------------------------
п()
п("## Вывод")
п()
п(f"до конца: +{расход_полных} | с обрывом: +{расход_рваных}")
if расход_полных > 0:
    д = 100 * (1 - расход_рваных / расход_полных)
    п(f"обрыв дешевле на **{д:.0f}%** по счёту шлюза")
    п()
    п(f"текста получено: до конца "
      f"{[x['знаков'] for x in полные]}, с обрывом {[x['знаков'] for x in рваные]}")
    п(f"секунд: до конца {[x['сек'] for x in полные]}, "
      f"с обрывом {[x['сек'] for x in рваные]}")
    if д < 10:
        п()
        п("**ОБРЫВ ДЕНЕГ НЕ СПАСАЕТ.** Шлюз считает то, что сгенерировала "
          "модель, а не то, что мы забрали. Наш собственный учёт после "
          "такой правки показывал бы экономию, которой нет.")
    else:
        п()
        п("**ОБРЫВ РАБОТАЕТ.** Экономия видна по стороннему счёту, а не "
          "только по нашему.")

текст = "\n".join(СТРОКИ) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/SCHET-OBRYVA.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: SCHET-OBRYVA.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:160])
