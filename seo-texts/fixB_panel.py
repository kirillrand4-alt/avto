# -*- coding: utf-8 -*-
"""fixB: поиск, статистика директора, новые результаты звонка (панель обзвона Meyer, 08.10).

Сводка проверки: seo-texts/PANEL-AUDIT-0810.md, разделы 7 и 8. Владелец: «исправляй всё».

1. Поиск: номер в любом виде (+7…, 8…, «8 (900) 000-00-00», последние 7/10 цифр) – цифры
   сравниваются с номерами компании (контакты, люди, ЛПР, номера от продавцов); город и
   населённый пункт – из адреса, региона, исходного региона; ФИО – из контактов.
2. Новые результаты звонка: «Не дозвонился» (компания остаётся в очереди, попытка пишется
   в zvonok_sobytie) и «Получен личный номер ЛПР» (ФИО, должность, номер; номер – в каталог,
   contact, источник «от продавца»). Старые три результата – как были.
3. Причины «не понравилась»: + «нет потребности», «не наш профиль», «компания закрыта»,
   «не та компания / не ЛПР»; причина – отдельной колонкой prichina (состояние, комментарий,
   журнал), старые записи понимаются разбором текста.
4. Статистика директора: «всё время» – настоящий период; якорь к очереди продавца; явные
   сообщения о перевёрнутых и будущих датах; пояснение суммы по «Источнику базы»; в фильтре
   «Результат звонка» – только то, что продавец ставит (+ новые); без строки meyer_admin; один
   порядок продавцов (по ФИО); «Балл очереди» везде.
5. Сортировка списка для директора и выгрузка CSV текущего отбора.
6. Форма продавца в карточке у директора свёрнута.
7. Подпись «база продаж по компрессорному оборудованию» в коде.
+ (координатор) фильтры «Пометка очереди», «Клиент СЦ», сегмент «учитывать доп. ОКВЭД».

Режимы:
  (без ключей)            – под замком: копия кода -> правки -> полная проверка на копиях баз ->
                            правки в боевых файлах -> быстрая проверка -> схема базы продаж ->
                            перезапуск.
  --proverka <корень>     – полная проверка (TestClient, временные копии баз продаж и каталога)
  --bystro <корень>       – быстрая проверка рендера
  --lokalno <папка app>   – только применить правки к локальной копии (сухой прогон якорей)
"""
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
ZAMOK = os.path.join(KOREN, '_zamok.txt')
METKA = time.strftime('%Y%m%d-%H%M%S')
BEKAP = os.path.join(KOREN, '_bekap', 'fixB-' + METKA)
TEST_DB = os.path.join(KOREN, '_bekap', 'fixB-test-sales.db')
TEST_KAT = os.path.join(KOREN, '_bekap', 'fixB-test-katalog.db')
FAJLY = {
    'rcs': os.path.join('api', 'routes_centro_sales.py'),
    'rp': os.path.join('api', 'routes_park.py'),
    'cs': os.path.join('services', 'centro_sales.py'),
    'C': os.path.join('templates', 'centro.html'),
    'L': os.path.join('templates', '_ochered_spisok.html'),
    'SB': os.path.join('templates', '_statblok.html'),
    'ST': os.path.join('templates', 'centro_stats.html'),
}

# =========================================================================== код: centro_sales
CS_DOP = r'''


# ===================================================================== fixB-блок (08.10)
# Новые результаты звонка (владелец 08.10, сводка проверки PANEL-AUDIT-0810, раздел 8):
# «Не дозвонился» – компания остаётся в очереди, попытка пишется и считается по продавцу и
# дню; «Получен личный номер ЛПР» – ФИО, должность, номер. Это СОБЫТИЯ, а не статусы: статус
# компании (company_state.call_result) они не меняют, поэтому «Вся очередь», вкладки и
# прежние три результата работают как раньше. Схема только расширяется.
SOBYTIYA_ZVONKA = {
    "ne_dozvonilsya": "Не дозвонился",
    "lpr_nomer": "Получен личный номер ЛПР",
}

_SCHEMA_DOP = (
    "CREATE TABLE IF NOT EXISTS zvonok_sobytie ("
    " id INTEGER PRIMARY KEY,"
    " inn TEXT NOT NULL,"
    " username TEXT NOT NULL,"            # кто нажал
    " state_user TEXT NOT NULL,"          # чья компания (продавец), ему и засчитывается
    " vid TEXT NOT NULL,"                 # ne_dozvonilsya | lpr_nomer
    " fio TEXT NOT NULL DEFAULT '',"
    " dolzhnost TEXT NOT NULL DEFAULT '',"
    " nomer TEXT NOT NULL DEFAULT '',"    # +7XXXXXXXXXX
    " nomer_10 TEXT NOT NULL DEFAULT '',"
    " dob TEXT NOT NULL DEFAULT '',"
    " kommentariy TEXT NOT NULL DEFAULT '',"
    " next_contact TEXT NOT NULL DEFAULT '',"
    " katalog_contact_id INTEGER,"
    " katalog_itog TEXT NOT NULL DEFAULT '',"
    " created_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS ix_zvonok_sobytie_inn ON zvonok_sobytie(inn, vid, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_zvonok_sobytie_kto ON zvonok_sobytie(state_user, vid, created_at)",
)


def ensure_dop(conn: sqlite3.Connection) -> None:
    """Таблица событий звонка и колонка prichina (причина отказа отдельным полем) в
    company_state и company_comment. Только CREATE IF NOT EXISTS и ADD COLUMN: существующие
    строки не меняются. Без commit – его делает вызывающий (with connect())."""
    for sql in _SCHEMA_DOP:
        conn.execute(sql)
    for tablica in ("company_state", "company_comment"):
        kolonki = {row[1] for row in conn.execute(f"PRAGMA table_info({tablica})")}
        if "prichina" not in kolonki:
            conn.execute(f"ALTER TABLE {tablica} ADD COLUMN prichina TEXT")


_DOBAVOCHNYY_B = re.compile(r"\s*(?:доб\.?|доп\.?|вн\.?|ext\.?|#)\s*(\d{1,6})\s*$", re.I)


def razobrat_nomer(syroe) -> tuple:
    """«8 (900) 000-00-00 доб. 12» -> («+79000000000», «9000000000», «12»).
    Не номер -> («», «», добавочный)."""
    t = str(syroe or "").strip()
    dob = ""
    m = _DOBAVOCHNYY_B.search(t)
    if m:
        dob, t = m.group(1), t[:m.start()]
    cifry = re.sub(r"\D", "", t)
    if len(cifry) == 11 and cifry[0] in "78":
        return "+7" + cifry[1:], cifry[1:], dob
    if len(cifry) == 10:
        return "+7" + cifry, cifry, dob
    if 11 <= len(cifry) <= 15:                 # иностранный номер – как есть
        return "+" + cifry, cifry[-10:], dob
    return "", "", dob


def nomer_pokaz(nomer: str) -> str:
    """+79000000000 -> «+7 900 000-00-00» (читать вслух и сверять)."""
    c = re.sub(r"\D", "", str(nomer or ""))
    if len(c) == 11 and c[0] == "7":
        return "+7 %s %s-%s-%s" % (c[1:4], c[4:7], c[7:9], c[9:11])
    return str(nomer or "")


def zapisat_sobytie(
    user: dict,
    inn: str,
    vid: str,
    *,
    comment: str = "",
    next_contact: str = "",
    fio: str = "",
    dolzhnost: str = "",
    nomer: str = "",
    path: str | Path | None = None,
) -> dict:
    """Записать «Не дозвонился» или «Получен личный номер ЛПР». Статус компании не меняется;
    «Следующий контакт», если указан, ставится (перезвон). Комментарий продавца – в обычные
    комментарии (виден под статусом в списке и в истории карточки)."""
    inn = normalize_inn(inn)
    comment = (comment or "").strip()
    fio = " ".join(str(fio or "").split())[:150]
    dolzhnost = " ".join(str(dolzhnost or "").split())[:150]
    if vid not in SOBYTIYA_ZVONKA:
        raise ValueError("Некорректный результат звонка")
    if not inn:
        raise ValueError("ИНН не указан")
    if len(comment) > 4000:
        raise ValueError("Комментарий длиннее 4000 символов")
    polnyy, k10, dob = razobrat_nomer(nomer)
    if vid == "lpr_nomer":
        if not polnyy:
            raise ValueError("Укажите личный номер ЛПР: 10 цифр, можно с +7 или 8")
        if not (fio or dolzhnost):
            raise ValueError("Укажите должность ЛПР (и ФИО, если назвали)")
    else:
        polnyy = k10 = dob = ""
        fio = dolzhnost = ""
    now = utcnow()
    with connect(path) as conn:
        ensure_dop(conn)
        owner = assignment_owner(conn, inn)
        if not allowed(conn, user, inn) or not owner:
            raise PermissionError(inn)
        state_user = owner if user["role"] == "admin" else user["username"]
        if vid == "lpr_nomer":
            # тот же номер у той же компании уже записан – второй раз не считаем
            byl = conn.execute(
                "SELECT id, katalog_contact_id, katalog_itog FROM zvonok_sobytie "
                "WHERE inn=? AND vid='lpr_nomer' AND nomer_10=? ORDER BY id LIMIT 1",
                (inn, k10)).fetchone()
            if byl:
                return {"id": byl[0], "povtor": True, "inn": inn, "state_user": state_user,
                        "nomer": polnyy, "nomer_10": k10, "dob": dob, "fio": fio,
                        "dolzhnost": dolzhnost, "created_at": now}
        if next_contact:
            # перезвон: только «Следующий контакт», результат и статус прежние
            conn.execute(
                "INSERT INTO company_state(inn,username,status,next_contact_at,call_result,updated_at) "
                "VALUES(?,?,'new',?,'new',?) ON CONFLICT(inn,username) DO UPDATE SET "
                "next_contact_at=excluded.next_contact_at,updated_at=excluded.updated_at",
                (inn, state_user, next_contact, now))
        if vid == "lpr_nomer":
            telo = "Получен личный номер ЛПР: " + ", ".join(
                x for x in (fio, dolzhnost, nomer_pokaz(polnyy) + (" доб. " + dob if dob else "")) if x)
            telo += (". " + comment) if comment else ""
        else:
            telo = ("Не дозвонился. " + comment) if comment else ""
        if telo:
            conn.execute(
                "INSERT INTO company_comment(inn,username,body,created_at,updated_at) VALUES(?,?,?,?,?)",
                (inn, user["username"], telo[:5000], now, now))
        cur = conn.execute(
            "INSERT INTO zvonok_sobytie(inn,username,state_user,vid,fio,dolzhnost,nomer,nomer_10,dob,"
            "kommentariy,next_contact,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (inn, user["username"], state_user, vid, fio, dolzhnost, polnyy, k10, dob,
             comment, next_contact or "", now))
        sid = cur.lastrowid
        conn.execute(
            "INSERT INTO activity_log(inn,username,action,payload_json,created_at) VALUES(?,?,?,?,?)",
            (inn, user["username"], vid,
             json.dumps({"state_user": state_user, "next_contact": next_contact, "sobytie_id": sid,
                         "fio": fio, "dolzhnost": dolzhnost, "kommentariy": comment},
                        ensure_ascii=False), now))
    return {"id": sid, "povtor": False, "inn": inn, "state_user": state_user, "nomer": polnyy,
            "nomer_10": k10, "dob": dob, "fio": fio, "dolzhnost": dolzhnost, "created_at": now}


def otmetit_katalog(sobytie_id: int, contact_id, itog: str, *, path: str | Path | None = None) -> None:
    """Чем кончилось добавление номера в каталог – в строке события (для карточки)."""
    with connect(path) as conn:
        conn.execute("UPDATE zvonok_sobytie SET katalog_contact_id=?, katalog_itog=? WHERE id=?",
                     (contact_id, str(itog or "")[:200], sobytie_id))
'''

