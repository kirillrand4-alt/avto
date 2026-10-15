# -*- coding: utf-8 -*-
r"""fixL (15.10): «Взял в работу ▸ Завести лид в Битрикс» в карточке панели Meyer.

Владелец 15.10: при наведении на «Взял в работу» – подпункт «Завести лид в Битрикс»; окно с редактируемыми полями лида
(заполнены из карточки), справа кнопки-блоки (паспорт, описание, почему покупатель Meyer, каждый ЛПР, реквизиты, метки
Битрикса, история комментариев) – дописывают текст в поле, где стоял курсор; «Создать лид» -> crm.lead.add и обычное
сохранение «Взял в работу»; строка «Лид в Битриксе №… →» в карточке; таблица bitrix_lid в базе продаж; ответственный –
настройка C:\centro2\data\bitrix-lid-nastroyki.json (сейчас «test»: всегда Баданина Ксения, 7981).

Меняется: app/api/routes_centro_sales.py (блок в конце файла), app/templates/centro.html (три якоря),
новый app/templates/_fixL_bitrix_lid.html. Python меняется – нужен перезапуск (только под замком, после stage).
Ссылка вебхука не печатается и не пишется никуда; на stage Битрикс подменён заглушкой (и вебхука в stage нет).

    python3 zapusk_na_servere.py fixL_kod.py --suho       # stage-копия кода + копии баз: «до/после» и проверки с заглушкой
    python3 zapusk_na_servere.py fixL_kod.py --primenit   # под замком: stage -> запись -> перезапуск -> проверка живого кода
    python3 zapusk_na_servere.py fixL_kod.py --proverka   # живой код на копиях баз (заглушка вместо Битрикса)
"""
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
NASTROYKI = os.path.join(KOREN, 'data', 'bitrix-lid-nastroyki.json')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
PORT = 8016
ZAMOK = r'C:\centro2\_zamok.txt'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_bekap', 'fixL-stage')
PRODAVCY = ['meyer%d' % i for i in range(1, 10)]
FAJLY = {'R': 'api/routes_centro_sales.py', 'C': 'templates/centro.html', 'L': 'templates/_fixL_bitrix_lid.html'}
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')
TULSKAYA = '7130001590'

