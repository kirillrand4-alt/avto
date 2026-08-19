# -*- coding: utf-8 -*-
"""Письма на не-клодовских моделях шлюза: работает ли вообще и как читается.

Владелец: «проверь качество письма ещё на других моделях, гемини, гпт,
дипсик и тд». Гоняем НАСТОЯЩИЙ промпт письма (те же правила, факты, формат)
на каждой модели по двум компаниям и смотрим три вещи:
  1. отвечает ли модель в нашем формате (строгий JSON) — половина чужих
     моделей на этом отваливается, и это не «плохое письмо», а вообще нет
     письма;
  2. как читается текст — печатаем целиком, судить будет владелец;
  3. во что обошёлся вызов по ФАКТИЧЕСКОЙ ставке шлюза (вторая колонка его
     прайса — «с учётом типа баланса»; она у deepseek в 17 раз ВЫШЕ
     номинала, а у gpt и grok ниже).

Журнал durable: строки пишутся в jsonl по мере готовности.
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\chuzhie-modeli-pisma.jsonl"
# Ставки — ФАКТИЧЕСКИЕ (вторая колонка прайса шлюза), не номинал.
СТАВКИ = {
    "gpt-5.6-luna":           (0.11, 0.67),
    "grok-4.6":               (0.93, 2.78),
    "gpt-5.6-terra":          (1.11, 6.67),
    "gpt-5.4":                (1.39, 8.33),
    "gemini-3.6-flash":       (2.60, 13.02),
    "gpt-5.5":                (2.78, 16.67),
    "gemini-3.1-pro-preview": (3.47, 20.83),
    "kimi-k3":                (6.41, 32.05),
    "deepseek-v4-flash":      (7.33, 22.00),
    "claude-opus-4-8":        (5.00, 25.00),
}
МОДЕЛИ = [м for м in sys.argv[1:] if not м.isdigit()] or list(СТАВКИ)

ФИРМЫ = [("ООО «Первый Прокатный»", "прокат чёрных металлов", "24.10"),
         ("ООО «Второй Литейный»", "литьё чугуна", "24.51")]
факты = load_facts(division="kc")


def разобрать(текст):
    """Наш формат: {"letters":[{"idx":N,"subject":..,"body":..}]}."""
    t = re.sub(r"```(json)?", "", текст or "").strip()
    try:
        d = json.loads(t)
    except Exception:                                            # noqa: BLE001
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except Exception:                                        # noqa: BLE001
            return None
    л = (d or {}).get("letters")
    return л[0] if isinstance(л, list) and л else None


итог = {}
for м in МОДЕЛИ:
    вх_ст, вых_ст = СТАВКИ.get(м, (5.0, 25.0))
    цена = 0.0
    удачи = 0
    письма = []
    for i, (фирма, вид, оквэд) in enumerate(ФИРМЫ):
        пол = {"mode": "GENERIC", "company_name": фирма, "activity": вид,
               "okved": оквэд, "extra": {}}
        промпт = gen_prompt([пол], факты, "kc", angle_base=i)
        сис, тело = GP.razrezat_promt(промпт)
        т0 = time.time()
        try:
            msg = GP._raw_stream([{"role": "user", "content": тело}], м, 2000,
                                 thinking=False, effort="low", system=сис)
        except Exception as ex:                                  # noqa: BLE001
            print(f"[{м}] вызов {i+1} упал: {type(ex).__name__}: "
                  f"{str(ex)[:120]}")
            continue
        текст = "".join(b.text for b in msg.content
                        if getattr(b, "type", "") == "text")
        u = getattr(msg, "usage", None)
        вх = int(getattr(u, "input_tokens", 0) or 0)
        вых = int(getattr(u, "output_tokens", 0) or 0)
        ц = вх / 1e6 * вх_ст + вых / 1e6 * вых_ст
        цена += ц
        п = разобрать(текст)
        if п:
            удачи += 1
            письма.append(п)
        запись = {"модель": м, "фирма": фирма, "формат_ок": bool(п),
                  "вход": вх, "выход": вых, "цена_$": round(ц, 5),
                  "сек": int(time.time() - т0),
                  "тема": (п or {}).get("subject"),
                  "тело": (п or {}).get("body"),
                  "сырое": None if п else текст[:600]}
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps(запись, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        print(f"[{м}] {i+1}/2 формат={'ок' if п else 'НЕТ'} "
              f"вход {вх} выход {вых} {int(time.time()-т0)}с ${ц:.4f}")
    итог[м] = (удачи, цена / max(1, len(ФИРМЫ)), письма)

print("\n== СВОДКА ==")
print(f"{'модель':<24} {'в формате':>10} {'$/вызов':>9}")
for м, (у, ц, _) in sorted(итог.items(), key=lambda t: t[1][1]):
    print(f"{м:<24} {у}/2{'':>7} {ц:>9.4f}")
print(f"\nжурнал: {ЖУРНАЛ}")