# =========================================================================== код: routes_centro_sales
RCS_DOP = r'''


# ===================================================================== fixB-блок (08.10)
# Поиск, новые результаты звонка, причина отдельным полем, статистика директора, сортировка
# и выгрузка. Сводка проверки PANEL-AUDIT-0810 (разделы 7 и 8), владелец: «исправляй всё».
import csv as _csv_b
import io as _io_b

from fastapi.responses import Response as _Response_b

# ---------------------------------------------------------------- 1. поиск
# Продавец вводит номер так, как он у него в руках: «+79000000000», «89000000000»,
# «8 (900) 000-00-00», последние 7 или 10 цифр. Раньше искалась подстрока в search_blob, где
# номер записан с пробелами и дефисами, – и «+7900…» не находилось вовсе. Теперь цифры запроса
# сравниваются с ЦИФРАМИ номеров компании (по последним 10, короткий запрос – по хвосту).
# Город и населённый пункт – из адреса, региона и исходного региона; ФИО – из контактов.
_POISK_NOMER_SIMVOLY = re.compile(r"^[\d\s+()\-.]+$")
_NOMER_V_TEKSTE = re.compile(r"\+?\d[\d\s\-()]{8,18}\d")
_POLYA_NOMEROV = ("lpr_kratko", "telefony_predpriyatiya", "telefony_iz_bazy",
                  "nomera_bez_vladelca", "telefony_checko")
_POLYA_POISKA = ("adres", "region", "region_ishodnyy", "direktor", "lpr_kratko", "lpr_roli",
                 "predpriyatie", "holding", "segment", "otrasl")


def _klyuch_nomera(cifry: str) -> str:
    if len(cifry) == 11 and cifry[0] in "78":
        return cifry[1:]
    if len(cifry) == 10:
        return cifry
    return ""


def _klyuchi_iz_teksta(tekst) -> set:
    out = set()
    for m in _NOMER_V_TEKSTE.finditer(str(tekst or "")):
        k = _klyuch_nomera(re.sub(r"\D", "", m.group(0)))
        if k:
            out.add(k)
    return out


def _norm_poiska(s) -> str:
    return str(s or "").casefold().replace("ё", "е")


def _poisk_razobrat(syroe) -> dict:
    q = " ".join(str(syroe or "").split())
    cifry = re.sub(r"\D", "", q)
    nomer = bool(q) and bool(_POISK_NOMER_SIMVOLY.match(q)) and len(cifry) >= 5
    qn = _norm_poiska(q)
    return {"q": qn, "slova": [s for s in re.split(r"[\s,;]+", qn) if s], "nomer": nomer,
            "cifry": cifry, "hvost": (_klyuch_nomera(cifry) or cifry[-10:]) if nomer else "",
            "indeks": None}


def _indeks_poiska() -> dict:
    """ИНН -> ключи номеров (10 цифр) и имена людей: контакты и люди каталога, номера ЛПР от
    продавцов. Строится на запрос с поиском (каталог читается без кэша, как и вся панель)."""
    nomera: dict = {}
    imena: dict = {}

    def dobavit(inn, nomer_txt, *slova):
        inn = sales.normalize_inn(inn)
        if not inn:
            return
        k = _klyuchi_iz_teksta(nomer_txt)
        if k:
            nomera.setdefault(inn, set()).update(k)
        t = " ".join(str(s or "") for s in slova).strip()
        if t:
            imena[inn] = imena.get(inn, "") + " " + _norm_poiska(t)
    try:
        kc = catalog.connect()
        try:
            if catalog.table_exists(kc, "contact"):
                for r in kc.execute("SELECT * FROM contact"):
                    d = dict(r)
                    dobavit(d.get("inn"), d.get("value") if str(d.get("kind") or "phone").lower() == "phone" else "",
                            d.get("person"), d.get("position"))
            if catalog.table_exists(kc, "person"):
                for r in kc.execute("SELECT * FROM person"):
                    d = dict(r)
                    dobavit(d.get("inn"), d.get("phone"), d.get("person"), d.get("position"))
        finally:
            kc.close()
    except Exception:  # noqa: BLE001 – каталог недоступен: ищем по полям компании
        pass
    try:
        with sales.connect() as conn:
            for r in conn.execute("SELECT inn, nomer, fio, dolzhnost FROM zvonok_sobytie WHERE vid='lpr_nomer'"):
                dobavit(r[0], r[1], r[2], r[3])
    except Exception:  # noqa: BLE001 – таблицы ещё нет
        pass
    return {"nomera": nomera, "imena": imena}


def _poisk_nomer_sovpal(company: dict, poisk: dict) -> bool:
    inn = str(company.get("inn") or "")
    cifry = poisk["cifry"]
    if inn and (inn == cifry or cifry in inn):
        return True
    if poisk["indeks"] is None:
        poisk["indeks"] = _indeks_poiska()
    klyuchi = set(poisk["indeks"]["nomera"].get(inn, ()))
    for pole in _POLYA_NOMEROV:
        klyuchi |= _klyuchi_iz_teksta(company.get(pole))
    klyuchi.discard(inn)
    if any(k.endswith(poisk["hvost"]) for k in klyuchi):
        return True
    return bool(poisk["q"]) and poisk["q"] in _norm_poiska(company.get("search_blob"))


def _poisk_tekst_sovpal(company: dict, poisk: dict) -> bool:
    blob = _norm_poiska(company.get("search_blob"))
    if not blob:
        blob = _norm_poiska(" ".join(str(v or "") for v in company.values()))
    if poisk["q"] in blob:
        return True                          # как раньше: запрос целиком в search_blob
    if poisk["indeks"] is None:
        poisk["indeks"] = _indeks_poiska()
    stog = " ".join([blob] + [_norm_poiska(company.get(p)) for p in _POLYA_POISKA]
                    + [poisk["indeks"]["imena"].get(str(company.get("inn") or ""), "")])
    return all(s in stog for s in poisk["slova"])


# ---------------------------------------------------------------- фильтры E1 (координатор)
# Пометка очереди (pometka_ocheredi: «нецелевая: …» / «недействующая: …»), действующий клиент
# сервисного центра (bitrix_klient_sc) и сегмент по доп. ОКВЭД (segment_dop) – колонки
# каталога от агента E1. Нет колонки – фильтра в форме нет.
_POMETKI = (("necel", "нецелевые"), ("nedeyst", "недействующие"),
            ("est", "любая пометка"), ("bez", "без пометки"))


def _segmenty(company: dict, s_dop: bool = False) -> list:
    out = [s.strip() for s in str(company.get("segment") or "").split("|") if s.strip()]
    if s_dop:
        out += [s.strip() for s in re.split(r"[|;]", str(company.get("segment_dop") or "")) if s.strip()]
    return out


def _pometka_sovpala(company: dict, znach: str) -> bool:
    p = str(company.get("pometka_ocheredi") or "").strip().casefold()
    if znach == "necel":
        return "нецелев" in p
    if znach == "nedeyst":
        return "недейств" in p
    if znach == "est":
        return bool(p)
    if znach == "bez":
        return not p
    return True


def _klient_sc(company: dict) -> bool:
    return str(company.get("bitrix_klient_sc") or "").strip() not in ("", "0", "0.0", "None")


def _kolonki_kataloga() -> set:
    try:
        kc = catalog.connect()
        try:
            return catalog.table_columns(kc, "company")
        finally:
            kc.close()
    except Exception:  # noqa: BLE001
        return set()


def _dop_vybor_filtrov(choices: dict, vidimye: list, params) -> None:
    kol = _kolonki_kataloga()
    choices["pometka_est"] = "pometka_ocheredi" in kol
    choices["klient_sc_est"] = "bitrix_klient_sc" in kol
    choices["segment_dop_est"] = "segment_dop" in kol
    choices["pometka_vybor"] = [(k, nz, sum(1 for c in vidimye if _pometka_sovpala(c, k)))
                                for k, nz in _POMETKI]
    choices["klient_sc_n"] = sum(1 for c in vidimye if _klient_sc(c))
    if params.get("segment_dop") == "1" and choices["segment_dop_est"]:
        sch: dict = {}
        for c in vidimye:
            for s in set(_segmenty(c, True)):
                sch[s] = sch.get(s, 0) + 1
        choices["segment"] = sorted(sch.items())


# ---------------------------------------------------------------- 2. события звонка
_SOB_DEYSTVIYA = ("ne_dozvonilsya", "lpr_nomer")
_SOB_NAZV = {"ne_dozvonilsya": "Не дозвонился", "lpr_nomer": "Получен личный номер ЛПР"}
_SOB_FILTR = {"ne_dozvonilsya": "popytok", "lpr_nomer": "lpr_poluchen"}
_LPR_DOLZHNOSTI = ("генеральный директор", "директор", "технический директор", "главный инженер",
                   "главный механик", "главный энергетик", "директор по производству",
                   "начальник производства", "главный технолог", "начальник отдела снабжения",
                   "коммерческий директор")


def _sobytiya_zvonka(conn, ot=None, do=None, inn=None) -> list:
    """События «не дозвонился» / «номер ЛПР» за период [ot, do] (дни по Москве)."""
    try:
        if inn:
            rows = conn.execute("SELECT * FROM zvonok_sobytie WHERE inn=? ORDER BY created_at, id",
                                (inn,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM zvonok_sobytie ORDER BY created_at, id").fetchall()
    except Exception:  # noqa: BLE001 – таблицы ещё нет
        return []
    out = []
    for r in rows:
        d = dict(r)
        kogda = _msk_vremya(d.get("created_at"))
        if kogda is None:
            continue
        if (ot and kogda.date() < ot) or (do and kogda.date() > do):
            continue
        d["inn"] = str(d.get("inn") or "")
        d["kogda"], d["den"] = kogda, kogda.date()
        d["kto"] = d.get("state_user") or d.get("username") or ""
        out.append(d)
    return out


def _prikrepit_sobytiya(companies: list) -> None:
    """К строкам списка: попыток «не дозвонился», последняя, получено номеров ЛПР."""
    po: dict = {}
    try:
        with sales.connect() as conn:
            for z in _sobytiya_zvonka(conn):
                s = po.setdefault(z["inn"], {"popytok": 0, "lpr": 0, "posled": None})
                if z["vid"] == "ne_dozvonilsya":
                    s["popytok"] += 1
                    s["posled"] = z["kogda"]
                elif z["vid"] == "lpr_nomer":
                    s["lpr"] += 1
    except Exception:  # noqa: BLE001
        po = {}
    for c in companies:
        s = po.get(str(c.get("inn") or ""))
        c["popytok"] = s["popytok"] if s else 0
        c["lpr_poluchen"] = s["lpr"] if s else 0
        c["popytka_posled"] = s["posled"].strftime("%d.%m %H:%M") if s and s["posled"] else ""


def _kartochka_sobytiya(inn: str) -> dict:
    out = {"popytok": 0, "posled_popytka": "", "posled_kto": "", "lpr": []}
    try:
        with sales.connect() as conn:
            for z in _sobytiya_zvonka(conn, inn=inn):
                if z["vid"] == "ne_dozvonilsya":
                    out["popytok"] += 1
                    out["posled_popytka"] = z["kogda"].strftime("%d.%m.%Y %H:%M")
                    out["posled_kto"] = z.get("username") or ""
                elif z["vid"] == "lpr_nomer":
                    out["lpr"].append({
                        "fio": z.get("fio") or "", "dolzhnost": z.get("dolzhnost") or "",
                        "nomer": sales.nomer_pokaz(z.get("nomer")) + (" доб. " + z["dob"] if z.get("dob") else ""),
                        "href": "tel:" + str(z.get("nomer") or "") + ("," + z["dob"] if z.get("dob") else ""),
                        "kto": z.get("username") or "", "kogda": z["kogda"].strftime("%d.%m.%Y %H:%M"),
                        "katalog": z.get("katalog_itog") or ""})
    except Exception:  # noqa: BLE001
        pass
    return out


# Роль контакта по должности, которую назвал продавец, – словами каталога (contact.role).
_ROLI_PO_DOLZHNOSTI = (
    (r"техническ\w*\s+директор|техдиректор|директор\w*\s+по\s+техн", "технический директор", 1, 0),
    (r"главн\w*\s+инженер|гл\.?\s*инженер", "главный инженер", 1, 0),
    (r"главн\w*\s+механик|гл\.?\s*механик", "главный механик", 1, 0),
    (r"главн\w*\s+энергетик|гл\.?\s*энергетик", "главный энергетик", 1, 0),
    (r"производств", "производство", 1, 0),
    (r"главн\w*\s+технолог|гл\.?\s*технолог", "главный технолог", 0, 0),
    (r"коммерческ\w*\s+директор|директор\w*\s+по\s+(?:продаж|коммерц)", "коммерческий директор", 0, 0),
    (r"снабжен|закупк|\bмто\b|материально", "закупки", 0, 1),
    (r"директор|руководител|председател|управляющ|собственник|владел|учредител|президент|глава",
     "директор/руководитель", 0, 0),
)


def _rol_po_dolzhnosti(dolzhnost) -> tuple:
    t = _norm_poiska(dolzhnost)
    for rx, rol, tech, zak in _ROLI_PO_DOLZHNOSTI:
        if re.search(rx, t):
            return rol, tech, zak
    return "ЛПР со слов продавца", 0, 0


def _familiya_b(person) -> str:
    s = re.sub(r"[^А-Яа-яЁёA-Za-z\s.-]", " ", str(person or "")).split()
    return s[0].lower().strip(".-") if s else ""


def _lpr_v_katalog(z: dict, user: dict) -> tuple:
    """Личный номер ЛПР от продавца – строкой в каталог (contact): источник «от продавца»,
    роль по должности, вид номера. Повтор той же записи не дублируется."""
    import sqlite3 as _sq_b
    put = catalog.db_path()
    if not put.exists():
        return None, "каталог недоступен – номер сохранён только в базе продаж"
    rol, tech, zak = _rol_po_dolzhnosti(z.get("dolzhnost"))
    den = (_msk_vremya(z.get("created_at")) or datetime.datetime.utcnow()).strftime("%d.%m.%Y")
    stroka = {
        "inn": z["inn"], "value": z["nomer"] + (" доб. " + z["dob"] if z.get("dob") else ""),
        "kind": "phone", "person": z.get("fio") or None, "role": rol,
        "position": z.get("dolzhnost") or None,
        "phone_type": ("мобильный" if z["nomer_10"].startswith("9")
                       else ("рабочий с добавочным" if z.get("dob") else "рабочий")),
        "source": "от продавца: %s, %s · личный номер ЛПР со слов продавца"
                  % (_fio_dlya_shablona(user["username"]), den),
        "source_url": None, "is_purchaser": zak, "is_tech": tech, "has_role": 1,
        "is_unknown_owner": 0, "istochniki": "от продавца", "istochnikov": 1}
    for popytka in range(4):
        try:
            kc = _sq_b.connect(str(put), timeout=20)
            try:
                kol = {r[1] for r in kc.execute("PRAGMA table_info(contact)")}
                if not kol:
                    return None, "в каталоге нет таблицы contact"
                for r in kc.execute("SELECT id, value, person, source FROM contact WHERE inn=? AND kind='phone'",
                                    (z["inn"],)):
                    if (str(r[3] or "").startswith("от продавца") and z["nomer_10"] in _klyuchi_iz_teksta(r[1])
                            and _familiya_b(r[2]) == _familiya_b(z.get("fio"))):
                        return r[0], "уже был в контактах (от продавца)"
                polya = [k for k in stroka if k in kol]
                cur = kc.execute("INSERT INTO contact(%s) VALUES(%s)" % (",".join(polya), ",".join("?" * len(polya))),
                                 [stroka[k] for k in polya])
                kc.commit()
                return cur.lastrowid, "добавлен в контакты компании"
            finally:
                kc.close()
        except _sq_b.OperationalError as exc:
            if "locked" in str(exc).lower() and popytka < 3:
                time.sleep(1.5)
                continue
            return None, "в каталог не добавлен (%s) – номер сохранён в базе продаж" % str(exc)[:80]
    return None, "каталог занят – номер сохранён в базе продаж"


def _sohranit_sobytie(user, inn, vid, comment, next_contact_at, return_query, fio, dolzhnost, nomer):
    try:
        z = sales.zapisat_sobytie(user, inn, vid, comment=comment, next_contact=next_contact_at,
                                  fio=fio, dolzhnost=dolzhnost, nomer=nomer)
    except PermissionError:
        raise HTTPException(404, "Компания не назначена пользователю")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if vid == "lpr_nomer" and not z.get("povtor"):
        cid, itog = _lpr_v_katalog(z, user)
        try:
            sales.otmetit_katalog(z["id"], cid, itog)
        except Exception:  # noqa: BLE001 – пометка о каталоге не важнее самого номера
            pass
    suffix = f"?{return_query}" if return_query else ""
    return RedirectResponse(f"{BP}/centro{suffix}", 303)


def _tekst_bez_prichiny(body, prichina) -> str:
    s = str(body or "")
    nachalo = "Причина: %s" % prichina
    if prichina and s.startswith(nachalo):
        return s[len(nachalo):].lstrip(".").strip()
    return _razbor_kommentariya(s)["tekst"]


# ---------------------------------------------------------------- 4. фильтры и период директора
def _dir_params_norm(params) -> tuple:
    """Параметры директора словарём; «с» позже «по» – даты переставляются (и это говорится)."""
    p = {k: params.get(k) for k in params.keys()}
    ot, do = _data_param(p.get("ot")), _data_param(p.get("do"))
    if ot and do and ot > do:
        p["ot"], p["do"] = do.isoformat(), ot.isoformat()
        return p, True
    return p, False


def _direktor_predikat_v2(params):
    p, _ = _dir_params_norm(params)
    sob = (p.get("sob") or "").strip()
    if sob not in _SOB_NAZV:
        return _direktor_predikat(p)
    ot, do = _data_param(p.get("ot")), _data_param(p.get("do"))
    kto_p = (p.get("kto_p") or "").strip()
    with sales.connect() as conn:
        inns = {z["inn"] for z in _sobytiya_zvonka(conn, ot, do)
                if z["vid"] == sob and (not kto_p or z["kto"] == kto_p)}
    ost = {k: v for k, v in p.items() if k not in ("ot", "do", "kto_p", "rez_p", "sob")}
    staryy = _direktor_predikat(ost)

    def pred(company) -> bool:
        if str(company.get("inn") or "") not in inns:
            return False
        return staryy is None or staryy(company)
    return pred


def _dir_opis_v2(params) -> str:
    p, perevernuty = _dir_params_norm(params)
    sob = (p.get("sob") or "").strip()
    chasti = []
    if sob in _SOB_NAZV:
        ot, do = _data_param(p.get("ot")), _data_param(p.get("do"))
        chasti.append("«%s»%s" % (_SOB_NAZV[sob], (" " + _period_ru(ot, do)) if (ot or do) else ""))
        if p.get("kto_p"):
            chasti.append("продавец: " + _fio_dlya_shablona(p.get("kto_p")))
        p = {k: v for k, v in p.items() if k not in ("ot", "do", "kto_p", "rez_p")}
    staroe = _dir_opis(p)
    if staroe:
        chasti.append(staroe)
    if perevernuty:
        chasti.append("дата «с» была позже «по» – даты переставлены")
    return " · ".join(chasti)


def _pervyy_den_dannyh():
    dni = []
    try:
        with sales.connect() as conn:
            for sql in ("SELECT MIN(created_at) FROM activity_log",
                        "SELECT MIN(created_at) FROM zvonok_sobytie",
                        "SELECT MIN(assigned_at) FROM company_assignment"):
                try:
                    v = conn.execute(sql).fetchone()[0]
                except Exception:  # noqa: BLE001
                    v = None
                m = _msk_vremya(v)
                if m:
                    dni.append(m.date())
    except Exception:  # noqa: BLE001
        pass
    return min(dni) if dni else None


def _proverit_period(params, den, ot) -> dict:
    """Период статистики: перевёрнутые, будущие и нераспознанные даты – с явным сообщением,
    а не молчаливой подменой. stat_vse=1 – «всё время»: с первого дня данных по сегодня."""
    segodnya = _segodnya_msk()
    f = "%d.%m.%Y"
    soobshch = []
    syroe_do = (params.get("stat_data") or "").strip()
    syroe_ot = (params.get("stat_ot") or "").strip()
    if params.get("stat_vse") == "1":
        pervyy = _pervyy_den_dannyh() or segodnya
        return {"ot": min(pervyy, segodnya), "do": segodnya, "vse": True,
                "ot_param": "", "do_param": "", "soobshcheniya": soobshch}
    if syroe_do and den is None:
        soobshch.append("Дата «по» не распознана («%s») – взят сегодняшний день." % syroe_do[:20])
    if syroe_ot and ot is None:
        soobshch.append("Дата «с» не распознана («%s») – показан один день." % syroe_ot[:20])
    if den and den > segodnya:
        soobshch.append("Дата «по» %s ещё не наступила – показано по сегодня, %s."
                        % (den.strftime(f), segodnya.strftime(f)))
        den = segodnya
    if ot and ot > segodnya:
        soobshch.append("Дата «с» %s ещё не наступила – взят сегодняшний день." % ot.strftime(f))
        ot = segodnya
    do_f = den or segodnya
    if ot and ot > do_f:
        soobshch.append("Дата «с» (%s) позже даты «по» (%s) – даты переставлены: показано с %s по %s."
                        % (ot.strftime(f), do_f.strftime(f), do_f.strftime(f), ot.strftime(f)))
        ot, den = do_f, ot
    return {"ot": ot, "do": den, "vse": False,
            "ot_param": ot.isoformat() if ot else "",
            "do_param": den.isoformat() if (den and (syroe_do or den != segodnya)) else "",
            "soobshcheniya": soobshch}


def _svodka_sobytiy(conn, ot, do, kto: str) -> dict:
    """Личные номера ЛПР и «не дозвонился» по продавцам и дням за [ot, do]. Засчитывается
    продавцу, за которым компания (как отметки). Компании – те, что открываются списком."""
    vidimye: set = set()
    try:
        kc = catalog.connect()
        try:
            vidimye = {sales.normalize_inn(r[0]) for r in kc.execute("SELECT inn FROM company")}
        finally:
            kc.close()
    except Exception:  # noqa: BLE001
        pass
    vidimye -= {str(r[0]) for r in conn.execute("SELECT inn FROM hidden_item WHERE kind='company'")}
    lyudi = {r["username"]: dict(r) for r in conn.execute("SELECT username, role, is_active FROM users")}
    prodavcy = sorted((u for u, r in lyudi.items() if r["role"] == "sales" and r["is_active"]),
                      key=lambda u: _fio_dlya_shablona(u).lower())
    if kto:
        prodavcy = [kto]
    per = {"ot": ot.isoformat(), "do": do.isoformat()}

    def pusto():
        return {"lpr": 0, "lpr_inn": set(), "nedozvon": 0, "ned_inn": set(), "dni": set(), "posled": None}
    po = {u: pusto() for u in prodavcy}
    dni: dict = {}
    for z in _sobytiya_zvonka(conn, ot, do):
        u = z["kto"]
        if kto and u != kto:
            continue
        if z["vid"] not in _SOB_NAZV:
            continue
        s = po.setdefault(u, pusto())
        dd = dni.setdefault(z["den"], {}).setdefault(u, {"lpr": 0, "nedozvon": 0})
        if z["vid"] == "lpr_nomer":
            s["lpr"] += 1
            dd["lpr"] += 1
            if z["inn"] in vidimye:
                s["lpr_inn"].add(z["inn"])
        else:
            s["nedozvon"] += 1
            dd["nedozvon"] += 1
            if z["inn"] in vidimye:
                s["ned_inn"].add(z["inn"])
        s["dni"].add(z["den"])
        if s["posled"] is None or z["kogda"] > s["posled"]:
            s["posled"] = z["kogda"]
    poryadok = prodavcy + sorted((u for u in po if u not in prodavcy), key=lambda u: _fio_dlya_shablona(u).lower())

    def yach(n, vid, u):
        k = {"kto_p": u} if u else {}
        return {"n": n, "url": _ssylka_spiska(**per, sob=vid, **k) if n else ""}

    def stroka(u, s, itog=False):
        uu = (kto or "") if itog else u
        return {"kto": u, "itog": itog, "lpr": s["lpr"],
                "lpr_komp": yach(len(s["lpr_inn"]), "lpr_nomer", uu),
                "nedozvon": s["nedozvon"], "nedozvon_komp": yach(len(s["ned_inn"]), "ne_dozvonilsya", uu),
                "dney": len(s["dni"]), "posled": s["posled"].strftime("%d.%m %H:%M") if s["posled"] else ""}
    stroki = [stroka(u, po[u]) for u in poryadok]
    itog = pusto()
    for u in poryadok:
        s = po[u]
        itog["lpr"] += s["lpr"]
        itog["nedozvon"] += s["nedozvon"]
        itog["lpr_inn"] |= s["lpr_inn"]
        itog["ned_inn"] |= s["ned_inn"]
        itog["dni"] |= s["dni"]
        if s["posled"] and (itog["posled"] is None or s["posled"] > itog["posled"]):
            itog["posled"] = s["posled"]
    it = stroka("", itog, itog=True)
    if len(poryadok) > 1:
        stroki.append(it)
    po_dnyam = []
    for den in sorted(dni, reverse=True)[:62]:
        yy = [dni[den].get(u, {"lpr": 0, "nedozvon": 0}) for u in poryadok]
        po_dnyam.append({"den_ru": den.strftime("%d.%m.%Y"), "yach": yy,
                         "lpr": sum(y["lpr"] for y in yy), "nedozvon": sum(y["nedozvon"] for y in yy)})
    return {"stroki": stroki, "itog": it, "po_dnyam": po_dnyam, "kolonki": poryadok}


def _obshchee_sobytiya(conn) -> dict:
    try:
        lpr = conn.execute("SELECT COUNT(*), COUNT(DISTINCT inn) FROM zvonok_sobytie WHERE vid='lpr_nomer'").fetchone()
        ned = conn.execute("SELECT COUNT(*) FROM zvonok_sobytie WHERE vid='ne_dozvonilsya'").fetchone()
        return {"lpr_vsego": lpr[0] or 0, "lpr_kompaniy": lpr[1] or 0, "nedozvon_vsego": ned[0] or 0}
    except Exception:  # noqa: BLE001
        return {"lpr_vsego": 0, "lpr_kompaniy": 0, "nedozvon_vsego": 0}


# ---------------------------------------------------------------- 5. сортировка и выгрузка
_SORT_VYBOR = [
    ("", "порядок очереди (как у продавца)"),
    ("ball", "балл очереди: больше – выше"),
    ("vyruchka", "выручка: больше – выше"),
    ("region", "регион: А → Я"),
    ("mestnoe", "местное время: восток → запад"),
    ("seychas", "кому звонить сейчас (рабочий час у компании)"),
]


def _chas_poyas_b(company) -> int:
    try:
        return int(company.get("chas_poyas"))
    except (TypeError, ValueError):
        return 3


def _minut_do_raboty(company) -> int:
    """0 – у компании сейчас рабочее время (как фильтр «Сейчас рабочее время»), иначе –
    сколько минут до 9:00 ближайшего буднего дня по её местному времени."""
    if _rabochee_vremya(company):
        return 0
    mest = datetime.datetime.utcnow() + datetime.timedelta(hours=_chas_poyas_b(company))
    sled = mest.replace(hour=9, minute=0, second=0, microsecond=0)
    if mest >= sled:
        sled += datetime.timedelta(days=1)
    while sled.weekday() >= 5:
        sled += datetime.timedelta(days=1)
    return int((sled - mest).total_seconds() // 60)


def _sortirovat_dir(spisok: list, sort: str) -> None:
    """Сортировка по колонке – поверх порядка очереди (он остаётся вторичным ключом).
    Без параметра – ничего не меняется."""
    sort = (sort or "").strip()
    if sort == "ball":
        spisok.sort(key=lambda c: -float(c.get("assignment_score") or 0))
    elif sort == "vyruchka":
        def kl(c):
            v = _company_number(c, "vyruchka_rub", "revenue_num", "revenue")
            return (v is None, -(v or 0))
        spisok.sort(key=kl)
    elif sort == "region":
        spisok.sort(key=lambda c: (not str(c.get("region") or "").strip(),
                                   str(c.get("region") or "").casefold()))
    elif sort == "mestnoe":
        spisok.sort(key=lambda c: -_chas_poyas_b(c))
    elif sort == "seychas":
        spisok.sort(key=_minut_do_raboty)


def _mestnoe_vremya(company) -> str:
    ch = _chas_poyas_b(company)
    t = (datetime.datetime.utcnow() + datetime.timedelta(hours=ch)).strftime("%H:%M")
    return "%s (МСК%s)" % (t, ("%+d" % (ch - 3)) if ch != 3 else "")


def _dop_kontekst(request, user, chosen, sales_users, vidimye) -> dict:
    """Что нужно шаблону сверх прежнего: меню результатов (+ новые), фильтр «Результат звонка»
    (только то, что продавец может поставить, + новые; старый статус – если он есть в данных),
    сортировка, продавцы по ФИО, попытки и номера ЛПР в карточке."""
    menu = dict(sales.CALL_RESULT_CHOICES)
    menu.update(sales.SOBYTIYA_ZVONKA)
    filtr = [("new", sales.CALL_RESULT_LABELS.get("new", "Новый"))] + list(sales.CALL_RESULT_CHOICES.items())
    filtr += [("ne_dozvonilsya", "Не дозвонился (были попытки)"), ("lpr_nomer", "Получен личный номер ЛПР")]
    est = {str(c.get("call_result") or "") for c in vidimye} - {k for k, _ in filtr} - {""}
    filtr += [(k, sales.CALL_RESULT_LABELS.get(k, k) + " – старый статус") for k in sorted(est)]
    sort_tek = (request.query_params.get("sort") or "").strip()
    if sort_tek not in dict(_SORT_VYBOR):
        sort_tek = ""
    return {
        "call_menu": menu,
        "call_filtr": filtr,
        "sort_vybor": _SORT_VYBOR,
        "sort_tek": sort_tek,
        "poryadok_opis": dict(_SORT_VYBOR)[sort_tek] if sort_tek else "",
        "sales_users": sorted(sales_users, key=lambda u: _fio_dlya_shablona(u).lower()),
        "dop_kartochka": _kartochka_sobytiya(chosen["inn"]) if chosen else None,
        "lpr_dolzhnosti": _LPR_DOLZHNOSTI,
    }


def _spisok_dlya_vygruzki(request, user) -> list:
    """Тот же отбор и порядок, что список на экране (без записи назначений)."""
    try:
        companies, _v, _i = _source_companies()
    except catalog.CentroDbUnavailable:
        companies = []
    with sales.connect() as conn:
        assignments = {row["inn"]: dict(row) for row in conn.execute("SELECT * FROM company_assignment")}
        states = {(row["inn"], row["username"]): dict(row) for row in conn.execute("SELECT * FROM company_state")}
    hidden_co = sales.hidden_companies()
    skrytye = str(request.query_params.get("skrytye") or "0") not in ("", "0")
    if hidden_co and not skrytye:
        companies = [c for c in companies if c["inn"] not in hidden_co]
    elif hidden_co and skrytye:
        companies = [c for c in companies if c["inn"] in hidden_co]
    vladelec = (request.query_params.get("assigned_user") or "").strip() if user["role"] == "admin" else user["username"]
    visible = []
    for sc in companies:
        a = assignments.get(sc["inn"])
        if user["role"] != "admin" and (not a or a["username"] != user["username"]):
            continue
        if vladelec == "__net__":
            if a:
                continue
        elif vladelec and (not a or a["username"] != vladelec):
            continue
        c = dict(sc)
        c["assigned_user"] = a["username"] if a else ""
        c["assignment_score"] = a.get("assignment_score", 0) if a else 0
        if a:
            c.update(states.get((c["inn"], a["username"]), {}))
        visible.append(c)
    _prikrepit_sobytiya(visible)
    visible = _matches(visible, request)
    visible.sort(key=_queue_rank)
    _sortirovat_dir(visible, request.query_params.get("sort", ""))
    return visible


@router.get("/centro/vygruzka.csv")
def vygruzka_csv(request: Request, user=Depends(current_user)):
    """Выгрузка текущего отобранного списка директора в CSV (Excel: «;», UTF-8 с BOM).
    Только то, что видно в списке на экране; номера телефонов в комментариях скрыты."""
    if user["role"] != "admin":
        raise HTTPException(403)
    spisok = _spisok_dlya_vygruzki(request, user)
    komm: dict = {}
    with sales.connect() as conn:
        for r in conn.execute("SELECT inn, username, body, created_at FROM company_comment "
                              "ORDER BY created_at DESC, id DESC"):
            komm.setdefault(str(r["inn"]), dict(r))
    buf = _io_b.StringIO()
    w = _csv_b.writer(buf, delimiter=";")
    w.writerow(["№", "Компания", "ИНН", "Регион", "Местное время", "Рабочий час сейчас", "ОКВЭД",
                "Выручка, млн ₽", "Сегмент", "Отрасль", "Роли ЛПР", "Статус", "Причина отказа",
                "Последний контакт", "Перезвонить", "Не дозвонился, попыток",
                "Личных номеров ЛПР получено", "Последний комментарий", "Балл очереди", "Продавец",
                "Базы", "Пометка очереди", "Клиент СЦ"])
    for i, c in enumerate(spisok, 1):
        rez = c.get("call_result") or "new"
        k = komm.get(str(c.get("inn")))
        rk = _razbor_kommentariya(k["body"]) if k else {"prichina": "", "tekst": ""}
        prichina = (c.get("prichina") or rk["prichina"]) if rez == "ne_ponravilas" else ""
        tekst = _NOMER_V_TEKSTE.sub("[номер]", rk["tekst"] or "")
        vyr = _company_number(c, "vyruchka_rub", "revenue_num", "revenue")
        w.writerow([
            i, c.get("predpriyatie") or c.get("name_short") or "", c.get("inn") or "", c.get("region") or "",
            _mestnoe_vremya(c), "да" if _rabochee_vremya(c) else "нет", c.get("okved") or "",
            ("%.1f" % (vyr / 1e6)).replace(".", ",") if vyr is not None else "",
            str(c.get("segment") or "").replace(" | ", ", "), c.get("otrasl") or "", c.get("lpr_roli") or "",
            sales.CALL_RESULT_LABELS.get(rez, rez), prichina,
            str(c.get("last_contact_at") or "")[:16].replace("T", " "),
            str(c.get("next_contact_at") or "")[:16].replace("T", " "),
            c.get("popytok") or 0, c.get("lpr_poluchen") or 0,
            (tekst[:117] + "…") if len(tekst) > 120 else tekst,
            ("%.1f" % float(c.get("assignment_score") or 0)).replace(".", ","),
            _fio_dlya_shablona(c.get("assigned_user")) if c.get("assigned_user") else "",
            str(c.get("bazy") or "").replace(" | ", ", "), c.get("pometka_ocheredi") or "",
            "да" if _klient_sc(c) else ""])
    imya = "meyer-spisok-%s.csv" % (datetime.datetime.utcnow() + _MSK_DIR).strftime("%Y%m%d-%H%M")
    return _Response_b(content=("\ufeff" + buf.getvalue()).encode("utf-8"),
                       media_type="text/csv; charset=utf-8",
                       headers={"Content-Disposition": 'attachment; filename="%s"' % imya})
'''

