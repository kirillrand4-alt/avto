# -*- coding: utf-8 -*-
"""Из чего складывается цена ОДНОГО письма: лог каждого вызова провайдера.

Журнал партии считает деньги только по вызовам боевого `caller` внутри
AiLetterGen. Мимо этого счёта идут идеи-линзы (`ai_quota._add_ideas_generic`
зовёт gen_provider.call напрямую), а это ещё четыре вызова на письмо. То
есть «$2.40 за письмо» - нижняя оценка, а не полная.

Здесь перехватываем ОБА пути - `_raw_stream` и `call` - и пишем на каждый
вызов: стадия, модель, потолок, thinking, effort, токены входа/выхода,
секунды, знаков текста, stop_reason. Стадию узнаём по промпту.

Письмо НЕ ставится в очередь: это замер, а не генерация. Аргумент - сколько
писем прогнать (по умолчанию 1).

    python zapusk_svoego_skripta.py ops/partiya_cena_pisma.py 1 --timeout=1500
"""
import io
import json
import os
import sys
import threading
import time
import urllib.request
from collections import Counter

sys.path.insert(0, r"C:\sender")
import gen_provider                                           # noqa: E402
from sender.ai_letter import AiLetterGen, load_facts          # noqa: E402
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.confirm import ConfirmSend                        # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.suppression import Suppression                    # noqa: E402

МОДЕЛЬ = "claude-opus-4-8"
ЦЕНА = {"opus": (5.0, 25.0), "haiku": (1.0, 5.0), "fable": (10.0, 50.0)}
ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ПОТОЛОК_ОТВЕТА = 4000
СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 else 1
ОТЧЁТ = r"C:\sender\_ops\CENA-PISMA.md"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
_факты = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}


def цена_за(модель, вх, вых):
    for к, (a, b) in ЦЕНА.items():
        if к in str(модель):
            return вх / 1e6 * a + вых / 1e6 * b
    return вх / 1e6 * 6.0 + вых / 1e6 * 30.0


def стадия_по_промпту(p):
    """Стадию узнаём по промпту: тегов сюда не доносят."""
    н = (p or "")[:4000].lower()
    if "какие 2 захода" in н or "заставили бы тебя ответить" in н:
        return "идея: линза"
    if "выбери одну лучшую идею" in н:
        return "идея: судья"
    if "выбери" in н and "вариант" in н and "idx" in н:
        return "письмо: судья best_of"
    if "verdict" in н or "вердикт" in н:
        return "письмо: верификатор"
    if "letters" in н and "subject" in н:
        return "письмо: генерация"
    return "прочее"


ЛОГ = []
замок = threading.Lock()
_настоящий_raw = gen_provider._raw_stream
_настоящий_call = gen_provider.call


def _мой_raw(messages, model, max_tokens, thinking=True, effort=None):
    промпт = ""
    try:
        промпт = str((messages or [{}])[0].get("content") or "")
    except Exception:                                          # noqa: BLE001
        pass
    т0 = time.time()
    сбой = None
    m = None
    try:
        m = _настоящий_raw(messages, model, max_tokens,
                           thinking=thinking, effort=effort)
    except Exception as ex:                                    # noqa: BLE001
        сбой = f"{type(ex).__name__}: {str(ex)[:90]}"
        raise
    finally:
        сек = round(time.time() - т0, 1)
        u = getattr(m, "usage", None) or {}
        if not isinstance(u, dict):
            u = {"input_tokens": getattr(u, "input_tokens", 0),
                 "output_tokens": getattr(u, "output_tokens", 0)}
        вх = int(u.get("input_tokens") or 0)
        вых = int(u.get("output_tokens") or 0)
        т = ""
        if m is not None:
            т = "".join(b.text for b in m.content
                        if getattr(b, "type", "") == "text")
        with замок:
            ЛОГ.append({
                "стадия": стадия_по_промпту(промпт), "модель": str(model),
                "потолок": max_tokens, "thinking": bool(thinking),
                "effort": effort or "(по умолчанию high)",
                "промпт_знаков": len(промпт), "вход": вх, "выход": вых,
                "знаков": len(т), "сек": сек,
                "стоп": getattr(m, "stop_reason", None) if m else None,
                "сбой": сбой,
                "цена": round(цена_за(model, вх, вых), 4),
                "срыв": bool(вых >= ПОТОЛОК_ОТВЕТА * 0.7 and len(т) < вых)})
    return m


def _мой_call(client, messages, model="claude-opus-4-8", attempts=8, effort=None):
    return _настоящий_call(client, messages, model=model, attempts=attempts,
                           effort=effort)


gen_provider._raw_stream = _мой_raw
gen_provider.call = _мой_call

# --- кого меряем: те же правила отбора, что в бою -------------------------
сделано = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                      # noqa: BLE001
            continue
        if (z.get("ок") or z.get("тело")) and z.get("inn"):
            сделано.add(str(z["inn"]))