BLOK_ROUTES = r'''

# ===== fixL-bitrix-lid (15.10): «Взял в работу ▸ Завести лид в Битрикс» =====
# Владелец 15.10: подпункт у «Взял в работу» открывает окно с полями лида (заполнены из карточки, правятся),
# «Создать лид» -> crm.lead.add и тут же обычное сохранение «Взял в работу» (sales.save_call – тот же путь,
# та же лента и статистика). Запись о каждой попытке – таблица bitrix_lid базы продаж. Ошибка Битрикса –
# «Взял в работу» НЕ сохраняется. Ссылка вебхука – только из data/bitrix-webhook.secret, нигде не
# печатается и браузеру не отдаётся. Ответственный – настройка data/bitrix-lid-nastroyki.json
# («test» – всегда test_id, сейчас Баданина Ксения 7981; «menedzher» – Bitrix ID менеджера компании).
# Права: менеджер – своя компания, админ – любая назначенная; руководитель (rop) – только видит строку.
import html as _html_fixL
import json as _json_fixL
import threading as _threading_fixL
import urllib.error as _urlerr_fixL
import urllib.request as _urlreq_fixL

from fastapi.responses import JSONResponse as _JSONResponse_fixL

_FIXL_DATA = sales.ROOT / "data"
_FIXL_VEBHUK = _FIXL_DATA / "bitrix-webhook.secret"
_FIXL_NASTROYKI = _FIXL_DATA / "bitrix-lid-nastroyki.json"
_FIXL_PORTAL = "https://bitrix-po22.ru"
_FIXL_PANEL = "https://parsercompressor.online" + BP + "/centro?inn="
_FIXL_PO_UMOLCHANIYU = {
    "otvetstvennyy": "test",            # test | menedzher
    "test_id": 7981,
    "test_fio": "Баданина Ксения",
    "menedzhery": {},                   # логин панели -> {"fio", "bitrix_id"}
    "source_id": "149", "source_nazv": "Маркетинг подогнали",
    "status_id": "NEW", "status_nazv": "Новый лид",
    "torguyushchaya_net": {"UF_CRM_61B6C14B0E2A1": "11198", "UF_CRM_1639366376": "5880"},
}
_FIXL_GRUPPY = [
    ("11789", "Пищевые – с/х"), ("11792", "Пищевые – замороженные продукты"),
    ("11790", "Пищевые – овощи, ягоды, фрукты"), ("11791", "Пищевые – орехи, сухофрукты, снеки"),
    ("11863", "Пищевые – кофе, чай, травы"), ("11793", "Непищевые – пластик"), ("11794", "Непищевые – стекло"),
    ("11795", "Непищевые – минералы"), ("11796", "Непищевые – резина"), ("11797", "Рентгены"),
    ("11798", "Другое"), ("11864", "Нецелевое"),
]
_FIXL_GRUPPA_SLOVA = [
    (r"заморож", "11792"), (r"пластм|пластик|полимер|гранул|вторсыр", "11793"), (r"стекл", "11794"),
    (r"\bруд|\bугол|\bуголь|нерудн|минерал|\bсоль\b|щеб|песок", "11795"), (r"резин|шин", "11796"),
    (r"орех|сухофрукт|снек|семечк", "11791"), (r"ягод|овощ|фрукт|дикорос|гриб", "11790"),
    (r"кофе|\bчай|\bтрав|специ", "11863"),
]
_FIXL_ZAMKI: dict = {}
_FIXL_ZAMKI_Z = _threading_fixL.Lock()


def _fixL_nastroyki() -> dict:
    n = dict(_FIXL_PO_UMOLCHANIYU)
    try:
        d = _json_fixL.loads(_FIXL_NASTROYKI.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            n.update({k: v for k, v in d.items() if not str(k).startswith("_")})
    except (OSError, ValueError):
        pass
    return n


def _fixL_otvetstvennyy(owner: str) -> dict:
    n = _fixL_nastroyki()
    if str(n.get("otvetstvennyy") or "") == "menedzher":
        m = (n.get("menedzhery") or {}).get(owner) or {}
        try:
            bid = int(m.get("bitrix_id") or 0)
        except (TypeError, ValueError):
            bid = 0
        if bid:
            return {"id": bid, "fio": str(m.get("fio") or _fio_dlya_shablona(owner)),
                    "rezhim": "менеджер компании"}
        rezhim = "у менеджера %s нет Bitrix ID в настройке – тестовый ответственный" % owner
    else:
        rezhim = "тестовый режим: все лиды на одного ответственного"
    return {"id": int(n.get("test_id") or 7981), "fio": str(n.get("test_fio") or ""), "rezhim": rezhim}


def _fixL_ensure(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS bitrix_lid ("
        " id INTEGER PRIMARY KEY,"
        " inn TEXT NOT NULL,"
        " lead_id TEXT NOT NULL DEFAULT '',"
        " kto TEXT NOT NULL,"                         # кто завёл (логин панели)
        " kogda TEXT NOT NULL,"                       # UTC ISO
        " state_user TEXT NOT NULL DEFAULT '',"       # чья компания
        " otvetstvennyy_id INTEGER,"
        " otvetstvennyy_fio TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL,"                      # ok | oshibka
        " oshibka TEXT NOT NULL DEFAULT '',"
        " nazvanie TEXT NOT NULL DEFAULT '',"
        " v_rabote_sohraneno INTEGER NOT NULL DEFAULT 0)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_bitrix_lid_inn ON bitrix_lid(inn, status)")


def _fixL_kogda(znach) -> str:
    dt = _msk_vremya(znach)
    return dt.strftime("%d.%m.%Y %H:%M") if dt else str(znach or "")


def fixL_lidy(inn) -> list:
    """Заведённые (успешно) лиды компании – для строки в карточке и для окна."""
    try:
        with sales.connect(bez_teni=True) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bitrix_lid'").fetchone():
                return []
            rows = conn.execute(
                "SELECT lead_id, kto, kogda, otvetstvennyy_fio, otvetstvennyy_id FROM bitrix_lid "
                "WHERE inn=? AND status='ok' ORDER BY id", (sales.normalize_inn(inn),)).fetchall()
    except Exception:  # noqa: BLE001 – строка о лиде не важнее карточки
        return []
    return [{"lead_id": str(r[0]), "url": "%s/crm/lead/details/%s/" % (_FIXL_PORTAL, r[0]),
             "kto": str(r[1]), "kto_fio": _fio_dlya_shablona(r[1]), "kogda": _fixL_kogda(r[2]),
             "otv_fio": str(r[3] or ""), "otv_id": r[4]} for r in rows]


templates.env.globals["fixL_lidy"] = fixL_lidy


def _fixL_dostup(user: dict, inn: str) -> tuple:
    if user.get("rop") or user.get("role") not in ("admin", "sales"):
        raise HTTPException(403, "Руководителю отдела продаж – только просмотр")
    inn = sales.normalize_inn(inn)
    if not inn:
        raise HTTPException(404, "Компания не найдена")
    with sales.connect(bez_teni=True) as conn:
        owner = sales.assignment_owner(conn, inn)
        if not owner or not sales.allowed(conn, user, inn):
            raise HTTPException(404, "Компания не назначена пользователю")
    return inn, owner


def _fixL_kompaniya(inn: str) -> dict:
    try:
        conn = catalog.connect()
    except catalog.CentroDbUnavailable:
        return {}
    try:
        r = conn.execute("SELECT * FROM company WHERE inn=?", (inn,)).fetchone()
        return dict(r) if r else {}
    finally:
        conn.close()


def _fixL_s(x) -> str:
    return str(x if x is not None else "").strip()


def _fixL_mob(x: dict) -> bool:
    return x.get("vid_nomera") == "мобильный" or _fixL_s(x.get("phone_type")) == "мобильный"


def _fixL_zam(dolzh) -> int:
    return 1 if re.search(r"(?i)заместител|\bзам\.|помощник|и\.\s?о\.", dolzh or "") else 0


def _fixL_podpis(x: dict) -> str:
    """Подпись номера, как в карточке: вид · чей («мобильный · ЛПР: первое лицо», «рабочий · приёмная, не ЛПР»)."""
    vid = _fixL_s(x.get("vid_nomera")) or _fixL_s(x.get("phone_type"))
    chuzh = _fixL_s(x.get("chuzhoy_istochnik"))
    if chuzh:
        rol = "с сайта другого юрлица: %s" % chuzh
    elif x.get("lpr"):
        rol = "ЛПР" + ((": " + _fixL_s(x.get("rol_vid"))) if _fixL_s(x.get("rol_vid")) else "")
    else:
        rol = (_fixL_s(x.get("nomer_ne_lichnyy")) or _fixL_s(x.get("rol_vid")) or "без роли") + ", не ЛПР"
    return " · ".join(z for z in (vid, rol) if z)


def _fixL_lyudi(c: dict, kontakty: list, lyudi: list, skrytye: dict) -> list:
    """Люди карточки для кнопок «Контакты»: с ФИО, ЛПР первыми (по уровню), затем руководитель из реквизитов,
    затем остальные. У каждого – лучший номер (мобильный раньше) с подписью и почта."""
    po: dict = {}
    poryadok: list = []

    def vzyat(fio, dolzh):
        k = catalog._kl_fio(fio) or fio.casefold()
        if k not in po:
            po[k] = {"fio": fio, "dolzhnost": dolzh, "tel": "", "tel_podpis": "", "email": "", "lpr": 0,
                     "uroven": 99, "otkuda": "", "_mob": False}
            poryadok.append(k)
        z = po[k]
        if len(fio) > len(z["fio"]):
            z["fio"] = fio
        if dolzh and not z["dolzhnost"]:
            z["dolzhnost"] = dolzh
        return z
    for x in kontakty:
        fio = _fixL_s(x.get("person"))
        if not fio:
            continue
        kind = x.get("kind")
        if kind == "phone" and x.get("value") in skrytye:
            continue
        z = vzyat(fio, _fixL_s(x.get("position")))
        if x.get("lpr") and not _fixL_s(x.get("chuzhoy_istochnik")):
            z["lpr"] = 1
            z["uroven"] = min(z["uroven"], int(x.get("uroven") or 9))
        if kind == "phone" and _fixL_s(x.get("value")):
            mob = _fixL_mob(x)
            if not z["tel"] or (mob and not z["_mob"]):
                z["tel"], z["tel_podpis"], z["_mob"] = _fixL_s(x.get("value")), _fixL_podpis(x), mob
        elif kind == "email" and _fixL_s(x.get("value")) and not z["email"]:
            z["email"] = _fixL_s(x.get("value"))
        elif kind == "sprosit" and not z["tel"]:
            z["tel_podpis"] = "без номера: спросить у приёмной"
    for p in lyudi:
        fio = _fixL_s(p.get("person"))
        if not fio or p.get("privyazka_snyata"):
            continue
        z = vzyat(fio, _fixL_s(p.get("position")))
        if p.get("lpr"):
            z["lpr"] = 1
            z["uroven"] = min(z["uroven"], 9)
        if not z["email"] and _fixL_s(p.get("email")):
            z["email"] = _fixL_pervoe(p.get("email"))
        tel = _fixL_s(p.get("phone"))
        if tel and not z["tel"] and tel not in skrytye:
            z["tel"], z["tel_podpis"] = tel, "номер из списка людей карточки"
    m = re.match(r"^\s*([^()]+?)\s*\(([^,()]+)", _fixL_s(c.get("direktor")))
    if m:
        fio = m.group(1).strip()
        k = catalog._kl_fio(fio) or fio.casefold()
        if k in po:
            po[k]["otkuda"] = po[k]["otkuda"] or "руководитель и по реквизитам"
        else:
            z = vzyat(fio, m.group(2).strip())
            z.update({"lpr": 1, "uroven": 50, "otkuda": "из реквизитов"})
    spisok = [po[k] for k in poryadok]
    spisok.sort(key=lambda z: (0 if z["lpr"] else 1, z["uroven"] if z["lpr"] else 0, _fixL_zam(z["dolzhnost"]),
                               0 if z["tel"] else 1, 0 if z["_mob"] else 1, poryadok.index(
                                   catalog._kl_fio(z["fio"]) or z["fio"].casefold())))
    return [{k: v for k, v in z.items() if not k.startswith("_") and k != "uroven"} for z in spisok[:60]]


def _fixL_nomera(kontakty: list, skrytye: dict) -> list:
    """Все номера компании (как в карточке: ЛПР сверху, затем остальные) с видом и подписью, чей номер."""
    out, bylo = [], set()
    for x in kontakty:
        tel = _fixL_s(x.get("value"))
        if x.get("kind") != "phone" or not tel or tel in skrytye or tel in bylo:
            continue
        bylo.add(tel)
        chey = ", ".join(z for z in (_fixL_s(x.get("person")), _fixL_s(x.get("position"))) if z)
        out.append({"tel": tel, "podpis": _fixL_podpis(x), "chey": chey, "lpr": 1 if x.get("lpr") else 0})
    return out[:80]


def _fixL_gruppa(c: dict) -> str:
    napr = _fixL_s(c.get("meyer_verdikt_napravlenie")).lower()
    if napr in ("рентген", "оба"):
        return "11797"
    tekst = " ".join(_fixL_s(c.get(k)) for k in ("segment", "segment_osn", "otrasl", "segment_meyer7")).lower()
    for rx, g in _FIXL_GRUPPA_SLOVA:
        if re.search(rx, tekst):
            return g
    return "11789"


def _fixL_dengi(v) -> str:
    s = _fixL_s(v)
    try:
        f = float(s.replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return s
    if f >= 100000:
        return ("%.1f млн руб." % (f / 1e6)).replace(".", ",", 1)
    return s


def _fixL_pervoe(v) -> str:
    return next((x.strip() for x in re.split(r"[,;|\s]+", _fixL_s(v)) if x.strip()), "")


def _fixL_bloki(c: dict, kontakty: list, skrytye: dict, user: dict, inn: str) -> list:
    def sobrat(pary):
        return "\n".join("%s: %s" % (n, _fixL_s(z)) for n, z in pary if _fixL_s(z))

    bloki = []
    pasp = sobrat([("Продукция", c.get("produkciya")), ("Сырьё", c.get("pasport_syrye")),
                   ("Оборудование", c.get("pasport_oborudovanie")), ("Упаковка", c.get("pasport_upakovka")),
                   ("Качество", c.get("pasport_kachestvo")), ("Экспорт", c.get("pasport_eksport")),
                   ("Масштаб", c.get("pasport_masshtab"))])
    if pasp:
        bloki.append({"nazv": "Паспорт компании", "tekst": "Паспорт компании:\n" + pasp})
    opis = sobrat([("Описание", c.get("opisanie")), ("Продукция", c.get("produkciya")),
                   ("Мощности", c.get("moshchnosti")), ("Отрасль", c.get("otrasl")),
                   ("Сегмент", c.get("segment"))])
    if opis:
        bloki.append({"nazv": "Описание и продукция / мощности", "tekst": opis})
    verd = _fixL_s(c.get("meyer_verdikt"))
    if verd:
        t = "Покупатель Meyer: %s" % ("да" if verd == "покупатель" else verd)
        if _fixL_s(c.get("meyer_verdikt_napravlenie")):
            t += " – " + _fixL_s(c.get("meyer_verdikt_napravlenie"))
        if _fixL_s(c.get("meyer_verdikt_uverennost")):
            t += " (уверенность: %s)" % _fixL_s(c.get("meyer_verdikt_uverennost"))
        if _fixL_s(c.get("meyer_verdikt_pochemu")):
            t += ". " + _fixL_s(c.get("meyer_verdikt_pochemu"))
        if _fixL_s(c.get("meyer_verdikt_dokaz")):
            t += "\nДоказательство: " + _fixL_s(c.get("meyer_verdikt_dokaz"))[:800]
        bloki.append({"nazv": "Почему покупатель Meyer", "tekst": t})
    rekv = sobrat([("ИНН", inn), ("Руководитель", c.get("direktor")), ("Адрес", c.get("adres")),
                   ("Выручка", ("%s%s" % (_fixL_dengi(c.get("vyruchka_rub")),
                                          (" (%s)" % _fixL_s(c.get("fin_god"))) if _fixL_s(c.get("fin_god")) else ""))
                    if _fixL_s(c.get("vyruchka_rub")) else ""),
                   ("Сотрудников", ("%s%s" % (_fixL_s(c.get("ssch")),
                                              (" (%s)" % _fixL_s(c.get("ssch_god"))) if _fixL_s(c.get("ssch_god")) else ""))
                    if _fixL_s(c.get("ssch")) else ""),
                   ("ОКВЭД", c.get("okved")), ("Статус", c.get("status_egrul")), ("Сайт", c.get("sayt"))])
    bloki.append({"nazv": "Реквизиты", "tekst": "Реквизиты:\n" + rekv})
    bx = []
    if _fixL_s(c.get("bitrix_metki")):
        bx.append("Метки Битрикса: " + _fixL_s(c.get("bitrix_metki")))
    for s in _fixL_s(c.get("bitrix_metki_podrobno")).split(" | "):
        if s.strip():
            bx.append(s.strip())
    if _fixL_s(c.get("bitrix_kc_info")):
        bx.append("Битрикс: " + _fixL_s(c.get("bitrix_kc_info"))[:600])
    if bx:
        bloki.append({"nazv": "Метки Битрикса", "tekst": "\n".join(bx)})
    with sales.connect(bez_teni=True) as conn:
        komm = [dict(r) for r in conn.execute(
            "SELECT username, body, created_at FROM company_comment WHERE inn=? ORDER BY created_at, id", (inn,))
            if user.get("role") == "admin" or r["username"] == user.get("username")]
    if komm:
        bloki.append({"nazv": "История комментариев (%d)" % len(komm), "tekst": "История комментариев:\n" + "\n".join(
            "%s %s: %s" % (_fixL_kogda(k["created_at"]), _fio_dlya_shablona(k["username"]), _fixL_s(k["body"]))
            for k in komm)})
    return bloki


@router.get("/centro/bitrix-lid/dannye")
def fixL_dannye(request: Request, inn: str = "", user=Depends(current_user)):
    inn, owner = _fixL_dostup(user, inn)
    c = _fixL_kompaniya(inn)
    if not c:
        raise HTTPException(404, "Компании нет в каталоге")
    try:
        kontakty = catalog.contacts(inn)
    except catalog.CentroDbUnavailable:
        kontakty = []
    skrytye = sales.hidden_for(inn).get("phone") or {}
    try:
        lyudi = catalog.persons(inn)
    except catalog.CentroDbUnavailable:
        lyudi = []
    nazv = _fixL_s(c.get("predpriyatie")) or inn
    verd = _fixL_s(c.get("meyer_verdikt"))
    kom = ["ИНН %s" % inn]
    if verd:
        kom.append("Покупатель Meyer: %s%s%s" % (
            "да" if verd == "покупатель" else verd,
            (" – " + _fixL_s(c.get("meyer_verdikt_napravlenie"))) if _fixL_s(c.get("meyer_verdikt_napravlenie")) else "",
            (". " + _fixL_s(c.get("meyer_verdikt_pochemu"))) if _fixL_s(c.get("meyer_verdikt_pochemu")) else ""))
    kom.append("Карточка в панели: %s%s" % (_FIXL_PANEL, inn))
    otv = _fixL_otvetstvennyy(owner)
    n = _fixL_nastroyki()
    return {
        "inn": inn,
        "polya": {
            "title": "%s (обзвон Meyer)" % nazv, "company_title": nazv,
            # владелец 15.10: ФИО, должность, телефон, почта – пустые; выбор кнопками «Контакты» / «Номера»
            # 15.10 (2): «ФИО, должность» – одно поле (должность Битрикс в лиде не показывает)
            "fio": "", "phone": "", "email": "", "web": _fixL_pervoe(c.get("sayt")),
            "address": _fixL_s(c.get("adres")), "region": _fixL_s(c.get("region")),
            "gruppa": _fixL_gruppa(c), "comments": "\n".join(kom),
        },
        "gruppy": _FIXL_GRUPPY,
        "kontakty": _fixL_lyudi(c, kontakty, lyudi, skrytye),
        "nomera": _fixL_nomera(kontakty, skrytye),
        "bloki": _fixL_bloki(c, kontakty, skrytye, user, inn),
        "lidy": fixL_lidy(inn),
        "tolko_chtenie": {
            "istochnik": "%s (%s)" % (n.get("source_nazv"), n.get("source_id")),
            "stadiya": "%s (%s)" % (n.get("status_nazv"), n.get("status_id")),
            "otvetstvennyy": "%s (Bitrix id %s) – %s" % (otv["fio"], otv["id"], otv["rezhim"]),
            "torguyushchaya": "Нет (оба поля «Торгующая компания?»)",
            "menedzher": _fio_dlya_shablona(owner),
        },
    }


def _fixL_html(tekst: str) -> str:
    """Комментарий для Битрикса: текст -> HTML (экранирование, ссылки, переносы)."""
    t = _html_fixL.escape(tekst or "", quote=True)
    t = re.sub(r"(https?://[^\s<]+)", lambda m: '<a href="%s">%s</a>' % (m.group(1), m.group(1)), t)
    return t.replace("\r\n", "\n").replace("\n", "<br>")


def _fixL_bitrix_vyzov(metod: str, dannye: dict) -> dict:
    """Вызов REST Битрикса входящим вебхуком. Ссылка – только из файла на сервере."""
    try:
        put = _FIXL_VEBHUK.read_text(encoding="utf-8").strip()
    except OSError:
        raise RuntimeError("на сервере не настроен вебхук Битрикса")
    if not put.endswith("/"):
        put += "/"
    zapros = _urlreq_fixL.Request(put + metod + ".json", data=_json_fixL.dumps(dannye).encode("utf-8"),
                                  headers={"Content-Type": "application/json"})
    try:
        with _urlreq_fixL.urlopen(zapros, timeout=30) as r:
            return _json_fixL.loads(r.read().decode("utf-8"))
    except _urlerr_fixL.HTTPError as e:
        try:
            return _json_fixL.loads(e.read().decode("utf-8") or "{}") or {"error": "HTTP %s" % e.code}
        except ValueError:
            return {"error": "HTTP %s" % e.code, "error_description": ""}


def _fixL_chisto(s) -> str:
    """Текст ошибки без ссылки вебхука и без пути /rest/…"""
    t = str(s or "")
    try:
        put = _FIXL_VEBHUK.read_text(encoding="utf-8").strip()
        if put:
            t = t.replace(put, "<вебхук>").replace(put.rstrip("/"), "<вебхук>")
    except OSError:
        pass
    return re.sub(r"https?://\S*/rest/\S*", "<вебхук>", t)[:500]


def _fixL_zapis(inn, lead_id, user, owner, otv, status, oshibka, nazvanie) -> int:
    with sales.connect(bez_teni=True) as conn:
        _fixL_ensure(conn)
        cur = conn.execute(
            "INSERT INTO bitrix_lid(inn, lead_id, kto, kogda, state_user, otvetstvennyy_id, otvetstvennyy_fio, "
            "status, oshibka, nazvanie) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (inn, str(lead_id or ""), user.get("username", ""), sales.utcnow(), owner, otv["id"], otv["fio"],
             status, oshibka or "", (nazvanie or "")[:300]))
        return int(cur.lastrowid)


def _fixL_imya(fio, dolzh, last_name="", name="", second_name="") -> str:
    """NAME лида: «ФИО, должность». Старое окно шлёт ФИО и должность (или фамилию/имя/отчество) раздельно – склеиваем."""
    f = _fixL_s(fio) or " ".join(_fixL_s(z) for z in (last_name, name, second_name) if _fixL_s(z))
    dl = _fixL_s(dolzh)
    if dl and dl.casefold() not in f.casefold():
        f = ", ".join(z for z in (f, dl) if z)
    return f[:255]


def _fixL_otvet(kod: int, **d):
    return _JSONResponse_fixL(status_code=kod, content=d)


@router.post("/centro/bitrix-lid", dependencies=[Depends(_same_origin)])
def fixL_sozdat_lid(
    request: Request,
    inn: str = Form(...),
    title: str = Form(""), company_title: str = Form(""),
    fio: str = Form(""), post: str = Form(""), dolzhnost: str = Form(""),   # post/dolzhnost – старые окна
    last_name: str = Form(""), name: str = Form(""), second_name: str = Form(""),   # старые окна (до 15.10)
    phone: str = Form(""), email: str = Form(""), web: str = Form(""),
    address: str = Form(""), region: str = Form(""), gruppa: str = Form(""), comments: str = Form(""),
    comment: str = Form(""), next_contact_at: str = Form(""), povtor: str = Form(""),
    user=Depends(current_user),
):
    inn, owner = _fixL_dostup(user, inn)
    title = title.strip()
    if not title:
        return _fixL_otvet(422, ok=False, oshibka="Название лида не может быть пустым")
    if gruppa not in dict(_FIXL_GRUPPY):
        return _fixL_otvet(422, ok=False, oshibka="Выберите группу товара (MEYER)")
    if len(comments) > 20000 or len(comment) > 5000:
        return _fixL_otvet(422, ok=False, oshibka="Слишком длинный комментарий")
    with _FIXL_ZAMKI_Z:
        zamok = _FIXL_ZAMKI.setdefault(inn, _threading_fixL.Lock())
    if not zamok.acquire(blocking=False):
        return _fixL_otvet(409, ok=False, oshibka="Лид по этой компании уже отправляется – подождите несколько секунд")
    try:
        prezhnie = fixL_lidy(inn)
        if prezhnie and povtor != "1":
            return _fixL_otvet(409, ok=False, nuzhno_podtverzhdenie=True, lidy=prezhnie,
                               oshibka="По этой компании лид уже заводили – подтвердите, что нужен ещё один")
        n = _fixL_nastroyki()
        otv = _fixL_otvetstvennyy(owner)
        tel = phone.strip()
        cifry = re.sub(r"\D", "", tel)
        polya = {
            "TITLE": title[:255], "COMPANY_TITLE": company_title.strip()[:255],
            # владелец 15.10: «Имя» в Битриксе показывало только имя, должность Битрикс не показывает –
            # одно поле «ФИО, должность» целиком в NAME; LAST_NAME, SECOND_NAME, POST не заполняются
            "NAME": _fixL_imya(fio, post or dolzhnost, last_name, name, second_name),
            "ADDRESS": address.strip()[:1000], "UF_CRM_68B688D287BE4": region.strip()[:255],
            "UF_CRM_1711628077": gruppa, "COMMENTS": _fixL_html(comments.strip()),
            "SOURCE_ID": str(n.get("source_id") or "149"), "SOURCE_DESCRIPTION": "Панель обзвона Meyer",
            "STATUS_ID": str(n.get("status_id") or "NEW"), "ASSIGNED_BY_ID": otv["id"],
        }
        for kod, znach in (n.get("torguyushchaya_net") or {}).items():
            polya[kod] = str(znach)
        if tel:
            mob = (len(cifry) == 11 and cifry[:2] in ("79", "89")) or (
                len(cifry) == 12 and cifry.startswith("375") and cifry[3:5] in ("25", "29", "33", "44"))
            polya["PHONE"] = [{"VALUE": tel, "VALUE_TYPE": "MOBILE" if mob else "WORK"}]
        if email.strip():
            polya["EMAIL"] = [{"VALUE": email.strip(), "VALUE_TYPE": "WORK"}]
        if web.strip():
            polya["WEB"] = [{"VALUE": web.strip(), "VALUE_TYPE": "WORK"}]
        try:
            otvet = _fixL_bitrix_vyzov("crm.lead.add", {"fields": polya, "params": {"REGISTER_SONET_EVENT": "Y"}})
        except Exception as exc:  # noqa: BLE001 – сеть, таймаут, нет вебхука
            msg = "Битрикс недоступен (%s: %s)" % (type(exc).__name__, _fixL_chisto(exc))
            _fixL_zapis(inn, "", user, owner, otv, "oshibka", msg, title)
            return _fixL_otvet(502, ok=False, oshibka=msg + ". «Взял в работу» не сохранён – нажмите «Повторить».")
        lead_id = ""
        if isinstance(otvet, dict) and not otvet.get("error"):
            lead_id = _fixL_s(otvet.get("result"))
        if not lead_id.isdigit():
            if isinstance(otvet, dict):
                opis = _fixL_s(otvet.get("error_description")) or _fixL_s(otvet.get("error")) or "пустой ответ"
                if otvet.get("error") and otvet.get("error_description"):
                    opis = "%s (%s)" % (_fixL_s(otvet.get("error_description")), _fixL_s(otvet.get("error")))
            else:
                opis = "непонятный ответ"
            msg = "Битрикс не создал лид: %s" % _fixL_chisto(opis)
            _fixL_zapis(inn, "", user, owner, otv, "oshibka", msg, title)
            return _fixL_otvet(502, ok=False, oshibka=msg + ". «Взял в работу» не сохранён – можно поправить поля и нажать «Повторить».")
        rid = _fixL_zapis(inn, lead_id, user, owner, otv, "ok", "", title)
        dop = "Заведён лид в Битриксе №%s" % lead_id
        tekst = comment.strip()
        tekst = (tekst[:5000 - len(dop) - 1] + "\n" + dop) if tekst else dop
        osh = ""
        try:
            sales.save_call(user, inn, "v_rabote", next_contact_at, tekst)
        except PermissionError:
            osh = "компания не назначена пользователю"
        except ValueError as exc:
            osh = str(exc)
        with sales.connect(bez_teni=True) as conn:
            conn.execute("UPDATE bitrix_lid SET v_rabote_sohraneno=?, oshibka=? WHERE id=?",
                         (0 if osh else 1, ("«Взял в работу» не сохранён: " + osh) if osh else "", rid))
        return _fixL_otvet(200, ok=True, lead_id=lead_id, url="%s/crm/lead/details/%s/" % (_FIXL_PORTAL, lead_id),
                           kto=_fio_dlya_shablona(user.get("username")), otvetstvennyy=otv["fio"],
                           sohraneno=not osh,
                           kartochka="%s/centro?%sinn=%s" % (BP, "" if osh else "call_status=v_rabote&", inn),
                           preduprezhdenie=("Лид создан, но «Взял в работу» не сохранён: %s" % osh) if osh else "")
    finally:
        zamok.release()
# ===== /fixL-bitrix-lid =====
'''
SHABLON_LID = r'''{# fixL-bitrix-lid (15.10): окно «Завести лид в Битрикс» – подпункт у «Взял в работу». Только менеджер (своя компания) и админ;
   руководителю отдела продаж окна нет. Поля заполняет сервер (/centro/bitrix-lid/dannye), правятся; «Создать лид» –
   /centro/bitrix-lid: crm.lead.add и сохранение «Взял в работу» тем же путём, что обычная отметка. #}
{% if fixL_lidy is defined and company and user and user.role in ('admin', 'sales') and not user.rop %}
<div class="fixL-okno" id="fixL-okno" hidden data-bp="{{ base_path }}" data-inn="{{ company.inn }}" data-qs="{{ query_string }}">
  <div class="fixL-fon" data-zakryt></div>
  <div class="fixL-dialog" role="dialog" aria-modal="true" aria-labelledby="fixL-zag">
    <div class="fixL-shapka"><h3 id="fixL-zag">Завести лид в Битрикс</h3><span class="fixL-komp">{{ company.predpriyatie or company.inn }}</span>
      <button type="button" class="fixL-x" data-zakryt aria-label="Закрыть">×</button></div>
    <div class="fixL-telo">
      <form class="fixL-forma" autocomplete="off" novalidate>
        <p class="fixL-zagruzka">Загружаю данные карточки…</p>
        <div class="fixL-uzhe" hidden></div>
        <div class="fixL-polya" hidden>
          <label class="shir">Название лида<input name="title" maxlength="255"></label>
          <label class="shir">Название компании<input name="company_title" maxlength="255"></label>
          <label class="shir">ФИО, должность<input name="fio" maxlength="255" placeholder="выберите справа в «Контактах» или впишите: Иванов Иван Иванович, главный инженер"></label>
          <label>Телефон<input name="phone" maxlength="60" placeholder="«Контакты» или «Номера» справа"></label>
          <label>E-mail<input name="email" maxlength="200"></label>
          <label>Сайт<input name="web" maxlength="300"></label>
          <label>Регион<input name="region" maxlength="255"></label>
          <label class="shir">Адрес<input name="address" maxlength="1000"></label>
          <label class="shir">Группа товара (MEYER)<select name="gruppa"></select></label>
          <label class="shir">Комментарий в Битрикс<textarea name="comments" rows="7" maxlength="20000"></textarea></label>
          <dl class="fixL-tolko shir">
            <div><dt>Источник</dt><dd data-t="istochnik"></dd></div>
            <div><dt>Стадия</dt><dd data-t="stadiya"></dd></div>
            <div><dt>Ответственный</dt><dd data-t="otvetstvennyy"></dd></div>
            <div><dt>Торгующая компания?</dt><dd data-t="torguyushchaya"></dd></div>
          </dl>
          <p class="fixL-primech shir">Вместе с лидом сохранится результат «Взял в работу» с комментарием из формы звонка
            (как обычное «Сохранить»). Если Битрикс ответит ошибкой – ничего не сохранится.</p>
        </div>
        <div class="fixL-oshibka" hidden role="alert"></div>
        <div class="fixL-gotovo" hidden></div>
        <div class="fixL-knopki">
          <button type="submit" class="primary-button fixL-sozdat" disabled>Создать лид</button>
          <button type="button" class="action-button fixL-otmena" data-zakryt>Отмена</button>
        </div>
      </form>
      <aside class="fixL-bloki">
        <p class="fixL-bloki-zag"><b>Контакты</b> – клик заменяет «ФИО, должность», телефон и почту (нет номера или почты – поле не трогается):</p>
        <div class="fixL-spisok fixL-kontakty"></div>
        <p class="fixL-bloki-zag"><b>Номера</b> – клик заменяет только телефон:</p>
        <div class="fixL-spisok fixL-nomera"></div>
        <p class="fixL-bloki-zag"><b>Дописать</b> в поле, где стоял курсор (по умолчанию – в комментарий):</p>
        <div class="fixL-bloki-spisok"></div>
      </aside>
    </div>
  </div>
</div>
<style>
.fixL-okno[hidden]{display:none}
.fixL-okno{position:fixed;inset:0;z-index:200;display:flex;align-items:flex-start;justify-content:center;padding:24px 16px;overflow:auto}
.fixL-fon{position:fixed;inset:0;background:rgba(15,23,42,.45)}
.fixL-dialog{position:relative;background:#fff;border-radius:10px;box-shadow:0 18px 50px rgba(15,23,42,.35);width:min(1180px,100%);
  color:var(--navy,#16233a);font-size:14px}
.fixL-shapka{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid #e3e8ef}
.fixL-shapka h3{margin:0;font-size:18px}
.fixL-komp{color:#5b6b80;font-size:13px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fixL-x{border:0;background:transparent;font-size:24px;line-height:1;cursor:pointer;color:#5b6b80;padding:0 4px}
.fixL-telo{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:0}
.fixL-forma{padding:14px 18px;display:grid;gap:10px;align-content:start}
.fixL-polya{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 12px}
.fixL-polya[hidden]{display:none}
.fixL-polya label{display:grid;gap:3px;font-size:12px;color:#5b6b80}
.fixL-polya .shir{grid-column:1/-1}
.fixL-polya input,.fixL-polya select,.fixL-polya textarea{font:inherit;font-size:14px;color:#16233a;border:1px solid #c9d2dd;border-radius:6px;padding:6px 8px;width:100%;box-sizing:border-box;background:#fff}
.fixL-polya textarea{resize:vertical;min-height:140px}
.fixL-polya input:focus,.fixL-polya textarea:focus,.fixL-polya select:focus{outline:2px solid #9db8ff;border-color:#6d8fe8}
.fixL-polya .fixL-posl{box-shadow:0 0 0 2px #ffd36a}
.fixL-tolko{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 12px;margin:0;background:#f5f7fa;border:1px solid #e3e8ef;border-radius:6px;padding:8px 10px}
.fixL-tolko dt{font-size:11px;color:#6b7a8f}.fixL-tolko dd{margin:0;font-size:13px}
.fixL-primech{margin:0;font-size:12px;color:#6b7a8f}
.fixL-uzhe{background:#fff7e0;border:1px solid #f0d58a;border-radius:6px;padding:8px 10px;font-size:13px}
.fixL-uzhe[hidden],.fixL-oshibka[hidden],.fixL-gotovo[hidden]{display:none}
.fixL-uzhe label{display:flex;gap:6px;align-items:center;margin-top:6px;font-weight:600}
.fixL-oshibka{background:#fdecea;border:1px solid #f1b0aa;color:#8a1c12;border-radius:6px;padding:8px 10px;font-size:13px}
.fixL-gotovo{background:#e8f6ee;border:1px solid #b7e1c7;color:#17663a;border-radius:6px;padding:10px 12px;font-size:14px}
.fixL-gotovo a{font-weight:700}
.fixL-knopki{display:flex;gap:8px;flex-wrap:wrap}
.fixL-knopki button[disabled]{opacity:.6;cursor:wait}
.fixL-bloki{min-width:0;border-left:1px solid #e3e8ef;padding:14px 14px;background:#fafbfc;border-radius:0 0 10px 0;display:grid;grid-template-columns:minmax(0,1fr);gap:6px;align-content:start;max-height:78vh;overflow-y:auto;overflow-x:hidden}
.fixL-bloki-zag{margin:0 0 4px;font-size:12px;color:#6b7a8f}
.fixL-bloki-spisok{display:grid;grid-template-columns:minmax(0,1fr);gap:6px;min-width:0}
.fixL-blok{display:block;width:100%;min-width:0;overflow:hidden;box-sizing:border-box;text-align:left;font:inherit;font-size:13px;border:1px solid #c9d2dd;background:#fff;border-radius:6px;padding:6px 8px;cursor:pointer;color:#16233a}
.fixL-blok:hover{background:#eef0fb;border-color:#9fb0d8}
.fixL-blok.lpr{border-left:3px solid #2f9e62}
.fixL-blok small{display:block;color:#6b7a8f;font-size:11px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fixL-blok.vstavlen{background:#e8f6ee}
.fixL-spisok{display:grid;grid-template-columns:minmax(0,1fr);gap:5px;min-width:0;max-height:30vh;overflow-y:auto;overscroll-behavior:contain;padding-right:2px}
.fixL-spisok .fixL-pusto{margin:0;font-size:12px;color:#6b7a8f}
.fixL-kn{display:block;width:100%;min-width:0;box-sizing:border-box;text-align:left;font:inherit;font-size:13px;border:1px solid #c9d2dd;background:#fff;border-radius:6px;padding:5px 8px;cursor:pointer;color:#16233a}
.fixL-kn:hover{background:#eef0fb;border-color:#9fb0d8}
.fixL-kn.lpr{border-left:3px solid #2f9e62}
.fixL-kn.vybran{background:#e8f6ee;border-color:#9bd3b3}
.fixL-kn b{font-weight:600}
.fixL-kn span,.fixL-kn small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fixL-kn span{font-size:12px;color:#3d4b60}
.fixL-kn small{font-size:11px;color:#6b7a8f}
.fixL-kn b .fixL-metka{display:inline-block;margin-left:4px;font-size:10px;padding:0 4px;border-radius:3px;background:#fff3cd;color:#7a5b00;vertical-align:1px}
.fixL-polya .fixL-zameneno{background:#fff9db}
body.fixL-otkryto{overflow:hidden}
.fixL-mob{margin:0;font-size:13px;grid-column:1/-1}
.fixL-mob[hidden]{display:none}
.fixL-mob button{border:0;background:transparent;color:#2346b5;text-decoration:underline;cursor:pointer;font:inherit;padding:0}
@media(max-width:860px){.fixL-telo{grid-template-columns:1fr}.fixL-bloki{border-left:0;border-top:1px solid #e3e8ef;max-height:none}
  .fixL-polya,.fixL-tolko{grid-template-columns:1fr}.fixL-okno{padding:8px}}
</style>
<script>
(function () {
  var okno = document.getElementById('fixL-okno');
  if (!okno) return;
  var bp = okno.dataset.bp || '', inn = okno.dataset.inn, qs = okno.dataset.qs || '';
  var forma = okno.querySelector('.fixL-forma');
  var polyaBlok = forma.querySelector('.fixL-polya');
  var zagr = forma.querySelector('.fixL-zagruzka');
  var uzhe = forma.querySelector('.fixL-uzhe');
  var osh = forma.querySelector('.fixL-oshibka');
  var gotovo = forma.querySelector('.fixL-gotovo');
  var knSozdat = forma.querySelector('.fixL-sozdat');
  var knOtmena = forma.querySelector('.fixL-otmena');
  var spisok = okno.querySelector('.fixL-bloki-spisok');
  var komm = forma.querySelector('textarea[name=comments]');
  var rabForma = document.querySelector('form.work-form');
  var posl = null, zagruzheno = false, otpravka = false, sdelano = false, nuzhnoPodtv = false, kudaPosle = '';

  function rabKomm() {
    var t = rabForma && rabForma.querySelector('textarea[name=comment]');
    return t ? t.value.trim() : '';
  }
  function pokazatOsh(t) { osh.textContent = t; osh.hidden = !t; }
  function lidyHtml(lidy) {
    return lidy.map(function (l) {
      var a = document.createElement('a');
      a.href = l.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = 'Лид №' + l.lead_id;
      return a.outerHTML + ' – ' + (l.kto_fio || l.kto || '') + ', ' + (l.kogda || '');
    }).join('<br>');
  }
  function pokazatUzhe(lidy) {
    if (!lidy || !lidy.length) { uzhe.hidden = true; nuzhnoPodtv = false; return; }
    nuzhnoPodtv = true;
    uzhe.innerHTML = '<b>По этой компании лид уже заводили:</b><br>' + lidyHtml(lidy) +
      '<label><input type="checkbox" name="povtor" value="1"> Да, завести ещё один лид</label>';
    uzhe.hidden = false;
  }
  function otkryt() {
    okno.hidden = false;
    document.body.classList.add('fixL-otkryto');
    if (!zagruzheno) zagruzit();
  }
  function zakryt() {
    if (otpravka) return;
    okno.hidden = true;
    document.body.classList.remove('fixL-otkryto');
    /* после лида компания уже во вкладке «Взял в работу» – туда и карточка */
    if (sdelano) location.href = kudaPosle || (bp + '/centro?inn=' + encodeURIComponent(inn) + (qs ? '&' + qs : ''));
  }
  okno.querySelectorAll('[data-zakryt]').forEach(function (b) { b.addEventListener('click', zakryt); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !okno.hidden) zakryt(); });

  function zagruzit() {
    zagr.hidden = false; zagr.textContent = 'Загружаю данные карточки…';
    fetch(bp + '/centro/bitrix-lid/dannye?inn=' + encodeURIComponent(inn), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return {r: r, d: d}; }); })
      .then(function (x) {
        if (!x.r.ok) { zagr.textContent = 'Не удалось загрузить данные: ' + (x.d.detail || ('ошибка ' + x.r.status)); return; }
        var d = x.d, p = d.polya || {};
        var sel = forma.querySelector('select[name=gruppa]');
        sel.innerHTML = '';
        (d.gruppy || []).forEach(function (g) { var o = document.createElement('option'); o.value = g[0]; o.textContent = g[1]; sel.appendChild(o); });
        Object.keys(p).forEach(function (k) { var el = forma.elements[k]; if (el) el.value = p[k] || ''; });
        var rk = rabKomm();
        if (rk) komm.value = komm.value + '\nКомментарий менеджера: ' + rk;
        var t = d.tolko_chtenie || {};
        forma.querySelectorAll('[data-t]').forEach(function (dd) { dd.textContent = t[dd.dataset.t] || '–'; });
        stroitKontakty(d.kontakty || [], d.nomera || []);
        spisok.innerHTML = '';
        (d.bloki || []).forEach(function (b) {
          var kn = document.createElement('button');
          kn.type = 'button'; kn.className = 'fixL-blok' + (b.lpr ? ' lpr' : '');
          kn.textContent = b.nazv;
          var m = document.createElement('small'); m.textContent = (b.tekst || '').replace(/\s+/g, ' ').slice(0, 90); kn.appendChild(m);
          kn.addEventListener('mousedown', function (e) { e.preventDefault(); });
          kn.addEventListener('click', function () { vstavit(b.tekst || ''); kn.classList.add('vstavlen'); });
          spisok.appendChild(kn);
        });
        pokazatUzhe(d.lidy);
        zagr.hidden = true; polyaBlok.hidden = false; knSozdat.disabled = false; zagruzheno = true;
        posl = komm; komm.classList.add('fixL-posl');
      })
      .catch(function () { zagr.textContent = 'Нет связи с панелью – закройте окно и попробуйте ещё раз.'; });
  }
  /* «Контакты» и «Номера»: клик ЗАМЕНЯЕТ значения полей (не дописывает) */
  function postavit(imya, znach) {
    var el = forma.elements[imya];
    if (!el) return;
    el.value = znach || '';
    el.classList.add('fixL-zameneno');
    setTimeout(function () { el.classList.remove('fixL-zameneno'); }, 1200);
  }
  function knopka(klass, stroki, naKlik) {
    var kn = document.createElement('button');
    kn.type = 'button'; kn.className = 'fixL-kn ' + klass;
    stroki.forEach(function (s, i) {
      if (!s || !s[0]) return;
      var el = document.createElement(i === 0 ? 'b' : (s[1] || 'span'));
      el.textContent = s[0];
      if (i === 0 && s[2]) { var m = document.createElement('span'); m.className = 'fixL-metka'; m.textContent = s[2]; kn.appendChild(el); el.appendChild(m); return; }
      kn.appendChild(el);
    });
    kn.addEventListener('mousedown', function (e) { e.preventDefault(); });
    kn.addEventListener('click', function () {
      kn.parentNode.querySelectorAll('.vybran').forEach(function (x) { x.classList.remove('vybran'); });
      kn.classList.add('vybran'); naKlik();
    });
    return kn;
  }
  function stroitKontakty(lyudi, nomera) {
    var sk = okno.querySelector('.fixL-kontakty'), sn = okno.querySelector('.fixL-nomera');
    sk.innerHTML = ''; sn.innerHTML = '';
    lyudi.forEach(function (z) {
      sk.appendChild(knopka(z.lpr ? 'lpr' : '', [
        [z.fio, '', z.otkuda || ''],
        [z.dolzhnost, 'span'],
        [z.tel ? (z.tel + (z.tel_podpis ? ' · ' + z.tel_podpis : '')) : (z.tel_podpis || 'номера нет'), 'small'],
        [z.email, 'small']
      ], function () {
        postavit('fio', z.dolzhnost ? z.fio + ', ' + z.dolzhnost : z.fio);
        if (z.tel) postavit('phone', z.tel);
        if (z.email) postavit('email', z.email);
      }));
    });
    nomera.forEach(function (n) {
      sn.appendChild(knopka(n.lpr ? 'lpr' : '', [
        [n.tel, ''], [n.podpis, 'span'], [n.chey, 'small']
      ], function () { postavit('phone', n.tel); }));
    });
    if (!lyudi.length) sk.innerHTML = '<p class="fixL-pusto">Людей с ФИО в карточке нет.</p>';
    if (!nomera.length) sn.innerHTML = '<p class="fixL-pusto">Номеров в карточке нет.</p>';
  }
  forma.addEventListener('focusin', function (e) {
    var el = e.target;
    if (el.matches && el.matches('.fixL-polya input, .fixL-polya textarea')) {
      if (posl) posl.classList.remove('fixL-posl');
      posl = el; el.classList.add('fixL-posl');
    }
  });
  function vstavit(t) {
    var pole = posl || komm;
    if (pole.tagName === 'TEXTAREA') pole.value = pole.value ? pole.value.replace(/\s+$/, '') + '\n' + t : t;
    else pole.value = pole.value ? pole.value.replace(/\s+$/, '') + ' ' + t.replace(/\s*\n\s*/g, '; ') : t.replace(/\s*\n\s*/g, '; ');
    pole.focus();
    if (pole.tagName === 'TEXTAREA') pole.scrollTop = pole.scrollHeight;
  }
  forma.addEventListener('submit', function (e) {
    e.preventDefault();
    if (otpravka || sdelano || !zagruzheno) return;
    pokazatOsh('');
    if (!forma.elements.title.value.trim()) { pokazatOsh('Название лида не может быть пустым.'); return; }
    var povt = forma.querySelector('input[name=povtor]');
    if (nuzhnoPodtv && !(povt && povt.checked)) { pokazatOsh('Лид уже заводили – отметьте «Да, завести ещё один лид» или закройте окно.'); return; }
    var fd = new URLSearchParams();
    ['title', 'company_title', 'fio', 'phone', 'email', 'web', 'region', 'address', 'gruppa', 'comments']
      .forEach(function (k) { fd.set(k, forma.elements[k].value); });
    fd.set('inn', inn);
    fd.set('comment', rabKomm());
    var nk = rabForma && rabForma.querySelector('input[name=next_contact_at]');
    fd.set('next_contact_at', nk ? nk.value : '');
    if (povt && povt.checked) fd.set('povtor', '1');
    otpravka = true; knSozdat.disabled = true; knOtmena.disabled = true; knSozdat.textContent = 'Отправляю в Битрикс…';
    fetch(bp + '/centro/bitrix-lid', {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}, body: fd.toString()})
      .then(function (r) { return r.json().catch(function () { return {ok: false, oshibka: 'Сервер ответил ' + r.status}; }).then(function (d) { return {r: r, d: d}; }); })
      .then(function (x) {
        var d = x.d || {};
        if (d.ok) {
          sdelano = true; kudaPosle = d.kartochka || '';
          var a = document.createElement('a'); a.href = d.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
          a.textContent = 'Лид в Битриксе №' + d.lead_id + ' →';
          gotovo.innerHTML = 'Создан ' + a.outerHTML + '<br>Ответственный: ' + (d.otvetstvennyy || '') + '. ' +
            (d.sohraneno ? 'Результат «Взял в работу» сохранён.' : (d.preduprezhdenie || ''));
          var rq = rabForma && rabForma.querySelector('input[name=return_query]');
          var dal = document.createElement('a'); dal.className = 'action-button'; dal.textContent = 'Дальше →';
          dal.href = bp + '/centro' + (rq && rq.value ? '?' + rq.value : '');
          gotovo.appendChild(document.createElement('br')); gotovo.appendChild(dal);
          gotovo.hidden = false; polyaBlok.hidden = true; uzhe.hidden = true;
          knSozdat.hidden = true; knOtmena.textContent = 'Закрыть'; knOtmena.disabled = false;
        } else if (x.r.status === 409 && d.nuzhno_podtverzhdenie) {
          pokazatUzhe(d.lidy); pokazatOsh(d.oshibka || 'Лид уже заводили.');
          knSozdat.textContent = 'Создать лид';
        } else {
          pokazatOsh(d.oshibka || d.detail || ('Ошибка ' + x.r.status));
          knSozdat.textContent = 'Повторить';
        }
      })
      .catch(function () { pokazatOsh('Нет связи с панелью. «Взял в работу» не сохранён – нажмите «Повторить».'); knSozdat.textContent = 'Повторить'; })
      .then(function () { otpravka = false; if (!sdelano) { knSozdat.disabled = false; knOtmena.disabled = false; } });
  });
  /* подпункт меню «Взял в работу ▸ Завести лид в Битрикс» */
  document.querySelectorAll('.fixL-lid-punkt').forEach(function (p) {
    p.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      var v = p.closest('.rez-vybor');
      if (v) { v.classList.remove('otkryt'); v.querySelectorAll('.est-pod.otkryt').forEach(function (x) { x.classList.remove('otkryt'); }); }
      otkryt();
    });
  });
  /* на телефоне наведения нет: после выбора «Взял в работу» под полем – ссылка на то же окно */
  if (rabForma) {
    var pole = rabForma.querySelector('input[name=call_result]');
    var podsk = rabForma.querySelector('.rez-podskazka');
    if (pole && podsk) {
      var mob = document.createElement('p'); mob.className = 'fixL-mob'; mob.hidden = true;
      var kn = document.createElement('button'); kn.type = 'button'; kn.textContent = 'Завести лид в Битрикс ▸';
      kn.addEventListener('click', otkryt); mob.appendChild(kn);
      podsk.parentNode.insertBefore(mob, podsk.nextSibling);
      var obn = function () { mob.hidden = pole.value !== 'v_rabote'; };
      rabForma.querySelectorAll('.rez-punkt[data-value]').forEach(function (x) { x.addEventListener('click', obn); });
      obn();
    }
  }
})();
</script>
{% endif %}
'''
MARKER_R = '# ===== fixL-bitrix-lid (15.10)'
KONEC_R = '# ===== /fixL-bitrix-lid ====='