# =========================================================================== шаблоны (вставки)
ST_BLOK = r'''  {# ======== fixB (08.10): цель владельца – личные номера ЛПР; «не дозвонился» – попытка без исхода #}
  {% set sd = sobytiya_dir %}
  {% if sd %}
  <h2 id="lpr-nomera">Личные номера ЛПР и недозвоны <span class="period-metka">{{ d.period_ru }}</span></h2>
  <div class="stat-setka">
    <div class="plitka plitka-cel"><b>{{ sd.itog.lpr }}</b><span>личных номеров ЛПР получено</span></div>
    <div class="plitka"><b>{{ ch(sd.itog.lpr_komp) }}</b><span>компаний, где получен номер ЛПР</span></div>
    <div class="plitka"><b>{{ sd.itog.nedozvon }}</b><span>попыток «не дозвонился»</span></div>
    <div class="plitka"><b>{{ ch(sd.itog.nedozvon_komp) }}</b><span>компаний с недозвоном</span></div>
  </div>
  <p class="pometka">«Получен личный номер ЛПР» – продавец вписал ФИО, должность и номер; номер добавлен в контакты компании с пометкой «от продавца». «Не дозвонился» – попытка без исхода, компания осталась в очереди. Засчитывается продавцу, за которым компания (как и отметки). Число компаний открывает их списком.</p>
  <div style="overflow-x:auto"><table class="stat">
    <thead><tr><th>Продавец</th><th>Личных номеров ЛПР</th><th>в компаниях</th><th>Не дозвонился, попыток</th><th>в компаниях</th><th>Дней с такими звонками</th><th>Последний</th></tr></thead>
    <tbody>
    {% for s in sd.stroki %}
      <tr{% if s.itog %} class="itog"{% endif %}><td>{% if s.itog %}Все продавцы{% else %}{{ s.kto|fio }}{% endif %}</td><td><b>{{ s.lpr }}</b></td><td>{{ ch(s.lpr_komp) }}</td><td>{{ s.nedozvon }}</td><td>{{ ch(s.nedozvon_komp) }}</td><td>{{ s.dney }}</td><td>{{ s.posled or '–' }}</td></tr>
    {% else %}<tr><td colspan="7">Продавцов нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>
  {% if sd.po_dnyam %}
  <h3>По дням <span class="period-metka">номеров ЛПР / попыток «не дозвонился»</span></h3>
  <div style="overflow-x:auto"><table class="stat">
    <thead><tr><th>День</th>{% for u in sd.kolonki %}<th>{{ u|fio }}</th>{% endfor %}<th>Всего</th></tr></thead>
    <tbody>
    {% for dn in sd.po_dnyam %}
      <tr><td style="white-space:nowrap">{{ dn.den_ru }}</td>{% for y in dn.yach %}<td>{% if y.lpr or y.nedozvon %}{{ y.lpr }} / {{ y.nedozvon }}{% else %}–{% endif %}</td>{% endfor %}<td><b>{{ dn.lpr }}</b> / {{ dn.nedozvon }}</td></tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% endif %}
  {% endif %}

'''

