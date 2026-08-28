# -*- coding: utf-8 -*-
"""Вторая партия копий на второй адрес: только те, кто прошёл паспорт и
выручку от 30 млн.

Владелец 28.08: «из них 873 с выручкой от 30 млн = давай их достанем и
также просудим посмотрим».

Отбор берём из skolko_eshchyo_dostanem.py (паспорт сайта, выручка, вердикт
гейта — всё на входе, а не после постановки). Тело письма и переписывание
приветствия — как в первой партии.

Без --katit ничего не пишет. След: _ops\\vtorye-adresa-2.jsonl (fsync).
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

КАТИТЬ = "--katit" in sys.argv
ПОТОЛОК = int(next((a.split("=")[1] for a in sys.argv if a.startswith("potolok=")), "0"))
ПОРОГ_ВЫР = float(next((a.split("=")[1] for a in sys.argv
                        if a.startswith("vyruchka=")), "30")) * 1e6
СЛЕД = r"C:\sender\_ops\vtorye-adresa-2.jsonl"

# отбор — тот же код, что считал 989/873
_отбор = open(r"C:\sender\server\ops\skolko_eshchyo_dostanem.py",
              encoding="utf-8").read().split('print("")\nprint("=== отсев ===")')[0]
exec(_отбор)
# Отбор кладёт C:\sender\sender в начало sys.path, и тогда «sender» — это
# модуль sender.py, а не пакет: from sender.config падает «not a package».
# Возвращаем корень вперёд.
while r"C:\sender" in sys.path:
    sys.path.remove(r"C:\sender")
sys.path.insert(0, r"C:\sender")
выбор = {и: sorted(v)[0] for и, v in годные.items()}
выбор = {и: v for и, v in выбор.items() if выр.get(и, 0) >= ПОРОГ_ВЫР}
print("")
print("под правило (паспорт + выручка от %.0f млн): %d компаний  режим: %s"
      % (ПОРОГ_ВЫР / 1e6, len(выбор), "БОЕВОЙ" if КАТИТЬ else "вхолостую"))

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.dtos import RecipientIn                               # noqa: E402
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.wiring import build_deps                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
q = build_ai_quota(store, cfg)

сделано = set()
if os.path.exists(СЛЕД):
    for с in io.open(СЛЕД, encoding="utf-8", errors="replace"):
        try:
            сделано.add(json.loads(с)["email"])
        except Exception:                                          # noqa: BLE001
            pass
print("уже поставлено ранее: %d" % len(сделано))

_ОТЧ = __import__("re").compile(r"(?i)(вич|вна|ична|инична)$")
_ГРИТ = __import__("re").compile(
    r"(?i)^\s*(добрый день|здравствуйте|доброе утро|добрый вечер)")


# ИМЯ СВЕРЯЕМ СО СПИСКОМ. В обогащении встречаются опечатки исходника
# («Стукаленко Адрей Александрович»), и обращение «Добрый день, Адрей
# Александрович!» хуже, чем обезличенное: отчество по шаблону распознаётся
# надёжно, а имя приходит как есть. Не узнали имя — здороваемся без имени.
ИМЕНА = set("""
александр алексей анатолий андрей антон аркадий арсений артем артём артур
богдан борис вадим валентин валерий василий виктор виталий владимир владислав
вячеслав геннадий георгий герман григорий давид даниил денис дмитрий евгений
егор иван игорь илья кирилл константин лев леонид максим марат михаил никита
николай олег павел петр пётр роман руслан рустам сергей станислав степан тимофей
тимур федор фёдор филипп эдуард эльдар юрий ярослав альберт азат ильдар ильнур
ринат равиль рафаэль дамир камиль наиль ренат тагир фарид шамиль ахмед магомед
альбина алена алёна алина алла анастасия ангелина анна антонина валентина
валерия вера вероника виктория галина дарья диана дина евгения екатерина елена
елизавета жанна зинаида зоя инна ирина карина кристина ксения лариса лидия
любовь людмила маргарита марина мария надежда наталия наталья нина оксана олеся
ольга полина раиса регина римма светлана снежана софия софья тамара татьяна
ульяна юлия яна алсу гульнара гузель лилия резеда фарида эльвира эльмира
""".split())


def имя_otchestvo(фио):
    ток = [т for т in __import__("re").split(r"\s+", str(фио or "").strip()) if т]
    for i, т in enumerate(ток):
        if i >= 1 and _ОТЧ.search(т) and len(ток[i - 1]) > 2 and ток[i - 1].isalpha():
            имя = ток[i - 1].lower().replace("ё", "е")
            if имя not in ИМЕНА and ток[i - 1].lower() not in ИМЕНА:
                return ""
            return "%s %s" % (ток[i - 1].capitalize(), т.capitalize())
    return ""


def переписать_privet(тело, фио):
    строки = str(тело or "").split("\n")
    if not строки or not _ГРИТ.match(строки[0]):
        return тело, "приветствия нет"
    ио = имя_otchestvo(фио)
    было = строки[0].strip()
    строки[0] = ("Добрый день, %s!" % ио) if ио else "Добрый день!"
    if строки[0].strip() == было:
        return "\n".join(строки), "не менялось"
    return "\n".join(строки), ("по имени" if ио else "обезличено")


c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
итог = Counter()
примеры = []
поток = io.open(СЛЕД, "a", encoding="utf-8") if КАТИТЬ else None

for инн, v in sorted(выбор.items()):
    if ПОТОЛОК and итог["поставлено"] >= ПОТОЛОК:
        break
    адрес, роль, фио = v[2], v[3], v[4]
    if адрес in сделано:
        итог["уже стояло"] += 1
        continue
    исход = c.execute(
        "SELECT cr.subject, cr.body, cr.panel_json, cr.campaign_id, cr.recipient_id "
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
    if len(примеры) < 5:
        примеры.append((инн, адрес, роль, исход["subject"], тело.split("\n", 1)[0]))
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
                   "rol_adresa": роль, "partiya": 2}))
        mid, _sid, почему = q._ensure_message(int(исход["campaign_id"]), rid)
        if mid is None:
            итог["нет message_id: " + str(почему)[:36]] += 1
            continue
        try:
            панель = json.loads(исход["panel_json"] or "{}") or {}
        except Exception:                                          # noqa: BLE001
            панель = {}
        панель["email"] = адрес
        панель["recipient_id"] = rid
        панель["vtoroy_adres"] = {
            "rol": роль, "fio": фио or "", "partiya": 2,
            "pervyy_adres": sorted(молч.get(инн, {"?"}))[0],
            "vyruchka": выр.get(инн, 0),
            "zametka": "второй адрес того же домена, первое письмо без ответа"}
        рез = cs.submit(email=адрес, subject=исход["subject"], body=тело,
                        inn=инн, campaign_id=int(исход["campaign_id"]),
                        recipient_id=rid, message_id=mid, panel=панель)
        итог["статус: " + str(рез.status)] += 1
        if рез.status == "pending":
            итог["поставлено"] += 1
            поток.write(json.dumps({"email": адрес, "inn": инн,
                                    "review": рез.review_id,
                                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                   ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
        else:
            итог["причина: " + str(рез.reason)[:40]] += 1
    except Exception as ex:                                        # noqa: BLE001
        итог["ошибка: " + str(ex)[:46]] += 1
    if КАТИТЬ and итог["поставлено"] and итог["поставлено"] % 100 == 0:
        print("   ... поставлено %d" % итог["поставлено"], flush=True)

if поток:
    поток.close()
c.close()
print("")
print("=== примеры ===")
for инн, а, р, т, п in примеры:
    print("   %-13s %-28s %-17s" % (инн, а[:28], р[:17]))
    print("      %s | %s" % (str(т)[:56], п[:32]))
print("")
print("=== итог ===")
for к, n in итог.most_common():
    print("   %-44s %5d" % (к, n))
