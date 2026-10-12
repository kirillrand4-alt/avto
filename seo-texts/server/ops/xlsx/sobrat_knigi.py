# -*- coding: utf-8 -*-
"""Собрать обе книги паспортов в записи для обогащения.

Ключ: российский ИНН как есть; белорусский УНП цифрами; у кого номера нет
— служебный, одиннадцать знаков, стабильный по домену сайта.

Уровень доверия к сайту:
  inn       — номер компании найден НА СТРАНИЦЕ и подтверждён;
  sam_sayt  — юрлица не называли, компания опознана этим сайтом;
  ""        — сомнение, привязка моделью или сайт холдинга: паспорт
              грузим, но как факты компании не утверждаем.
"""
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

НС = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
АДРЕС = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
ПАСПОРТ = ["Паспорт: сырьё", "Паспорт: мощности", "Паспорт: контроль качества",
           "Паспорт: оборудование и линии", "Паспорт: упаковка и фасовка",
           "Паспорт: экспорт", "Паспорт: масштаб"]


def домен(url):
    s = re.sub(r"^https?://", "", str(url or "").strip().lower()).strip("/")
    return s.split("/")[0].replace("www.", "")


def читать(путь):
    z = zipfile.ZipFile(путь)
    общие = []
    if "xl/sharedStrings.xml" in z.namelist():
        with z.open("xl/sharedStrings.xml") as f:
            буф = []
            for _, эл in ET.iterparse(f, events=("end",)):
                if эл.tag == НС + "t":
                    буф.append(эл.text or "")
                elif эл.tag == НС + "si":
                    общие.append("".join(буф))
                    буф = []
                    эл.clear()
    имена = {}
    кор = ET.fromstring(z.read("xl/workbook.xml"))
    for i, s in enumerate(кор.iter(НС + "sheet"), start=1):
        имена[i] = s.get("name")
    for лист in sorted((n for n in z.namelist()
                        if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                       key=lambda s: int(re.findall(r"\d+", s)[0])):
        имя = имена.get(int(re.findall(r"\d+", лист)[0]), "")
        if имя == "Сводка":
            continue
        шапка = None
        with z.open(лист) as f:
            for _, эл in ET.iterparse(f, events=("end",)):
                if эл.tag != НС + "row":
                    continue
                я = []
                for c in эл.findall(НС + "c"):
                    v, из, т = c.find(НС + "v"), c.find(НС + "is"), c.get("t")
                    if из is not None:
                        з = "".join(x.text or "" for x in из.iter(НС + "t"))
                    elif v is None:
                        з = ""
                    else:
                        з = v.text or ""
                        if т == "s" and з.isdigit() and int(з) < len(общие):
                            з = общие[int(з)]
                    я.append(str(з).strip())
                эл.clear()
                if шапка is None:
                    шапка = я
                    continue
                yield имя, dict(zip(шапка, я))


ВТОРОЙ_УРОВЕНЬ = ("В", "Г", "Д")


def доверие(чей, класс=""):
    """Уровень доверия с учётом класса сомнения (владелец 12.10).

    А и Б — сомнение формальное либо уже перебито: первый уровень.
    В (сайт другой организации), Г (сайт не открылся), Д (не сходится
    регион/профиль/масштаб) — второй уровень: паспорт грузим, но как
    подтверждённый сайт компании не засчитываем."""
    к = str(класс or "").strip()[:1].upper()
    if к in ВТОРОЙ_УРОВЕНЬ:
        return ""
    ч = str(чей or "").lower()
    if "на сайте" in ч and "подтвержда" in ч:
        return "inn"
    return "sam_sayt"


служебные, счёт = {}, 0
компании, адреса, контакты = {}, [], 0
for путь in sys.argv[1:-1]:
    for лист, р in читать(путь):
        if лист == "Контакты (все)":
            а = str(р.get("E-mail") or "").strip().lower()
            ид = str(р.get("ИНН / УНП") or "").strip()
            if АДРЕС.match(а) and ид:
                контакты += 1
                адреса.append({"ид": ид, "email": а,
                               "role": str(р.get("Роль") or "").strip(),
                               "person": str(р.get("ФИО") or "").strip(),
                               "url": str(р.get("Ссылка на источник") or "")[:300]})
            continue
        ид = str(р.get("ИНН / УНП") or "").strip()
        if not ид or ид in компании:
            continue
        сайт = домен(р.get("Сайт"))
        ц = "".join(c for c in ид if c.isdigit())
        if ид.isdigit() and len(ц) in (10, 12):
            ключ = ц
        elif ид.upper().startswith("BY") and len(ц) == 9:
            ключ = ц
        else:
            if сайт not in служебные:
                счёт += 1
                служебные[сайт] = str(счёт).zfill(11)
            ключ = служебные[сайт]
        куски = []
        о = str(р.get("Описание (по сайту)") or "").strip()
        пр = str(р.get("Продукция") or "").strip()
        if о:
            куски.append(о)
        if пр:
            куски.append("Продукция: " + пр)
        for поле in ПАСПОРТ:
            з = str(р.get(поле) or "").strip()
            if з:
                куски.append(поле.replace("Паспорт: ", "").capitalize() + ": " + з)
        выр = "".join(c for c in str(р.get("Выручка, руб") or "") if c.isdigit())
        компании[ид] = {
            "inn": ключ, "ид": ид, "name": str(р.get("Название") or "")[:200],
            "site": сайт, "activity": "; ".join(куски)[:4000],
            "verified": доверие(р.get("Сайт: чей"),
                                р.get("Сомнение в сайте (класс)")),
            "klass": str(р.get("Сомнение в сайте (класс)") or "")[:120],
            "pochemu": str(р.get("Сомнение: кто и почему") or "")[:300],
            "chey": str(р.get("Сайт: чей") or "")[:150],
            "region": str(р.get("Регион") or "")[:80],
            "okved": str(р.get("Основной ОКВЭД") or "")[:40],
            "okved_all": str(р.get("Доп. ОКВЭД") or "")[:200],
            "revenue": int(выр) if выр else None,
            "otrasl": str(р.get("Направление") or "")[:60],
            "strana": str(р.get("Страна") or "")[:40],
            "pismo": str(р.get("Письмо: e-mail") or "").strip().lower(),
            "stupen": str(р.get("Письмо: ступень лесенки") or "")[:60],
            "fio": str(р.get("Письмо: кому (ФИО)") or "")[:120],
            "dolzh": str(р.get("Письмо: должность") or "")[:120],
        }
        for поле, метка in (("Все почты по лесенке (роль, ЛПР, ФИО/должность)", ""),
                            ("Почты не для письма (кадры, бухгалтерия, прессa)",
                             "не для письма")):
            for кус in str(р.get(поле) or "").replace("\n", ";").split(";"):
                a = кус.split("—")[0].strip().lower()
                if not АДРЕС.match(a):
                    continue
                хв = кус.split("—", 1)[1].strip() if "—" in кус else ""
                адреса.append({"ид": ид, "email": a,
                               "role": хв.split(",")[0].strip() or метка,
                               "person": "", "url": р.get("Сайт") or ""})

# адреса привязываем к ключу компании
по_ид = {к: v["inn"] for к, v in компании.items()}
готовые, видели = [], set()
for а in адреса:
    ключ = по_ид.get(а["ид"])
    if not ключ:
        continue
    п = (ключ, а["email"])
    если = видели and п in видели
    if если:
        continue
    видели.add(п)
    готовые.append({"inn": ключ, "email": а["email"], "role": а["role"],
                    "person": а["person"], "url": а["url"][:300]})

вых = {"компании": list(компании.values()), "адреса": готовые}
json.dump(вых, open(sys.argv[-1], "w", encoding="utf-8"), ensure_ascii=False)
ур = {}
for к in компании.values():
    ур[к["verified"] or "(нет)"] = ур.get(к["verified"] or "(нет)", 0) + 1
print("компаний: %d, адресов: %d (строк контактов разобрано %d)"
      % (len(компании), len(готовые), контакты))
print("служебных ключей: %d" % len(служебные))
print("уровни доверия: %s" % ур)