C1_STARO = '''<li class="rez-punkt" data-value="{{ value }}" data-label="{{ label }}" role="menuitem">{{ label }}</li>'''
C1_NOVO = ('''{% if value == 'v_rabote' and fixL_lidy is defined and user.role in ('admin', 'sales') and not user.rop %}'''
           '''{# fixL-bitrix-lid: подпункт «Завести лид в Битрикс» (обычный клик – «Взял в работу», как прежде) #}'''
           '''<li class="rez-punkt est-pod fixL-vrab" data-value="{{ value }}" data-label="{{ label }}" role="menuitem" aria-haspopup="true">'''
           '''<span>{{ label }}</span><span class="rez-strelka">▸</span><ul class="rez-pod" role="menu">'''
           '''<li class="rez-punkt fixL-lid-punkt" role="menuitem">Завести лид в Битрикс</li></ul></li>{% else %}'''
           + C1_STARO + '''{% endif %}''')
C2_STARO = '''<section class="card work-card">'''
C2_NOVO = ('''<section class="card work-card">{# fixL-bitrix-lid: заведённые лиды компании #}'''
           '''{% if fixL_lidy is defined and company %}{% for _лид in fixL_lidy(company.inn) %}'''
           '''<p class="fixL-lid-stroka" style="margin:0;padding:8px 12px;background:#e8f6ee;border:1px solid #b7e1c7;border-radius:7px;color:#17663a">'''
           '''<a href="{{ _лид.url }}" target="_blank" rel="noopener noreferrer" style="color:#17663a"><b>Лид в Битриксе №{{ _лид.lead_id }} →</b></a> '''
           '''<span style="font-size:13px">завёл(а) {{ _лид.kto_fio }}, {{ _лид.kogda }}{% if _лид.otv_fio %} · ответственный в Битриксе: {{ _лид.otv_fio }}{% endif %}</span></p>'''
           '''{% endfor %}{% endif %}''')