группы = store.recipient_groups().get("по_id") or {}
пары, видели = [], set()
for rid in sorted(r for r, gr in группы.items() if ГРУППА in gr):
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email or inn in видели or inn in сделано:
        continue
    видели.add(inn)
    if cs._guard(inn=inn, email=email):
        continue
    пары.append((rid, rec, inn))
    if len(пары) >= СКОЛЬКО:
        break

print(f"меряю писем: {len(пары)}  (в очередь НЕ ставлю)")

СТРОКИ = []


def п(s=""):
    СТРОКИ.append(s)
    print(s)


for rid, rec, inn in пары:
    ЛОГ.clear()
    имя = str(getattr(rec, "company_name", "") or "")[:44]
    т0 = time.time()
    req = q._request(rec)
    div = str(req.get("target_division") or "kc")
    req["target_division"] = div if div in ("kc", "meyer") else "kc"
    req.setdefault("extra", {})["angle_shift"] = rid
    идеи_т0 = time.time()
    try:
        q._add_ideas_generic([req])
    except Exception as ex:                                    # noqa: BLE001
        print("  идеи не раздались:", str(ex)[:80])
    идеи_сек = round(time.time() - идеи_т0, 1)
    идей_вызовов = len(ЛОГ)

    def caller(prompt):
        усилие = "low"
        посл = None
        for i in range(4):
            try:
                m = gen_provider._raw_stream(
                    [{"role": "user", "content": prompt}], МОДЕЛЬ,
                    ПОТОЛОК_ОТВЕТА, thinking=False, effort=усилие)
                т = "".join(b.text for b in m.content
                            if getattr(b, "type", "") == "text")
                if т and len(т) >= 20:
                    return т
                raise RuntimeError("короткий ответ")
            except Exception as ex:                            # noqa: BLE001
                посл = ex
                time.sleep(min(20, 2 ** i))
        raise RuntimeError(str(посл)[:150])

    try:
        res = AiLetterGen(caller, facts_by_division=_факты,
                          best_of=3).generate([req])
        L = res.ok.get(0)
        брак = [str(x)[:110] for x in (res.rejected.get(0) or [])][:3]
    except Exception as ex:                                    # noqa: BLE001
        L, брак = None, ["упало: " + str(ex)[:110]]
    всего_сек = round(time.time() - т0, 1)

    п(f"\n# Цена письма: {имя}")
    п()
    п(f"rid {rid} | направление {req['target_division']} | "
      f"{'ПИСЬМО ВЫШЛО' if L else 'БРАК: ' + str(брак)[:90]}")
    п(f"всего {всего_сек} с, из них идеи {идеи_сек} с ({идей_вызовов} вызовов)")
    п()
    п("| # | стадия | модель | thinking | effort | вход | выход | знаков | сек | срыв | $ |")
    п("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, z in enumerate(ЛОГ, 1):
        п(f"| {i} | {z['стадия']} | {z['модель'].replace('claude-', '')} | "
          f"{'да' if z['thinking'] else 'нет'} | {z['effort']} | {z['вход']} | "
          f"{z['выход']} | {z['знаков']} | {z['сек']} | "
          f"{'ДА' if z['срыв'] else ''} | {z['цена']:.4f} |")
    итого = sum(z["цена"] for z in ЛОГ)
    по_стадиям = Counter()
    цена_стадий = Counter()
    for z in ЛОГ:
        по_стадиям[z["стадия"]] += 1
        цена_стадий[z["стадия"]] += z["цена"]
    п()
    п(f"**ИТОГО {len(ЛОГ)} вызовов, ${итого:.3f}**")
    п()
    п("| стадия | вызовов | $ | доля |")
    п("|---|---|---|---|")
    for с, n in по_стадиям.most_common():
        п(f"| {с} | {n} | {цена_стадий[с]:.3f} | "
          f"{100 * цена_стадий[с] / max(1e-9, итого):.0f}% |")
    срывов = sum(1 for z in ЛОГ if z["срыв"])
    цена_срывов = sum(z["цена"] for z in ЛОГ if z["срыв"])
    п()
    п(f"срывов {срывов} из {len(ЛОГ)} вызовов, на них ${цена_срывов:.3f} "
      f"({100 * цена_срывов / max(1e-9, итого):.0f}% цены письма)")
    п(f"вход суммарно {sum(z['вход'] for z in ЛОГ)} токенов, "
      f"выход {sum(z['выход'] for z in ЛОГ)}")
    п(f"цена входа ${sum(z['вход'] for z in ЛОГ) / 1e6 * 6:.3f}, "
      f"цена выхода ${sum(z['выход'] for z in ЛОГ) / 1e6 * 30:.3f}")

текст = "\n".join(СТРОКИ) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    req2 = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/CENA-PISMA.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(req2, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: CENA-PISMA.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:160])
