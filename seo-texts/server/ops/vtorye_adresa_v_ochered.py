# -*- coding: utf-8 -*-
"""Копия письма на ВТОРОЙ адрес того же домена — тем компаниям, кому писали
раньше 3 дней назад и кто не ответил. По одному адресу на компанию.

Владелец 27.08: «давай по 1 письму кому писали больше 3 дней назад
(следующую почту на домене компании)».

Тело берём из карточки подтверждения, а НЕ из отправленного письма: там
лежит шаблон с меткой ИМЯ_ОТПРАВИТЕЛЯ и без подписи — имя менеджера и род
движок подставит сам при отправке, по тому ящику, который реально отправит.
Переписываем только приветствие: имя старого адресата убираем, новое ставим,
если в обогащении есть распознаваемое отчество.

Без --katit ничего не пишет: считает и показывает примеры.
Durability: каждая поставленная карточка — строкой в _ops\\vtorye-adresa.jsonl
с fsync, повторный запуск их пропускает.
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

КАТИТЬ = "--katit" in sys.argv
ПОТОЛОК = int(next((a.split("=")[1] for a in sys.argv if a.startswith("potolok=")), "0"))
СЛЕД = r"C:\sender\_ops\vtorye-adresa.jsonl"

exec(open(r"C:\sender\server\ops\zapas_kopiy_3dnya.py", encoding="utf-8")
     .read().split("print(\"\")\nprint(\"=== отсев адресов ===\")")[0])
выбор = {инн: sorted(v)[0] for инн, v in годные.items()}
print("")
print("отобрано компаний: %d   режим: %s"
      % (len(выбор), "БОЕВОЙ" if КАТИТЬ else "вхолостую"))

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.dtos import RecipientIn                               # noqa: E402
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.wiring import build_deps                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
q = build_ai_quota(store, cfg)
print("сборка как у панели: проба %s, гейт направлений %s"
      % ("есть" if getattr(cs, "_probe", None) else "НЕТ",
         "есть" if getattr(cs, "_cards", None) else "НЕТ"))

сделано = set()
if os.path.exists(СЛЕД):
    for с in io.open(СЛЕД, encoding="utf-8", errors="replace"):
        try:
            сделано.add(json.loads(с)["email"])
        except Exception:                                          # noqa: BLE001
            pass
print("уже поставлено ранее: %d" % len(сделано))

# Служебные ящики: туда пишем не «коллеге по закупкам», а в никуда. Сверка
# ТОЧНАЯ по локальной части без хвостовых цифр, а не по подстроке: подстрочный
# поиск ловил «smirnova» на «smi» и «fedorko» на «edo».
СЛУЖЕБНЫЕ = {
    "gosuslugi", "buh", "buhgalter", "buhgalteria", "buhgalteriya", "buhg",
    "kadry", "kadri", "kadr", "ok", "hr", "vacancy", "vacancies", "vakansii",
    "rabota", "job", "jobs", "career", "press", "pressa", "smi", "pr",
    "edo", "diadoc", "sbis", "kontur", "nalog", "fss", "pfr", "otchet",
    "noreply", "no-reply", "postmaster", "webmaster", "abuse", "spam",
    "podpiska", "rassylka", "news", "newsletter", "unsubscribe",
}
_ХВОСТ_ЦИФР = re.compile(r"\d+$")


def sluzhebnyy(адрес):
    л = str(адрес or "").split("@", 1)[0].lower()
    return _ХВОСТ_ЦИФР.sub("", л) in СЛУЖЕБНЫЕ or л in СЛУЖЕБНЫЕ


_ОТЧ = re.compile(r"(?i)(вич|вна|ична|инична)$")
_ГРИТ = re.compile(r"(?i)^\s*(добрый день|здравствуйте|доброе утро|добрый вечер)")


def имя_otchestvo(фио):
    ток = [т for т in re.split(r"\s+", str(фио or "").strip()) if т]
    for i, т in enumerate(ток):
        if i >= 1 and _ОТЧ.search(т) and len(ток[i - 1]) > 2 and ток[i - 1].isalpha():
            return "%s %s" % (ток[i - 1].capitalize(), т.capitalize())
    return ""


def переписать_privet(тело, фио):
    """Первую строку-приветствие меняем под нового адресата. Нет приветствия —
    тело не трогаем вовсе."""
    строки = str(тело or "").split("\n")
    if not строки or not _ГРИТ.match(строки[0]):
        return тело, "приветствия нет"
    ио = имя_otchestvo(фио)
    было = строки[0].strip()
    строки[0] = ("Добрый день, %s!" % ио) if ио else "Добрый день!"
    if строки[0].strip() == было:
        return "\n".join(строки), "приветствие не менялось"
    return "\n".join(строки), ("по имени" if ио else "обезличено")


c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
итог = Counter()
примеры = []
поток = io.open(СЛЕД, "a", encoding="utf-8") if КАТИТЬ else None

for н, (инн, v) in enumerate(sorted(выбор.items())):
    if ПОТОЛОК and итог["поставлено"] >= ПОТОЛОК:
        break
    адрес, роль, фио = v[3], v[4], v[5]
    if адрес in сделано:
        итог["уже стояло"] += 1
        continue
    if sluzhebnyy(адрес):
        итог["служебный ящик - пропуск"] += 1
        continue
    # КАРТОЧКУ БЕРЁМ ТУ, ЧТО РЕАЛЬНО УШЛА, а не последнюю по ИНН. Без связи
    # через messages вхолостую вылезла тема «Что уже можно доверить ИИ в
    # контроле качества» — рассылочная карточка того же ИНН, а не холодное
    # письмо, которое компания получила и на которое молчит.
    # Берём ПЕРВОЕ отправленное (sent_at ASC), а не последнее: новый адресат
    # у нас ничего не читал, ему нужно первое знакомство, а не рассылка,
    # которая пришла его коллеге третьей по счёту.
    # Рассылочные карточки (вебинар) исключены: у 19 компаний холодного
    # письма нет вовсе, ушёл только анонс — копировать анонс на второй
    # адрес это уже не «то же письмо коллеге», а новая рассылка.
    исход = c.execute(
        "SELECT cr.subject, cr.body, cr.panel_json, cr.campaign_id, "
        "       cr.recipient_id, m.sent_at "
        "  FROM confirm_reviews cr JOIN messages m ON m.id = cr.message_id "
        " WHERE cr.inn=? AND m.status='sent' AND COALESCE(cr.body,'')<>'' "
        "   AND LOWER(COALESCE(cr.dedup_key,'')) NOT LIKE '%vebinar%' "
        " ORDER BY m.sent_at ASC LIMIT 1", (инн,)).fetchone()
    if исход is None:
        итог["нет исходной карточки"] += 1
        continue
    тело, как = переписать_privet(исход["body"], фио)
    итог["приветствие: " + как] += 1
    стар = store.get_recipient(int(исход["recipient_id"])) if исход["recipient_id"] else None
    if стар is None:
        итог["нет исходного получателя"] += 1
        continue
    if len(примеры) < 8:
        примеры.append((инн, адрес, роль, фио, исход["subject"],
                        тело.split("\n", 1)[0]))
    if not КАТИТЬ:
        итог["прошло бы"] += 1
        continue
    try:
        rid = store.upsert_recipient(RecipientIn(
            email=адрес, domain=адрес.split("@", 1)[1], inn=инн,
            company_name=getattr(стар, "company_name", None),
            okved=getattr(стар, "okved", None),
            segment=getattr(стар, "segment", None),
            contact_name=(фио or None), source="vtoroy_adres",
            priority_max=getattr(стар, "priority_max", None),
            priority_total=getattr(стар, "priority_total", None),
            pxr=getattr(стар, "pxr", None),
            region=getattr(стар, "region", None), tz=getattr(стар, "tz", None),
            extra={"vtoroy_adres": True, "iz_recipient": int(исход["recipient_id"]),
                   "rol_adresa": роль}))
        mid, _sid, почему = q._ensure_message(int(исход["campaign_id"]), rid)
        if mid is None:
            итог["нет message_id: " + str(почему)[:40]] += 1
            continue
        панель = {}
        try:
            панель = json.loads(исход["panel_json"] or "{}") or {}
        except Exception:                                          # noqa: BLE001
            панель = {}
        панель["email"] = адрес
        панель["recipient_id"] = rid
        панель["vtoroy_adres"] = {
            "rol": роль, "fio": фио or "",
            "pervyy_adres": sorted(молч.get(инн, {"?"}))[0],
            "zametka": "второй адрес того же домена, первое письмо без ответа"}
        рез = cs.submit(email=адрес, subject=исход["subject"], body=тело,
                        inn=инн, campaign_id=int(исход["campaign_id"]),
                        recipient_id=rid, message_id=mid, panel=панель)
        итог["статус: " + str(рез.status)] += 1
        if рез.status == "pending":
            итог["поставлено"] += 1
            поток.write(json.dumps({"email": адрес, "inn": инн, "review": рез.review_id,
                                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                   ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
        else:
            итог["причина: " + str(рез.reason)[:44]] += 1
    except Exception as e:                                         # noqa: BLE001
        итог["ошибка: " + str(e)[:50]] += 1
    if КАТИТЬ and итог["поставлено"] and итог["поставлено"] % 100 == 0:
        print("   ... поставлено %d" % итог["поставлено"], flush=True)

if поток:
    поток.close()
c.close()
print("")
print("=== примеры ===")
for инн, а, р, ф, т, п in примеры:
    print("   %-13s %-28s %-17s %s" % (инн, а[:28], р[:17], ф[:22]))
    print("      тема: %s | привет: %s" % (str(т)[:56], п[:34]))
print("")
print("=== итог ===")
for к, n in итог.most_common():
    print("   %-46s %5d" % (к, n))