C3_STARO = '''{% if user.role == 'admin' %}</details>{% endif %}'''
C3_NOVO = C3_STARO + '''{% include '_fixL_bitrix_lid.html' %}'''
PRAVKI = [('C', 'меню результата: подпункт у «Взял в работу»', C1_STARO, C1_NOVO),
          ('C', 'карточка: строка «Лид в Битриксе №…»', C2_STARO, C2_NOVO),
          ('C', 'карточка: окно лида (include)', C3_STARO, C3_NOVO)]

TABLICA = ("CREATE TABLE IF NOT EXISTS bitrix_lid (id INTEGER PRIMARY KEY, inn TEXT NOT NULL, lead_id TEXT NOT NULL DEFAULT '', "
           "kto TEXT NOT NULL, kogda TEXT NOT NULL, state_user TEXT NOT NULL DEFAULT '', otvetstvennyy_id INTEGER, "
           "otvetstvennyy_fio TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, oshibka TEXT NOT NULL DEFAULT '', "
           "nazvanie TEXT NOT NULL DEFAULT '', v_rabote_sohraneno INTEGER NOT NULL DEFAULT 0)")
NASTROYKI_TEKST = {
    "_opisanie": "fixL 15.10: ответственный лидов из панели Meyer. otvetstvennyy: 'test' – все лиды на test_id; "
                 "'menedzher' – на bitrix_id менеджера компании из menedzhery (панель перечитывает файл на каждом лиде, "
                 "перезапуск не нужен). Ссылка вебхука – отдельно, в bitrix-webhook.secret.",
    "otvetstvennyy": "test",
    "test_id": 7981,
    "test_fio": "Баданина Ксения",
    "menedzhery": {
        "meyer1": {"fio": "Пяткова Ксения", "bitrix_id": 12334}, "meyer2": {"fio": "Ерохин Александр", "bitrix_id": 11918},
        "meyer3": {"fio": "Беляев Максим", "bitrix_id": 10527}, "meyer4": {"fio": "Волков Роман", "bitrix_id": 12373},
        "meyer5": {"fio": "Козлов Андрей", "bitrix_id": 4757}, "meyer6": {"fio": "Тюнин Артем", "bitrix_id": 2880},
        "meyer7": {"fio": "Иванов Вадим", "bitrix_id": 3379}, "meyer8": {"fio": "Кузнецова Ирина", "bitrix_id": 7209},
        "meyer9": {"fio": "Кузьмин Юрий", "bitrix_id": 6937}},
}