C_KARTOCHKA_NACHALO = r'''  <section class="card work-card">
    {# fixB: попытки «не дозвонился» и личные номера ЛПР от продавцов по этой компании #}
    {% if dop_kartochka and (dop_kartochka.popytok or dop_kartochka.lpr) %}
    <div class="zv-sobytiya">
      {% if dop_kartochka.popytok %}<p><b>Не дозвонились:</b> попыток: {{ dop_kartochka.popytok }}, последняя {{ dop_kartochka.posled_popytka }}{% if dop_kartochka.posled_kto %} ({{ dop_kartochka.posled_kto|fio }}){% endif %}</p>{% endif %}
      {% for l in dop_kartochka.lpr %}<p><b>Личный номер ЛПР</b> ({{ l.kto|fio }}, {{ l.kogda }}): {{ l.fio or 'ФИО не названо' }}{% if l.dolzhnost %}, {{ l.dolzhnost }}{% endif %} – <a href="{{ l.href }}">{{ l.nomer }}</a>{% if l.katalog %} <span class="zv-tiho">· {{ l.katalog }}</span>{% endif %}</p>{% endfor %}
    </div>
    {% endif %}
    {# fixB: директор не звонит – форма продавца у него свёрнута, но на месте #}
    {% if user.role == 'admin' %}<details class="dir-forma"><summary>Отметить звонок за продавца{% if company.assigned_user %} ({{ company.assigned_user|fio }}){% endif %} – форма продавца</summary>{% endif %}
    <form method="post" action="{{ base_path }}/centro/save" class="work-form">'''

C_LPR_POLYA = r'''        </div>
      </div>
      {# fixB: «Получен личный номер ЛПР» – ФИО, должность, номер (номер уйдёт в контакты компании) #}
      <div class="lpr-polya" hidden>
        <label>ФИО ЛПР<input name="lpr_fio" maxlength="150" autocomplete="off" placeholder="Иванов Иван Иванович"></label>
        <label>Должность<input name="lpr_dolzhnost" maxlength="150" list="lpr-dolzhnosti" autocomplete="off" placeholder="главный инженер"></label>
        <datalist id="lpr-dolzhnosti">{% for d in (lpr_dolzhnosti or []) %}<option value="{{ d }}">{% endfor %}</datalist>
        <label>Личный номер<input name="lpr_nomer" type="tel" maxlength="40" autocomplete="off" placeholder="+7 900 000-00-00"></label>
      </div>
      <p class="rez-podskazka"></p>
      <style>
      .work-form{grid-auto-flow:row dense}
      .lpr-polya{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;
        background:#f2f8f4;border:1px solid #bfe3d2;border-radius:6px;padding:10px}
      .lpr-polya[hidden]{display:none}
      .lpr-polya input.oshibka{border-color:#b3261e;box-shadow:0 0 0 2px #b3261e22}
      .rez-podskazka{grid-column:1/-1;margin:0;font-size:12px;color:var(--muted)}
      .rez-podskazka:empty{display:none}
      @media(max-width:760px){.lpr-polya{grid-template-columns:1fr}}
      </style>
      <style>
      .rez-pole{display:grid;gap:4px;font-size:13px;color:var(--muted)}'''

C_LPR_JS = r'''      })();
      </script>
      <script>
      /* fixB: поля ЛПР – только для «Получен личный номер ЛПР»; номер (10 цифр) и должность
         или ФИО обязательны. Подсказка под результатом – что произойдёт с компанией. */
      (function () {
        var forma = document.querySelector('form.work-form');
        if (!forma) return;
        var pole = forma.querySelector('input[name=call_result]');
        var blok = forma.querySelector('.lpr-polya');
        var podsk = forma.querySelector('.rez-podskazka');
        if (!pole || !blok) return;
        function obnovit() {
          var lpr = pole.value === 'lpr_nomer';
          blok.hidden = !lpr;
          if (podsk) podsk.textContent = pole.value === 'ne_dozvonilsya'
            ? 'Компания останется в очереди, попытка запишется.'
            : (lpr ? 'Номер добавится в контакты компании с пометкой «от продавца»; компания останется в очереди.' : '');
        }
        forma.querySelectorAll('.rez-punkt[data-value]').forEach(function (p) { p.addEventListener('click', obnovit); });
        obnovit();
        forma.addEventListener('submit', function (e) {
          if (pole.value !== 'lpr_nomer') return;
          var n = forma.querySelector('input[name=lpr_nomer]');
          var d = forma.querySelector('input[name=lpr_dolzhnost]');
          var f = forma.querySelector('input[name=lpr_fio]');
          var cifry = (n.value || '').replace(/\D/g, '');
          var plohoNomer = cifry.length < 10 || cifry.length > 15;
          var bezKogo = !((d.value || '').trim() || (f.value || '').trim());
          n.classList.toggle('oshibka', plohoNomer);
          d.classList.toggle('oshibka', bezKogo);
          if (plohoNomer || bezKogo) { e.preventDefault(); blok.hidden = false; (plohoNomer ? n : d).focus(); }
        });
      })();
      </script>
      <label>Следующий контакт<input type="datetime-local"'''

C_DIREKTOR_SORT = r'''    {% for k in ('rez_p', 'kto_p', 'sob') %}{% if request.query_params.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.query_params.get(k) }}">{% endif %}{% endfor %}
    {# fixB: сортировка списка и выгрузка текущего отбора (только у директора) #}
    {% if sort_vybor %}<select name="sort" title="Порядок списка. По умолчанию – как у очереди продавца">{% for v, nz in sort_vybor %}<option value="{{ v }}" {% if sort_tek == v %}selected{% endif %}>{{ 'Порядок: ' ~ nz }}</option>{% endfor %}</select>{% endif %}
    <button type="submit">Показать</button>
    {% if sort_vybor %}<a class="dir-csv" href="{{ base_path }}/centro/vygruzka.csv{% if query_string %}?{{ query_string }}{% endif %}" title="Отобранный сейчас список в том же порядке – файл для Excel. Номера телефонов не выгружаются">Выгрузить CSV · {{ total }}</a>{% endif %}'''

C_STILI = r'''.zv-sobytiya{display:grid;gap:4px;font-size:13px;color:var(--navy);background:#f6f7fb;border-left:3px solid #c7cbe8;border-radius:4px;padding:6px 10px}
.zv-sobytiya p{margin:0}
.zv-tiho{color:var(--muted);font-size:12px}
.dir-forma>summary{cursor:pointer;color:#475467;font-weight:650;margin-bottom:8px}
.dir-forma[open]>summary{margin-bottom:12px}
.dir-csv{color:var(--blue);white-space:nowrap}
.hide-form{display:inline;margin-left:6px}'''

C_FILTRY_DOP = r'''          <label class="check"><input type="checkbox" name="bitrix" value="1" {% if request.query_params.get('bitrix') == '1' %}checked{% endif %}> Есть номер в битриксе · {{ choices.bitrix_n }}</label>
          {% if choices.klient_sc_est %}<label class="check" title="Действующий клиент сервисного центра (сделки Битрикса: гарантия, ПНР, сопровождение)"><input type="checkbox" name="klient_sc" value="1" {% if request.query_params.get('klient_sc') == '1' %}checked{% endif %}> Клиент СЦ · {{ choices.klient_sc_n }}</label>{% endif %}
          {% if choices.segment_dop_est %}<label class="check" title="Сегмент ищется и по дополнительным ОКВЭД, а не только по основному"><input type="checkbox" name="segment_dop" value="1" {% if request.query_params.get('segment_dop') == '1' %}checked{% endif %}> Сегмент: учитывать доп. ОКВЭД</label>{% endif %}'''

C_POMETKA = r'''{% if op %} – {{ op }}{% endif %} · {{ n }}</option>{% endfor %}</select></label>
          {% if choices.pometka_est %}<label title="Пометка очереди: нецелевая (по основному ОКВЭД) или недействующая (ликвидирована, к исключению из ЕГРЮЛ). Такие компании не удаляются">Пометка очереди<select name="pometka_och"><option value="">Любая</option>{% for k, nz, n in choices.pometka_vybor %}<option value="{{ k }}" {% if request.query_params.get('pometka_och') == k %}selected{% endif %}>{{ nz }} · {{ n }}</option>{% endfor %}</select></label>{% endif %}
        </div>'''

SB_SOOBSHCH = r'''      </form>
      {# fixB: перевёрнутые, будущие и нераспознанные даты – явным сообщением #}
      {% if statblok.soobshcheniya %}<div class="period-oshibka" role="alert">{% for s in statblok.soobshcheniya %}<div>{{ s }}</div>{% endfor %}</div>{% endif %}
      <div style="overflow-x:auto">
      <table class="sp-stat-tab">'''

