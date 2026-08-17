# -*- coding: utf-8 -*-
"""Генерация партии 935 С ПОШТУЧНЫМ УЧЁТОМ каждого вызова провайдера.

Зачем отдельный скрипт, а не флаг в partiya_gen.py: тот файл делят две
сессии, и 17.08 их выкатка легла поверх нашей за 21 секунду до старта -
оба прогона выполнили чужой код. Пока это так, свои правки держим по своему
пути.

Отличия от partiya_gen.py ровно два:

  * перехвачен gen_provider._raw_stream: на КАЖДЫЙ вызов пишется строка в
    gen-partiya-935-vyzovy.jsonl - модель, thinking, effort, токены входа и
    выхода, знаки текста, секунды, stop_reason, признак срыва. Журнал партии
    так не умеет: он считает только вызовы боевого caller внутри
    AiLetterGen, а идеи-линзы (ai_quota._add_ideas_generic зовёт
    gen_provider.call напрямую) идут мимо его счёта. Отсюда и была
    заниженная оценка «$2.40 за письмо»;
  * режим рассуждения задаётся аргументом, чтобы сравнивать замером, а не
    спором.

Письма ставятся в очередь как обычно: замер на десяти письмах стоит около
двадцати долларов, и выбрасывать за эти деньги готовые письма незачем.

    python zapusk_svoego_skripta.py ops/partiya_gen_s_zamerom.py \\
        10 1500 kak_seychas --timeout=1600

argv: сколько писем | лимит секунд | режим рассуждения
режимы: kak_seychas | disabled | disabled_bez_effort | bez_nastroek
"""
import io
import json
import os
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.path.insert(0, r"C:\sender")
import gen_provider                                           # noqa: E402
from sender.ai_letter import AiLetterGen, load_facts          # noqa: E402
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.confirm import ConfirmSend                        # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.suppression import Suppression                    # noqa: E402

МОДЕЛЬ = "claude-opus-4-8"
ЦЕНА = (6.0, 30.0)
ЦЕНА_HAIKU = (1.0, 5.0)
ГРУППА = "Партия 935"
КАМПАНИЯ = {"kc": 10, "meyer": 11}
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ВЫЗОВЫ = r"C:\sender\_ops\gen-partiya-935-vyzovy.jsonl"
ОТЧЁТ = r"C:\sender\_ops\ZAMER-10-PISEM.md"
ПОТОКОВ = 25
ПОТОЛОК_ОТВЕТА = 4000

ПОТОЛОК = int(sys.argv[1]) if len(sys.argv) > 1 else 10
ЛИМИТ_СЕК = (int(sys.argv[2]) if len(sys.argv) > 2 else 1500) - 150
РЕЖИМ = sys.argv[3] if len(sys.argv) > 3 else "kak_seychas"

# РЕЖИМЫ РАССУЖДЕНИЯ. «Как сейчас» - ровно то, что шлёт боевой код:
# поле thinking НЕ КЛАДЁТСЯ вовсе (gen_provider при thinking=False его
# просто опускает), effort=low. Остальные - способы сказать «не рассуждай»
# явно; какой из них дешевле, решает замер.
РЕЖИМЫ = {
    "kak_seychas": (None, "low"),
    "disabled": ({"type": "disabled"}, "low"),
    "disabled_bez_effort": ({"type": "disabled"}, None),
    "bez_nastroek": (None, None),
}
if РЕЖИМ not in РЕЖИМЫ:
    print(f"неизвестный режим {РЕЖИМ!r}, знаю: {', '.join(РЕЖИМЫ)}")
    raise SystemExit(2)
ДУМАТЬ, УСИЛИЕ = РЕЖИМЫ[РЕЖИМ]

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
_факты = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}

замок = threading.Lock()
замок_вызовов = threading.Lock()
ЛОГ = []


def _в_вызовы(з):
    with замок_вызовов:
        ЛОГ.append(з)
        with io.open(ВЫЗОВЫ, "a", encoding="utf-8") as f:
            f.write(json.dumps(з, ensure_ascii=False) + "\n")
            f.flush()


_настоящий_raw = gen_provider._raw_stream