def nl_kak_v(t, x):
    return x.replace('\n', '\r\n') if t.count('\r\n') * 2 > t.count('\n') else x


def nalozhit(teksty):
    novye = dict(teksty)
    zh, ok = [], True
    t = novye['R']
    if MARKER_R in t:
        nachalo = t.index(MARKER_R)
        konec = t.index(KONEC_R, nachalo) + len(KONEC_R)
        nov = nl_kak_v(t, BLOK_ROUTES.strip('\n'))
        if t[nachalo:konec] == nov:
            zh.append('[уже] routes_centro_sales.py: блок fixL')
        else:
            novye['R'] = t[:nachalo] + nov + t[konec:]
            zh.append('[ок] routes_centro_sales.py: блок fixL заменён новой версией')
    elif not t.strip():
        zh.append('[НЕТ ФАЙЛА] routes_centro_sales.py')
        ok = False
    else:
        novye['R'] = t.rstrip('\r\n') + nl_kak_v(t, '\n' + BLOK_ROUTES.rstrip('\n') + '\n')
        zh.append('[ок] routes_centro_sales.py: блок fixL в конец файла')
    for kl, imya, staro, novo in PRAVKI:
        t = novye[kl]
        st, nv = nl_kak_v(t, staro), nl_kak_v(t, novo)
        if t.count(nv) == 1:
            zh.append('[уже] ' + imya)
            continue
        n = t.count(st)
        if n != 1:
            zh.append('[ЯКОРЬ НАЙДЕН %d РАЗ] %s' % (n, imya))
            ok = False
            continue
        novye[kl] = t.replace(st, nv, 1)
        zh.append('[ок] ' + imya)
    if novye['L'] == SHABLON_LID:
        zh.append('[уже] _fixL_bitrix_lid.html')
    else:
        zh.append('[ок] _fixL_bitrix_lid.html %s' % ('заменён' if novye['L'] else 'новый'))
        novye['L'] = SHABLON_LID
    return novye, zh, ok


