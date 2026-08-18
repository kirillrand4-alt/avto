# -*- coding: utf-8 -*-
"""Пилот: письма ПАЧКОЙ в один вызов вместо одного за раз.

Владелец помнит разговор: «ты говорил судить по 4 и ещё что-то». Речь про
это. Сейчас конвейер зовёт generate([req]) - одно письмо на круг, и все
проверки (судья вариантов, верификатор правил, инженерная линза) читают
одно письмо. У AiLetterGen есть batch, и проверки умеют читать пачку: на
четырёх письмах их постоянная часть делится на четыре.

Чего ждать честно. После починки кэша (18.08) постоянная часть промпта уже
читается из кэша по 0.1 ставки, так что вторая экономия будет МЕНЬШЕ, чем
я обещал до того замера: выход моделей пачка не сокращает, а он и есть
большая доля счёта. Поэтому меряем, а не рассуждаем.

Письма не выбрасываем: текст ложится в тот же журнал партии, и штатный
ops/partiya_dolozhit_iz_zhurnala.py кладёт их в очередь тем же кодом, что
и обычный прогон. Пилот ничего не отправляет.

    python zapusk_svoego_skripta.py ops/pilot_pachka.py 8 4 kc 2
      8  - сколько писем, 4 - размер пачки,
      kc - направление, 2 - только корпоративные (1 - только публичные)
"""
import io
import json
import os
import sys
import threading
import time
from collections import Counter
from datetime import date

sys.path.insert(0, r"C:\sender")
import gen_provider                                              # noqa: E402
from sender.ai_letter import (AiLetterGen, load_facts,           # noqa: E402
                              target_division)
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

ПИСЕМ = int(sys.argv[1]) if len(sys.argv) > 1 else 8
ПАЧКА = int(sys.argv[2]) if len(sys.argv) > 2 else 4
НАПР = (sys.argv[3] if len(sys.argv) > 3 else "kc").lower()
КОРП = sys.argv[4] if len(sys.argv) > 4 else "2"

МОДЕЛЬ = "claude-opus-4-8"
ЦЕНА = (5.0, 25.0)
МОДЕЛЬ_ПРОВЕРОК = os.environ.get("GEN_CHECKER_MODEL", "claude-sonnet-4-6")
ЦЕНА_ПРОВЕРОК = (3.0, 15.0)
ВАРИАНТОВ = int(os.environ.get("GEN_BEST_OF", "2"))
ГРУППА = "Партия 935"
КАМПАНИЯ = {"kc": 10, "meyer": 11}
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ПОТОЛОК_ОТВЕТА = 4000
СВОЙ_СЕРВЕР = ("other", "unknown", "")


def _цена(расход, тариф):
    вход = (расход.get("in", 0) + 1.25 * расход.get("cw", 0)
            + 0.10 * расход.get("cr", 0))
    return вход / 1e6 * тариф[0] + расход.get("out", 0) / 1e6 * тариф[1]


cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
_факты = {"kc": load_facts(division="kc"),
          "meyer": load_facts(division="meyer")}

# --- отбор: тот же, что у партийного прогона ------------------------------
сделано_инн = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
        except Exception:                                        # noqa: BLE001
            continue
        if z.get("ок") or z.get("тело"):
            сделано_инн.add(str(z.get("inn") or ""))

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
пары, счёт, видели = [], Counter(), set()
for rid in в_группе:
    if len(пары) >= ПИСЕМ:
        break
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email or inn in видели or inn in сделано_инн:
        счёт["уже есть / без реквизитов"] += 1
        continue
    видели.add(inn)
    причина = cs._guard(inn=inn, email=email)
    if причина:
        счёт[f"заслон: {причина.split(':')[0]}"] += 1
        continue
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    свой = mx in СВОЙ_СЕРВЕР
    if (КОРП == "2" and not свой) or (КОРП == "1" and свой):
        счёт["не тот почтовик"] += 1
        continue
    req = q._request(rec)
    _явное = str(req.get("target_division") or "")
    div = _явное if _явное in КАМПАНИЯ else target_division(req,
                                                            default="kc")[0]
    div = div if div in КАМПАНИЯ else "kc"
    if div != НАПР:
        счёт[f"другое направление: {div}"] += 1
        continue
    req["target_division"] = div
    req.setdefault("extra", {})["angle_shift"] = rid
    try:
        q._add_ideas_generic([req])
    except Exception as ex:                                      # noqa: BLE001
        print(f"  идеи не раздались #{rid}: {str(ex)[:80]}")
    пары.append((rid, rec, inn, req, div))