# =========================================================================== правки по якорям
# (ключ файла, было, стало, имя, признак «уже сделано», обязательная)
PRAVKI = [
    # ------------------------------------------------ centro_sales.py
    ('cs', '''    "ne_ponravilas": "Компания не понравилась",
    "dubl": "Дубль – уже работают",
}

# ЧТО ПРЕДЛАГАЕТСЯ В ФОРМЕ.''', '''    "ne_ponravilas": "Компания не понравилась",
    "dubl": "Дубль – уже работают",
    # fixB: события звонка – не статусы (в очередь и вкладки не влияют), подписи для ленты
    "ne_dozvonilsya": "Не дозвонился",
    "lpr_nomer": "Получен личный номер ЛПР",
}

# ЧТО ПРЕДЛАГАЕТСЯ В ФОРМЕ.''', 'centro_sales: подписи новых результатов', '"lpr_nomer": "Получен личный номер ЛПР",\n}', True),
    ('cs', '''        _ensure_assignment_columns(conn)
        _ensure_users_columns(conn)
        try:
            conn.execute("PRAGMA journal_mode=WAL")''', '''        _ensure_assignment_columns(conn)
        _ensure_users_columns(conn)
        ensure_dop(conn)            # fixB: события звонка и причина отказа отдельным полем
        try:
            conn.execute("PRAGMA journal_mode=WAL")''', 'centro_sales: init_schema -> ensure_dop', 'ensure_dop(conn)            # fixB', True),
    ('cs', '''    comment: str = "",
    *,
    path: str | Path | None = None,
) -> None:
    inn = normalize_inn(inn)
    comment = comment.strip()''', '''    comment: str = "",
    *,
    path: str | Path | None = None,
    prichina: str = "",
) -> None:
    inn = normalize_inn(inn)
    comment = comment.strip()''', 'save_call: параметр prichina', '    prichina: str = "",\n) -> None:\n    inn = normalize_inn(inn)', True),
    ('cs', '''                    {
                        "result": result,
                        "next_contact": next_contact,
                        "state_user": state_user,
                    },''', '''                    {
                        "result": result,
                        "next_contact": next_contact,
                        "state_user": state_user,
                        **({"prichina": prichina} if prichina else {}),
                    },''', 'save_call: причина в журнале', '**({"prichina": prichina} if prichina else {}),', True),
    ('cs', '''                    ensure_ascii=False,
                ),
                now,
            ),
        )


def edit_comment(''', '''                    ensure_ascii=False,
                ),
                now,
            ),
        )
        # fixB (владелец 08.10): причина отказа – отдельным полем prichina в состоянии и в
        # комментарии этой отметки; текст «Причина: …» остаётся – по нему понимаются старые
        ensure_dop(conn)
        conn.execute("UPDATE company_state SET prichina=? WHERE inn=? AND username=?",
                     (prichina or None, inn, state_user))
        if comment and prichina:
            conn.execute("UPDATE company_comment SET prichina=? WHERE inn=? AND username=? AND created_at=?",
                         (prichina, inn, user["username"], now))


def edit_comment(''', 'save_call: причина отдельной колонкой', 'conn.execute("UPDATE company_state SET prichina=?', True),

    # ------------------------------------------------ routes_centro_sales.py
    ('rcs', '''    q = params.get("q", "").strip().casefold()
    exact_inn = q if q.isdigit() and len(q) in {10, 12} else ""''', '''    q = params.get("q", "").strip().casefold()
    exact_inn = q if q.isdigit() and len(q) in {10, 12} else ""
    poisk = _poisk_razobrat(params.get("q", ""))   # fixB: номер в любом виде, город, ФИО''', '_matches: разбор поиска', 'poisk = _poisk_razobrat(', True),
    ('rcs', '''        if exact_inn:
            if str(company.get("inn") or "") == exact_inn:
                out.append(company)
            continue

        blob = str(company.get("search_blob") or "").casefold()
        if not blob:
            blob = " ".join(str(value or "") for value in company.values()).casefold()
        if q and q not in blob:
            continue''', '''        # fixB: номер (или ИНН) в любом виде – по цифрам номеров компании, мимо вкладок и
        # прочих фильтров, как прежний точный ИНН; текст – ещё и по адресу, региону, ФИО
        if poisk["nomer"]:
            if _poisk_nomer_sovpal(company, poisk):
                out.append(company)
            continue
        if q and not _poisk_tekst_sovpal(company, poisk):
            continue''', '_matches: поиск по номеру и городу', 'if _poisk_nomer_sovpal(company, poisk):', True),
    ('rcs', '    dir_pred = _direktor_predikat(params)          # фильтры директора (None – не заданы)',
     '    dir_pred = _direktor_predikat_v2(params)       # фильтры директора (None – не заданы); fixB: + события',
     '_matches: предикат директора v2', 'dir_pred = _direktor_predikat_v2(params)', True),
    ('rcs', '''        if call_status and company.get("call_result", "new") != call_status:
            continue''', '''        if call_status in _SOB_FILTR:              # fixB: «не дозвонился» / «номер ЛПР» – по событиям
            if not company.get(_SOB_FILTR[call_status]):
                continue
        elif call_status and company.get("call_result", "new") != call_status:
            continue''', '_matches: фильтр по событиям', 'if call_status in _SOB_FILTR:', True),
    ('rcs', '''        if segment and segment not in [s.strip() for s in str(company.get("segment") or "").split("|")]:
            continue''', '''        # fixB: сегмент – по основному ОКВЭД, с галочкой – и по доп. (segment_dop, агент E1)
        if segment and segment not in _segmenty(company, params.get("segment_dop") == "1"):
            continue
        if params.get("pometka_och", "").strip() and not _pometka_sovpala(company, params.get("pometka_och", "").strip()):
            continue
        if params.get("klient_sc") == "1" and not _klient_sc(company):
            continue''', '_matches: сегмент с доп. ОКВЭД, пометка, клиент СЦ', 'not _pometka_sovpala(company,', True),
    ('rcs', '''    vidimye_vladeltsu = list(visible)   # для счётчиков у фильтров: «из ваших компаний»''',
     '''    _prikrepit_sobytiya(visible)        # fixB: попытки «не дозвонился» и номера ЛПР – к строкам
    vidimye_vladeltsu = list(visible)   # для счётчиков у фильтров: «из ваших компаний»''',
     'centro(): события к строкам', '_prikrepit_sobytiya(visible)        # fixB', True),
    ('rcs', '''    size = min(100, max(10, size))
    pages = max(1, (len(visible) + size - 1) // size)''', '''    _sortirovat_dir(visible, request.query_params.get("sort", ""))   # fixB: только с ?sort=
    size = min(100, max(10, size))
    pages = max(1, (len(visible) + size - 1) // size)''', 'centro(): сортировка директора', '_sortirovat_dir(visible, request.query_params.get("sort", ""))   # fixB', True),
    ('rcs', '''    choices["segment"] = sorted(счёт_сегм.items())''', '''    choices["segment"] = sorted(счёт_сегм.items())
    _dop_vybor_filtrov(choices, vidimye_vladeltsu, request.query_params)   # fixB: пометка, клиент СЦ, доп. ОКВЭД''',
     'centro(): счётчики новых фильтров', '_dop_vybor_filtrov(choices, vidimye_vladeltsu', True),
    ('rcs', '            "dir_opis": _dir_opis(request.query_params),',
     '            "dir_opis": _dir_opis_v2(request.query_params),', 'centro(): описание отбора v2', '"dir_opis": _dir_opis_v2(', True),
    ('rcs', '''            "call_choices": sales.CALL_RESULT_CHOICES,
            "db_info": db_info,
        },''', '''            "call_choices": sales.CALL_RESULT_CHOICES,
            "db_info": db_info,
            **_dop_kontekst(request, user, chosen, sales_users, vidimye_vladeltsu),   # fixB
        },''', 'centro(): контекст fixB', '**_dop_kontekst(request, user, chosen, sales_users, vidimye_vladeltsu)', True),
    ('rcs', '''    prichina: str = Form(""),
    user=Depends(current_user),
):
    # «Компания не понравилась» — только с причиной из списка.''', '''    prichina: str = Form(""),
    lpr_fio: str = Form(""),
    lpr_dolzhnost: str = Form(""),
    lpr_nomer: str = Form(""),
    user=Depends(current_user),
):
    # fixB (владелец 08.10): «Не дозвонился» и «Получен личный номер ЛПР» – не статус, а
    # событие: компания остаётся там, где была, попытка или номер пишутся отдельно
    if call_result in sales.SOBYTIYA_ZVONKA:
        return _sohranit_sobytie(user, inn, call_result, comment, next_contact_at, return_query,
                                 lpr_fio, lpr_dolzhnost, lpr_nomer)
    # «Компания не понравилась» — только с причиной из списка.''', 'save(): новые результаты', 'return _sohranit_sobytie(user, inn, call_result', True),
    ('rcs', '        sales.save_call(user, inn, call_result, next_contact_at, comment)',
     '        sales.save_call(user, inn, call_result, next_contact_at, comment,\n'
     '                        prichina=prichina if call_result == "ne_ponravilas" else "")   # fixB',
     'save(): причина отдельным полем', 'prichina=prichina if call_result == "ne_ponravilas" else ""', True),
    ('rcs', '''        "SELECT username, role, is_active FROM users WHERE is_active=1 ORDER BY username"''',
     '''        "SELECT username, role, is_active FROM users WHERE is_active=1 AND role='sales' ORDER BY username"''',
     'статистика: без meyer_admin в «По продавцам»', "WHERE is_active=1 AND role='sales' ORDER BY username\"", True),
    ('rcs', '''    return sorted(stroki.values(), key=lambda z: (-z["naznacheno"], z["username"]))''',
     '''    # fixB: один порядок продавцов везде – по ФИО
    return sorted(stroki.values(), key=lambda z: _fio_dlya_shablona(z["username"]).lower())''',
     'статистика: продавцы по ФИО', 'key=lambda z: _fio_dlya_shablona(z["username"]).lower())', True),
    ('rcs', '''        obshchee = _stats_obshchee(conn)''', '''        obshchee = _stats_obshchee(conn)
        obshchee.update(_obshchee_sobytiya(conn))      # fixB: номера ЛПР и недозвоны всего''',
     'статистика: итоги событий', 'obshchee.update(_obshchee_sobytiya(conn))', True),
    ('rcs', '''    stat_ot_d = _data_param(stat_ot_param)
    if stat_ot_d is None:
        stat_ot_param = ""
    sc = _sq_st.connect(''', '''    stat_ot_d = _data_param(stat_ot_param)
    if stat_ot_d is None:
        stat_ot_param = ""
    # fixB: период проверяется явно – перевёрнутые и будущие даты не подменяются молча
    _per = _proverit_period(request.query_params, stat_den, stat_ot_d)
    stat_den, stat_ot_d = _per["do"], _per["ot"]
    stat_data_param, stat_ot_param = _per["do_param"], _per["ot_param"]
    stat_vse_param = "1" if _per["vse"] else ""
    sc = _sq_st.connect(''', 'статистика: проверка периода', '_per = _proverit_period(request.query_params', True),
    ('rcs', '''        d = {k: v for k, v in {"stat_ot": stat_ot_param, "stat_data": stat_data_param,
                               "stat_user": stat_user, "user": vybrannyy, **kw}.items() if v}''',
     '''        d = {k: v for k, v in {"stat_ot": stat_ot_param, "stat_data": stat_data_param,
                               "stat_vse": stat_vse_param,
                               "stat_user": stat_user, "user": vybrannyy, **kw}.items() if v}''',
     'статистика: stat_vse в ссылках', '"stat_vse": stat_vse_param,', True),
    ('rcs', '''        direktor = _direktor_svodka(conn_d, d_ot, d_do, stat_user)''',
     '''        direktor = _direktor_svodka(conn_d, d_ot, d_do, stat_user)
        sobytiya_dir = _svodka_sobytiy(conn_d, d_ot, d_do, stat_user)     # fixB''',
     'статистика: сводка событий', 'sobytiya_dir = _svodka_sobytiy(conn_d', True),
    ('rcs', '''    statblok["bystrye"] = _bystrye_periody(stat_ssylka, pervyy, d_ot, d_do)''',
     '''    statblok["bystrye"] = _bystrye_periody(stat_ssylka, pervyy, d_ot, d_do, vse=bool(stat_vse_param))
    # fixB: «всё время» – свой период и своя подпись; сообщения о датах – над таблицей
    statblok["vse"] = bool(stat_vse_param)
    statblok["soobshcheniya"] = _per["soobshcheniya"]
    if statblok["vse"]:
        statblok["period"] = True
        direktor["period_ru"] = "за всё время (с %s)" % d_ot.strftime("%d.%m.%Y")''',
     'статистика: «всё время» и сообщения', 'statblok["soobshcheniya"] = _per["soobshcheniya"]', True),
    ('rcs', '''            "direktor": direktor,
''', '''            "direktor": direktor,
            "sobytiya_dir": sobytiya_dir,
''', 'статистика: sobytiya_dir в шаблон', '"sobytiya_dir": sobytiya_dir,', True),
    ('rcs', '''def _bystrye_periody(ssylka, pervyy, ot, do) -> list[dict]:
    segodnya = _segodnya_msk()
    d1 = datetime.timedelta(days=1)
    pervyy_den = (_msk_vremya(pervyy).date() if _msk_vremya(pervyy) else segodnya)
    pervyy_den = min(pervyy_den, segodnya)
    out = []
    for nazv, a, b in (("сегодня", segodnya, segodnya), ("вчера", segodnya - d1, segodnya - d1),
                       ("7 дней", segodnya - 6 * d1, segodnya),
                       ("30 дней", segodnya - 29 * d1, segodnya),
                       ("всё время", pervyy_den, segodnya)):
        out.append({"nazv": nazv, "aktiven": (a, b) == (ot, do),
                    "url": ssylka(stat_ot=a.isoformat() if a != b else "",
                                  stat_data=b.isoformat() if b != segodnya else "")})
    return out''', '''def _bystrye_periody(ssylka, pervyy, ot, do, vse=False) -> list[dict]:
    # fixB: «всё время» – настоящий период (stat_vse=1): раньше, пока отметок не было, он
    # совпадал с «сегодня» и вёл туда же; активна ровно одна кнопка
    segodnya = _segodnya_msk()
    d1 = datetime.timedelta(days=1)
    out = []
    for nazv, a, b in (("сегодня", segodnya, segodnya), ("вчера", segodnya - d1, segodnya - d1),
                       ("7 дней", segodnya - 6 * d1, segodnya),
                       ("30 дней", segodnya - 29 * d1, segodnya)):
        out.append({"nazv": nazv, "aktiven": (not vse) and (a, b) == (ot, do),
                    "url": ssylka(stat_ot=a.isoformat() if a != b else "",
                                  stat_data=b.isoformat() if b != segodnya else "", stat_vse="")})
    out.append({"nazv": "всё время", "aktiven": bool(vse),
                "url": ssylka(stat_ot="", stat_data="", stat_vse="1")})
    return out''', 'статистика: быстрые периоды', 'def _bystrye_periody(ssylka, pervyy, ot, do, vse=False)', True),
    ('rcs', '''    komm = {}
    for r in conn.execute("SELECT inn, username, body, created_at FROM company_comment"):
        komm[(str(r["inn"]), r["username"], r["created_at"])] = r["body"]
    vidy = ("call_saved", "comment_edited", "reassigned") if vse_deystviya else ("call_saved",)''', '''    komm = {}
    komm_pr = {}
    try:   # fixB: причина отдельным полем (колонка prichina); старые записи – разбором текста
        for r in conn.execute("SELECT inn, username, body, created_at, prichina FROM company_comment"):
            komm[(str(r["inn"]), r["username"], r["created_at"])] = r["body"]
            if r["prichina"]:
                komm_pr[(str(r["inn"]), r["username"], r["created_at"])] = r["prichina"]
    except Exception:  # noqa: BLE001 – колонки ещё нет
        for r in conn.execute("SELECT inn, username, body, created_at FROM company_comment"):
            komm[(str(r["inn"]), r["username"], r["created_at"])] = r["body"]
    vidy = (("call_saved", "comment_edited", "reassigned") + _SOB_DEYSTVIYA) if vse_deystviya else ("call_saved",)''',
     '_sobytiya: причина из колонки', 'komm_pr[(str(r["inn"]), r["username"], r["created_at"])] = r["prichina"]', True),
    ('rcs', '''            if body is not None:
                rk = _razbor_kommentariya(body)
                z["prichina"], z["tekst"] = rk["prichina"], rk["tekst"]
        elif r["action"] == "reassigned":''', '''            if body is not None:
                rk = _razbor_kommentariya(body)
                z["prichina"], z["tekst"] = rk["prichina"], rk["tekst"]
            # fixB: причина из отдельного поля (журнал, комментарий) важнее разбора текста
            pr_pole = pl.get("prichina") or komm_pr.get((inn, r["username"], r["created_at"]))
            if pr_pole and z["rez"] == "ne_ponravilas":
                z["prichina"] = pr_pole
                if body is not None:
                    z["tekst"] = _tekst_bez_prichiny(body, pr_pole)
        elif r["action"] in _SOB_DEYSTVIYA:       # fixB: «не дозвонился», «номер ЛПР»
            z["rez"] = r["action"]
            z["tekst"] = str(pl.get("kommentariy") or "")
        elif r["action"] == "reassigned":''', '_sobytiya: события звонка', 'elif r["action"] in _SOB_DEYSTVIYA:', True),
    ('rcs', '''    chasy_po: dict = {}
    for z in zvonki:
        if kto and z["deystvoval"] != kto:''', '''    chasy_po: dict = {}
    # fixB: и попытки «не дозвонился» / номера ЛПР – это тоже работа в этот час
    for z in zvonki + [z for z in sobytiya if z["deystvie"] in _SOB_DEYSTVIYA]:
        if kto and z["deystvoval"] != kto:''', 'svodka: часы с событиями', 'for z in zvonki + [z for z in sobytiya if z["deystvie"] in _SOB_DEYSTVIYA]:', True),
    ('rcs', '''        else:
            chto = "изменил комментарий"''', '''        elif z["deystvie"] in _SOB_DEYSTVIYA:       # fixB
            chto = _SOB_NAZV.get(z["deystvie"], z["deystvie"])
            if z["deystvie"] == "lpr_nomer":
                kto_lpr = ", ".join(x for x in (z["pl"].get("fio"), z["pl"].get("dolzhnost")) if x)
                chto += (": " + kto_lpr) if kto_lpr else ""
        else:
            chto = "изменил комментарий"''', 'svodka: лента с событиями', 'chto = _SOB_NAZV.get(z["deystvie"], z["deystvie"])', True),
    ('rcs', '''        razrezy.append({"nazv": nazv, "stroki": stroki[:20], "vsego_znacheniy": len(stroki)})''',
     '''        # fixB: сумма строк больше числа компаний – компания с двумя значениями считается в обоих
        razrezy.append({"nazv": nazv, "stroki": stroki[:20], "vsego_znacheniy": len(stroki),
                        "summa": sum(s["otmecheno"] for s in sch.values()), "kompaniy": len(posl),
                        "pochemu": ("компания в двух базах считается в обеих" if pole == "bazy"
                                    else "компания с двумя значениями считается в каждом")})''',
     'svodka: сумма срезов', '"summa": sum(s["otmecheno"] for s in sch.values())', True),
    ('rcs', '''                istochniki.setdefault(inn, set()).add(v["vid"] or "без ссылки")''',
     '''                istochniki.setdefault(inn, set()).add(
                    "от продавца" if str(r["source"] or "").startswith("от продавца")   # fixB
                    else (v["vid"] or "без ссылки"))''', 'svodka: источник «от продавца»', '"от продавца" if str(r["source"] or "").startswith("от продавца")', True),
    ('rcs', '''    "уже купили у конкурентов",
]''', '''    "уже купили у конкурентов",
    # fixB (08.10, проверка панели): ещё четыре причины; прежние формулировки не переименованы
    "нет потребности",
    "не наш профиль",
    "компания закрыта",
    "не та компания / не ЛПР",
]''', 'причины: + четыре', '"не та компания / не ЛПР",', True),
    ('rcs', '''    "PANEL_PODPIS", "база продаж по компрессорному оборудованию")''',
     '''    "PANEL_PODPIS", "база продаж")   # fixB: без подписи компрессорной панели''',
     'подпись панели без «компрессорного»', '"PANEL_PODPIS", "база продаж")', False),
    ('rcs', '''            "stats": stats,
            "sales_users": users,''', '''            "stats": sorted(stats, key=lambda z: _fio_dlya_shablona(z["username"]).lower()),   # fixB
            "sales_users": sorted(users, key=lambda u: _fio_dlya_shablona(u).lower()),''',
     'админка: продавцы по ФИО', '"stats": sorted(stats, key=lambda z: _fio_dlya_shablona', False),

    # ------------------------------------------------ routes_park.py (_statblok)
    ('rp', '''    def pusto():
        return {"v_rabote": 0, "ne_ponravilas": 0, "dubl": 0, "ochered": 0, "prochee": 0}''',
     '''    def pusto():
        return {"v_rabote": 0, "ne_ponravilas": 0, "dubl": 0, "ochered": 0, "prochee": 0,
                "lpr": 0, "nedozvon": 0}      # fixB: личные номера ЛПР, «не дозвонился»''',
     '_statblok: новые счётчики', '"lpr": 0, "nedozvon": 0}      # fixB', True),
    ('rp', '''    for u, ch in lyudi.items():
        if ch.get("role") == "sales" and ch.get("is_active"):
            stroka(u)                      # активный продавец виден и с нулями''', '''    # fixB (08.10): личные номера ЛПР и попытки «не дозвонился» – из таблицы событий звонка
    # (в старой базе её нет – тогда нули). Засчитываются владельцу компании, как отметки.
    try:
        for r in conn.execute("select state_user, vid, created_at from zvonok_sobytie"):
            kl = {"lpr_nomer": "lpr", "ne_dozvonilsya": "nedozvon"}.get(str(r["vid"] or ""))
            d = _msk_den(r["created_at"])
            if not kl or d is None:
                continue
            z = stroka(str(r["state_user"] or ""))
            z["vse"][kl] += 1
            if ot <= d <= den:
                z["den"][kl] += 1
    except sqlite3.OperationalError:
        pass
    for u, ch in lyudi.items():
        if ch.get("role") == "sales" and ch.get("is_active"):
            stroka(u)                      # активный продавец виден и с нулями''',
     '_statblok: события звонка', 'select state_user, vid, created_at from zvonok_sobytie', True),

    # ------------------------------------------------ centro.html
    ('C', ("""<input type="search" name="q" value="{{ request.query_params.get('q','') }}" placeholder="{{ 'Название, ИНН, модель, телефон, человек…' if choices.est_oborudovanie else 'Название, ИНН, телефон, человек…' }}">""",
           """<input type="search" name="q" value="{{ request.query_params.get('q','') }}" placeholder="Название, ИНН, модель, телефон, человек…">"""),
     """<input type="search" name="q" value="{{ request.query_params.get('q','') }}" placeholder="{{ 'Название, ИНН, модель, телефон, человек…' if choices.est_oborudovanie else 'Название, ИНН, телефон, город, ФИО…' }}" title="Телефон – в любом виде: +7 900 …, 8900…, 8 (900) …, последние 7 или 10 цифр. Город – из адреса и региона. ФИО – из контактов компании">""",
     'главная: честная подсказка поиска', "'Название, ИНН, телефон, город, ФИО…'", True),
    ('C', '''placeholder="название, ИНН, ФИО, телефон"''', '''placeholder="название, ИНН, телефон в любом виде, город, ФИО"''',
     'фильтры: подсказка поиска', 'placeholder="название, ИНН, телефон в любом виде, город, ФИО"', False),
    ('C', '''{% for value,label in call_results.items() %}<option value="{{ value }}" {% if request.query_params.get('call_status') == value %}selected{% endif %}>{{ label }}</option>{% endfor %}''',
     '''{% for value,label in (call_filtr or call_results.items()) %}<option value="{{ value }}" {% if request.query_params.get('call_status') == value %}selected{% endif %}>{{ label }}</option>{% endfor %}''',
     'фильтры: «Результат звонка» – только ставимые', '(call_filtr or call_results.items())', True),
    ('C', '''    {% for k in ('rez_p', 'kto_p') %}{% if request.query_params.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.query_params.get(k) }}">{% endif %}{% endfor %}
    <button type="submit">Показать</button>''', C_DIREKTOR_SORT, 'директор: сортировка и CSV', 'class="dir-csv"', True),
    ('C', '''{% for k in ('ot', 'do', 'prichina', 'bez_poyasneniya', 'rez_p', 'kto_p') %}''',
     '''{% for k in ('ot', 'do', 'prichina', 'bez_poyasneniya', 'rez_p', 'kto_p', 'sob', 'sort') %}''',
     'фильтры: не терять sob и sort', "'rez_p', 'kto_p', 'sob', 'sort') %}", True),
    ('C', '''  <section class="card work-card">
    <form method="post" action="{{ base_path }}/centro/save" class="work-form">''', C_KARTOCHKA_NACHALO,
     'карточка: попытки, номера ЛПР, форма у директора свёрнута', '<details class="dir-forma">', True),
    ('C', '''      <button class="primary-button">Сохранить и перейти дальше</button>
    </form>''', '''      <button class="primary-button">Сохранить и перейти дальше</button>
    </form>
    {% if user.role == 'admin' %}</details>{% endif %}''', 'карточка: конец свёрнутой формы', "</form>\n    {% if user.role == 'admin' %}</details>{% endif %}", True),
    ('C', '''            {% for value,label in call_choices.items() %}
            {% if value == 'ne_ponravilas' and prichiny %}''', '''            {% for value,label in (call_menu or call_choices).items() %}
            {% if value == 'ne_ponravilas' and prichiny %}''', 'форма: новые результаты в меню', '(call_menu or call_choices).items()', True),
    ('C', '''        </div>
      </div>
      <style>
      .rez-pole{display:grid;gap:4px;font-size:13px;color:var(--muted)}''', C_LPR_POLYA, 'форма: поля ЛПР', 'class="lpr-polya"', True),
    ('C', '''      })();
      </script>
      <label>Следующий контакт<input type="datetime-local"''', C_LPR_JS, 'форма: скрипт полей ЛПР', "pole.value === 'lpr_nomer'", True),
    ('C', '''.hide-form{display:inline;margin-left:6px}''', C_STILI, 'главная: стили fixB', '.zv-sobytiya{', True),
    ('C', C_FILTRY_DOP.split('\n')[0], C_FILTRY_DOP, 'фильтры: клиент СЦ, доп. ОКВЭД', 'name="klient_sc"', True),
    ('C', '''{% if op %} – {{ op }}{% endif %} · {{ n }}</option>{% endfor %}</select></label>
        </div>''', C_POMETKA, 'фильтры: пометка очереди', 'name="pometka_och"', True),
    ('C', '''</select>{% endif %}
  {% if choices.otrasl %}<select name="otrasl" title="Отрасль по основному ОКВЭД">''', '''</select>{% endif %}
  {% if choices.segment and choices.segment_dop_est %}<label class="check" title="Сегмент ищется и по дополнительным ОКВЭД, а не только по основному"><input type="checkbox" name="segment_dop" value="1" {% if request.query_params.get('segment_dop') == '1' %}checked{% endif %}> + доп. ОКВЭД</label>{% endif %}
  {% if choices.otrasl %}<select name="otrasl" title="Отрасль по основному ОКВЭД">''', 'главная: сегмент + доп. ОКВЭД', '> + доп. ОКВЭД</label>', False),
    ('C', '''<label>Источник базы<select name="baza">''', '''<label title="Компания из двух баз считается в каждой – сумма чисел в списке больше числа компаний">Источник базы <small style="font-weight:400;color:var(--muted)">(компания из двух баз – в обеих)</small><select name="baza">''',
     'фильтры: пояснение суммы по базам', '(компания из двух баз – в обеих)', False),
    ('C', '''<span title="Место в очереди. Считается как важность предприятия плюс надбавки за то, что до него есть чем дозвониться: телефон, закупщик, технический человек, свежий сигнал, факты. Минус 1000, если юрлицо ликвидировано."><b>Очередь</b>''',
     '''<span title="Балл очереди: по нему строится очередь продавца (больше – выше). Важность предприятия плюс надбавки за то, что до него есть чем дозвониться: телефон, закупщик, технический человек; поправка по ОКВЭД. Минус 1000, если юрлицо ликвидировано."><b>Балл очереди</b>''',
     'карточка: «Балл очереди»', '<b>Балл очереди</b>', False),
    ('C', '''<h3>Выручка и приоритет</h3>''', '''<h3>Выручка и балл очереди</h3>''', 'фильтры: «Выручка и балл очереди»', '<h3>Выручка и балл очереди</h3>', False),
    ('C', '''<label>Приоритет от<input''', '''<label>Балл очереди от<input''', 'фильтры: «Балл очереди от»', '<label>Балл очереди от<input', False),
    ('C', '''<label>Приоритет до<input''', '''<label>Балл очереди до<input''', 'фильтры: «Балл очереди до»', '<label>Балл очереди до<input', False),

    # ------------------------------------------------ _ochered_spisok.html (необязательные)
    ('L', '''          {% if c.next_contact_at %}<br><span class="tiho">перезвонить {{ c.next_contact_at[:16]|replace('T', ' ') }}</span>{% endif %}''',
     '''          {% if c.next_contact_at %}<br><span class="tiho">перезвонить {{ c.next_contact_at[:16]|replace('T', ' ') }}</span>{% endif %}
          {% if c.popytok %}<br><span class="tiho" title="Не дозвонился: попыток {{ c.popytok }}, последняя {{ c.popytka_posled }}">не дозвонился: {{ c.popytok }}{% if c.popytka_posled %}, {{ c.popytka_posled }}{% endif %}</span>{% endif %}
          {% if c.lpr_poluchen %}<br><span class="och-tag da" title="Продавец получил личный номер ЛПР – он в контактах карточки">номер ЛПР получен{% if c.lpr_poluchen > 1 %}: {{ c.lpr_poluchen }}{% endif %}</span>{% endif %}''',
     'список: попытки и номер ЛПР', 'не дозвонился: {{ c.popytok }}', False),
    ('L', '''<th>Статус</th><th>Балл</th>''', '''<th>Статус</th><th title="По нему строится очередь продавца: больше – выше">Балл очереди</th>''',
     'список: «Балл очереди»', '>Балл очереди</th>', False),
    ('L', '''<span>порядок – как у очереди: сначала новые, внутри по баллу</span>''',
     '''<span>{% if poryadok_opis %}порядок: {{ poryadok_opis }}{% else %}порядок – как у очереди: сначала новые, внутри по баллу очереди{% endif %}</span>''',
     'список: подпись порядка', '{% if poryadok_opis %}порядок: {{ poryadok_opis }}', False),

    # ------------------------------------------------ _statblok.html
    ('SB', '''<td>{{ yach(d.ochered, ss.ochered if ss else '') }}</td>{% endmacro %}''',
     '''<td>{{ yach(d.ochered, ss.ochered if ss else '') }}</td><td class="cel" title="личных номеров ЛПР получено">{{ d.lpr or 0 }}</td><td title="попыток «не дозвонился»">{{ d.nedozvon or 0 }}</td>{% endmacro %}''',
     'календарь: ячейки номер ЛПР / не дозвонился', '{{ d.lpr or 0 }}', True),
    ('SB', '''            <th class="gr razd" colspan="4">{% if statblok.period %}с {{ statblok.ot_ru }} по {{ statblok.den_ru }}{% else %}за {{ statblok.den_ru }}{% endif %}{% if statblok.eto_segodnya and not statblok.period %} (сегодня){% endif %}</th>
            <th class="gr razd" colspan="4">за всё время</th></tr>''',
     '''            <th class="gr razd" colspan="6">{% if statblok.vse %}за всё время (с {{ statblok.ot_ru }} по {{ statblok.den_ru }}){% elif statblok.period %}с {{ statblok.ot_ru }} по {{ statblok.den_ru }}{% else %}за {{ statblok.den_ru }}{% endif %}{% if statblok.eto_segodnya and not statblok.period %} (сегодня){% endif %}</th>
            <th class="gr razd" colspan="6">{% if statblok.vse %}нынешний статус{% else %}за всё время{% endif %}</th></tr>''',
     'календарь: заголовки групп', '{% if statblok.vse %}за всё время (с {{ statblok.ot_ru }}', True),
    ('SB', '''          <tr><th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди</th>
            <th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди</th></tr>''',
     '''          <tr><th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди</th><th title="личных номеров ЛПР получено">номер ЛПР</th><th title="попыток «не дозвонился» (компания осталась в очереди)">не дозвонился</th>
            <th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди</th><th title="личных номеров ЛПР получено">номер ЛПР</th><th title="попыток «не дозвонился» (компания осталась в очереди)">не дозвонился</th></tr>''',
     'календарь: подписи колонок', '<th title="личных номеров ЛПР получено">номер ЛПР</th>', True),
    ('SB', '''<tr><td colspan="9" class="tiho">продавцов нет</td></tr>''', '''<tr><td colspan="13" class="tiho">продавцов нет</td></tr>''',
     'календарь: colspan', 'colspan="13" class="tiho">продавцов нет', True),
    ('SB', '''      </form>
      <div style="overflow-x:auto">
      <table class="sp-stat-tab">''', SB_SOOBSHCH, 'календарь: сообщения о датах', 'class="period-oshibka"', True),
    ('SB', '''        За всё время – нынешний статус; в очереди только то, что продавец видит (без скрытых).''',
     '''        За всё время – нынешний статус; в очереди только то, что продавец видит (без скрытых).
        «Номер ЛПР» – личные номера ЛПР, которые продавец получил и вписал; «не дозвонился» – попытки без исхода, компания остаётся в очереди.''',
     'календарь: пояснение новых колонок', '«Номер ЛПР» – личные номера ЛПР, которые продавец получил', True),
    ('SB', '''  table.sp-stat-tab tr.itog td{font-weight:700}
</style>''', '''  table.sp-stat-tab tr.itog td{font-weight:700}
  table.sp-stat-tab td.cel{color:#17663a;font-weight:700}
  .period-oshibka{background:#fff4e0;border:1px solid #f3d39b;color:#8a5300;border-radius:6px;padding:6px 10px;font-size:13px}
</style>''', 'календарь: стили', '.period-oshibka{', True),

    # ------------------------------------------------ centro_stats.html
    ('ST', '''  <h2>Причины отказов по продавцам <span class="period-metka">{{ d.period_ru }}</span></h2>''',
     ST_BLOK + '''  <h2>Причины отказов по продавцам <span class="period-metka">{{ d.period_ru }}</span></h2>''',
     'статистика: блок «Личные номера ЛПР и недозвоны»', 'id="lpr-nomera"', True),
    ('ST', '''    <div class="plitka"><b>{{ obshchee.obrabotano }}</b><span>обработано</span></div>''',
     '''    <div class="plitka"><b>{{ obshchee.obrabotano }}</b><span>обработано</span></div>
    <div class="plitka plitka-cel"><b>{{ obshchee.lpr_vsego or 0 }}</b><span>личных номеров ЛПР получено за всё время{% if obshchee.lpr_kompaniy %} ({{ obshchee.lpr_kompaniy }} комп.){% endif %}</span></div>
    <div class="plitka"><b>{{ obshchee.nedozvon_vsego or 0 }}</b><span>попыток «не дозвонился» за всё время</span></div>''',
     'статистика: плитки номеров ЛПР', 'obshchee.lpr_vsego or 0', True),
    ('ST', '''        <td><a href="{{ stat_ssylka(user=p.username) }}">{{ p.username|fio }}</a>''',
     '''        <td><a href="{{ stat_ssylka(user=p.username) }}#ochered-prodavca">{{ p.username|fio }}</a>''',
     'статистика: якорь к очереди продавца', '#ochered-prodavca">{{ p.username|fio }}', True),
    ('ST', '''  <h2>Очередь продавца {{ vybrannyy|fio }}''', '''  <h2 id="ochered-prodavca">Очередь продавца {{ vybrannyy|fio }}''',
     'статистика: id очереди продавца', '<h2 id="ochered-prodavca">', True),
    ('ST', '''<th>Сумма балла</th><th>Средний балл</th>''', '''<th>Сумма балла очереди</th><th>Средний балл очереди</th>''',
     'статистика: «балл очереди» у продавцов', '<th>Сумма балла очереди</th>', True),
    ('ST', '''<th>№</th><th>Компания</th><th>ИНН</th><th>Балл</th><th>Результат</th>''',
     '''<th>№</th><th>Компания</th><th>ИНН</th><th>Балл очереди</th><th>Результат</th>''',
     'статистика: «балл очереди» в очереди продавца', '<th>ИНН</th><th>Балл очереди</th>', True),
    ('ST', '''сроку, внутри – по убыванию балла.''', '''сроку, внутри – по убыванию балла очереди.''',
     'статистика: пояснение порядка', 'по убыванию балла очереди.', False),
    ('ST', '''      <h3>{{ r.nazv }}{% if r.vsego_znacheniy > r.stroki|length %} <span class="pometka">(первые {{ r.stroki|length }} из {{ r.vsego_znacheniy }})</span>{% endif %}</h3>''',
     '''      <h3>{{ r.nazv }}{% if r.vsego_znacheniy > r.stroki|length %} <span class="pometka">(первые {{ r.stroki|length }} из {{ r.vsego_znacheniy }})</span>{% endif %}</h3>
      {% if r.summa and r.kompaniy and r.summa > r.kompaniy %}<p class="pometka">Сумма по строкам {{ r.summa }} при {{ r.kompaniy }} компаниях: {{ r.pochemu }}.</p>{% endif %}''',
     'статистика: пояснение суммы среза', 'Сумма по строкам {{ r.summa }}', True),
    ('ST', '''  <p class="pometka">Сколько отметок поставлено в каждый час. Считается тот, кто нажал кнопку.</p>''',
     '''  <p class="pometka">Сколько отметок и звонков без исхода («не дозвонился», «номер ЛПР») сохранено в каждый час. Считается тот, кто нажал кнопку.</p>''',
     'статистика: подпись часов', 'звонков без исхода («не дозвонился», «номер ЛПР»)', True),
    ('ST', '''    .bystrye b{color:var(--navy)}''', '''    .bystrye b{color:var(--navy)}
    .plitka-cel{border-color:#9fd3b6;background:#f2faf5}
    .plitka-cel b{color:#17663a}
    .st-l.st-lpr_nomer{color:#17663a;font-weight:600}
    .st-l.st-ne_dozvonilsya{color:#8a5300}''', 'статистика: стили', '.plitka-cel{', True),
    ('ST', '''    .st-l.st-ne_dozvonilsya{color:#8a5300}''', '''    .st-l.st-ne_dozvonilsya{color:#8a5300}
    /* fixB: на телефоне и планшете таблицы прокручиваются внутри своего блока – страница не шире экрана */
    .razrezy{grid-template-columns:repeat(auto-fit,minmax(min(440px,100%),1fr))}
    .razrezy>section{min-width:0}
    .stat-setka>.plitka{min-width:min(150px,100%)}
    @media(max-width:1100px){
      table.stat{display:block;max-width:100%;overflow-x:auto}
      .sp-stat-forma{gap:8px}
    }
    @media(max-width:760px){
      main.admin-page{padding:10px 8px!important}
      .stat-setka{gap:8px}
      .stat-setka>.plitka{flex:1 1 140px;min-width:0;padding:8px 10px}
      .pometka{overflow-wrap:anywhere}
    }''', 'статистика: телефон и планшет', 'fixB: на телефоне и планшете', True),
]