def prochitat(koren_app):
    out = {}
    for k, p in FAJLY.items():
        f = os.path.join(koren_app, *p.split('/'))
        out[k] = io.open(f, encoding='utf-8', newline='').read() if os.path.exists(f) else ''
    return out


def zapisat(koren_app, teksty, klyuchi):
    for k in klyuchi:
        with io.open(os.path.join(koren_app, *FAJLY[k].split('/')), 'w', encoding='utf-8', newline='') as f:
            f.write(teksty[k])


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


# ====================================================================== проверка (venv, копии баз)
def test(koren, kat, sales_db, metka, polnyy):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение
    sys.path.insert(0, koren)
    import logging
    import warnings
    import urllib.error
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = sales_db
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[k] = kat
    from app import web
    from app.api import routes_centro_sales as rcs
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
    ok(os.path.normcase(os.path.dirname(web.__file__)).startswith(os.path.normcase(koren)), 'код: %s' % os.path.dirname(web.__file__))
    ok(str(catalog.db_path()) == kat and str(sales.sales_db_path()) == sales_db, 'базы – временные копии')
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides.clear()
    s = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
    s.row_factory = sqlite3.Row
    lyudi = [dict(r) for r in s.execute("SELECT username, role, COALESCE(gorod,'') AS gorod FROM users WHERE is_active=1 ORDER BY id")]
    adminy = [u['username'] for u in lyudi if u['role'] == 'admin']
    ropy = [u for u in lyudi if u['role'] == 'rop']
    nazn = {}
    for r in s.execute('SELECT inn, username FROM company_assignment ORDER BY inn'):
        nazn.setdefault(r[1], []).append(str(r[0]))
    otm = {str(r[0]) for r in s.execute('SELECT inn FROM company_state')}
    skr = {str(r[0]) for r in s.execute("SELECT inn FROM hidden_item WHERE kind='company'")}
    s.close()
    kk = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
    v_kat = {str(r[0]) for r in kk.execute('SELECT inn FROM company')}
    kk.close()
    novye = {u: [i for i in nazn.get(u, []) if i in v_kat and i not in otm and i not in skr and i != TULSKAYA] for u in nazn}
    gorod = {u['username']: u['gorod'] for u in lyudi}
    sn = {}

    def kuki(login):
        return {'Cookie': '%s=%s' % (rcs.COOKIE, rcs._token(login, int(time.time()) + 3600))}

    with TestClient(vnutr) as kl:
        def get(login, put, **params):
            return kl.get(PUT + put, params=params, headers=kuki(login), follow_redirects=False)

        def post(login, put, data):
            return kl.post(PUT + put, data=data, headers=kuki(login), follow_redirects=False)

        # ---------- «до/после»: главная, карточка, статистика у всех
        proverit = adminy[:1] + PRODAVCY + [u['username'] for u in ropy]
        kartochki = {}
        for login in proverit:
            if login in PRODAVCY:
                inn = (nazn.get(login) or [''])[0]
            elif login in adminy:
                inn = (nazn.get('meyer1') or [''])[0]
            else:
                g = next((u['gorod'] for u in ropy if u['username'] == login), '')
                kom = [p for p in PRODAVCY if gorod.get(p, '').strip().casefold() == g.strip().casefold()]
                inn = (nazn.get(kom[0]) or [''])[0] if kom else ''
            kartochki[login] = inn
            o1 = get(login, '/centro')
            o2 = get(login, '/centro', inn=inn) if inn else None
            o3 = get(login, '/centro/stats')
            sn[login] = {'glavnaya': o1.status_code, 'kartochka': o2.status_code if o2 is not None else None,
                         'stats': o3.status_code}
            print('   %-20s главная %s, карточка %s %s, статистика %s' % (login, o1.status_code, inn, sn[login]['kartochka'], o3.status_code))
            if polnyy and o2 is not None and o2.status_code == 200:
                t = o2.text
                rop = login not in PRODAVCY and login not in adminy
                if rop:
                    ok('fixL-lid-punkt' not in t and 'id="fixL-okno"' not in t, '%s: у руководителя нет подпункта и окна' % login)
                else:
                    ok('fixL-lid-punkt' in t and 'Завести лид в Битрикс' in t and 'id="fixL-okno"' in t and 'fixL-vrab' in t,
                       '%s: подпункт «Завести лид в Битрикс» и окно в разметке' % login)
        json.dump(sn, io.open(os.path.join(os.path.dirname(sales_db), 'fixL-snimok-%s.json' % metka), 'w', encoding='utf-8'),
                  ensure_ascii=False)
        if not polnyy:
            print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
            return plohih[0]

        # ---------- эндпоинты лида: заглушка вместо Битрикса
        ok(hasattr(rcs, '_fixL_bitrix_vyzov'), 'код fixL загружен')
        if os.path.normcase(koren) != os.path.normcase(KOREN):
            ok(not rcs._FIXL_VEBHUK.exists(), 'stage: вебхука в stage нет (%s)' % ('есть' if rcs._FIXL_VEBHUK.exists() else 'нет'))
        ZAGL = {'rezhim': 'ok', 'n': 900000, 'vyzovy': []}

        def zaglushka(metod, dannye):
            ZAGL['vyzovy'].append((metod, dannye))
            if ZAGL['rezhim'] == 'isklyuchenie':
                raise urllib.error.URLError('timed out')
            if ZAGL['rezhim'] == 'oshibka':
                return {'error': 'ACCESS_DENIED', 'error_description': 'Access denied (заглушка)'}
            ZAGL['n'] += 1
            return {'result': ZAGL['n'], 'time': {}}
        rcs._fixL_bitrix_vyzov = zaglushka

        def baza(sql, *a):
            c = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
            c.row_factory = sqlite3.Row
            try:
                return [dict(r) for r in c.execute(sql, a)]
            finally:
                c.close()

        def maska(t):
            return re.sub(r'\d(?=(?:\D*\d){2})', '•', str(t or ''))

        def polya_formy(login, inn):
            o = get(login, '/centro/bitrix-lid/dannye', inn=inn)
            return o, (o.json() if o.status_code == 200 else {})

        # Тульская: предзаполнение (как увидит meyer9) и права
        o, d = polya_formy('meyer9', TULSKAYA)
        ok(o.status_code == 200, 'meyer9: данные окна для %s – %s' % (TULSKAYA, o.status_code))
        p = d.get('polya') or {}
        print('      предзаполнение %s: %s' % (TULSKAYA, json.dumps({k: (maska(v) if k == 'phone' else (v if k != 'comments' else v[:300]))
                                                                     for k, v in p.items()}, ensure_ascii=False)))
        print('      только чтение: %s' % json.dumps(d.get('tolko_chtenie'), ensure_ascii=False))
        print('      блоки: %s' % [b['nazv'] for b in d.get('bloki') or []])
        ok(p.get('title', '').endswith('(обзвон Meyer)') and p.get('gruppa') == '11797' and 'inn=%s' % TULSKAYA in p.get('comments', ''),
           'название «… (обзвон Meyer)», группа «Рентгены», ссылка на карточку в комментарии')
        ok('7981' in (d.get('tolko_chtenie') or {}).get('otvetstvennyy', ''), 'ответственный – 7981 (тестовый режим)')
        ok(len(d.get('bloki') or []) >= 4 and d.get('lidy') == [], 'блоки справа есть, прежних лидов нет')
        # правки владельца 15.10: ФИО/должность/телефон/почта пустые, короткий комментарий, «Контакты» и «Номера»
        ok(all(p.get(k) == '' for k in ('fio', 'phone', 'email')) and not any(k in p for k in ('last_name', 'name', 'second_name', 'post')),
           '«ФИО, должность», телефон, почта при открытии пустые; одно поле «ФИО, должность»')
        ok('Реквизиты' not in p.get('comments', '') and 'Телефон' not in p.get('comments', '') and 'ЛПР' not in p.get('comments', '')
           and 'ИНН %s' % TULSKAYA in p.get('comments', '') and 'Покупатель Meyer' in p.get('comments', ''),
           'комментарий короткий: ИНН, «Покупатель Meyer», ссылка (без реквизитов и номеров)')
        kt, nm = d.get('kontakty') or [], d.get('nomera') or []
        print('      контакты %s: %s' % (TULSKAYA, json.dumps([dict(z, tel=maska(z.get('tel'))) for z in kt], ensure_ascii=False)))
        print('      номера %s: %s' % (TULSKAYA, json.dumps([dict(z, tel=maska(z.get('tel'))) for z in nm], ensure_ascii=False)))
        ok(any(z.get('otkuda') == 'из реквизитов' for z in kt) and len(nm) >= 1 and all(z.get('podpis') for z in nm),
           'Тульская: руководитель «из реквизитов» в «Контактах», номера с подписью')
        ok(not any(z['nazv'].startswith('ЛПР:') for z in d.get('bloki') or []), 'блоков «ЛПР: …» больше нет (их место – «Контакты»)')
        # компания с несколькими людьми и номерами
        kk = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
        kand = [r[0] for r in kk.execute(
            "SELECT inn FROM contact WHERE kind='phone' GROUP BY inn HAVING COUNT(DISTINCT CASE WHEN COALESCE(TRIM(person),'')<>'' "
            "THEN person END) >= 3 AND COUNT(*) >= 5 ORDER BY inn")]
        kk.close()
        vlad = {i: u for u in nazn for i in nazn[u]}
        mn = next((i for i in kand if i in vlad and vlad[i] in PRODAVCY), '')
        if mn:
            o, dm = polya_formy(vlad[mn], mn)
            kt, nm = dm.get('kontakty') or [], dm.get('nomera') or []
            lpr_snachala = all(not (not a['lpr'] and b['lpr']) for a, b in zip(kt, kt[1:]))
            print('      %s (%s): людей %d, номеров %d; первые: %s' % (mn, vlad[mn], len(kt), len(nm), json.dumps(
                [dict(z, tel=maska(z.get('tel'))) for z in kt[:4]] + [dict(z, tel=maska(z.get('tel'))) for z in nm[:4]], ensure_ascii=False)))
            ok(o.status_code == 200 and len(kt) >= 2 and len(nm) >= 3 and lpr_snachala and all(z.get('podpis') for z in nm)
               and all(z.get('fio') for z in kt), 'много людей и номеров (%s): кнопки контактов %d, номеров %d, ЛПР первыми' % (mn, len(kt), len(nm)))
        else:
            ok(False, 'нет компании с несколькими людьми и номерами для проверки')
        for login, zhdu in (('meyer1', 404), (adminy[0], 200)):
            o, _ = polya_formy(login, TULSKAYA)
            ok(o.status_code == zhdu, '%s: данные окна чужой/любой компании – %s (ждём %s)' % (login, o.status_code, zhdu))
        for r in ropy[:3]:
            o, _ = polya_formy(r['username'], TULSKAYA)
            ok(o.status_code == 403, '%s: данные окна – %s (ждём 403)' % (r['username'], o.status_code))

        def forma(d_, **dop):
            f = dict((d_.get('polya') or {}))
            f.update(dop)
            return f
        n0 = len(ZAGL['vyzovy'])
        o = post('meyer1', '/centro/bitrix-lid', forma(d, inn=TULSKAYA))
        ok(o.status_code == 404 and len(ZAGL['vyzovy']) == n0, 'meyer1: лид по чужой компании – %s, Битрикс не вызван' % o.status_code)
        for r in ropy[:3]:
            o = post(r['username'], '/centro/bitrix-lid', forma(d, inn=TULSKAYA))
            ok(o.status_code == 403 and len(ZAGL['vyzovy']) == n0, '%s: создать лид – %s (ждём 403)' % (r['username'], o.status_code))
        o = post('meyer9', '/centro/bitrix-lid', forma(d, inn=TULSKAYA, title='  '))
        ok(o.status_code == 422 and len(ZAGL['vyzovy']) == n0, 'пустое название – %s' % o.status_code)

        # успех (meyer9, Тульская – на копии базы; поля, которые уйдут в Битрикс)
        z_t = next((z for z in d.get('kontakty') or [] if len(z['fio'].split()) == 3), {'fio': 'Иванов Иван Иванович', 'dolzhnost': 'директор'})
        fio_t = z_t['fio'] + (', ' + z_t['dolzhnost'] if z_t.get('dolzhnost') else '')
        o = post('meyer9', '/centro/bitrix-lid', forma(d, inn=TULSKAYA, title='ТЕСТ — ' + p.get('title', ''),
                                                       comment='проверка fixL на копии', fio=fio_t, phone='+7 495 000-00-00'))
        j = o.json() if o.headers.get('content-type', '').startswith('application/json') else {}
        ok(o.status_code == 200 and j.get('ok') and j.get('sohraneno') and j.get('kartochka') == PUT + '/centro?call_status=v_rabote&inn=' + TULSKAYA,
           'meyer9: лид создан (заглушка) – %s %s' % (o.status_code, j))
        t = get('meyer9', '/centro', inn=TULSKAYA)
        print('      карточка без вкладки после «Взял в работу»: %s (так и было в панели; окно ведёт во вкладку «Взял в работу»)' % t.status_code)
        f = ZAGL['vyzovy'][-1][1]['fields'] if ZAGL['vyzovy'] else {}
        print('      поля crm.lead.add: %s' % json.dumps({k: (maska(v) if k == 'PHONE' else (v[:200] if isinstance(v, str) else v))
                                                         for k, v in f.items()}, ensure_ascii=False))
        ok(f.get('SOURCE_ID') == '149' and f.get('STATUS_ID') == 'NEW' and f.get('ASSIGNED_BY_ID') == 7981
           and f.get('UF_CRM_61B6C14B0E2A1') == '11198' and f.get('UF_CRM_1639366376') == '5880' and f.get('UF_CRM_1711628077') == '11797'
           and '<a href="https://parsercompressor.online/obzvon-meyer/centro?inn=%s">' % TULSKAYA in f.get('COMMENTS', '')
           and f.get('TITLE', '').startswith('ТЕСТ — '), 'поля лида: источник 149, NEW, 7981, «Торгующая?» = Нет×2, группа, ссылка')
        ok(f.get('NAME') == fio_t and ', ' in fio_t and not any(k in f for k in ('LAST_NAME', 'SECOND_NAME', 'POST')),
           '«ФИО, должность» целиком в NAME («%s»); LAST_NAME, SECOND_NAME, POST не заполняются' % f.get('NAME'))
        st = baza('SELECT * FROM company_state WHERE inn=?', TULSKAYA)
        km = baza('SELECT * FROM company_comment WHERE inn=? ORDER BY id DESC LIMIT 1', TULSKAYA)
        al = baza("SELECT * FROM activity_log WHERE inn=? AND action='call_saved' ORDER BY id DESC LIMIT 1", TULSKAYA)
        bl = baza('SELECT * FROM bitrix_lid WHERE inn=?', TULSKAYA)
        lid1 = str(j.get('lead_id'))
        ok(len(st) == 1 and st[0]['call_result'] == 'v_rabote' and st[0]['username'] == 'meyer9', '«Взял в работу» сохранён: %s' % st)
        ok(km and 'проверка fixL на копии' in km[0]['body'] and ('№' + lid1) in km[0]['body'] and km[0]['username'] == 'meyer9',
           'комментарий записан: %s' % (km[0]['body'] if km else None))
        ok(al and '"v_rabote"' in al[0]['payload_json'], 'лента: call_saved v_rabote')
        ok(len(bl) == 1 and bl[0]['status'] == 'ok' and bl[0]['lead_id'] == lid1 and bl[0]['v_rabote_sohraneno'] == 1
           and bl[0]['otvetstvennyy_id'] == 7981 and bl[0]['kto'] == 'meyer9', 'запись о лиде: %s' % bl)
        for login in ('meyer9', adminy[0]) + tuple(r['username'] for r in ropy if r['gorod'].strip().casefold() == gorod.get('meyer9', '').strip().casefold()):
            t = get(login, '/centro', inn=TULSKAYA, call_status='v_rabote')
            ok(t.status_code == 200 and 'class="fixL-lid-stroka"' in t.text and ('Лид в Битриксе №%s' % lid1) in t.text
               and 'crm/lead/details/%s/' % lid1 in t.text,
               '%s: в карточке строка «Лид в Битриксе №%s →» (%s)' % (login, lid1, t.status_code))
        # повтор: без подтверждения – 409, с подтверждением – второй лид
        n0 = len(ZAGL['vyzovy'])
        o = post('meyer9', '/centro/bitrix-lid', forma(d, inn=TULSKAYA))
        j = o.json() if o.status_code in (200, 409) else {}
        ok(o.status_code == 409 and j.get('nuzhno_podtverzhdenie') and len(ZAGL['vyzovy']) == n0 and len(j.get('lidy') or []) == 1,
           'повтор без подтверждения – %s, окно показывает прежний лид' % o.status_code)
        _, d2 = polya_formy('meyer9', TULSKAYA)
        ok(len(d2.get('lidy') or []) == 1, 'окно: «уже заводили» (%d)' % len(d2.get('lidy') or []))
        o = post('meyer9', '/centro/bitrix-lid', forma(d, inn=TULSKAYA, povtor='1'))
        j = o.json() if o.status_code == 200 else {}
        ok(o.status_code == 200 and j.get('ok') and len(baza("SELECT 1 FROM bitrix_lid WHERE inn=? AND status='ok'", TULSKAYA)) == 2,
           'повтор с подтверждением – второй лид %s' % j.get('lead_id'))

        # ошибка Битрикса и «Повторить»
        def novaya(login):
            for i in novye.get(login, []):
                if not baza('SELECT 1 FROM company_state WHERE inn=?', i):
                    return i
            return ''
        i2 = novaya('meyer2')
        o, d2 = polya_formy('meyer2', i2)
        for rezhim, slovo in (('oshibka', 'Битрикс не создал лид'), ('isklyuchenie', 'Битрикс недоступен')):
            ZAGL['rezhim'] = rezhim
            o = post('meyer2', '/centro/bitrix-lid', forma(d2, inn=i2, comment='не должно сохраниться'))
            j = o.json() if o.headers.get('content-type', '').startswith('application/json') else {}
            ok(o.status_code == 502 and not j.get('ok') and slovo in (j.get('oshibka') or '')
               and not baza('SELECT 1 FROM company_state WHERE inn=?', i2)
               and not baza("SELECT 1 FROM company_comment WHERE inn=? AND body LIKE '%не должно сохраниться%'", i2),
               'meyer2 %s, Битрикс «%s»: %s – «%s», «Взял в работу» НЕ сохранён' % (i2, rezhim, o.status_code, j.get('oshibka')))
        t = get('meyer2', '/centro', inn=i2)
        ok(t.status_code == 200 and 'class="fixL-lid-stroka"' not in t.text, 'после ошибок строки о лиде нет')
        ok(len(baza("SELECT 1 FROM bitrix_lid WHERE inn=? AND status='oshibka'", i2)) == 2, 'ошибки записаны в bitrix_lid')
        ZAGL['rezhim'] = 'ok'
        o = post('meyer2', '/centro/bitrix-lid', forma(d2, inn=i2, comment='после повтора'))
        ok(o.status_code == 200 and o.json().get('ok') and baza("SELECT 1 FROM company_state WHERE inn=? AND call_result='v_rabote'", i2),
           '«Повторить» после ошибки: лид создан, «Взял в работу» сохранён')
        # админ за менеджера
        i3 = novaya('meyer4')
        _, d3 = polya_formy(adminy[0], i3)
        o = post(adminy[0], '/centro/bitrix-lid', forma(d3, inn=i3, comment='админ за менеджера',
                                                        fio='Петров Пётр Петрович', dolzhnost='главный инженер'))
        f = ZAGL['vyzovy'][-1][1]['fields'] if ZAGL['vyzovy'] else {}
        ok(f.get('NAME') == 'Петров Пётр Петрович, главный инженер' and 'POST' not in f,
           'старое окно (ФИО и должность раздельно) – склеено в NAME: «%s»' % f.get('NAME'))
        st = baza('SELECT username, call_result FROM company_state WHERE inn=?', i3)
        km = baza('SELECT username FROM company_comment WHERE inn=? ORDER BY id DESC LIMIT 1', i3)
        ok(o.status_code == 200 and st == [{'username': 'meyer4', 'call_result': 'v_rabote'}] and km and km[0]['username'] == adminy[0],
           'админ по компании meyer4 %s: %s, состояние %s' % (i3, o.status_code, st))
        # настройка «menedzher» (только на stage: свой data\)
        if os.path.normcase(koren) != os.path.normcase(KOREN):
            put_n = str(rcs._FIXL_NASTROYKI)
            os.makedirs(os.path.dirname(put_n), exist_ok=True)
            json.dump(dict(NASTROYKI_TEKST, otvetstvennyy='menedzher'), io.open(put_n, 'w', encoding='utf-8'), ensure_ascii=False)
            i4 = novaya('meyer5')
            _, d4 = polya_formy('meyer5', i4)
            o = post('meyer5', '/centro/bitrix-lid', forma(d4, inn=i4))
            f = ZAGL['vyzovy'][-1][1]['fields']
            ok(o.status_code == 200 and f.get('ASSIGNED_BY_ID') == 4757 and 'Козлов' in (d4.get('tolko_chtenie') or {}).get('otvetstvennyy', ''),
               'настройка «menedzher»: ответственный – Bitrix ID менеджера (meyer5 → %s)' % f.get('ASSIGNED_BY_ID'))
            os.remove(put_n)
        # ничего похожего на вебхук в ответах
        sekret = ''
        try:
            sekret = rcs._FIXL_VEBHUK.read_text(encoding='utf-8').strip()
        except OSError:
            pass
        t_all = get('meyer9', '/centro', inn=TULSKAYA).text + json.dumps(polya_formy('meyer9', TULSKAYA)[1], ensure_ascii=False)
        ok('/rest/' not in t_all and (not sekret or sekret not in t_all), 'в разметке и ответах нет ссылки вебхука')
        for login in (adminy[0], 'meyer9', 'meyer2') + tuple(r['username'] for r in ropy[:1]):
            o3 = get(login, '/centro/stats')
            ok(o3.status_code == sn[login]['stats'], '%s: статистика после лидов %s (как было %s)' % (login, o3.status_code, sn[login]['stats']))
        print('   вызовов заглушки: %d (настоящий Битрикс не вызывался)' % len(ZAGL['vyzovy']))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


