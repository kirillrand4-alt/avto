# -*- coding: utf-8 -*-
"""Залить компании каталога ProdExpo в базу рассылки группой под Meyer.

Ключ компании. Вся цепочка рассыльщика — резюм партии, заслон 90 дней,
карточка обогащения — завязана на ИНН. У белорусского участника его нет и
быть не может. Поэтому берём УНП с сайта, а где не нашли — присваиваем
СВОЙ ключ вида 9990xxxxxxxx: двенадцать цифр, начинающихся с 9990, не
бывают настоящим ИНН (первые цифры — код региона, региона 99 нет), и по
extra видно, что ключ наш. Настоящий УНП кладём рядом отдельным полем.

    python belarus_zalit.py            # вхолостую
    python belarus_zalit.py primenit   # залить
"""
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.dtos import RecipientIn  # noqa: E402
from sender.store import Store       # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
КАРТОЧКИ = r"C:\sender\_ops\belarus\kartochki.jsonl"
ЗАЛИТО = r"C:\sender\_ops\belarus\zalito.jsonl"
ГРУППА = "prodexpo2025"
ИСТОЧНИК = "prodexpo-2025"

АДРЕС = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def почта_одна(сырое):
    """В каталоге в одной строке бывает несколько адресов через запятую
    («atinori777@gmail.com, 6080660@mail.ru») — берём первый годный.
    Строка целиком в поле email означала бы адрес с запятой внутри и
    отбивку на первом же письме."""
    найдены = АДРЕС.findall(str(сырое or ""))
    return найдены[0].strip().lower() if найдены else ""


ФОРМЫ = [
    ("совместное общество с ограниченной ответственностью", "СООО"),
    ("общество с ограниченной ответственностью", "ООО"),
    ("общество с дополнительной ответственностью", "ОДО"),
    ("открытое акционерное общество", "ОАО"),
    ("закрытое акционерное общество", "ЗАО"),
    ("частное производственное унитарное предприятие", "ЧПУП"),
    ("производственное унитарное предприятие", "ПУП"),
    ("частное торговое унитарное предприятие", "ЧТУП"),
    ("иностранное унитарное предприятие", "ИУП"),
    ("унитарное предприятие", "УП"),
    ("индивидуальный предприниматель", "ИП"),
    ("акционерное общество", "АО"),
]


def коротко(имя):
    """«Общество с ограниченной ответственностью «Агропродукт»» → «ООО «Агропродукт»».

    Полная юридическая форма в приветствии письма выглядит канцелярски;
    в базе у российских компаний тоже стоят сокращения.
    """
    т = " ".join(str(имя or "").split())
    ниж = т.lower()
    for полн, кратк in ФОРМЫ:
        if ниж.startswith(полн):
            return (кратк + " " + т[len(полн):].strip()).strip()
        if полн in ниж:
            i = ниж.index(полн)
            return " ".join((т[:i] + кратк + " " + т[i + len(полн):]).split())
    return т


def ключ(запись):
    """УНП, если добыли; иначе свой стабильный ключ 9990xxxxxxxx."""
    унп = "".join(c for c in str(запись.get("унп") or "") if c.isdigit())
    if len(унп) == 9:
        return унп, "УНП с сайта"
    основа = (str(запись.get("сайт") or "") + "|"
              + str(запись.get("название") or "")).lower()
    ц = str(int(hashlib.sha1(основа.encode("utf-8")).hexdigest()[:12], 16))
    return "9990" + (ц + "00000000")[:8], "свой ключ (УНП не нашли)"


def страна(запись):
    г = str(запись.get("город") or "").lower()
    сайт = str(запись.get("сайт") or "").lower()
    if "беларус" in г or "белорус" in г or ".by" in сайт:
        return "BY"
    if "российск" in г or "россия" in г or ".ru" in сайт or ".рф" in сайт:
        return "RU"
    return "BY"


записи = []
for с in io.open(КАРТОЧКИ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if с:
        try:
            записи.append(json.loads(с))
        except Exception:                                    # noqa: BLE001
            pass
# на всякий случай схлопываем повторы по названию
уник = {}
for з in записи:
    уник[str(з.get("название") or "").lower()] = з
записи = list(уник.values())
print("карточек: %d" % len(записи))

store = Store(r"C:\sender\sender.db")
занятые = set()
with store._lock:
    for (и,) in store._conn.execute(
            "SELECT inn FROM recipients WHERE inn IS NOT NULL").fetchall():
        занятые.add(str(и))

к_заливке, пропуск = [], {"нет почты": 0, "ключ занят": 0}
for з in записи:
    почта = почта_одна(з.get("почта"))
    if not почта:
        пропуск["нет почты"] += 1
        continue
    инн, откуда = ключ(з)
    if инн in занятые:
        # УНП совпал с чужим ИНН — такого быть не должно, но молча
        # подменять компанию нельзя: пусть будет видно.
        пропуск["ключ занят"] += 1
        continue
    занятые.add(инн)
    имя = коротко(з.get("название"))
    extra = {
        "gruppy": [ГРУППА],
        "strana": страна(з),
        "unp": з.get("унп") or None,
        "psevdo_inn": not (з.get("унп") or ""),
        "istochnik": "каталог ProdExpo 2025",
        "site": з.get("сайт") or None,
        "activity": з.get("чем_занимается") or None,
        "produkciya": з.get("продукция") or None,
        "phone": з.get("телефон") or None,
        # Остальные адреса компании из каталога — оператору в карточку.
        "pochty_eshchyo": [а for а in АДРЕС.findall(str(з.get("почта") or ""))
                           if а.lower() != почта] or None,
        "city": з.get("город") or None,
        "city_source": "карточка",
        # Сайт назван в каталоге выставки самой компанией — принадлежность
        # доказана не догадкой поисковика, и письмо вправе опираться на его
        # содержимое. Найденный поиском помечаем честно.
        "verified": ("каталог выставки" if з.get("как_нашли_сайт") == "каталог"
                     else "найден поиском"),
    }
    if з.get("текст_сайта"):
        extra["site_text"] = з["текст_сайта"]
    к_заливке.append((RecipientIn(
        email=почта,
        domain=почта.split("@", 1)[1],
        inn=инн,
        company_name=имя,
        segment="meyer",
        source=ИСТОЧНИК,
        region=str(з.get("город") or "")[:80] or None,
        tz="Europe/Moscow",
        extra=extra), откуда, з))

print("к заливке: %d, пропуск: %s" % (len(к_заливке), пропуск))
print("")
for р, откуда, з in к_заливке[:8]:
    print("   %-42s %-30s %s | текст сайта %d зн. | %s"
          % (р.company_name[:42], р.email[:30], р.inn,
             len(з.get("текст_сайта") or ""), откуда))

if not ДЕЛАТЬ:
    print("\nвхолостую. Залить — primenit")
    raise SystemExit(0)

ф = io.open(ЗАЛИТО, "a", encoding="utf-8")
залито = 0
for р, откуда, з in к_заливке:
    rid = store.upsert_recipient(р)
    залито += 1
    ф.write(json.dumps({"id": rid, "inn": р.inn, "почта": р.email,
                        "имя": р.company_name, "ключ": откуда},
                       ensure_ascii=False) + "\n")
ф.flush()
os.fsync(ф.fileno())
ф.close()
print("\nзалито получателей: %d" % залито)
группы = store.recipient_groups().get("по_id") or {}
print("в группе %s: %d" % (ГРУППА, sum(1 for g in группы.values() if ГРУППА in g)))
