# -*- coding: utf-8 -*-
"""Ручная загрузка обогащённой базы в панель рассылки.

Владелец 11.08: «сейчас дообогащается ещё одна партия для будущих писем,
сделай кнопку для загрузки ручной такой базы в панель, чтобы я мог создать
компанию и загрузить новые емайлы + сгенерировать очередь писем».

До этого дня база получателей пополнялась только моими руками через серверные
скрипты: владелец не мог залить партию сам, и каждая новая пачка ждала меня.

Форм у партий две, и обе живые, поэтому понимаем обе:

1. JSONL обогащения (`enrich_panel_run2.jsonl` и родня) — строка на компанию:
       {"inn": "...", "emails": [{"email", "person", "role", "mx_ok",
        "source_url", "source", "smtp"}], "activity": "...",
        "is_competitor": false, "site_title": "...", "_okved": "..."}
2. CSV выгрузок (`PARK-BAZA-*.csv`, `DOLIVKA-*.csv`) — строка на контакт, с
   заголовками латиницей: inn;predpriyatie;chelovek;dolzhnost;pochta;...

Разделитель у CSV бывает и `;`, и `,` — определяем по первой строке, а не
угадываем: выгрузки делают разные руки.

Главное правило разбора: НИЧЕГО не выдумывать. Нет ИНН — строка идёт в отчёт
как «без ИНН», а не получает пустую строку в базу. Компания-конкурент из
обогащения (`is_competitor`) не попадает в загрузку вовсе: писать конкуренту —
дороже, чем потерять строку.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_АДРЕС = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# Заголовки CSV, которые встречаются в наших выгрузках. Слева — то, что пишут
# люди и скрипты, справа — поле панели.
_КОЛОНКИ = {
    "inn": "inn", "инн": "inn",
    "email": "email", "pochta": "email", "почта": "email", "e-mail": "email",
    "mail": "email",
    "company": "company_name", "predpriyatie": "company_name",
    "компания": "company_name", "предприятие": "company_name",
    "name": "company_name", "naimenovanie": "company_name",
    "fio": "contact_name", "chelovek": "contact_name", "человек": "contact_name",
    "fio_ili_nomer": "contact_name", "контакт": "contact_name",
    "dolzhnost": "role", "должность": "role", "rol": "role", "роль": "role",
    "okved": "okved", "оквэд": "okved",
    "region": "region", "регион": "region",
    "site": "site", "sayt": "site", "сайт": "site",
}


def _чистый_адрес(значение: Any) -> str:
    а = str(значение or "").strip().strip("<>").lower()
    return а if _АДРЕС.match(а) else ""


def _цифры(значение: Any) -> str:
    return "".join(c for c in str(значение or "") if c.isdigit())


def _из_jsonl(текст: str) -> tuple[list, list]:
    """Строки обогащения → плоский список контактов + список замечаний."""
    контакты, замечания = [], []
    компаний = конкурентов = 0
    for н, с in enumerate(текст.splitlines(), 1):
        с = с.strip()
        if not с:
            continue
        try:
            д = json.loads(с)
        except Exception:  # noqa: BLE001 - битая строка не рвёт загрузку
            замечания.append(f"строка {н}: не разбирается как JSON")
            continue
        if not isinstance(д, dict):
            continue
        компаний += 1
        # Конкурента не берём вовсе: цена ошибки здесь несимметрична.
        if д.get("is_competitor"):
            конкурентов += 1
            continue
        инн = _цифры(д.get("inn"))
        компания = (д.get("company_name") or д.get("name")
                    or д.get("site_title") or "")
        оквэд = д.get("_okved") or д.get("okved") or ""
        занятие = д.get("activity") or д.get("site_description") or ""
        почты = д.get("emails")
        if isinstance(почты, str):
            почты = [{"email": почты}]
        for e in (почты or []):
            если = e if isinstance(e, dict) else {"email": e}
            адрес = _чистый_адрес(если.get("email"))
            if not адрес:
                continue
            контакты.append({
                "inn": инн, "email": адрес,
                "company_name": str(компания)[:300],
                "contact_name": str(если.get("person") or "")[:150],
                "role": str(если.get("role") or "")[:100],
                "okved": str(оквэд)[:200], "activity": str(занятие)[:400],
                "site": str(д.get("site_meta_url") or д.get("site")
                                or д.get("url") or "")[:200],
                "smtp": str(если.get("smtp") or ""),
                "source_url": str(если.get("source_url") or "")[:300],
            })
    if конкурентов:
        замечания.append(f"пропущено конкурентов: {конкурентов}")
    замечания.append(f"компаний в файле: {компаний}")
    return контакты, замечания


def _из_csv(текст: str) -> tuple[list, list]:
    """CSV выгрузок → тот же плоский список."""
    контакты, замечания = [], []
    первая = текст.splitlines()[0] if текст.strip() else ""
    # Разделитель определяем, а не предполагаем: выгрузки делают разные руки.
    разделитель = ";" if первая.count(";") >= первая.count(",") else ","
    чтец = csv.DictReader(io.StringIO(текст), delimiter=разделитель)
    поля = {}
    for имя in (чтец.fieldnames or []):
        ключ = str(имя or "").strip().lower().lstrip("﻿")
        if ключ in _КОЛОНКИ:
            поля[имя] = _КОЛОНКИ[ключ]
    if "email" not in поля.values():
        замечания.append("в файле нет колонки с почтой — загружать нечего")
        return [], замечания
    замечания.append("узнаны колонки: "
                     + ", ".join(f"{k}→{v}" for k, v in поля.items()))
    for строка in чтец:
        собрано = {"inn": "", "email": "", "company_name": "",
                   "contact_name": "", "role": "", "okved": "", "site": "",
                   "activity": "", "smtp": "", "source_url": ""}
        for имя, поле in поля.items():
            значение = строка.get(имя) or ""
            собрано[поле] = str(значение).strip()
        собрано["inn"] = _цифры(собрано["inn"])
        собрано["email"] = _чистый_адрес(собрано["email"])
        if собрано["email"]:
            контакты.append(собрано)
    return контакты, замечания


def разобрать(текст: str, имя_файла: str = "") -> tuple[list, list]:
    """Файл любой из двух форм → (контакты, замечания). Форму определяем по
    содержимому, а не по расширению: имя файла врёт чаще, чем первая строка."""
    т = (текст or "").lstrip()
    if not т:
        return [], ["файл пустой"]
    if т.startswith("{") or т.startswith("["):
        if т.startswith("["):
            try:
                # Целый JSON-массив — разложим в строки и разберём как JSONL.
                т = "\n".join(json.dumps(x, ensure_ascii=False)
                              for x in json.loads(т))
            except Exception:  # noqa: BLE001
                return [], ["файл похож на JSON, но не разбирается"]
        return _из_jsonl(т)
    return _из_csv(т)


def свод(контакты: list, store: Any = None) -> dict:
    """Что получится, ЕСЛИ загрузить. Показывается до записи в базу.

    Оператор должен видеть не «загружено N», а заранее: сколько адресов новых,
    сколько уже есть, сколько в стоп-листе. Загрузка вслепую — это способ
    написать тому, кто просил не писать.
    """
    видели, уник = set(), []
    без_инн = 0
    for к in контакты:
        а = к["email"]
        if а in видели:
            continue
        видели.add(а)
        уник.append(к)
        if not к.get("inn"):
            без_инн += 1

    уже, в_стопе = set(), set()
    if store is not None and уник:
        try:
            con = store._conn  # noqa: SLF001 - читаем ту же живую базу
            метки = ",".join("?" * len(видели))
            зн = list(видели)
            for (e,) in con.execute(
                    f"SELECT lower(email) FROM recipients "
                    f"WHERE lower(email) IN ({метки})", зн):
                уже.add(e)
            домены = {a.split("@")[-1] for a in видели}
            инны = {к["inn"] for к in уник if к.get("inn")}
            значения = list(видели | домены | инны)
            метки2 = ",".join("?" * len(значения))
            for (v,) in con.execute(
                    f"SELECT lower(value) FROM suppression "
                    f"WHERE lower(value) IN ({метки2})", значения):
                в_стопе.add(v)
        except Exception:  # noqa: BLE001 - свод важнее, чем идеальные цифры
            logger.exception("свод импорта: не прочиталась база")

    def под_стопом(к):
        return (к["email"] in в_стопе or к["email"].split("@")[-1] in в_стопе
                or (к.get("inn") and к["inn"] in в_стопе))

    к_загрузке = [к for к in уник if not под_стопом(к)]
    return {
        "vsego_strok": len(контакты),
        "unikalnyh_adresov": len(уник),
        "uzhe_v_baze": len([к for к in уник if к["email"] in уже]),
        "v_stop_liste": len(уник) - len(к_загрузке),
        "bez_inn": без_инн,
        "k_zagruzke": len(к_загрузке),
        "primery": [{k: v for k, v in к.items() if v} for к in к_загрузке[:8]],
        "kontakty": к_загрузке,
    }


def применить(store: Any, контакты: list, *, группа: str,
              источник: str = "ручная загрузка") -> dict:
    """Записать контакты в базу получателей одной группой."""
    from sender.dtos import RecipientIn

    добавлено = обновлено = пропущено = 0
    ошибки = []
    поля = set(getattr(RecipientIn, "__dataclass_fields__", {}) or
               getattr(RecipientIn, "model_fields", {}) or {})
    for к in контакты:
        адрес = к.get("email") or ""
        if "@" not in адрес:
            пропущено += 1
            continue
        было = None
        try:
            было = store.get_recipient_by_email(адрес) if hasattr(
                store, "get_recipient_by_email") else None
        except Exception:  # noqa: BLE001
            было = None
        заготовка = {
            "email": адрес, "domain": адрес.split("@")[-1],
            "inn": к.get("inn") or None,
            "company_name": к.get("company_name") or None,
            "okved": к.get("okved") or None,
            "segment": группа,
            "contact_name": к.get("contact_name") or None,
            "region": к.get("region") or None,
            "source": источник,
        }
        try:
            store.upsert_recipient(RecipientIn(
                **{k: v for k, v in заготовка.items() if k in поля}))
            if было is None:
                добавлено += 1
            else:
                обновлено += 1
        except Exception as e:  # noqa: BLE001 - одна строка не рвёт загрузку
            пропущено += 1
            if len(ошибки) < 5:
                ошибки.append(f"{адрес}: {str(e)[:120]}")
    return {"dobavleno": добавлено, "obnovleno": обновлено,
            "propushcheno": пропущено, "oshibki": ошибки, "gruppa": группа}