def venv(*argi):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + list(argi), capture_output=True, timeout=1500, cwd=KOREN, env=SREDA)
    v = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        v += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:]
    return 'ПЛОХИХ ПРОВЕРОК: 0' in v, v


def ubrat(*f):
    for x in f:
        for y in (x, x + '-wal', x + '-shm'):
            try:
                os.remove(y)
            except OSError:
                pass


def kopii_baz(papka, metka):
    ts, tk = os.path.join(papka, 't_sales_%s.db' % metka), os.path.join(papka, 't_kat_%s.db' % metka)
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    return tk, ts


def podnovit_zamok():
    try:
        os.utime(ZAMOK, None)
    except OSError:
        pass


def sravnit(papka, m_do, m_po):
    do = json.load(io.open(os.path.join(papka, 'fixL-snimok-%s.json' % m_do), encoding='utf-8'))
    po = json.load(io.open(os.path.join(papka, 'fixL-snimok-%s.json' % m_po), encoding='utf-8'))
    return ['%s: %s → %s' % (k, do.get(k), po.get(k)) for k in sorted(set(do) | set(po)) if do.get(k) != po.get(k)]


def proverit(koren_app, papka, metka, vyvod, s_do=True):
    good = True
    if s_do:
        tk, ts = kopii_baz(papka, 'do-' + metka)
        g0, v0 = venv('--test', KOREN, tk, ts, 'do-' + metka)
        vyvod.append('----- «до» (живой код, копии баз)\n' + v0[-2500:])
        ubrat(tk, ts)
        good = good and g0
        podnovit_zamok()
    tk, ts = kopii_baz(papka, 'po-' + metka)
    g1, v1 = venv('--test', koren_app, tk, ts, 'po-' + metka, '--polnyy')
    vyvod.append('----- «после» и проверки лида с заглушкой (%s)\n' % koren_app + v1)
    ubrat(tk, ts)
    good = good and g1
    podnovit_zamok()
    if s_do:
        raz = sravnit(papka, 'do-' + metka, 'po-' + metka)
        vyvod.append('----- главная/карточка/статистика «до/после»: РАСХОЖДЕНИЙ %d %s' % (len(raz), raz))
        good = good and not raz
    return good


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
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


