# -*- coding: utf-8 -*-
"""Работает ли кэш промпта на шлюзе. Перепроверка по СТОРОННЕМУ счёту.

Первый замер 17.08 сказал «кэш не работает и на 19% дороже». Оба вывода
стояли на непроверенных допущениях:

  * «дороже» посчитано по тарифу Anthropic (запись кэша 1.25 ставки,
    чтение 0.1). Как этот шлюз выставляет счёт за запись - НЕ ПРОВЕРЕНО.
    То есть число вышло из формулы, а не из замера;
  * не пробовал заголовок anthropic-beta и не пробовал случай, когда
    запрос повторяется ЦЕЛИКОМ, без меняющегося хвоста.

Здесь оба недостатка сняты. Расход берём из монотонного total_usage самого
шлюза (GET /dashboard/billing/usage, Bearer): что бы он ни считал, разница
до и после одинакового числа одинаковых вызовов - честная.

Условие корректности: пока идёт чужая генерация, счётчик бежит сам, и замер
испорчен. Поэтому сначала меряем дрейф в покое и печатаем его.
"""
import io
import json
import os
import sys
import time
import urllib.request

БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
КЛЮЧ = os.environ["PROVIDER_API_KEY"]
МОДЕЛЬ = "claude-opus-4-8"
ПОВТОРОВ = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ОТЧЁТ = r"C:\sender\_ops\KESH-PROMTA.md"

ПРАВИЛО = ("Правило письма: предприятие названо в теме и в теле; объём "
           "45-140 слов; длинные тире запрещены; списки запрещены; марки "
           "оборудования запрещены; числа только из карточки; байлайн "
           "«ООО «Руспром»»; заход не повторяет предыдущие письма партии. ")
СТАТИКА = "СТАЙЛГАЙД.\n" + "".join(
    f"{i+1}. {ПРАВИЛО}\n" for i in range(120))

С = []


def п(s=""):
    С.append(s)
    print(s)


def счёт():
    rq = urllib.request.Request(
        БАЗА + "/dashboard/billing/usage",
        headers={"Authorization": "Bearer " + КЛЮЧ,
                 "User-Agent": "curl/8.5.0"})
    try:
        with urllib.request.urlopen(rq, timeout=40) as r:
            return float(json.loads(r.read()).get("total_usage"))
    except Exception as ex:                                    # noqa: BLE001
        п(f"счётчик не прочитался: {str(ex)[:120]}")
        return None


