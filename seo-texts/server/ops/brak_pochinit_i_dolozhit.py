# -*- coding: utf-8 -*-
"""Забракованные письма: починить механику и доложить в очередь.

Владелец: «те которые бракованные, ты можешь вручную пофиксить и положить?».
Может: текст письма лежит в журнале целиком (поле «тело» пишется ДО первого
обращения к базе), то есть письмо оплачено и не потеряно - его завернул
гейт. На 17.08 таких $15.85.

ЧТО ЧИНИМ, А ЧТО НЕТ. Механический дефект - это форма: не назвали
предприятие, лишние слова, цифра в теме, заход, который велено было сменить.
Такое правится точечно и проверяется тем же гейтом. Содержательный дефект -
это когда письмо написано НЕ ТОМУ (инженерная линза: «получатель -
профсоюзная организация», «композит режут не плазмой») или в нём выдуман
факт. Это правкой строки не лечится, и такие письма мы не трогаем: пусть
уходят на перегенерацию.

Каждая починка проверяется gate() ЗАНОВО. Не прошло - не кладём.

Без аргумента - сухой прогон. Кладёт при `--класть`.

    python zapusk_svoego_skripta.py ops/brak_pochinit_i_dolozhit.py
    python zapusk_svoego_skripta.py ops/brak_pochinit_i_dolozhit.py --класть
"""
import io
import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import (gate, load_facts, короткое_имя,   # noqa: E402
                              форма_захода, zashit_kontsovku)
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
КАМПАНИЯ = {"kc": 10, "meyer": 11}
КЛАСТЬ = "--класть" in sys.argv
ПОТОЛОК = 400

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))
ФАКТЫ = {"kc": load_facts(division="kc"), "meyer": load_facts(division="meyer")}

# --- собрать брак с текстом ------------------------------------------------ #
# Берём ПОСЛЕДНЮЮ запись по ИНН: письмо могли переписать удачно позже.
последний = {}
если_ок = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                       # noqa: BLE001
            continue
        inn = str(z.get("inn") or "")
        if not inn:
            continue
        if z.get("ок") and z.get("review_id"):
            если_ок.add(inn)
        if z.get("этап") == "сгенерировано" and z.get("тело"):
            последний[inn] = z

брак = [z for inn, z in последний.items()
        if inn not in если_ок and not z.get("ок")]
print(f"в журнале компаний с текстом: {len(последний)}; "
      f"из них брак без удачного письма: {len(брак)}")


def _причина(z):
    return str((z.get("брак") or [""])[0])


СОДЕРЖАТЕЛЬНЫЕ = ("инженерная линза", "модель отказалась", "получатель",
                  "прогон упал", "нет message_id", "очередь")


def чинимо(причина: str) -> str:
    """Какой ремонт применим. '' - не наш случай."""
    п = причина.lower()
    if any(с in п for с in СОДЕРЖАТЕЛЬНЫЕ):
        return ""
    if "предприятие не названо" in п:
        return "назвать предприятие"
    if "израсходован на партии" in п:
        return "сменить первую фразу"
    if re.search(r"объём \d+ слов", п):
        return "укоротить"
    if "цифра в теме" in п:
        return "убрать цифру из темы"
    if "канцелярит" in п or "оборот «" in п:
        return "убрать оборот"
    return ""


# --- сами починки ---------------------------------------------------------- #
def назвать_предприятие(тема, тело, имя):
    """Гейт требует имя компании в теме или теле. Дописываем в ТЕМУ: тело
    трогать опаснее, там выстроен смысл."""
    кратко = короткое_имя(имя) or ""
    if not кратко or кратко.lower() in f"{тема}\n{тело}".lower():
        return тема, тело
    return f"{тема.rstrip('.').rstrip()} в «{кратко}»", тело


_ЗАЧИН = re.compile(
    r'^\s*((?:по)?смотрел\w*|изучил\w*|глянул\w*|видел\w*|ознакомил\w*)'
    r'[\s,]+[^.\n]*?[-–—:]\s*', re.I)


def сменить_первую_фразу(тема, тело, _имя):
    """«Смотрел профиль «Х» - вы режете металл» -> «Вы режете металл».

    Режем ровно зачин до тире: остаток - готовое предложение о самом
    производстве, то есть та самая замена, которую промпт и просит.
    """
    строки = тело.split("\n")
    for i, с in enumerate(строки):
        if not с.strip() or re.match(r'(?i)^(добрый день|здравствуйте)', с):
            continue
        новая = _ЗАЧИН.sub("", с)
        if новая != с and новая.strip():
            новая = новая.strip()
            строки[i] = новая[0].upper() + новая[1:]
            return тема, "\n".join(строки)
        break
    return тема, тело