def ostanovit():
    p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    for l in p.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
            subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
    time.sleep(2)


def zapustit(prichina):
    lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
    lg.write('\n===== перезапуск: %s %s =====\n' % (prichina, time.strftime('%Y-%m-%d %H:%M:%S')))
    lg.flush()
    subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                     stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                     close_fds=True, env=SREDA)
    import urllib.request
    kod = ''
    for _ in range(12):
        time.sleep(5)
        try:
            kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            if kod == 200:
                break
        except Exception as e:  # noqa: BLE001
            kod = str(e)[:80]
    return kod


def sdelat_stage(novye, izm):
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    shutil.copytree(APP, os.path.join(STAGE, 'app'),
                    ignore=shutil.ignore_patterns('__pycache__', 'dokaz', '*.pyc', '*.db', '*.log'))
    zapisat(os.path.join(STAGE, 'app'), novye, izm)


def vernut_svoi(papka, izm, novye):
    for k_ in izm:
        dst = os.path.join(APP, *FAJLY[k_].split('/'))
        kop = os.path.join(papka, 'app', *FAJLY[k_].split('/'))
        if os.path.exists(kop):
            shutil.copy2(kop, dst)
        elif k_ == 'L' and os.path.exists(dst):
            os.remove(dst)


if '--test' in sys.argv:
    i = sys.argv.index('--test')
    raise SystemExit(1 if test(*sys.argv[i + 1:i + 5], '--polnyy' in sys.argv) else 0)

PAPKA = os.path.join(KOREN, '_bekap', 'fixL-' + VREMYA)
os.makedirs(PAPKA, exist_ok=True)
if '--proverka' in sys.argv:
    vyvod = []
    g = proverit(KOREN, PAPKA, 'proverka-' + VREMYA, vyvod, s_do=False)
    t = '\n'.join(vyvod)
    io.open(os.path.join(DROP, 'fixL-proverka-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
    print(t[-5500:])
    raise SystemExit(0 if g else 5)

if '--suho' in sys.argv:
    teksty = prochitat(APP)
    novye, zh, vse_ok = nalozhit(teksty)
    print('\n'.join('   ' + x for x in zh))
    if not vse_ok:
        print('ЯКОРЯ НЕ НАЙДЕНЫ – ничего не делаю')
        raise SystemExit(4)
    izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
    sdelat_stage(novye, izm)
    vyvod = []
    good = proverit(os.path.join(STAGE), PAPKA, 'suho-' + VREMYA, vyvod)
    t = '\n'.join(vyvod)
    io.open(os.path.join(DROP, 'fixL-kod-suho-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
    print(t[-5600:])
    print('СУХОЙ ПРОГОН: %s (живые файлы и базы не тронуты; меняются: %s)' % (
        'ОК' if good else 'ЕСТЬ ПЛОХОЕ', ', '.join(FAJLY[k_] for k_ in izm)))
    raise SystemExit(0)

if '--primenit' in sys.argv:
    vzyat_zamok('fixL (лид в Битрикс из карточки: код и шаблоны)')
    vyvod = []
    try:
        teksty = prochitat(APP)
        novye, zh, vse_ok = nalozhit(teksty)
        vyvod.append('\n'.join('   ' + x for x in zh))
        if not vse_ok:
            print(vyvod[0])
            print('ЯКОРЯ НЕ НАЙДЕНЫ – живые файлы не тронуты')
            raise SystemExit(4)
        izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
        for k_ in izm:                                  # копия прежних файлов – только свои
            src = os.path.join(APP, *FAJLY[k_].split('/'))
            if os.path.exists(src):
                dst = os.path.join(PAPKA, 'app', *FAJLY[k_].split('/'))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        if izm:
            sdelat_stage(novye, izm)
            good = proverit(STAGE, PAPKA, 'stage-' + VREMYA, vyvod, s_do=True)
            if not good:
                t = '\n'.join(vyvod)
                io.open(os.path.join(DROP, 'fixL-kod-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
                print(t[-4500:])
                print('ПРОВЕРКА НА STAGE НЕ ПРОШЛА – живые файлы и базы не тронуты')
                raise SystemExit(5)
            for k_ in izm:
                if prochitat(APP)[k_] != teksty[k_]:
                    print('ФАЙЛ %s ИЗМЕНИЛСЯ ЗА ВРЕМЯ ПРОГОНА – не пишу' % FAJLY[k_])
                    raise SystemExit(6)
        # база продаж: копия, затем таблица bitrix_lid (CREATE IF NOT EXISTS; строки не меняются)
        kopiya(SALES, os.path.join(PAPKA, 'centro_sales_meyer1-do-fixL.db'))
        b = sqlite3.connect(SALES, timeout=30)
        b.execute(TABLICA)
        b.execute('CREATE INDEX IF NOT EXISTS ix_bitrix_lid_inn ON bitrix_lid(inn, status)')
        b.commit()
        b.close()
        vyvod.append('база продаж: копия %s; таблица bitrix_lid есть' % os.path.join(PAPKA, 'centro_sales_meyer1-do-fixL.db'))
        if not os.path.exists(NASTROYKI):
            json.dump(NASTROYKI_TEKST, io.open(NASTROYKI, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            vyvod.append('настройка ответственного создана: %s (test, 7981)' % NASTROYKI)
        else:
            vyvod.append('настройка ответственного уже есть: %s – не трогаю' % NASTROYKI)
        if izm and 'R' not in izm:                      # только шаблоны: перечитываются сами, без перезапуска
            zapisat(APP, novye, izm)
            vyvod.append('записано: %s (Python не менялся – без перезапуска)' % ', '.join(FAJLY[k_] for k_ in izm))
            g2 = proverit(KOREN, PAPKA, 'zhivoy-' + VREMYA, vyvod, s_do=False)
            if not g2:
                vernut_svoi(PAPKA, izm, novye)
                vyvod.append('ПОСЛЕ ЗАПИСИ ПЛОХО – свои файлы возвращены из %s' % PAPKA)
            else:
                vyvod.append('ПРИМЕНЕНО: %s; копия прежних файлов: %s' % (', '.join(FAJLY[k_] for k_ in izm), PAPKA))
        elif izm:
            ostanovit()
            zapisat(APP, novye, izm)
            kod = zapustit('исправитель L: лид в Битрикс из карточки')
            vyvod.append('записано: %s; перезапуск, вход: %s' % (', '.join(FAJLY[k_] for k_ in izm), kod))
            podnovit_zamok()
            g2 = proverit(KOREN, PAPKA, 'zhivoy-' + VREMYA, vyvod, s_do=False)
            if kod != 200 or not g2:
                vernut_svoi(PAPKA, izm, novye)
                ostanovit()
                kod2 = zapustit('исправитель L: ОТКАТ своих файлов')
                vyvod.append('ПОСЛЕ ЗАПИСИ ПЛОХО – свои файлы возвращены из %s, перезапуск, вход: %s' % (PAPKA, kod2))
            else:
                vyvod.append('ПРИМЕНЕНО: %s; копия прежних файлов: %s' % (', '.join(FAJLY[k_] for k_ in izm), PAPKA))
        else:
            vyvod.append('правки кода уже стоят – файлы не меняю')
        t = '\n'.join(vyvod)
        io.open(os.path.join(DROP, 'fixL-kod-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
        print(t[-5500:])
    finally:
        otdat_zamok()