def вызов(хвост, с_кэшем, бета):
    зг = {"anthropic-version": "2023-06-01",
          "content-type": "application/json", "User-Agent": "curl/8.5.0",
          "x-api-key": КЛЮЧ}
    for h in ("X-Stainless-Lang", "X-Stainless-Package-Version",
              "X-Stainless-OS", "X-Stainless-Arch", "X-Stainless-Runtime",
              "X-Stainless-Runtime-Version", "X-Stainless-Retry-Count",
              "X-Stainless-Timeout"):
        зг[h] = ""
    if бета:
        зг["anthropic-beta"] = "prompt-caching-2024-07-31"
    блоки = [{"type": "text", "text": СТАТИКА}]
    if с_кэшем:
        блоки[0]["cache_control"] = {"type": "ephemeral"}
    блоки.append({"type": "text", "text": хвост})
    тело = {"model": МОДЕЛЬ, "max_tokens": 100, "stream": True,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": блоки}]}
    rq = urllib.request.Request(БАЗА + "/v1/messages", method="POST",
                                data=json.dumps(тело).encode(), headers=зг)
    u = {}
    with urllib.request.urlopen(rq, timeout=200) as r:
        for сырая in r:
            s = сырая.decode("utf-8", "replace").strip()
            if not s.startswith("data:"):
                continue
            к = s[5:].strip()
            if к == "[DONE]":
                break
            try:
                d = json.loads(к)
            except Exception:                                  # noqa: BLE001
                continue
            if d.get("type") == "message_start":
                u.update(((d.get("message") or {}).get("usage")) or {})
            elif d.get("type") == "message_delta":
                u.update(d.get("usage") or {})
    return {"вход": int(u.get("input_tokens") or 0),
            "запись": int(u.get("cache_creation_input_tokens") or 0),
            "чтение": int(u.get("cache_read_input_tokens") or 0),
            "выход": int(u.get("output_tokens") or 0)}


def серия(имя, с_кэшем, бета, одинаковый_хвост):
    до = счёт()
    ряд = []
    for i in range(ПОВТОРОВ):
        хвост = ("Ответь одним словом: готово." if одинаковый_хвост
                 else f"Вариант {i}. Ответь одним словом: готово.")
        ряд.append(вызов(хвост, с_кэшем, бета))
    time.sleep(10)
    после = счёт()
    д = None if (до is None or после is None) else после - до
    п(f"| {имя} | {ряд[0]['вход']} | {ряд[0]['запись']} | {ряд[0]['чтение']} "
      f"| {ряд[-1]['вход']} | {ряд[-1]['запись']} | {ряд[-1]['чтение']} | "
      f"{'—' if д is None else format(д, '.4f')} |")
    return {"имя": имя, "ряд": ряд, "счёт": д}


п("# Кэш промпта на шлюзе: перепроверка по стороннему счёту")
п()
п(f"статика {len(СТАТИКА)} знаков | модель {МОДЕЛЬ} | повторов на серию "
  f"{ПОВТОРОВ}")
п()

а = счёт()
time.sleep(25)
б = счёт()
дрейф = None if (а is None or б is None) else б - а
п(f"счётчик в покое за 25 с: {а} -> {б}, дрейф **{дрейф}**")
if дрейф:
    п()
    п("**ВНИМАНИЕ: счётчик бежит сам** — идёт чужая генерация. Числа ниже "
      "содержат этот фон, отношение серий смотреть с поправкой на него.")
п()
п("| серия | 1-й: вход | 1-й: запись | 1-й: чтение | посл: вход | "
  "посл: запись | посл: чтение | прирост счёта |")
п("|---|---|---|---|---|---|---|---|")

итоги = [
    серия("без cache_control (как в бою)", False, False, False),
    серия("cache_control, хвост меняется", True, False, False),
    серия("cache_control, хвост ОДИНАКОВЫЙ", True, False, True),
    серия("cache_control + anthropic-beta", True, True, False),
    серия("без cache_control, хвост одинаковый", False, False, True),
]

п()
п("## Вывод")
п()
чит = [x for x in итоги if any(r["чтение"] > 100 for r in x["ряд"])]
if чит:
    п("Шлюз ОТДАЁТ чтение кэша в сериях: "
      + ", ".join(x["имя"] for x in чит))
else:
    п("**Ни в одной серии шлюз не отдал чтение кэша больше 100 токенов.** "
      "Поле cache_read_input_tokens держится на постоянной величине и без "
      "cache_control — это не наши токены.")
п()
база = итоги[0]["счёт"]
if база:
    for x in итоги[1:]:
        if x["счёт"] is None:
            continue
        п(f"* {x['имя']}: прирост {x['счёт']:.4f} против {база:.4f} у "
          f"базовой серии — {'дешевле' if x['счёт'] < база else 'ДОРОЖЕ'} "
          f"на {abs(100 * (x['счёт'] - база) / база):.0f}%")
    п()
    п("Это отношение снято со счётчика самого шлюза, а не из тарифной "
      "формулы — прошлый вывод «на 19% дороже» был как раз из формулы и "
      "потому не считается.")
else:
    п("Счётчик не дал разницы — либо недоступен, либо шаг слишком мелкий "
      "для такого числа вызовов. Увеличить ПОВТОРОВ и повторить.")

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/KESH-PROMTA.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: KESH-PROMTA.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:160])
