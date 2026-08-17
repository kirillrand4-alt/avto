# -*- coding: utf-8 -*-
"""Когда в срыве приходит текст: до взрыва токенов или после.

От этого зависит, можно ли гасить срыв обрывом потока. Замер 17.08 показал:
вызов №6 отдал письмо в 980 знаков за 1829 токенов и 28 секунд, вызов №7 -
те же 942 знака за 13260 токенов и 129 секунд. Взрыв паразитный. Но рвать
поток можно только если текст приходит РАНЬШЕ взрыва: иначе обрыв рубит
готовое письмо, и повтор обойдётся дороже.

Берём НАСТОЯЩИЙ боевой промпт (его собирает gen_prompt на реальной карточке
партии, ~13 тысяч токенов - на маленьком промпте срыв не воспроизводится) и
пишем ленту: на какой секунде сколько знаков текста накоплено и сколько
кадров пришло. Ничего не ставим в очередь.
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

ПОВТОРОВ = int(sys.argv[1]) if len(sys.argv) > 1 else 3
МОДЕЛЬ = "claude-opus-4-8"
ПОТОЛОК = 4000
ГРУППА = "Партия 935"
ОТЧЁТ = r"C:\sender\_ops\LENTA-SRYVA.md"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

# --- собираем НАСТОЯЩИЙ промпт -------------------------------------------
группы = store.recipient_groups().get("по_id") or {}
rid = sorted(r for r, gr in группы.items() if ГРУППА in gr)[0]
rec = store.get_recipient(rid)
req = q._request(rec)
div = str(req.get("target_division") or "kc")
div = div if div in ("kc", "meyer") else "kc"
req["target_division"] = div
ПРОМПТ = gen_prompt([req], load_facts(division=div), div, angle_base=0)
print(f"боевой промпт собран: {len(ПРОМПТ)} знаков "
      f"(~{len(ПРОМПТ) // 3} токенов), компания "
      f"{str(getattr(rec, 'company_name', ''))[:40]}")

ЗАГОЛОВКИ = {"anthropic-version": "2023-06-01",
             "content-type": "application/json",
             "User-Agent": "curl/8.5.0",
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


def один(n):
    тело = {"model": МОДЕЛЬ, "max_tokens": ПОТОЛОК, "stream": True,
            "messages": [{"role": "user", "content": ПРОМПТ}],
            "output_config": {"effort": "low"}}
    req2 = urllib.request.Request(
        os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
        + "/v1/messages", method="POST",
        data=json.dumps(тело).encode(), headers=ЗАГОЛОВКИ)
    т0 = time.time()
    текст = ""
    вых = вх = 0
    стоп = None
    лента = []          # (секунда, знаков текста накоплено)
    молчание = 0.0
    посл_текст = т0
    макс_молчания = 0.0
    with urllib.request.urlopen(req2, timeout=400) as r:
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
            т = d.get("type")
            сейчас = time.time()
            if т == "message_start":
                вх = int(((d.get("message") or {}).get("usage")
                          or {}).get("input_tokens") or 0)
            elif т == "content_block_delta":
                кус = (d.get("delta") or {}).get("text") or ""
                if кус:
                    молчание = сейчас - посл_текст
                    макс_молчания = max(макс_молчания, молчание)
                    посл_текст = сейчас
                    текст += кус
                    лента.append((round(сейчас - т0, 1), len(текст)))
            elif т == "message_delta":
                вых = int((d.get("usage") or {}).get("output_tokens") or вых)
                стоп = (d.get("delta") or {}).get("stop_reason") or стоп
    всего = time.time() - т0
    макс_молчания = max(макс_молчания, time.time() - посл_текст)
    п(f"\n### вызов {n}")
    п()
    п(f"вход {вх} | выход {вых} | текста {len(текст)} знаков | "
      f"{всего:.1f} с | stop={стоп!r}")
    п(f"знаков на токен выхода: {len(текст) / max(1, вых):.2f} "
      f"(норма около 2)")
    п(f"максимальная пауза без текста: {макс_молчания:.1f} с")
    if лента:
        п(f"первый знак текста: {лента[0][0]} с | последний: {лента[-1][0]} с")
        # где текст был бы уже цел, если резать по времени
        for порог in (30, 45, 60, 90):
            было = max([з for с, з in лента if с <= порог] or [0])
            п(f"  обрыв на {порог:>3} с: в руках было бы {было} знаков "
              f"из {len(текст)}")
    else:
        п("ТЕКСТА НЕ БЫЛО ВОВСЕ")
    return {"вых": вых, "знаков": len(текст), "сек": всего,
            "пауза": макс_молчания, "лента": лента}


п("# Лента срыва: когда приходит текст")
п()
п(f"промпт {len(ПРОМПТ)} знаков, модель {МОДЕЛЬ}, потолок {ПОТОЛОК}, "
  f"effort=low - как в бою")
итоги = []
for i in range(ПОВТОРОВ):
    try:
        итоги.append(один(i + 1))
    except Exception as ex:                                    # noqa: BLE001
        п(f"\nвызов {i+1} УПАЛ: {type(ex).__name__} {str(ex)[:140]}")

if итоги:
    п()
    п("## Свод")
    п()
    п("| вызов | выход | знаков | зн/ток | сек | макс пауза без текста |")
    п("|---|---|---|---|---|---|")
    for i, x in enumerate(итоги, 1):
        п(f"| {i} | {x['вых']} | {x['знаков']} | "
          f"{x['знаков'] / max(1, x['вых']):.2f} | {x['сек']:.1f} | "
          f"{x['пауза']:.1f} |")
    п()
    п("Если текст приходит рано, а дальше идёт долгая тишина - обрыв по "
      "тишине гасит срыв, не трогая письмо. Если текст приходит В КОНЦЕ - "
      "обрыв рубит готовое письмо, и предложение резать поток неверно.")

текст = "\n".join(СТРОКИ) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/LENTA-SRYVA.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: LENTA-SRYVA.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:160])