def укоротить(тема, тело, _имя):
    """Сносим последнее предложение абзаца-середины, пока не влезем в норму."""
    for _ in range(6):
        слов = len([w for w in re.split(r"\s+", тело) if w.strip()])
        if слов <= 140:
            break
        абзацы = [а for а in тело.split("\n\n")]
        # самый длинный абзац, кроме первого и последних двух
        серёдка = абзацы[1:-2] or абзацы[1:-1]
        if not серёдка:
            break
        самый = max(серёдка, key=lambda а: len(а))
        предложения = re.split(r'(?<=[.!?])\s+', самый.strip())
        if len(предложения) < 2:
            break
        абзацы[абзацы.index(самый)] = " ".join(предложения[:-1])
        тело = "\n\n".join(абзацы)
    return тема, тело


def убрать_цифру_из_темы(тема, тело, имя):
    """Цифра в теме запрещена, но в названии фирмы она законна («СУ-567»).
    Если цифра только внутри названия - тему не трогаем, чинить нечего."""
    кратко = короткое_имя(имя) or ""
    без_имени = тема.replace(кратко, " ") if кратко else тема
    if not re.search(r"\d", без_имени):
        return тема, тело           # цифра только в названии - не наш случай
    return re.sub(r"\s*\d[\d\s.,%]*", " ", тема).strip(), тело


ПОЧИНКИ = {"назвать предприятие": назвать_предприятие,
           "сменить первую фразу": сменить_первую_фразу,
           "укоротить": укоротить,
           "убрать цифру из темы": убрать_цифру_из_темы}

# --- прогон ---------------------------------------------------------------- #
счёт = Counter()
готовые = []
for z in брак[:ПОТОЛОК]:
    причина = _причина(z)
    вид = чинимо(причина)
    if not вид:
        счёт["содержательный брак - не чиним"] += 1
        continue
    if вид not in ПОЧИНКИ:
        счёт[f"нет починки под «{вид}»"] += 1
        continue
    rid = z.get("recipient_id")
    rec = store.get_recipient(int(rid)) if rid else None
    if not rec:
        счёт["получатель пропал"] += 1
        continue
    div = str(z.get("направление") or "kc")
    div = div if div in КАМПАНИЯ else "kc"
    тема, тело = str(z.get("тема") or ""), str(z.get("тело") or "")
    тема2, тело2 = ПОЧИНКИ[вид](тема, тело, getattr(rec, "company_name", ""))
    if (тема2, тело2) == (тема, тело):
        счёт[f"починка «{вид}» ничего не изменила"] += 1
        continue
    тело2 = zashit_kontsovku(тело2, div)
    беды = gate(тема2, тело2, mode="GENERIC", division=div,
                facts=ФАКТЫ[div],
                extra={"company_name": getattr(rec, "company_name", "")})
    if беды:
        счёт[f"после починки «{вид}» гейт всё равно против"] += 1
        continue
    счёт[f"ПОЧИНЕНО: {вид}"] += 1
    готовые.append((z, rec, div, тема2, тело2))

print()
for k, n in счёт.most_common():
    print(f"  {k:<46} {n}")
print(f"\nготовы к докладке: {len(готовые)}")
for z, rec, div, тема2, _т in готовые[:8]:
    print(f"  {str(getattr(rec, 'company_name', ''))[:34]:<36} {div:<5} "
          f"{тема2[:52]}")

if not КЛАСТЬ:
    print("\nсухой прогон: в очередь ничего не положено. Класть - --класть")
    raise SystemExit(0)

положено = сбоев = 0
день = time.strftime("%Y-%m-%d")
for z, rec, div, тема2, тело2 in готовые:
    inn = str(z.get("inn") or "")
    cid = КАМПАНИЯ[div]
    try:
        пара = q._ensure_message(cid, int(z.get("recipient_id")))
        mid = пара[0] if пара else None
        if not mid:
            сбоев += 1
            continue
        req = q._request(rec)
        panel = q._panel(rec, {"subject": тема2, "body": тело2,
                               "division": div}, день, req)
        r = cs.submit(email=str(getattr(rec, "email", "") or ""),
                      subject=тема2, body=тело2, inn=inn, campaign_id=cid,
                      recipient_id=int(z.get("recipient_id")),
                      message_id=mid, panel=panel)
        if r is None or str(getattr(r, "status", "")) != "pending":
            сбоев += 1
            continue
        положено += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "inn": inn, "recipient_id": z.get("recipient_id"),
                "имя": z.get("имя"), "направление": div, "этап": "итог",
                "ок": True, "починено": True, "тема": тема2, "тело": тело2,
                "review_id": getattr(r, "review_id", None),
                "цена_$": 0.0}, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex:                                     # noqa: BLE001
        сбоев += 1
        if сбоев <= 5:
            print(f"  {inn}: {type(ex).__name__} {str(ex)[:110]}")

print(f"\nположено в очередь: {положено} | сбоев: {сбоев}")