def _токены(m):
    """(вход, выход) из ответа. Учёт 17.08 показал ноль по всем письмам.

    Причина: _Msg.usage это ОБЪЕКТ _Usage, а не словарь (gen_provider
    строит его как `self.usage = _Usage(usage)`). Первая редакция читала
    его через .get() и на проверке isinstance(u, dict) обнуляла всё - в
    отчёте на десяти письмах цена вышла $0.000, и это был баг замера, а не
    бесплатные письма. Боевой partiya_gen.py читает через getattr, потому
    у него числа и правильные. Читаем обоими способами.
    """
    u = getattr(m, "usage", None)
    if u is None:
        return 0, 0
    if isinstance(u, dict):
        return int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
    return (int(getattr(u, "input_tokens", 0) or 0),
            int(getattr(u, "output_tokens", 0) or 0))


def _мой_raw(messages, model, max_tokens, thinking=True, effort=None):
    """Перехват: считаем КАЖДЫЙ вызов, включая идеи-линзы.

    Режим применяем ко ВСЕМ моделям, а не только к боевой. Линзы идей идут
    через gen_provider.call, а там thinking=True по умолчанию - и замер
    17.08 показал, чем это кончается: три вызова haiku по 67-69 секунд,
    205 секунд из 707 на письмо. Стоят они копейки ($0.008), но время едят
    втрое больше, чем сама генерация.
    """
    свой = РЕЖИМ != "kak_seychas"
    if свой:
        thinking = False
        effort = УСИЛИЕ
    промпт = ""
    try:
        промпт = str((messages or [{}])[0].get("content") or "")
    except Exception:                                          # noqa: BLE001
        pass
    т0 = time.time()
    m = None
    сбой = None
    try:
        if свой and ДУМАТЬ is not None:
            m = _с_dumat(messages, model, max_tokens)
        else:
            m = _настоящий_raw(messages, model, max_tokens,
                               thinking=thinking, effort=effort)
        return m
    except Exception as ex:                                    # noqa: BLE001
        сбой = f"{type(ex).__name__}: {str(ex)[:90]}"
        raise
    finally:
        вх, вых = _токены(m)
        т = ""
        if m is not None:
            т = "".join(b.text for b in m.content
                        if getattr(b, "type", "") == "text")
        a, b = ЦЕНА_HAIKU if "haiku" in str(model) else ЦЕНА
        _в_вызовы({
            "режим": РЕЖИМ, "модель": str(model),
            "промпт_знаков": len(промпт), "вход": вх, "выход": вых,
            "знаков": len(т), "сек": round(time.time() - т0, 1),
            "стоп": getattr(m, "stop_reason", None) if m else None,
            "сбой": сбой,
            "цена_$": round(вх / 1e6 * a + вых / 1e6 * b, 5),
            "срыв": bool(вых >= ПОТОЛОК_ОТВЕТА * 0.7 and len(т) < вых)})


def _с_dumat(messages, model, max_tokens):
    """Тот же стрим, но с ЯВНЫМ полем thinking (его штатный путь не умеет).

    gen_provider._raw_stream либо кладёт thinking={'type':'adaptive'}, либо
    не кладёт поле вовсе. Явного запрета в нём нет, а проверить его надо -
    отсутствие поля и запрет это разные вещи.
    """
    e = gen_provider.env()
    url = e["PROVIDER_BASE_URL"].rstrip("/") + "/v1/messages"
    headers = dict(gen_provider._RAW_HEADERS)
    headers["x-api-key"] = e["PROVIDER_API_KEY"]
    body = {"model": gen_provider.resolve_model(model),
            "max_tokens": max_tokens, "stream": True, "messages": messages,
            "thinking": ДУМАТЬ}
    if УСИЛИЕ:
        body["output_config"] = {"effort": УСИЛИЕ}
    текст, дум, usage, стоп = [], [], {}, None
    req = urllib.request.Request(url, method="POST",
                                 data=json.dumps(body).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=400) as r:
        for сырая in r:
            s = сырая.decode("utf-8", "replace").strip()
            if not s.startswith("data:"):
                continue
            к = s[5:].strip()
            if not к or к == "[DONE]":
                continue
            try:
                d = json.loads(к)
            except Exception:                                  # noqa: BLE001
                continue
            т = d.get("type")
            if т == "content_block_delta":
                dl = d.get("delta") or {}
                if dl.get("type") == "text_delta":
                    текст.append(dl.get("text") or "")
                elif dl.get("type") == "thinking_delta":
                    дум.append(dl.get("thinking") or "")
            elif т == "message_start":
                usage.update((d.get("message") or {}).get("usage") or {})
            elif т == "message_delta":
                usage.update(d.get("usage") or {})
                стоп = (d.get("delta") or {}).get("stop_reason") or стоп
    return gen_provider._Msg("".join(текст), "".join(дум), usage, стоп)


