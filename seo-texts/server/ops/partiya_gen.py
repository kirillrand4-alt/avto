# -*- coding: utf-8 -*-
"""Генерация партии 935 на opus-4.8, с раскладкой по направлениям.

Отличия от прогона «Богатых карточек», и каждое - следствие своей ошибки:

  * постановка в очередь идёт через ConfirmSend.submit, а НЕ через
    store.confirm_submit. Штатный путь проверяет три вещи разом - стоп-лист,
    заведомо мёртвый адрес и контакт моложе 90 дней; прямой вызов обходил
    все три, и владелец увидел это в очереди дважды за сутки;
  * заслон спрашиваем ДО генерации, а не после: 11 снятых писем - это
    оплаченные впустую круги модели;
  * резюм по ИНН, а не по recipient_id: у 233 компаний партии в панели по
    несколько строк, и по id одна фирма получила бы два письма;
  * направление решает штатный target_division, кампания выбирается по
    нему (КЦ -> 10, Meyer -> 11). На автоотправку поедет только КЦ -
    решение владельца, поэтому кампании разные.

Резюмируемо: журнал durable с fsync, повторный запуск добивает остаток.
"""
import io
import json
import os
import sys
import threading
import time
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
ГРУППА = "Партия 935"
КАМПАНИЯ = {"kc": 10, "meyer": 11}
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ПОТОКОВ = 25
# ПОТОЛОК ОТВЕТА. Письмо - около 500 токенов, тройка вариантов - до двух
# тысяч. Шестнадцать тысяч не нужны никому, кроме срыва: он выжигает весь
# потолок и стоит 28-58 центов. На четырёх тысячах урон со срыва падает
# вчетверо, а нормальному ответу места хватает с запасом.
ПОТОЛОК_ОТВЕТА = 4000
ПОТОЛОК = int(sys.argv[1]) if len(sys.argv) > 1 else None

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
_факты = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}

# --- резюм по ИНН --------------------------------------------------------
сделано_инн, попыток_инн = set(), Counter()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:
            continue
        inn = str(z.get("inn") or "")
        if not inn:
            continue
        попыток_инн[inn] += 1
        if z.get("ок"):
            сделано_инн.add(inn)

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)

пары, счёт = [], Counter()
видели_инн = set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    if inn in видели_инн:
        счёт["дубль строки той же фирмы"] += 1
        continue
    видели_инн.add(inn)
    if inn in сделано_инн:
        счёт["письмо уже есть"] += 1
        continue
    if попыток_инн[inn] >= 3:
        счёт["исчерпал 3 попытки"] += 1
        continue
    причина = cs._guard(inn=inn, email=email)
    if причина:
        счёт[f"заслон: {причина.split(':')[0]}"] += 1
        continue
    пары.append((rid, rec, inn))

if ПОТОЛОК:
    пары = пары[:ПОТОЛОК]
print(f"режим очереди confirm.mode = {cs.mode()!r}")
print(f"в группе {len(в_группе)} строк | к генерации {len(пары)}")
for k, n in счёт.most_common():
    print(f"  {k:<30} {n}")
if not пары:
    print("генерировать некого")
    raise SystemExit(0)

# БЕЗ ПАЧЕК. Пул держит в работе ПОТОКОВ писем одновременно и берёт
# следующее, как только освободился поток. Пачек нет вовсе: раньше идеи
# раздавались на всю пачку до первой генерации, и на пачке в 50 это съедало
# весь круг - оп умирал по таймауту, не записав ни строки. Теперь идеи
# раздаёт сам поток, для своего письма.
СТАРТ = time.time()
ЛИМИТ_СЕК = (int(sys.argv[2]) if len(sys.argv) > 2 else 3300) - 150

замок = threading.Lock()
день = date.today().isoformat()
итоги = []


ВСЕГО = len(пары)