DOBAVKI = [('cs', CS_DOP, '# ===================================================================== fixB-блок (08.10)\n# Новые результаты'),
           ('rcs', RCS_DOP, '# ===================================================================== fixB-блок (08.10)\n# Поиск, новые')]


def primenit(koren_app, log) -> tuple:
    """Правки по якорям в папке koren_app (…\\app). Возвращает (сделано, обязательных_провалено)."""
    provaleno = []
    for kl, staro, novo, imya, priznak, nado in PRAVKI:
        p = os.path.join(koren_app, FAJLY[kl])
        t = io.open(p, encoding='utf-8').read()
        if priznak in t:
            log.append('[уже] ' + imya)
            continue
        if isinstance(staro, tuple):           # несколько вариантов якоря (файл правят и другие)
            staro = next((v for v in staro if t.count(v) == 1), staro[0])
        n = t.count(staro)
        if n != 1:
            log.append('[%s ЯКОРЬ: %d] %s' % ('НЕТ' if nado else 'пропуск', n, imya))
            if nado:
                provaleno.append(imya)
            continue
        io.open(p, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
        log.append('[ок] ' + imya)
    for kl, blok, priznak in DOBAVKI:
        p = os.path.join(koren_app, FAJLY[kl])
        t = io.open(p, encoding='utf-8').read()
        if priznak in t:
            log.append('[уже] блок fixB в ' + FAJLY[kl])
            continue
        io.open(p, 'w', encoding='utf-8').write(t.rstrip('\n') + '\n' + blok)
        log.append('[ок] блок fixB в ' + FAJLY[kl])
    return provaleno


def kopiya_bazy(otkuda, kuda):
    """Копия sqlite через backup API (WAL учтён, файл может быть открыт панелью)."""
    if os.path.exists(kuda):
        os.remove(kuda)
    src = sqlite3.connect('file:%s?mode=ro' % otkuda, uri=True, timeout=30)
    dst = sqlite3.connect(kuda)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


# =========================================================================== сухой прогон
if '--lokalno' in sys.argv:
    papka = sys.argv[sys.argv.index('--lokalno') + 1]
    log = []
    prov = primenit(papka, log)
    print('\n'.join(log))
    print('ПРОВАЛЕНО обязательных: %s' % prov)
    raise SystemExit(1 if prov else 0)


# =========================================================================== проверка
def proverka(koren_koda, bystro):
    import datetime as dt
    import json
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение (живые пути), chdir
    sys.path.insert(0, koren_koda)
    ZH_S = os.environ['CENTRO_SALES_DB']
    ZH_K = os.environ['CENTRIFUGAL_DB']
    kopiya_bazy(ZH_S, TEST_DB)
    kopiya_bazy(ZH_K, TEST_KAT)
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = TEST_DB                 # всё ниже пишет только во временные копии
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[k] = TEST_KAT
    import app
    from app.api import routes_centro_sales as rcs
    from app.api import routes_park as rp
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()

    ok(os.path.abspath(app.__file__).lower().startswith(os.path.abspath(koren_koda).lower()),
       'код из %s' % koren_koda)
    ok(rp.SALES_DB == TEST_DB and str(catalog.db_path()) == TEST_KAT and str(sales.sales_db_path()) == TEST_DB,
       'базы продаж и каталога – временные копии')

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 5, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 7, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    vnutr.dependency_overrides[rcs._same_origin] = lambda: None

    def chislo(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1

    b = sqlite3.connect(TEST_DB)
    b.row_factory = sqlite3.Row
    kat = sqlite3.connect(TEST_KAT)
    kat.row_factory = sqlite3.Row
    segodnya = (dt.datetime.utcnow() + dt.timedelta(hours=3)).date()
    zanyatye = {str(r[0]) for r in b.execute('select inn from company_state')}
    v_kat = {str(r[0]) for r in kat.execute('select inn from company')}
    skryt = {str(r[0]) for r in b.execute("select inn from hidden_item where kind='company'")}
    A = [str(r['inn']) for r in b.execute("select inn from company_assignment where username='meyer2' "
                                         "order by assignment_score desc")
         if str(r['inn']) not in zanyatye and str(r['inn']) in v_kat and str(r['inn']) not in skryt]
    with TestClient(vnutr) as k:
        def poluchit(u, kak=ADMIN, **kw):
            kto['u'] = kak
            return k.get(PUT + u, **kw)

        def otpravit(dannye, kak=PROD):
            kto['u'] = kak
            return k.post(PUT + '/centro/save', data=dannye, follow_redirects=False)

        # ---------- рендер
        for nazv, u, kak, kod in (('главная, админ', '/centro', ADMIN, 200),
                                  ('карточка, админ', '/centro?inn=' + A[0], ADMIN, 200),
                                  ('статистика, админ', '/centro/stats', ADMIN, 200),
                                  ('список компаний, админ', '/centro/spisok', ADMIN, 200),
                                  ('главная, продавец', '/centro', PROD, 200),
                                  ('карточка, продавец', '/centro?inn=' + A[0], PROD, 200),
                                  ('список компаний, продавец', '/centro/spisok', PROD, 200),
                                  ('статистика, продавец', '/centro/stats', PROD, 403)):
            o = poluchit(u, kak)
            ok(o.status_code == kod, '%s: %s' % (nazv, o.status_code))
        t_adm = poluchit('/centro?inn=' + A[0]).text
        t_pr = poluchit('/centro?inn=' + A[0], PROD).text
        ok('<details class="dir-forma">' in t_adm and 'class="work-form"' in t_adm, 'у директора форма продавца свёрнута, но есть')
        ok('<details class="dir-forma">' not in t_pr and 'class="work-form"' in t_pr, 'у продавца форма открыта')
        ok('data-value="ne_dozvonilsya"' in t_pr and 'data-value="lpr_nomer"' in t_pr and 'name="lpr_nomer"' in t_pr,
           'в меню результата «Не дозвонился» и «Получен личный номер ЛПР», поля ЛПР')
        for p in ('нет потребности', 'не наш профиль', 'компания закрыта', 'не та компания / не ЛПР',
                  'неверно указан номер', 'уже купили у конкурентов'):
            ok('data-prichina="%s"' % p in t_pr, 'причина в меню: %s' % p)
        if bystro:
            t = poluchit('/centro').text
            ok('Название, ИНН, телефон, город, ФИО…' in t, 'подсказка поиска')
            t = poluchit('/centro/stats').text
            ok('id="lpr-nomera"' in t and 'всё время' in t, 'статистика: блок номеров ЛПР')
            ok(poluchit('/centro/vygruzka.csv').status_code == 200, 'CSV отдаётся')
            print()
            print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
            raise SystemExit(0 if not plohih[0] else 1)

        t = poluchit('/centro').text
        ok('placeholder="Название, ИНН, телефон, город, ФИО…"' in t and 'модель, телефон' not in t, 'подсказка поиска честная (без «модели»)')
        m = re.search(r'<select name="call_status">(.*?)</select>', t, re.S)
        zn = set(re.findall(r'<option value="([^"]*)"', m.group(1))) if m else set()
        ok(zn == {'', 'new', 'v_rabote', 'ne_ponravilas', 'dubl', 'ne_dozvonilsya', 'lpr_nomer'},
           'фильтр «Результат звонка»: %s' % sorted(zn))
        ok('class="dir-csv"' in t and 'name="sort"' in t, 'у директора сортировка и CSV')
        ok('class="dir-csv"' not in poluchit('/centro', PROD).text, 'у продавца нет CSV')

        # ---------- «Не дозвонился»
        o = otpravit({'inn': A[0], 'call_result': 'ne_dozvonilsya', 'comment': 'fixB-тест занято'})
        ok(o.status_code == 303, '«не дозвонился» №1: %s' % o.status_code)
        o = otpravit({'inn': A[0], 'call_result': 'ne_dozvonilsya'})
        ok(o.status_code == 303, '«не дозвонился» №2: %s' % o.status_code)
        zavtra = (dt.datetime.utcnow() + dt.timedelta(hours=27)).strftime('%Y-%m-%dT10:00')
        o = otpravit({'inn': A[1], 'call_result': 'ne_dozvonilsya', 'next_contact_at': zavtra, 'comment': 'fixB-тест перезвон'})
        ok(o.status_code == 303, '«не дозвонился» с перезвоном: %s' % o.status_code)
        n = b.execute("select count(*) from zvonok_sobytie where inn=? and vid='ne_dozvonilsya'", (A[0],)).fetchone()[0]
        ok(n == 2, 'попыток у %s в базе: %d' % (A[0], n))
        ok(b.execute('select count(*) from company_state where inn=?', (A[0],)).fetchone()[0] == 0,
           'статус компании не тронут (строки состояния нет)')
        st1 = b.execute('select call_result, next_contact_at from company_state where inn=?', (A[1],)).fetchone()
        ok(st1 is not None and st1[0] == 'new' and st1[1] == zavtra, 'перезвон записан, результат «new»: %r' % ((tuple(st1) if st1 else None),))
        t = poluchit('/centro?size=100', PROD).text
        ok(('inn=' + A[0]) in t and ('inn=' + A[1]) in t, 'обе компании остались во «Всей очереди» продавца')
        ok('попыток: 2, последняя' in poluchit('/centro?inn=' + A[0], PROD).text, 'в карточке «попыток: 2, последняя …»')
        t = poluchit('/centro?call_status=ne_dozvonilsya', PROD).text
        ok(chislo(t) == 2, 'фильтр «Не дозвонился (были попытки)»: %d' % chislo(t))

        # ---------- «Получен личный номер ЛПР»
        dannye = {'inn': A[2], 'call_result': 'lpr_nomer', 'lpr_fio': 'Тестов Тест Тестович',
                  'lpr_dolzhnost': 'главный инженер', 'lpr_nomer': '8 (495) 000-00-00', 'comment': 'fixB-тест'}
        o = otpravit(dannye)
        ok(o.status_code == 303, '«номер ЛПР»: %s' % o.status_code)
        o = otpravit(dannye)
        ok(o.status_code == 303, '«номер ЛПР» повтор: %s' % o.status_code)
        rr = b.execute("select * from zvonok_sobytie where inn=? and vid='lpr_nomer'", (A[2],)).fetchall()
        ok(len(rr) == 1 and rr[0]['nomer_10'] == '4950000000' and rr[0]['state_user'] == 'meyer2',
           'событие одно (повтор не считается), номер нормализован')
        ok(rr and 'добавлен' in (rr[0]['katalog_itog'] or ''), 'в каталог: %s' % (rr[0]['katalog_itog'] if rr else '-'))
        kk = kat.execute("select * from contact where inn=? and source like 'от продавца%'", (A[2],)).fetchall()
        ok(len(kk) == 1 and kk[0]['role'] == 'главный инженер' and kk[0]['is_tech'] == 1 and kk[0]['has_role'] == 1
           and kk[0]['person'] == 'Тестов Тест Тестович' and kk[0]['value'] == '+74950000000',
           'контакт в каталоге: роль, тех. ЛПР, ФИО, источник «от продавца»')
        t = poluchit('/centro?inn=' + A[2], PROD).text
        ok('Тестов Тест Тестович' in t and 'от продавца' in t, 'карточка: контакт от продавца виден')
        ok(('inn=' + A[2]) in poluchit('/centro?size=100', PROD).text, 'компания с номером ЛПР осталась в очереди')
        ok(chislo(poluchit('/centro?call_status=lpr_nomer', PROD).text) == 1, 'фильтр «Получен личный номер ЛПР»: 1')
        o = otpravit({'inn': A[3], 'call_result': 'lpr_nomer', 'lpr_fio': 'Тестов', 'lpr_dolzhnost': 'директор', 'lpr_nomer': '12345'})
        ok(o.status_code == 422, 'номер ЛПР без номера – 422')
        o = otpravit({'inn': A[3], 'call_result': 'lpr_nomer', 'lpr_nomer': '+7 495 000-00-01'})
        ok(o.status_code == 422, 'номер ЛПР без ФИО и должности – 422')

        # ---------- причины
        o = otpravit({'inn': A[3], 'call_result': 'ne_ponravilas', 'prichina': 'нет потребности', 'comment': 'fixB-тест не нужно'})
        ok(o.status_code == 303, 'новая причина «нет потребности»: %s' % o.status_code)
        s3 = b.execute('select prichina, call_result from company_state where inn=?', (A[3],)).fetchone()
        k3 = b.execute('select prichina, body from company_comment where inn=? order by id desc limit 1', (A[3],)).fetchone()
        l3 = b.execute("select payload_json from activity_log where inn=? and action='call_saved' order by id desc limit 1", (A[3],)).fetchone()
        ok(s3 and s3[0] == 'нет потребности' and k3 and k3[0] == 'нет потребности'
           and json.loads(l3[0]).get('prichina') == 'нет потребности',
           'причина отдельным полем: состояние, комментарий, журнал')
        o = otpravit({'inn': A[5], 'call_result': 'ne_ponravilas', 'prichina': 'чужая причина'})
        ok(o.status_code == 422, 'причина не из списка – 422')
        # старая запись: причина только в начале текста, колонки нет
        iso = (dt.datetime.utcnow() - dt.timedelta(hours=1)).replace(microsecond=0).isoformat() + '+00:00'
        b.execute('insert into company_comment(inn,username,body,created_at,updated_at) values(?,?,?,?,?)',
                  (A[4], 'meyer2', 'Причина: уже купили у конкурентов. fixB-тест старый', iso, iso))
        b.execute('insert into activity_log(inn,username,action,payload_json,created_at) values(?,?,?,?,?)',
                  (A[4], 'meyer2', 'call_saved', json.dumps({'result': 'ne_ponravilas', 'next_contact': '', 'state_user': 'meyer2'}), iso))
        b.execute("insert into company_state(inn,username,status,last_contact_at,call_result,updated_at) values(?,?,?,?,?,?)",
                  (A[4], 'meyer2', 'processed', iso, 'ne_ponravilas', iso))
        b.commit()
        t = poluchit('/centro', params={'prichina': 'уже купили у конкурентов'}).text
        ok(chislo(t) == 1 and ('inn=' + A[4]) in t, 'старая запись понята разбором текста: %d' % chislo(t))
        t = poluchit('/centro', params={'prichina': 'нет потребности'}).text
        ok(chislo(t) == 1 and ('inn=' + A[3]) in t, 'фильтр директора по новой причине: %d' % chislo(t))
        # старые результаты как раньше
        o = otpravit({'inn': A[5], 'call_result': 'v_rabote', 'comment': 'fixB-тест взял'})
        ok(o.status_code == 303, '«Взял в работу»: %s' % o.status_code)
        ok(('inn=' + A[5]) in poluchit('/centro?call_status=v_rabote', PROD).text
           and ('inn=' + A[5]) not in poluchit('/centro?size=100', PROD).text, '«Взял в работу» уводит из очереди, как раньше')

        # ---------- поиск
        for f in ('+74950000000', '84950000000', '8 (495) 000-00-00', '0000000', '4950000000', '+7 495 000-00-00'):
            t = poluchit('/centro', params={'q': f}).text
            ok(('inn=' + A[2]) in t and 0 < chislo(t) <= 3, 'поиск номера «%s»: %d' % (f, chislo(t)))
        t = poluchit('/centro', params={'q': '8 (495) 000-00-00'}, kak=PROD).text
        ok(('inn=' + A[2]) in t, 'продавец находит свою компанию по номеру')
        # настоящий номер из каталога, у одной компании
        po_kl = {}
        for r in kat.execute("select c.inn, c.value from contact c where c.kind='phone'"):
            d = re.sub(r'\D', '', str(r['value'] or '').split('доб')[0])
            kl = d[1:] if len(d) == 11 and d[0] in '78' else (d if len(d) == 10 else '')
            if kl:
                po_kl.setdefault(kl, set()).add(str(r['inn']))
        naznach = {str(r[0]) for r in b.execute('select inn from company_assignment')}
        kand = [(kl, list(i)[0]) for kl, i in po_kl.items() if len(i) == 1 and list(i)[0] in naznach
                and list(i)[0] not in skryt and kl[0] == '9']
        if kand:
            kl, inn_x = kand[len(kand) // 2]
            formaty = ['+7' + kl, '8' + kl, '8 (%s) %s-%s-%s' % (kl[:3], kl[3:6], kl[6:8], kl[8:]), kl[-7:], kl]
            for i, f in enumerate(formaty):
                t = poluchit('/centro', params={'q': f}).text
                ok(('inn=' + inn_x) in t, 'настоящий номер компании %s, формат %d (+7…, 8…, 8 (…), 7 цифр, 10 цифр): найдено %d'
                   % (inn_x, i + 1, chislo(t)))
        else:
            ok(False, 'не нашлось номера для проверки поиска')
        # город
        gorod = None
        for r in kat.execute('select inn, adres, search_blob, region from company'):
            mm = re.search(r'\bг\.\s*([А-ЯЁ][а-яё]{4,}(?:-[А-ЯЁ]?[а-яё]+)?)', r['adres'] or '')
            if (mm and str(r['inn']) in naznach and str(r['inn']) not in skryt
                    and mm.group(1).lower() not in (r['search_blob'] or '').lower()):
                gorod = (str(r['inn']), mm.group(1))
                break
        if gorod:
            t = poluchit('/centro', params={'q': gorod[1], 'size': 100}).text
            ok(('inn=' + gorod[0]) in t, 'поиск по городу «%s»: найдено %d' % (gorod[1], chislo(t)))
        # ФИО из контактов
        fio = None
        for r in kat.execute("select inn, person from contact where coalesce(person,'')<>'' and source not like 'от продавца%'"):
            fam = str(r['person']).split()[0] if str(r['person']).split() else ''
            if len(fam) >= 5 and str(r['inn']) in naznach and str(r['inn']) not in skryt:
                blob = kat.execute('select search_blob from company where inn=?', (r['inn'],)).fetchone()
                if blob and fam.lower() not in (blob[0] or '').lower():
                    fio = (str(r['inn']), fam)
                    break
        if fio:
            t = poluchit('/centro', params={'q': fio[1], 'size': 100}).text
            ok(('inn=' + fio[0]) in t, 'поиск по фамилии из контактов: найдено %d' % chislo(t))
        t = poluchit('/centro', params={'q': A[0]}).text
        ok(chislo(t) == 1 and ('inn=' + A[0]) in t, 'поиск по ИНН – как раньше: %d' % chislo(t))

        # ---------- фильтры E1
        kol = {r[1] for r in kat.execute('pragma table_info(company)')}
        sost = {str(r[0]): r[1] for r in b.execute('select inn, call_result from company_state')}
        vidno = [r for r in kat.execute('select * from company') if str(r['inn']) in naznach and str(r['inn']) not in skryt
                 and sost.get(str(r['inn']), 'new') not in ('v_rabote', 'ne_ponravilas', 'dubl')]
        if 'pometka_ocheredi' in kol:
            for zn, slovo in (('necel', 'нецелев'), ('nedeyst', 'недейств')):
                ozh = sum(1 for r in vidno if slovo in str(r['pometka_ocheredi'] or '').lower())
                n = chislo(poluchit('/centro', params={'pometka_och': zn}).text)
                ok(n == ozh, 'пометка «%s»: список %d = независимо %d' % (zn, n, ozh))
            ozh = sum(1 for r in vidno if not str(r['pometka_ocheredi'] or '').strip())
            n = chislo(poluchit('/centro', params={'pometka_och': 'bez'}).text)
            ok(n == ozh, 'без пометки: %d = %d' % (n, ozh))
        else:
            print('   (колонки pometka_ocheredi в каталоге нет – фильтр скрыт)')
        if 'bitrix_klient_sc' in kol:
            ozh = sum(1 for r in vidno if str(r['bitrix_klient_sc'] or '').strip() not in ('', '0'))
            n = chislo(poluchit('/centro', params={'klient_sc': '1'}).text)
            ok(n == ozh, 'клиент СЦ: %d = %d' % (n, ozh))
        if 'segment_dop' in kol:
            vse_s = {}
            for r in vidno:
                for s in [x.strip() for x in str(r['segment'] or '').split('|') if x.strip()] + \
                         [x.strip() for x in re.split(r'[|;]', str(r['segment_dop'] or '')) if x.strip()]:
                    vse_s.setdefault(s, set()).add(str(r['inn']))
            for s in list(vse_s)[:3]:
                n = chislo(poluchit('/centro', params={'segment': s, 'segment_dop': '1'}).text)
                ok(n == len(vse_s[s]), 'сегмент «%s» с доп. ОКВЭД: %d = %d' % (s[:30], n, len(vse_s[s])))

        # ---------- статистика
        st = poluchit('/centro/stats').text
        io.open(os.path.join(DROP, 'fixB-stats.html'), 'w', encoding='utf-8').write(st)
        with sales.connect() as conn:
            sv = rcs._svodka_sobytiy(conn, segodnya, segodnya, '')
        m2 = next((s for s in sv['stroki'] if s['kto'] == 'meyer2'), None)
        ok(m2 and m2['lpr'] == 1 and m2['lpr_komp']['n'] == 1 and m2['nedozvon'] == 3 and m2['nedozvon_komp']['n'] == 2,
           'сводка meyer2: номеров ЛПР 1 (1 комп.), недозвонов 3 (2 комп.)')
        ok('id="lpr-nomera"' in st and 'Личные номера ЛПР и недозвоны' in st, 'блок «Личные номера ЛПР и недозвоны»')
        sc = sqlite3.connect('file:%s?mode=ro' % TEST_DB, uri=True)
        sc.row_factory = sqlite3.Row
        sc.execute('attach database ? as centro', ('file:%s?mode=ro' % TEST_KAT,))
        sb = rp._statblok(sc, ADMIN, None, '')
        sc.close()
        z2 = next((z for z in sb['stroki'] if z['username'] == 'meyer2'), None)
        ok(z2 and z2['den']['lpr'] == 1 and z2['den']['nedozvon'] == 3 and z2['vse']['lpr'] == 1,
           'календарный блок: meyer2 номер ЛПР 1, не дозвонился 3')
        tab = re.search(r'<h2>По продавцам</h2>(.*?)</table>', st, re.S)
        tab = tab.group(1) if tab else ''
        ok(tab and 'meyer_admin' not in tab, 'в «По продавцам» нет meyer_admin')
        imena = re.findall(r'#ochered-prodavca">([^<]+)</a>', tab)
        ok(len(imena) == 4 and imena == sorted(imena, key=str.lower), 'продавцы по ФИО, со ссылкой-якорем: %s' % imena)
        ok('id="ochered-prodavca"' in poluchit('/centro/stats?user=meyer2').text, 'у очереди продавца есть якорь')
        bys = dict((n, u) for u, n in re.findall(r'<a href="([^"]*/centro/stats[^"]*)">(сегодня|вчера|7 дней|30 дней|всё время)</a>', st))
        ok('всё время' in bys and 'stat_vse=1' in bys['всё время'] and bys.get('всё время') != bys.get('сегодня'),
           '«всё время» – своя ссылка: %s' % bys.get('всё время', '-'))
        from html import unescape
        tv = poluchit(unescape(bys.get('всё время', '/centro/stats?stat_vse=1')).replace(PUT, '', 1)).text
        ok('за всё время (с ' in tv and '<b>всё время</b>' in tv, '«всё время» открывается и подписан')
        vchera7 = (segodnya - dt.timedelta(days=7)).isoformat()
        tv = poluchit('/centro/stats?stat_ot=%s&stat_data=%s' % (segodnya.isoformat(), vchera7)).text
        ok('позже даты «по»' in tv and 'с %s по %s' % ((segodnya - dt.timedelta(days=7)).strftime('%d.%m.%Y'), segodnya.strftime('%d.%m.%Y')) in tv,
           'перевёрнутые даты: сообщение и переставленный период')
        tv = poluchit('/centro/stats?stat_data=%s' % (segodnya + dt.timedelta(days=5)).isoformat()).text
        ok('ещё не наступила' in tv, 'будущая дата: сообщение')
        tv = poluchit('/centro/stats?stat_data=abc').text
        ok('не распознана' in tv, 'кривая дата: сообщение')
        ok('Получен личный номер ЛПР: Тестов Тест Тестович, главный инженер' in st and 'Не дозвонился' in st, 'лента: новые события')
        # каждая цифра-ссылка = число строк списка
        from html import unescape as un
        ssylki = list(dict.fromkeys((un(u), int(n)) for u, n in re.findall(
            r'<a href="(%s/centro\?[^"]*|%s/centro)">(\d+)</a>' % (PUT, PUT), st)))
        nerav = []
        for u, n in ssylki:
            c = chislo(poluchit(u.replace(PUT, '', 1)).text)
            if c != n:
                nerav.append((u, n, c))
        ok(len(ssylki) >= 20 and not nerav, 'цифры-ссылки статистики: %d, расхождений %d %s' % (len(ssylki), len(nerav), nerav[:4]))
        t = poluchit('/centro', params={'sob': 'lpr_nomer', 'ot': segodnya.isoformat(), 'do': segodnya.isoformat(), 'kto_p': 'meyer2'}).text
        ok(chislo(t) == 1 and 'Получен личный номер ЛПР' in t, 'список директора по событию: 1')
        t = poluchit('/centro', params={'ot': segodnya.isoformat(), 'do': vchera7, 'rez_p': 'v_rabote'}).text
        ok('переставлены' in t and chislo(t) == 1, 'главная: перевёрнутые даты переставлены и сказано об этом (%d)' % chislo(t))

        # ---------- сортировка и CSV
        import csv as _csv
        def csv_stroki(params):
            o = poluchit('/centro/vygruzka.csv', params=params)
            return o, list(_csv.reader(io.StringIO(o.content.decode('utf-8-sig')), delimiter=';'))
        o, rr = csv_stroki({'assigned_user': 'meyer2'})
        ok(o.status_code == 200 and 'text/csv' in o.headers.get('content-type', ''), 'CSV: %s %s' % (o.status_code, o.headers.get('content-type')))
        n_ekr = chislo(poluchit('/centro?assigned_user=meyer2').text)
        ok(len(rr) - 1 == n_ekr, 'CSV: строк %d = в списке %d' % (len(rr) - 1, n_ekr))
        ves = o.content.decode('utf-8-sig')
        ok(not re.search(r'\+7\s?\(?\d|\b8\s?\(\d{3}\)|\b\d{3}-\d{2}-\d{2}\b', ves), 'в CSV нет номеров телефонов')
        o, rr = csv_stroki({'sort': 'vyruchka'})
        iv = rr[0].index('Выручка, млн ₽')
        vv = [float(r[iv].replace(',', '.')) for r in rr[1:] if r[iv]]
        ok(vv == sorted(vv, reverse=True) and len(vv) > 10, 'сортировка по выручке: %d значений по убыванию' % len(vv))
        o, rr = csv_stroki({'sort': 'seychas'})
        ir = rr[0].index('Рабочий час сейчас')
        flagi = [r[ir] for r in rr[1:]]
        ok(flagi == sorted(flagi), 'кому звонить сейчас: сначала «да» (%d), потом «нет»' % flagi.count('да'))
        o, rr = csv_stroki({'sort': 'region'})
        ig = rr[0].index('Регион')
        reg = [r[ig].lower() for r in rr[1:] if r[ig]]
        ok(reg == sorted(reg), 'сортировка по региону')
        o, rr = csv_stroki({})
        ok(len(rr) - 1 == chislo(poluchit('/centro').text), 'CSV без фильтров = «Вся очередь» директора')
        ok(poluchit('/centro/vygruzka.csv', PROD).status_code == 403, 'CSV продавцу – 403')
        t = poluchit('/centro?sort=mestnoe').text
        ok('порядок: местное время' in t or 'Порядок: местное время' in t, 'список с сортировкой подписан')
    b.close()
    kat.close()
    # ---------- рабочие базы не тронуты
    zs = sqlite3.connect('file:%s?mode=ro' % ZH_S, uri=True)
    sledy = zs.execute("select count(*) from company_comment where body like '%fixB-тест%'").fetchone()[0]
    try:
        sledy += zs.execute("select count(*) from zvonok_sobytie where fio like 'Тестов%' or kommentariy like '%fixB-тест%'").fetchone()[0]
    except sqlite3.OperationalError:
        pass
    zs.close()
    zk = sqlite3.connect('file:%s?mode=ro' % ZH_K, uri=True)
    sledy += zk.execute("select count(*) from contact where person='Тестов Тест Тестович'").fetchone()[0]
    zk.close()
    ok(sledy == 0, 'рабочие базы продаж и каталога: следов проверки %d' % sledy)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    raise SystemExit(0 if not plohih[0] else 1)


if '--proverka' in sys.argv or '--bystro' in sys.argv:
    fl = '--proverka' if '--proverka' in sys.argv else '--bystro'
    proverka(sys.argv[sys.argv.index(fl) + 1], fl == '--bystro')


# =========================================================================== боевой прогон
def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)                      # брошенный (старше 25 мин)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


def zapustit_proverku(koren_koda, rezhim, imya_otcheta):
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), rezhim, koren_koda], capture_output=True,
                       timeout=1300, cwd=KOREN, env=sreda)
    vyvod = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-5000:]
    for p in (TEST_DB, TEST_KAT):
        for hvost in ('', '-wal', '-shm'):
            try:
                os.remove(p + hvost)
            except OSError:
                pass
    io.open(os.path.join(DROP, imya_otcheta), 'w', encoding='utf-8').write(vyvod)
    return r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod, vyvod