print(f"к генерации пачками по {ПАЧКА}: {len(пары)}")
for k, n in счёт.most_common(6):
    print(f"  {k}: {n}")
if not пары:
    raise SystemExit(0)

расход = {"in": 0, "out": 0}
расход_проверок = {"in": 0, "out": 0}
свой_замок = threading.Lock()


def _зов(prompt, модель, счёт_):
    посл = None
    системный, тело = gen_provider.razrezat_promt(prompt)
    усилие = "low"
    for i in range(4):
        try:
            m = gen_provider._raw_stream(
                [{"role": "user", "content": тело}], модель, ПОТОЛОК_ОТВЕТА,
                thinking=False, effort=усилие, system=системный)
            т = "".join(b.text for b in m.content
                        if getattr(b, "type", "") == "text")
            u = getattr(m, "usage", None)
            with свой_замок:
                счёт_["in"] += int(getattr(u, "input_tokens", 0) or 0)
                счёт_["cw"] = счёт_.get("cw", 0) + int(
                    getattr(u, "cache_creation_input_tokens", 0) or 0)
                счёт_["cr"] = счёт_.get("cr", 0) + int(
                    getattr(u, "cache_read_input_tokens", 0) or 0)
                счёт_["out"] += int(getattr(u, "output_tokens", 0) or 0)
                счёт_["вызовов"] = счёт_.get("вызовов", 0) + 1
            if т and len(т) >= 20:
                return т
            raise RuntimeError("короткий ответ")
        except Exception as ex:                                  # noqa: BLE001
            посл = ex
            time.sleep(min(20, 2 ** i))
    raise RuntimeError(str(посл)[:150])


t0 = time.time()
res = AiLetterGen(lambda p: _зов(p, МОДЕЛЬ, расход),
                  facts_by_division=_факты, best_of=ВАРИАНТОВ,
                  batch=ПАЧКА,
                  checker=((lambda p: _зов(p, МОДЕЛЬ_ПРОВЕРОК,
                                           расход_проверок))
                           if МОДЕЛЬ_ПРОВЕРОК else None)
                  ).generate([п[3] for п in пары])
сек = time.time() - t0

день = date.today().isoformat()
вышло = 0
for i, (rid, rec, inn, req, div) in enumerate(пары):
    L = res.ok.get(i)
    брак = [str(x)[:150] for x in (res.rejected.get(i) or [])][:2]
    зап = {"recipient_id": rid, "inn": inn,
           "имя": str(getattr(rec, "company_name", "") or "")[:40],
           "направление": div, "модель": МОДЕЛЬ, "ок": bool(L),
           "брак": брак, "день": день, "пилот": f"пачка {ПАЧКА}",
           "этап": "сгенерировано"}
    if L:
        вышло += 1
        зап["тема"] = L.get("subject")
        зап["тело"] = L.get("body")
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
        f.write(json.dumps(зап, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print(f"  [{i + 1}/{len(пары)}] {'ОК  ' if L else 'брак'} "
          f"{зап['имя'][:32]:<34} {(брак or [''])[0][:70]}")

ц = _цена(расход, ЦЕНА) + _цена(расход_проверок, ЦЕНА_ПРОВЕРОК)
вызовов = расход.get("вызовов", 0) + расход_проверок.get("вызовов", 0)
print(f"\nпачками по {ПАЧКА}: {len(пары)} попыток -> {вышло} писем за "
      f"{сек:.0f}с")
print(f"  вызовов: {вызовов} ({вызовов / max(1, len(пары)):.1f} на письмо)")
print(f"  кэш: прочитано {расход.get('cr', 0) + расход_проверок.get('cr', 0)}"
      f", записано {расход.get('cw', 0) + расход_проверок.get('cw', 0)}")
print(f"  по журналу: ${ц:.2f} = ${ц / max(1, len(пары)):.4f} за попытку, "
      f"${ц / max(1, вышло):.4f} за готовое письмо")
print("\nдля сравнения по одному письму на вызов (замер 18.08): "
      "$0.1570 за попытку, $0.1963 за готовое")
print("тексты в журнале партии; в очередь их кладёт "
      "ops/partiya_dolozhit_iz_zhurnala.py primenit")