gen_provider._raw_stream = _мой_raw

# --- резюм по ИНН (как в бою) -------------------------------------------
сделано_инн, попыток_инн = set(), Counter()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                      # noqa: BLE001
            continue
        inn = str(z.get("inn") or "")
        if not inn:
            continue
        if z.get("этап") != "итог":
            попыток_инн[inn] += 1
        if z.get("ок") or z.get("тело"):
            сделано_инн.add(inn)

группы = store.recipient_groups().get("по_id") or {}
пары, счёт, видели = [], Counter(), set()
for rid in sorted(r for r, gr in группы.items() if ГРУППА in gr):
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    if inn in видели:
        счёт["дубль строки той же фирмы"] += 1
        continue
    видели.add(inn)
    if inn in сделано_инн:
        счёт["письмо уже есть"] += 1
        continue
    if попыток_инн[inn] >= 3:
        счёт["исчерпал 3 попытки"] += 1
        continue
    if cs._guard(inn=inn, email=email):
        счёт["заслон"] += 1
        continue
    пары.append((rid, rec, inn))
пары = пары[:ПОТОЛОК]

print(f"режим рассуждения: {РЕЖИМ} (thinking={ДУМАТЬ}, effort={УСИЛИЕ})")
print(f"к генерации {len(пары)} писем, потоков {ПОТОКОВ}")
for k, n in счёт.most_common():
    print(f"  {k:<30} {n}")
if not пары:
    print("генерировать некого")
    raise SystemExit(0)

def счёт_шлюза():
    """total_usage шлюза: сторонний счёт, независимый от нашего учёта.

    Нужен потому, что свой учёт уже один раз соврал: 17.08 замер на десяти
    письмах показал цену $0.000, потому что _Msg.usage читался как словарь,
    а он объект. Числа, которые нечем перепроверить, - не числа.
    """
    try:
        rq = urllib.request.Request(
            os.environ.get("PROVIDER_BASE_URL",
                           "https://router.cheap").rstrip("/")
            + "/dashboard/billing/usage",
            headers={"Authorization": "Bearer "
                     + os.environ["PROVIDER_API_KEY"],
                     "User-Agent": "curl/8.5.0"})
        with urllib.request.urlopen(rq, timeout=40) as r:
            return float(json.loads(r.read()).get("total_usage"))
    except Exception as ex:                                    # noqa: BLE001
        print("счётчик шлюза не прочитался:", str(ex)[:120])
        return None


СЧЁТ_ДО = счёт_шлюза()
print(f"счётчик шлюза до круга: {СЧЁТ_ДО}")
СТАРТ = time.time()
день = date.today().isoformat()
итоги = []
ВСЕГО = len(пары)


