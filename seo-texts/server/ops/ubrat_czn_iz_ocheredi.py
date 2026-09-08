# -*- coding: utf-8 -*-
"""Снять с очереди письма, ушедшие на адрес центра занятости, а не хозяйства.

Чеко берёт почту в том числе из вакансий, и в карточке хозяйства оказывается
ящик районного ЦЗН. Письмо про фотосепаратор уходит на биржу труда: не тот
адресат, и отвечать там некому.

Снимаем ДВА шага, как это делает probe_sync: решение по карточке и само
письмо. Одной карточки мало - строка письма осталась бы живой, и
автоотправка увидела бы то, чего оператор в очереди уже не видит.

Адрес при этом НЕ хороним в стоп-лист: он живой и принадлежит настоящей
организации, просто чужой. Решение про стоп-лист - за владельцем.

    python ubrat_czn_iz_ocheredi.py            # показать, кого снимаем
    python ubrat_czn_iz_ocheredi.py --primenit
"""
import io
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

СПИСОК = r"C:\sender\_ops\agro-czn-snyat.txt"

ТЕМА = "Для качества: вопрос по сортировке зерна"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
ПРИЧИНА = ("адрес центра занятости, а не хозяйства: почта подтянута из "
           "вакансии, письмо ушло бы не тому адресату")

# СПИСКОМ, А НЕ РЕГУЛЯРКОЙ. Первая попытка отбирала шаблоном по домену и
# сразу показала, почему так нельзя: «[a-z]zan» поймал agro@ryazan.ru и
# info@kazan.ru (Рязань и Казань), а czn.krasnodar.ru и but-czn@sinn.ru
# пропустил. Снимать письма по такому признаку - терять живые контакты.
# Поэтому: широкий невод даёт КАНДИДАТОВ, снимаем только то, что названо
# в СНИМАЕМ поимённо, глазами.
НЕВОД = ("czn", "szn", "zanyat", "zanyatost", "trud", "rabota", "vsem",
         "stavzan", "cznz", "zan.")


def кандидат(адрес):
    а = str(адрес or "").lower()
    лок, _, дом = а.partition("@")
    метки = set()
    for ч in re.split(r"[.\-_+]", лок) + дом.split("."):
        if ч in НЕВОД:
            метки.add(ч)
    for сл in НЕВОД:
        if сл in дом:
            метки.add(сл)
    return метки


# СПИСОК ПОИМЁННО, И ОН ЛЕЖИТ В КОДЕ. Тридцать адресов ниже я прочитал
# глазами: это районные центры занятости (czn.krasnodar.ru, stavzan.ru,
# tatar.ru, bashzan.ru, samaratrud.ru и такие же). Пять кандидатов из
# невода в список НЕ вошли - rabota@ruseed.ru, rabota@bezrk.ru,
# gk-svetlyi.rabota@yandex.ru, sv-trud@yandex.ru, lider1@mail.ryazan.ru:
# это ящики самих компаний на своих доменах, просто кадровые. Не тот
# отдел - не повод не писать.
СНИМАЕМ = {
    "but-czn@sinn.ru",
    "mostovskaya@czn.krasnodar.ru",
    "16-czn@stavzan.ru",
    "25-czn@stavzan.ru",
    "belglina@czn.krasnodar.ru",
    "otradnaya@czn.krasnodar.ru",
    "pavlovskaya@czn.krasnodar.ru",
    "slaviansk@czn.krasnodar.ru",
    "starominskaya@czn.krasnodar.ru",
    "11-czn@stavzan.ru",
    "12-czn@stavzan.ru",
    "04-czn@stavzan.ru",
    "pil-czn@czn.kreml.nnov.ru",
    "kr-zar_czn@zar.orel.ru",
    "lunino_czn@mail.ru",
    "zyran@rabota.tomsk.ru",
    "08-czn@stavzan.ru",
    "czn_never@mail.ru",
    "scherbinovskaya@czn.krasnodar.ru",
    "kalininskaya@czn.krasnodar.ru",
    "tihoretsk@czn.krasnodar.ru",
    "26-czn@stavzan.ru",
    "obliv_szn@oblivka.donpac.ru",
    "czn.tetyushi@tatar.ru",
    "davlekan@bashzan.ru",
    "czn.alekseevskoe@tatar.ru",
    "kro-czn@sinn.ru",
    "czn.cheremshan@tatar.ru",
    "kamczn@samaratrud.ru",
    "kuschevskaya@czn.krasnodar.ru",
}

store = Store(r"C:\sender\sender.db")
цели = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, email, status, message_id, recipient_id "
            "  FROM confirm_reviews WHERE subject=?", (ТЕМА,)):
        а = str(р["email"] or "")
        метки = кандидат(а)
        if not метки:
            continue
        имя = ""
        if р["recipient_id"]:
            rec = store.get_recipient(int(р["recipient_id"]))
            имя = str(getattr(rec, "company_name", "") or "")
        запас = []
        if р["recipient_id"]:
            доп = (getattr(rec, "extra", None) or {}).get("pochty_eshchyo")
            запас = [x for x in (доп or []) if x and кандидат(x) == set()]
        цели.append((int(р["id"]), а, str(р["status"]), р["message_id"], имя,
                     ",".join(sorted(метки)), запас))

счёт = Counter(с for _i, _a, с, _m, _n, _k, _z in цели)
домены = Counter(а.split("@", 1)[-1] for _i, а, _с, _m, _n, _k, _z in цели)
с_запасом = [(а, з) for _i, а, _с, _m, _n, _k, з in цели
             if а.lower() in СНИМАЕМ and з]

снято = писем = уже = 0
if ПРИМЕНИТЬ:
    for rid, а, статус, mid, _имя, _k, _z in цели:
        if а.lower() not in СНИМАЕМ:
            continue
        if статус != "pending":
            уже += 1
            continue
        try:
            if store.confirm_decide(rid, status="skipped",
                                    decided_by="проверка адресов партии",
                                    reason=ПРИЧИНА):
                снято += 1
        except Exception as ex:                                # noqa: BLE001
            print("   карточка %s не снялась: %s" % (rid, str(ex)[:80]))
            continue
        if mid:
            try:
                if store.mark_skipped_if_not_terminal(
                        int(mid), "проверка адресов партии: " + ПРИЧИНА):
                    писем += 1
            except Exception as ex:                            # noqa: BLE001
                print("   письмо %s не снялось: %s" % (mid, str(ex)[:80]))

for rid, а, статус, _m, имя, метки, запас in цели:
    print("   %-6s %-32s %-9s %-8s %-22s %s"
          % (rid, а[:32], статус,
             "СНЯТЬ" if а.lower() in СНИМАЕМ else "оставить",
             имя[:22], (запас[0] if запас else "")[:24]))
print("")
print("=" * 74)
print("=== АДРЕСА СЛУЖБЫ ЗАНЯТОСТИ В ПАРТИИ: %s ==="
      % ("СНЯТО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("найдено писем: %d" % len(цели))
for к, в in счёт.most_common():
    print("   было в статусе %-12s %4d" % (к, в))
print("доменов: %d" % len(домены))
for к, в in домены.most_common(12):
    print("   %-34s %4d" % (к, в))
if ПРИМЕНИТЬ:
    print("")
    print("снято карточек: %d; снято писем: %d; уже были не pending: %d"
          % (снято, писем, уже))
else:
    print("")
    print("вхолостую. В списке на снятие: %d" % len(СНИМАЕМ))
print("у скольких снимаемых есть запасной адрес компании: %d" % len(с_запасом))