def kopiya_koda(kuda):
    app = os.path.join(KOREN, 'app')
    for d, dirs, fs in os.walk(app):
        dirs[:] = [x for x in dirs if x not in ('dokaz', '__pycache__')]
        cel = os.path.join(kuda, 'app', os.path.relpath(d, app))
        os.makedirs(cel, exist_ok=True)
        for f in fs:
            shutil.copy2(os.path.join(d, f), os.path.join(cel, f))


def perezapusk():
    p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    for l in p.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
            subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
    time.sleep(2)
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
    lg.write('\n===== перезапуск: fixB поиск, результаты звонка, статистика директора %s =====\n'
             % time.strftime('%Y-%m-%d %H:%M:%S'))
    lg.flush()
    subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg, stderr=subprocess.STDOUT,
                     creationflags=0x00000008 | 0x00000200, close_fds=True, env=sreda)
    import urllib.request
    kod = '?'
    for _ in range(6):
        time.sleep(5)
        try:
            kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            if kod == 200:
                break
        except Exception as e:  # noqa: BLE001
            kod = str(e)[:80]
    return kod


def boevoy():
    vzyat_zamok('fixB')
    try:
        # 1. копия кода, правки в копии, полная проверка на копиях баз
        vremya = os.path.join(KOREN, '_bekap', 'fixB-kod-' + METKA)
        kopiya_koda(vremya)
        log = []
        prov = primenit(os.path.join(vremya, 'app'), log)
        print('--- правки в копии кода:')
        print('\n'.join('   ' + x for x in log))
        if prov:
            print('НЕ ВСЕ ОБЯЗАТЕЛЬНЫЕ ЯКОРЯ НАЙДЕНЫ: %s – боевые файлы не тронуты' % prov)
            return 1
        os.utime(ZAMOK, None)
        uspeh, vyvod = zapustit_proverku(vremya, '--proverka', 'fixB-proverka.txt')
        print('--- полная проверка (копия кода, копии баз):')
        print(vyvod[-3500:])
        if not uspeh:
            print('ПРОВЕРКА НЕ ПРОШЛА – боевые файлы не тронуты')
            return 1
        # 2. боевые файлы: бэкап своих файлов, те же правки, быстрая проверка
        os.makedirs(BEKAP, exist_ok=True)
        app = os.path.join(KOREN, 'app')
        for kl, otn in FAJLY.items():
            shutil.copy2(os.path.join(app, otn), os.path.join(BEKAP, kl + '-' + os.path.basename(otn)))

        def vernut():
            for kl, otn in FAJLY.items():
                shutil.copy2(os.path.join(BEKAP, kl + '-' + os.path.basename(otn)), os.path.join(app, otn))
        log = []
        prov = primenit(app, log)
        print('--- правки в боевых файлах:')
        print('\n'.join('   ' + x for x in log))
        if prov:
            vernut()
            print('ЯКОРЯ В БОЕВЫХ ФАЙЛАХ НЕ СОШЛИСЬ: %s – файлы возвращены из %s' % (prov, BEKAP))
            return 1
        os.utime(ZAMOK, None)
        uspeh, vyvod = zapustit_proverku(KOREN, '--bystro', 'fixB-proverka-boevaya.txt')
        print('--- быстрая проверка боевого кода:')
        print(vyvod[-1500:])
        if not uspeh:
            vernut()
            print('БЫСТРАЯ ПРОВЕРКА НЕ ПРОШЛА – файлы возвращены из %s, перезапуска нет' % BEKAP)
            return 1
        # 3. база продаж: копия, затем только расширение схемы (таблица событий, колонки prichina)
        zh = None
        for l in io.open(os.path.join(KOREN, '.env'), encoding='utf-8'):
            if l.strip().startswith('CENTRO_SALES_DB='):
                zh = l.split('=', 1)[1].strip().strip('"').strip("'")
        kopiya_bazy(zh, os.path.join(BEKAP, os.path.basename(zh)))
        c = sqlite3.connect(zh, timeout=30)
        try:
            do = {t: [r[1] for r in c.execute('pragma table_info(%s)' % t)] for t in ('company_state', 'company_comment')}
            for _ in range(5):
                try:
                    c.execute('CREATE TABLE IF NOT EXISTS zvonok_sobytie (id INTEGER PRIMARY KEY, inn TEXT NOT NULL, '
                              'username TEXT NOT NULL, state_user TEXT NOT NULL, vid TEXT NOT NULL, '
                              "fio TEXT NOT NULL DEFAULT '', dolzhnost TEXT NOT NULL DEFAULT '', nomer TEXT NOT NULL DEFAULT '', "
                              "nomer_10 TEXT NOT NULL DEFAULT '', dob TEXT NOT NULL DEFAULT '', kommentariy TEXT NOT NULL DEFAULT '', "
                              "next_contact TEXT NOT NULL DEFAULT '', katalog_contact_id INTEGER, katalog_itog TEXT NOT NULL DEFAULT '', "
                              'created_at TEXT NOT NULL)')
                    c.execute('CREATE INDEX IF NOT EXISTS ix_zvonok_sobytie_inn ON zvonok_sobytie(inn, vid, created_at)')
                    c.execute('CREATE INDEX IF NOT EXISTS ix_zvonok_sobytie_kto ON zvonok_sobytie(state_user, vid, created_at)')
                    for t in ('company_state', 'company_comment'):
                        if 'prichina' not in do[t]:
                            c.execute('ALTER TABLE %s ADD COLUMN prichina TEXT' % t)
                    c.commit()
                    break
                except sqlite3.OperationalError as e:
                    c.rollback()
                    if 'locked' not in str(e).lower():
                        raise
                    time.sleep(2)
            posle = {t: [r[1] for r in c.execute('pragma table_info(%s)' % t)] for t in ('company_state', 'company_comment')}
            print('--- схема базы продаж: было %s; стало %s; zvonok_sobytie: %s' % (
                {t: 'prichina' in v for t, v in do.items()}, {t: 'prichina' in v for t, v in posle.items()},
                c.execute("select count(*) from sqlite_master where name='zvonok_sobytie'").fetchone()[0]))
        finally:
            c.close()
        # 4. перезапуск
        kod = perezapusk()
        print('перезапущено, вход: %s' % kod)
        print('бэкап файлов и базы продаж: %s' % BEKAP)
        return 0 if kod == 200 else 2
    finally:
        otdat_zamok()


def tolko_proverka():
    """Без замка и без боевых правок: копия кода -> правки -> полная проверка на копиях баз."""
    vremya = os.path.join(KOREN, '_bekap', 'fixB-kod-' + METKA)
    kopiya_koda(vremya)
    log = []
    prov = primenit(os.path.join(vremya, 'app'), log)
    print('\n'.join('   ' + x for x in log if not x.startswith('[ок]')))
    print('правок: %d, не сошлось обязательных: %s' % (len(log), prov))
    if prov:
        return 1
    uspeh, vyvod = zapustit_proverku(vremya, '--proverka', 'fixB-proverka.txt')
    print(vyvod[-5500:])
    shutil.rmtree(vremya, ignore_errors=True)
    return 0 if uspeh else 1


if __name__ == '__main__':
    if '--tolko-proverka' in sys.argv:
        raise SystemExit(tolko_proverka())
    raise SystemExit(boevoy())