def _в_журнал(запись):
    with замок:
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps(запись, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def _с_ожиданием(зовём):
    посл = None
    for поп in range(6):
        try:
            return зовём(), None
        except Exception as ex:                                # noqa: BLE001
            посл = ex
            if "locked" not in str(ex).lower() and поп >= 2:
                break
            time.sleep(2 + поп * 3)
    return None, посл


def один(g):
    try:
        _один(g)
    except Exception as ex:                                    # noqa: BLE001
        print(f"  поток упал на #{g[0]}: {str(ex)[:110]}")


def _один(g):
    rid, rec, inn = g
    req = q._request(rec)
    div = str(req.get("target_division") or "kc")
    div = div if div in КАМПАНИЯ else "kc"
    req["target_division"] = div
    req.setdefault("extra", {})["angle_shift"] = rid
    т_идей = time.time()
    try:
        q._add_ideas_generic([req])
    except Exception as ex:                                    # noqa: BLE001
        print(f"  идеи не раздались #{rid}: {str(ex)[:80]}")
    сек_идей = int(time.time() - т_идей)
    имя = str(getattr(rec, "company_name", "") or "")[:40]
    расход = {"in": 0, "out": 0}
    свой = threading.Lock()

    def caller(prompt):
        посл = None
        for i in range(4):
            try:
                m = gen_provider._raw_stream(
                    [{"role": "user", "content": prompt}], МОДЕЛЬ,
                    ПОТОЛОК_ОТВЕТА, thinking=False, effort="low")
                т = "".join(b.text for b in m.content
                            if getattr(b, "type", "") == "text")
                вх_т, вых = _токены(m)
                with свой:
                    расход["in"] += вх_т
                    расход["out"] += вых
                    расход["вызовов"] = расход.get("вызовов", 0) + 1
                    if вых >= ПОТОЛОК_ОТВЕТА * 0.7 and len(т or "") < вых:
                        расход["срывов"] = расход.get("срывов", 0) + 1
                if т and len(т) >= 20:
                    return т
                raise RuntimeError("короткий ответ")
            except Exception as ex:                            # noqa: BLE001
                посл = ex
                time.sleep(min(20, 2 ** i))
        raise RuntimeError(str(посл)[:150])

    т0 = time.time()
    try:
        res = AiLetterGen(caller, facts_by_division=_факты,
                          best_of=3).generate([req])
        L = res.ok.get(0)
        брак = [str(x)[:150] for x in (res.rejected.get(0) or [])][:3]
    except Exception as ex:                                    # noqa: BLE001
        L, брак = None, ["прогон упал: " + str(ex)[:150]]

    зап = {"recipient_id": rid, "inn": inn, "имя": имя, "направление": div,
           "модель": МОДЕЛЬ, "режим": РЕЖИМ, "сек": int(time.time() - т0),
           "сек_идей": сек_идей, "ок": bool(L), "брак": брак,
           "вызовов": расход.get("вызовов", 0),
           "срывов": расход.get("срывов", 0),
           "цена_$": round(расход["in"] / 1e6 * ЦЕНА[0]
                           + расход["out"] / 1e6 * ЦЕНА[1], 4)}
    if L:
        зап["тема"] = L.get("subject")
        зап["тело"] = L.get("body")
    зап["этап"] = "сгенерировано"
    _в_журнал(зап)

    if L:
        cid = КАМПАНИЯ[div]
        пара, сбой = _с_ожиданием(lambda: q._ensure_message(cid, rid))
        mid = почему = None
        if пара is not None:
            mid, _step, почему = пара
        if not mid:
            зап["ок"] = False
            зап["брак"] = [f"нет message_id: {почему or str(сбой)[:110]}"]
        else:
            try:
                panel = q._panel(rec, L, день, req)
            except Exception as ex:                            # noqa: BLE001
                panel = {}
                зап["панель_упала"] = str(ex)[:120]
            r, сбой = _с_ожиданием(lambda: cs.submit(
                email=str(getattr(rec, "email", "") or ""),
                subject=L["subject"], body=L["body"], inn=inn,
                campaign_id=cid, recipient_id=rid, message_id=mid,
                panel=panel))
            if r is None:
                зап["ок"] = False
                зап["брак"] = ["очередь не приняла: " + str(сбой)[:110]]
            зап["review_id"] = getattr(r, "review_id", None)
            зап["статус_очереди"] = getattr(r, "status", "")
            # СОЗДАНА ЛИ КАРТОЧКА. dedup_key под UNIQUE-индексом, и повторная
            # постановка того же письма возвращает СУЩЕСТВУЮЩИЙ review_id со
            # статусом pending. Боевой скрипт этого не различает и пишет
            # ок=true - отсюда 21 лишняя запись 17.08 и расхождение 159/138.
            зап["создана"] = bool(getattr(r, "created", False))
            if r is not None and str(getattr(r, "status", "")) != "pending":
                зап["ок"] = False
                зап["брак"] = [f"очередь: {getattr(r, 'status', '')}"]
    зап["этап"] = "итог"
    with замок:
        итоги.append(зап)
    _в_журнал(зап)
    print(f"  [{len(итоги)}/{ВСЕГО}] {'ОК  ' if зап['ок'] else 'брак'} "
          f"{div:<5} {имя[:28]:<30} {зап['сек']:>4}с ${зап['цена_$']:.3f} "
          f"выз {зап['вызовов']} срыв {зап['срывов']}"
          + (f" #{зап.get('review_id')}"
             f"{'' if зап.get('создана') else ' (ПОВТОР)'}" if зап["ок"] else ""))


def _с_часами(g):
    if time.time() - СТАРТ > ЛИМИТ_СЕК:
        return
    один(g)


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
    list(pool.map(_с_часами, пары))

# --- отчёт ---------------------------------------------------------------
С = []


def п(s=""):
    С.append(s)
    print(s)


ок = [x for x in итоги if x["ок"]]
всего_денег = sum(x["цена_$"] for x in итоги)
п(f"# Замер на {len(итоги)} письмах, режим «{РЕЖИМ}»")
п()
п(f"вышло {len(ок)} из {len(итоги)} | ${всего_денег:.2f} | "
  f"{int(time.time() - СТАРТ)} с на весь круг")
п()
п("| компания | ок | сек | идеи, с | вызовов | срывов | $ | карточка |")
п("|---|---|---|---|---|---|---|---|")
for x in итоги:
    п(f"| {str(x['имя'])[:26]} | {'да' if x['ок'] else 'нет'} | {x['сек']} | "
      f"{x.get('сек_идей', '?')} | {x['вызовов']} | {x['срывов']} | "
      f"{x['цена_$']:.3f} | "
      f"{x.get('review_id') or '—'}"
      f"{'' if x.get('создана', True) else ' повтор'} |")

if итоги:
    цены = sorted(x["цена_$"] for x in итоги)
    n = len(цены)
    п()
    п(f"цена письма: медиана ${цены[n // 2]:.3f}, мин ${цены[0]:.3f}, "
      f"макс ${цены[-1]:.3f}")
    if ок:
        цо = sorted(x["цена_$"] for x in ок)
        п(f"цена ВЫШЕДШЕГО письма: медиана ${цо[len(цо) // 2]:.3f}, "
          f"среднее ${sum(цо) / len(цо):.3f}")
    п(f"вызовов боевого caller: {sum(x['вызовов'] for x in итоги)}, "
      f"срывов {sum(x['срывов'] for x in итоги)} "
      f"({100 * sum(x['срывов'] for x in итоги) // max(1, sum(x['вызовов'] for x in итоги))}%)")

# полный лог вызовов, включая идеи-линзы мимо счёта журнала
if ЛОГ:
    п()
    п("## Все вызовы провайдера (журнал партии их не видит целиком)")
    п()
    по_модели = Counter()
    цена_модели = Counter()
    for z in ЛОГ:
        по_модели[z["модель"]] += 1
        цена_модели[z["модель"]] += z["цена_$"]
    п("| модель | вызовов | $ | срывов |")
    п("|---|---|---|---|")
    for м, k in по_модели.most_common():
        ср = sum(1 for z in ЛОГ if z["модель"] == м and z["срыв"])
        п(f"| {м} | {k} | {цена_модели[м]:.3f} | {ср} |")
    полная = sum(z["цена_$"] for z in ЛОГ)
    п()
    п(f"**ПОЛНАЯ цена всех вызовов: ${полная:.2f}** против ${всего_денег:.2f} "
      f"по счёту журнала (разница — идеи-линзы и повторы)")
    if итоги:
        п(f"на письмо: ${полная / len(итоги):.3f}")

    # СВЕРКА СО СТОРОННИМ СЧЁТОМ. Свой учёт уже врал (цена $0.000 из-за
    # чтения объекта как словаря), поэтому число без второго источника не
    # предъявляем.
    time.sleep(10)
    СЧЁТ_ПОСЛЕ = счёт_шлюза()
    п()
    if СЧЁТ_ДО is not None and СЧЁТ_ПОСЛЕ is not None:
        д = СЧЁТ_ПОСЛЕ - СЧЁТ_ДО
        п(f"счётчик шлюза: {СЧЁТ_ДО} -> {СЧЁТ_ПОСЛЕ}, прирост **{д:.4f}**")
        if полная > 0:
            п(f"единиц счётчика на наш доллар: {д / полная:.1f} "
              f"(если чужие прогоны молчали — это курс единицы)")
        п("Абсолютную цену по этому счётчику брать нельзя, пока курс не "
          "откалиброван на контрольной паре; но ОТНОШЕНИЕ старого и нового "
          "режима по нему честное.")
    else:
        п("сторонний счёт недоступен — цифра цены держится только на нашем "
          "учёте, перепроверить нечем")
    срывы = [z for z in ЛОГ if z["срыв"]]
    if срывы:
        п(f"срывов {len(срывы)} из {len(ЛОГ)} вызовов, "
          f"на них ${sum(z['цена_$'] for z in срывы):.2f} "
          f"({100 * sum(z['цена_$'] for z in срывы) / max(1e-9, полная):.0f}% "
          f"всех денег)")
        вых = sorted(z["выход"] for z in срывы)
        п(f"выход на срыве: медиана {вых[len(вых) // 2]}, макс {вых[-1]}")

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/ZAMER-10-PISEM.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: ZAMER-10-PISEM.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:160])