def _записать(зап, итог=False):
    """Строка в durable-журнал. Пишем и промежуточную, и итоговую: письмо на
    диске важнее аккуратности журнала."""
    зап = dict(зап)
    зап["этап"] = "итог" if итог else "сгенерировано"
    with замок:
        if итог:
            итоги.append(зап)
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps(зап, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def один(g):
    # НИ ОДНО падение не смеет убить круг. pool.map перевыбрасывает первое
    # же исключение из потока, и вместе с ним пропадают ВСЕ письма круга -
    # включая уже написанные и оплаченные. 17.08 так умирали целые круги на
    # «database is locked».
    try:
        _один(g)
    except Exception as ex:                                   # noqa: BLE001
        print(f"  поток упал на #{g[0]}: {str(ex)[:110]}")


def _один(g):
    rid, rec, inn = g
    # ИДЕИ РАЗДАЁТ САМ ПОТОК, для СВОЕГО письма. Раньше идеи раздавались на
    # всю пачку до первой генерации - это барьер: при пачке в 50 он съедал
    # весь круг, и оп умирал по таймауту, не записав ни строки. Теперь
    # барьера нет вовсе, и число потоков больше ничем не ограничено.
    req = q._request(rec)
    div = str(req.get("target_division") or "kc")
    div = div if div in КАМПАНИЯ else "kc"
    req["target_division"] = div
    req.setdefault("extra", {})["angle_shift"] = rid
    try:
        q._add_ideas_generic([req])
    except Exception as ex:                                   # noqa: BLE001
        print(f"  идеи не раздались #{rid}: {str(ex)[:90]}")
    имя = str(getattr(rec, "company_name", "") or "")[:40]
    расход = {"in": 0, "out": 0}
    свой = threading.Lock()

    def caller(prompt):
        посл = None
        # ПЕРВЫЙ ЗАХОД СРАЗУ НА low (владелец 17.08, по журналу роутера).
        # На medium шесть вызовов из восьми уходили в срыв: 18-19 тысяч
        # токенов выхода, 55 центов и НИ ОДНОГО знака текста. Текст всё
        # равно приходил с повторного вызова, а повторный шёл на low - то
        # есть письма и так писались без рассуждения, а medium оплачивался
        # впустую. Оставляем medium запасным на случай, если low не осилит.
        усилие = "low"
        for i in range(4):
            try:
                m = gen_provider._raw_stream(
                    [{"role": "user", "content": prompt}], МОДЕЛЬ, ПОТОЛОК_ОТВЕТА,
                    thinking=False, effort=усилие)
                т = "".join(b.text for b in m.content
                            if getattr(b, "type", "") == "text")
                u = getattr(m, "usage", None)
                вых = int(getattr(u, "output_tokens", 0) or 0)
                with свой:
                    расход["in"] += int(getattr(u, "input_tokens", 0) or 0)
                    расход["out"] += вых
                    расход["вызовов"] = расход.get("вызовов", 0) + 1
                # СРЫВ В РАССУЖДЕНИЕ. Владелец 17.08: такие вызовы частые.
                # Признак - гора токенов выхода при почти пустом тексте:
                # 18 414 токенов и полторы тысячи знаков, $0.55 за штуку.
                # Потолок здесь НЕ помогает: 18 414 больше заданных 16 000,
                # то есть рассуждение под max_tokens не подпадает. Ловим по
                # факту и переспрашиваем на пониженном усилии.
                if вых >= ПОТОЛОК_ОТВЕТА * 0.7 and len(т or "") < вых:
                    with свой:
                        расход["срывов"] = расход.get("срывов", 0) + 1
                    print(f"    срыв: выход {вых} токенов, текста "
                          f"{len(т or '')} знаков -> повтор на low")
                    if усилие != "low":
                        усилие = "low"
                        continue
                if т and len(т) >= 20:
                    return т
                raise RuntimeError("короткий ответ")
            except Exception as ex:                           # noqa: BLE001
                посл = ex
                time.sleep(min(20, 2 ** i))
        raise RuntimeError(str(посл)[:150])

    т0 = time.time()
    try:
        res = AiLetterGen(caller, facts_by_division=_факты,
                          best_of=3).generate([req])
        L = res.ok.get(0)
        брак = [str(x)[:150] for x in (res.rejected.get(0) or [])][:3]
    except Exception as ex:                                   # noqa: BLE001
        L, брак = None, ["прогон упал: " + str(ex)[:150]]

    зап = {"recipient_id": rid, "inn": inn, "имя": имя, "направление": div,
           "модель": МОДЕЛЬ, "сек": int(time.time() - т0), "ок": bool(L),
           "брак": брак,
           "вызовов": расход.get("вызовов", 0),
           "срывов": расход.get("срывов", 0),
           "цена_$": round(расход["in"] / 1e6 * ЦЕНА[0]
                           + расход["out"] / 1e6 * ЦЕНА[1], 4)}
    # ЖУРНАЛ ПЕРВЫМ ШАГОМ, ОЧЕРЕДЬ ВТОРЫМ. Находка соседней сессии 17.08:
    # строка журнала писалась в КОНЦЕ функции, после блока постановки в
    # очередь. А в этом блоке q._ensure_message пишет в ту же занятую sqlite
    # и НИЧЕМ не обёрнут - блокировка выбрасывала исключение мимо шести
    # попыток cs.submit, строки в журнале не появлялось, и оплаченное письмо
    # пропадало. Теперь текст ложится на диск сразу после генерации, до
    # первого обращения к базе.
    if L:
        зап["тема"] = L.get("subject")
        зап["тело"] = L.get("body")
    _записать(зап)

    if L:
        cid = КАМПАНИЯ[div]
        mid = _step = None
        почему = ""
        # _ensure_message тоже пишет в базу и тоже ловит блокировку.
        for _поп in range(6):
            try:
                mid, _step, почему = q._ensure_message(cid, rid)
                break
            except Exception as ex:                           # noqa: BLE001
                почему = str(ex)[:110]
                if "locked" not in почему.lower() and _поп >= 2:
                    break
                time.sleep(2 + _поп * 3)
        if not mid:
            зап["ок"] = False
            зап["брак"] = [f"нет message_id: {почему}"]
        else:
            try:
                panel = q._panel(rec, L, день, req)
            except Exception as ex:                           # noqa: BLE001
                panel = {}
                зап["панель_упала"] = str(ex)[:120]
            # БАЗА БЫВАЕТ ЗАБЛОКИРОВАНА. Работник пишет вердикты проб
            # пачками в ту же sqlite, куда кладут письма 25 потоков, и
            # «database is locked» прилетает регулярно. Без обёртки первая
            # же блокировка выбрасывала исключение из потока, pool.map его
            # перевыбрасывал - и ВЕСЬ круг умирал, потеряв все готовые
            # письма. Ждём и пробуем снова: письмо уже оплачено, терять его
            # из-за занятой базы нельзя.
            r = None
            for _поп in range(6):
                try:
                    r = cs.submit(
                        email=str(getattr(rec, "email", "") or ""),
                        subject=L["subject"], body=L["body"], inn=inn,
                        campaign_id=cid, recipient_id=rid,
                        message_id=mid, panel=panel)
                    break
                except Exception as ex:                       # noqa: BLE001
                    if "locked" not in str(ex).lower() and _поп >= 2:
                        зап["ок"] = False
                        зап["брак"] = ["очередь упала: " + str(ex)[:110]]
                        break
                    time.sleep(2 + _поп * 3)
            if r is None and зап.get("ок"):
                зап["ок"] = False
                зап["брак"] = ["очередь занята: не записалось за 6 попыток"]
            зап["review_id"] = getattr(r, "review_id", None)
            зап["статус_очереди"] = getattr(r, "status", "")
            if r is not None and str(getattr(r, "status", "")) != "pending":
                зап["ок"] = False
                зап["брак"] = [f"очередь: {getattr(r, 'status', '')}"]
    # Итоговая строка (уже с review_id и статусом очереди). Первая строка
    # с текстом письма записана выше и остаётся: пусть в журнале будет две
    # записи, чем ни одной.
    _записать(зап, итог=True)
    n = len(итоги)
    print(f"  [{n}/{ВСЕГО}] {'ОК  ' if зап['ок'] else 'брак'} "
          f"{div:<5} {имя[:30]:<32} {зап['сек']:>3}с ${зап['цена_$']:.3f}"
          + (f" срывов {зап['срывов']}" if зап.get("срывов") else "")
          + (f" #{зап.get('review_id')}" if зап["ок"]
             else f" | {(зап['брак'] or [''])[0][:80]}"))


оборвано = False


def _с_часами(g):
    if time.time() - СТАРТ > ЛИМИТ_СЕК:
        return
    один(g)


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
    list(pool.map(_с_часами, пары))
if time.time() - СТАРТ > ЛИМИТ_СЕК:
    оборвано = True
    print("время вышло - остаток добьёт следующий круг (резюм по журналу)")

ок = [x for x in итоги if x["ок"]]
print(f"\nсрывов в рассуждение: {sum(x.get('срывов', 0) for x in итоги)} "
      f"на {sum(x.get('вызовов', 0) for x in итоги)} вызовов")
print(f"\nитог: вышло {len(ок)} из {len(итоги)} | "
      f"${sum(x['цена_$'] for x in итоги):.2f} | "
      f"по направлениям {dict(Counter(x['направление'] for x in ок))}"
      + (" | ОБОРВАНО ПО ВРЕМЕНИ" if оборвано else ""))
