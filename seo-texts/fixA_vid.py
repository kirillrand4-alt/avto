# -*- coding: utf-8 -*-
"""Исправитель A: вид карточки и списка панели Meyer (проверка 08.10, PANEL-AUDIT-0810, разд. 3 и 7).

Что меняется (только показ, данные в базах не трогаются):
  1. «Люди предприятия»: добавочный больше не склеен с номером в tel: – ссылка тем же
     помощником, что в «Контактах» (contact_href -> tel:+7…,105), показ «… доб. 105».
  2. Номер читаемо: «+7 900 000-00-00», «+7 (4872) 00-00-00 доб. 208» (фильтр telefon в web.py);
     href не меняется – полные цифры.
  3. В «Контактах» должность у человека всегда, когда она есть у номера или у того же человека
     в «Людях» (каталог снимает её у номеров одной линии с разными добавочными); метка
     «с сайта другого юрлица» (ключ chuzhoy_istochnik) и вид «8-800» – если есть.
  4. Местное время компании в списке и карточке: «местное 16:40 (МСК+4)», «нерабочее» вне 9–18.
  5. ЛПР в строке списка текстом: ФИО, должность, вид номера.
  6. Пояснения пальцем: «?» у базы, цитата со страницы-источника – <details>; Битрикс – текстом.
  7. Битрикс: число сделок и воронки, «действующий клиент СЦ» при воронках СЦ сопровождения/гарантии/ПНР.
  8. Телефон 390: без горизонтальной прокрутки, поле поиска нормальной высоты, фильтры под одной
     кнопкой «Фильтры», контакты сразу после названия, кнопка «К результату звонка».
     Ноутбук: в карточке шапка и фильтры не закреплены, фильтры свёрнуты в одну строку.
  9. Люди, уже стоящие в «Контактах», в «Людях предприятия» свёрнуты.
 10. «убрать» номер / «убрать предприятие» – с подтверждением и не рядом с номером.
 11. В карточке – статус звонка как в списке («Новый»), ЕГРЮЛ – только если не действующая.
 12. Остатки компрессорной панели: «воздух» в подсказке важности, «модель» в поиске, «В базе
     обзвона», «Оборудование по ОКВЭД» (пустое у всех 600) – у Meyer не показываются/поясняются;
     «Пропустить» не выглядит как «Сохранить».

Режимы:
  --suho [ИНН…]   без замка и без правки живых файлов: правки накладываются на КОПИИ шаблонов
                  в C:\\centro2\\_bekap\\fixA-stage, рендер TestClient-ом на копии базы продаж
                  -> на дроп fixA_html_suho.zip (+ полный обход всех карточек «до/после»).
  --primenit      под замком: web.py (новые фильтры) -> проверка рендера на копиях шаблонов ->
                  остановка панели -> шаблоны и CSS на место -> запуск -> проверка живых файлов;
                  провал – свои файлы из своей копии этого же прогона и снова запуск.
Шаблоны пишутся в живую папку только в момент перезапуска: иначе живой процесс со старым
web.py получил бы шаблон с неизвестным фильтром и отдал продавцу 500.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
T = os.path.join(APP, 'templates')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
ZAMOK = r'C:\centro2\_zamok.txt'
STAGE = os.path.join(KOREN, '_bekap', 'fixA-stage')
FAJLY = {
    'C': os.path.join(T, 'centro.html'),
    'L': os.path.join(T, '_ochered_spisok.html'),
    'W': os.path.join(APP, 'web.py'),
    'S': os.path.join(APP, 'static', 'css', 'centro.css'),
}
STAGE_PUT = {'C': r'templates\centro.html', 'L': r'templates\_ochered_spisok.html',
             'W': 'web.py', 'S': 'centro.css'}
PRIMERY = ['5251001312', '6382000106', '7203319557', '3254002818', '1829013726', '2245002584',
           '6111008006']
WEB_METKA = '# ------------------------------------------------- вид карточки и списка (исправитель A'

# ====================================================================== web.py: фильтры показа
WEB_BLOK = r'''

# ------------------------------------------------- вид карточки и списка (исправитель A, 08.10)
# Проверка панели 08.10 (PANEL-AUDIT-0810, разделы 3 и 7): номер слитно «+79000000000»
# трудно читать вслух; в «Людях предприятия» добавочный склеен с номером в ссылке звонка;
# местного времени нет; ЛПР в списке и Битрикс – только во всплывающей подсказке.
# Всё ниже – ТОЛЬКО показ: значения в базе не меняются, ссылка tel: строится тем же
# помощником, что в «Контактах» (centro_catalog.contact_href). Ни одна функция не
# бросает исключение: ошибка фильтра роняла бы страницу продавцу в 500.
import datetime as _dt_vid
import re as _re_vid

# Междугородние коды. Трёхзначные – города с семизначными местными номерами; остальные
# собраны из текста страниц-источников каталога («8 (3452) 00-00-00» у номера 73452000000,
# 1453 номера из 2388). Выбирается самый длинный подходящий код; не нашёлся –
# «+7 XXX XXX-XX-XX» без скобок, то есть без утверждения, где кончается код.
_KODY_GORODOV = frozenset((
    "495 499 812 343 383 831 846 843 863 861 351 342 347 391 473 423 862 496 498 "
    "3012 3412 34130 34141 34261 34262 34271 34273 34344 3435 34373 34376 3452 34551 3462 "
    "3466 34754 34764 34768 34782 34784 34798 35139 35168 3519 3522 3532 3537 365 381 3812 "
    "3822 385 3852 38537 3854 38567 38584 3919 3952 39543 3955 4012 4015 40163 4112 41144 "
    "4152 4162 4212 42337 4242 4712 4722 47231 47247 47248 4725 47391 47396 474 4742 475 "
    "47542 4822 4832 48348 48352 4836 484 4842 4852 48532 48536 4855 4862 48677 48679 4872 "
    "48731 48751 48762 4912 492 4922 49231 49235 49341 4942 49640 8112 813 81371 814 8142 "
    "81459 8152 8162 8172 81737 81739 81755 8184 8202 82145 8313 83171 83176 8332 8342 8352 "
    "8362 8412 8422 84238 8442 84457 845 8452 8453 84650 8482 851 8512 855 8553 85557 85594 "
    "856 8572 86130 86137 86149 86150 86160 86162 86163 86164 86167 86370 8652 86542 86549 "
    "8692 87779 8793").split())
_DOB_VID = _re_vid.compile(r"[\s,;(]*(?:доб(?:авочный)?|доп|вн(?:утр)?|ext|#)\.?\s*:?\s*(\d{1,6})\s*\)?\s*$", _re_vid.I)


def _mestnye_cifry(mest: str) -> str:
    if len(mest) == 7:
        return "%s-%s-%s" % (mest[:3], mest[3:5], mest[5:])
    if len(mest) == 6:
        return "%s-%s-%s" % (mest[:2], mest[2:4], mest[4:])
    if len(mest) == 5:
        return "%s-%s-%s" % (mest[:1], mest[1:3], mest[3:])
    return mest


def _telefon(raw, fragment="") -> dict:
    """Номер -> {"pokaz": «+7 (3452) 00-00-00 доб. 208», "href": «tel:+73452000000,208»,
    "mobilnyy", "vosem_sot", "dob"}. Понимает и склеенный добавочный («+73452000000208» –
    так приходит номер человека из каталога), и явный («… доб. 105»). fragment – текст
    страницы-источника: если там код в скобках, группировка берётся оттуда."""
    s = str(raw or "").strip()
    pusto = {"pokaz": s, "href": "", "mobilnyy": False, "vosem_sot": False, "dob": ""}
    try:
        osn, dob = s, ""
        m = _DOB_VID.search(s)
        if m:
            osn, dob = s[:m.start()].strip(), m.group(1)
        d = _re_vid.sub(r"\D", "", osn)
        if not dob and len(d) > 11 and d[0] in "78":
            d, dob = d[:11], d[11:]          # склеенный добавочный: 11 цифр номера + хвост
        if len(d) == 11 and d[0] == "8":
            d = "7" + d[1:]
        elif len(d) == 10:
            d = "7" + d
        if len(d) != 11 or d[0] != "7":
            return pusto
        nac = d[1:]
        try:
            from app.services.centro_catalog import contact_href
            href = contact_href("phone", "+" + d + (" доб. " + dob if dob else ""))
        except Exception:  # noqa: BLE001
            href = ""
        href = href or ("tel:+" + d + ("," + dob if dob else ""))
        if nac[0] == "9":
            pokaz = "+7 %s %s-%s-%s" % (nac[:3], nac[3:6], nac[6:8], nac[8:])
        elif nac.startswith("800"):
            pokaz = "8 800 %s-%s-%s" % (nac[3:6], nac[6:8], nac[8:])
        else:
            kod = ""
            for mk in _re_vid.finditer(r"\(\s*(?:8\s*)?(\d{3,5})\s*\)", str(fragment or "")):
                if nac.startswith(mk.group(1)):
                    kod = mk.group(1)
                    break
            if not kod:
                for n in (5, 4, 3):
                    if nac[:n] in _KODY_GORODOV:
                        kod = nac[:n]
                        break
            if kod:
                pokaz = "+7 (%s) %s" % (kod, _mestnye_cifry(nac[len(kod):]))
            else:
                pokaz = "+7 %s %s-%s-%s" % (nac[:3], nac[3:6], nac[6:8], nac[8:])
        if dob:
            pokaz += " доб. " + dob
        return {"pokaz": pokaz, "href": href, "mobilnyy": nac[0] == "9",
                "vosem_sot": nac.startswith("800"), "dob": dob}
    except Exception:  # noqa: BLE001
        return pusto


def _mestnoe_vremya(chas_poyas) -> dict:
    """chas_poyas – смещение от UTC (проставлено по региону), нет – Москва.
    -> {"vremya": «16:40», "msk": «МСК+4», "rabochee", "pometka": «нерабочее»/«выходной»/""}."""
    try:
        izvesten = chas_poyas not in (None, "")
        try:
            sm = int(float(str(chas_poyas).replace(",", "."))) if izvesten else 3
        except (TypeError, ValueError):
            sm, izvesten = 3, False
        if not -12 <= sm <= 14:
            sm, izvesten = 3, False
        t = _dt_vid.datetime.utcnow() + _dt_vid.timedelta(hours=sm)
        raz = sm - 3
        msk = "МСК" if raz == 0 else ("МСК+%d" % raz if raz > 0 else "МСК−%d" % -raz)
        vyhodnoy = t.weekday() >= 5
        rabochee = (not vyhodnoy) and 9 <= t.hour < 18
        return {"vremya": t.strftime("%H:%M"), "msk": msk, "rabochee": rabochee,
                "pometka": "выходной" if vyhodnoy else ("" if rabochee else "нерабочее"),
                "izvesten": izvesten}
    except Exception:  # noqa: BLE001
        return {"vremya": "", "msk": "", "rabochee": True, "pometka": "", "izvesten": False}


def _mn(n, odna, dve, pyat) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return odna
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return dve
    return pyat


_SC_KLIENT = _re_vid.compile(r"сопровожд|гарант|пнр|пуско|наладк|сервис|ремонт", _re_vid.I)


def _celoe(x):
    try:
        return int(float(str(x).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _bitrix_razbor(info, n=None, klient_sc=None, sdelok=None) -> dict:
    """«сделок 28: СЦ - Гарантия ×3, КЦ - Продажа ×2» -> {"est", "n", "sdelok", "tekst",
    "voronki": [(имя, число)], "klient_sc"}. Флаг bitrix_klient_sc и число bitrix_sdelok из
    каталога (их ставит разбор выгрузки Битрикса) главнее; нет колонок – «клиент СЦ»
    по воронкам СЦ с сопровождением, гарантией, ПНР, сервисом или ремонтом.
    tekst: «Клиент СЦ · 28 сделок» / «28 сделок»."""
    try:
        s = str(info or "").strip()
        m = _re_vid.match(r"сделок\s+(\d+)\s*:?\s*(.*)$", s, _re_vid.I | _re_vid.S)
        vsego = _celoe(sdelok) or (int(m.group(1)) if m else (_celoe(n) or 0))
        ostatok = m.group(2) if m else s
        voronki = []
        for kusok in ostatok.split(","):
            kusok = kusok.strip()
            if not kusok:
                continue
            mm = _re_vid.match(r"(.+?)\s*[×x]\s*(\d+)$", kusok)
            imya, chislo = (mm.group(1), int(mm.group(2))) if mm else (kusok, None)
            voronki.append((_re_vid.sub(r"\s*[-–—]\s*", " – ", imya.strip(), count=1), chislo))
        sc = [v for v in voronki if v[0].upper().startswith("СЦ")]
        flag = _celoe(klient_sc)
        klient = bool(flag) if flag is not None else any(_SC_KLIENT.search(v[0]) for v in sc)
        sd = "%d %s" % (vsego, _mn(vsego, "сделка", "сделки", "сделок")) if vsego else ""
        tekst = " · ".join(x for x in ("Клиент СЦ" if klient else "", sd) if x)
        return {"est": bool(_celoe(n) or vsego or klient or s), "n": vsego, "sdelok": sd, "tekst": tekst,
                "voronki": voronki, "sc": bool(sc), "klient_sc": klient}
    except Exception:  # noqa: BLE001
        return {"est": bool(n), "n": 0, "sdelok": "", "tekst": "", "voronki": [], "sc": False, "klient_sc": False}


def _lpr_razbor(kratko) -> dict:
    """lpr_kratko «ФИО · должность · +7 … (+ ещё 3)» -> {"fio", "dolzhnost", "vid", "eshche"}.
    Без ФИО строка короче: «снабжение/закупки · +7 …». Сам номер в список не выводится –
    звонят из карточки, где видно, откуда номер."""
    pusto = {"fio": "", "dolzhnost": "", "vid": "", "eshche": 0}
    try:
        chasti = [c.strip() for c in str(kratko or "").split(" · ") if c.strip()]
        if not chasti:
            return pusto
        nomer = ""
        for c in chasti:
            if len(_re_vid.sub(r"\D", "", _re_vid.sub(r"\(.*?\)", "", c))) >= 10:
                nomer = c
        drugie = [c for c in chasti if c is not nomer]
        eshche = 0
        me = _re_vid.search(r"ещё\s*(\d+)", nomer)
        if me:
            eshche = int(me.group(1))
        vid = ""
        if nomer:
            t = _telefon(_re_vid.sub(r"\(\s*\+\s*ещё.*?\)", "", nomer))
            if t["href"]:
                vid = "8-800" if t["vosem_sot"] else ("мобильный" if t["mobilnyy"] else
                                                      ("городской, доб." if t["dob"] else "городской"))
        fio = drugie[0] if len(drugie) >= 2 else ""
        dolzhnost = " · ".join(drugie[1:] if len(drugie) >= 2 else drugie)
        return {"fio": fio, "dolzhnost": dolzhnost, "vid": vid, "eshche": eshche}
    except Exception:  # noqa: BLE001
        return pusto


def _imya_kl(x) -> str:
    return " ".join(str(x or "").replace("ё", "е").replace("Ё", "Е").lower().split())


def _nomer_kl(raw) -> str:
    t = _telefon(raw)
    return t["href"] or ""


def _lyudi_razdelit(lyudi, kontakty) -> dict:
    """Люди предприятия -> {"novye": […], "uzhe": […]}: «uzhe» – тот же номер (с добавочным)
    или то же ФИО уже стоит в «Контактах» выше. Их сворачиваем: одни и те же люди
    в трёх блоках подряд мешали дойти до формы результата."""
    try:
        nomera = {_nomer_kl(k.get("value")) for k in (kontakty or []) if k.get("kind") == "phone"}
        nomera.discard("")
        imena = {_imya_kl(k.get("person")) for k in (kontakty or []) if str(k.get("person") or "").strip()}
        novye, uzhe = [], []
        for p in lyudi or []:
            nk = _nomer_kl(p.get("phone")) if p.get("phone") else ""
            if (nk and nk in nomera) or (_imya_kl(p.get("person")) and _imya_kl(p.get("person")) in imena):
                uzhe.append(p)
            else:
                novye.append(p)
        return {"novye": novye, "uzhe": uzhe}
    except Exception:  # noqa: BLE001
        return {"novye": list(lyudi or []), "uzhe": []}


def _dolzhnost_kontakta(kontakt, lyudi=None) -> str:
    """Должность у номера: своя (position/role/dolzhnost), а если каталог её снял (общий
    основной номер с разными добавочными считается «линией») – у того же человека из
    «Людей предприятия»."""
    try:
        d = str(kontakt.get("position") or kontakt.get("role") or kontakt.get("dolzhnost") or "").strip()
        if d:
            return d
        imya = _imya_kl(kontakt.get("person"))
        if imya:
            for p in lyudi or []:
                if _imya_kl(p.get("person")) == imya:
                    return str(p.get("position") or p.get("role") or "").strip()
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _egrul_deystvuet(status) -> bool:
    s = str(status or "").strip().lower()
    return (not s) or s == "active" or s.startswith("действующ")


templates.env.filters["telefon"] = _telefon
templates.env.filters["lpr_razbor"] = _lpr_razbor
templates.env.filters["bitrix_razbor"] = _bitrix_razbor
templates.env.globals["mestnoe_vremya"] = _mestnoe_vremya
templates.env.globals["lyudi_razdelit"] = _lyudi_razdelit
templates.env.globals["dolzhnost_kontakta"] = _dolzhnost_kontakta
templates.env.globals["egrul_deystvuet"] = _egrul_deystvuet
'''

# ====================================================================== centro.html: стили и скрипт
STIL = r'''<style id="fixA-vid">
/* Исправитель A 08.10 (проверка панели, PANEL-AUDIT-0810 разд. 3 и 7): вид карточки и списка.
   Стоит в конце страницы, чтобы перекрывать прежние правила. */
.st-metka{display:inline-block;padding:2px 8px;border-radius:5px;font-size:12px;font-weight:600;
  white-space:nowrap;background:#f0f1f3;border:1px solid #d1d4db;color:#525a69}
.company-hero .st-metka.st-new{background:#eef1fb;border-color:#d5daf3;color:#3b3f8f}
.st-metka.st-ne_ponravilas{background:#fdecec;border-color:#f3c2c2;color:#9b1c1c}
.st-metka.st-v_rabote{background:#e8f6ee;border-color:#b7e1c7;color:#17663a}
.company-hero .hero-stroka{display:flex;flex-wrap:wrap;gap:3px 14px;margin:2px 0 0;font-size:13px;color:var(--muted)}
.mest-vr{white-space:nowrap;color:#17663a;font-weight:600;font-size:12px}
.mest-vr.nerab{color:#b42318}
.tag-egrul-net{background:#fdecec;border-color:#f3c2c2;color:#9b1c1c;font-weight:600;white-space:normal}
.egrul-net{display:inline-block;margin-top:2px;font-size:11px;padding:1px 6px;border-radius:4px;
  background:#fdecec;border:1px solid #f3c2c2;color:#9b1c1c;font-weight:600}
details.baza-det{display:inline-block;vertical-align:middle;margin-left:6px}
details.baza-det>summary{list-style:none;cursor:pointer;display:inline-flex}
details.baza-det>summary::-webkit-details-marker{display:none}
details.baza-det>summary .baza-metka{margin-left:0}
details.baza-det .baza-opis{display:block;max-width:300px;margin-top:4px;padding:6px 8px;font-size:12px;
  line-height:1.35;color:#475467;background:#f6f7fb;border:1px solid #e4e7ec;border-radius:6px;white-space:normal}
.bitrix-blok{display:inline-flex;flex-wrap:wrap;align-items:center;gap:3px 6px;font-size:12px;line-height:1.3;
  color:#17663a;background:#e8f6ee;border:1px solid #b7e1c7;border-radius:5px;padding:3px 8px}
.bitrix-blok .bitrix-galka{margin-right:0}
.bitrix-voronki{color:#33373e;font-weight:400}
.tag-pometka,.pometka-och{background:#fff4e0;border:1px solid #f3d39b;color:#8a5300;font-weight:700}
.pometka-och{display:inline-block;margin-top:3px;font-size:11px;padding:1px 6px;border-radius:4px;line-height:1.3}
.klient-sc{display:inline-block;background:#fff4e0;border:1px solid #f3d39b;color:#8a5300;border-radius:4px;
  padding:0 6px;font-weight:700;font-size:12px;white-space:nowrap}
.contact-card .copy-button{position:static}
.kontakt-niz{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:9px;
  padding-top:7px;border-top:1px dashed #e4e7ec}
.kontakt-niz .hide-form{margin-left:auto}
.kontakt-niz .sec-btn{font-size:12px;color:#8a909b}
.chuzhoy-metka{margin-top:6px;padding:4px 8px;border-radius:5px;background:#fff4e0;border:1px solid #f3d39b;
  color:#8a5300;font-size:12px;font-weight:600}
.contact-card.is-chuzhoy{border-color:#f3d39b;background:#fffbf3}
.tag-800{background:#fff4e0;border-color:#f3d39b;color:#8a5300;font-weight:600}
details.citata{margin-top:4px;font-size:12px;color:#7e8188}
details.citata>summary{cursor:pointer;color:#667085}
details.citata q{display:block;margin-top:4px;padding:5px 8px;background:#f6f7fb;border-left:3px solid #c7cbe8;
  border-radius:4px;color:#33373e;quotes:"«" "»";overflow-wrap:anywhere}
.citata-pometka{margin:4px 0 0;color:#7e8188;overflow-wrap:anywhere}
.person-card a,.contact-person,.source-line{overflow-wrap:anywhere}
.lyudi-uzhe-nadpis{color:var(--muted);font-size:13px;margin:0 0 6px}
.action-button.propustit{background:#fff;border-style:dashed;color:#475467}
details.ubrat-pred{margin-top:12px;font-size:13px;border-top:1px solid #eff0f1;padding-top:8px}
details.ubrat-pred>summary{cursor:pointer;color:#9b1c1c}
details.ubrat-pred .hide-company{margin-top:8px}
.o-kompanii-mob{display:none}
.o-kompanii-mob p{margin:0 0 6px;color:var(--muted)}
.o-kompanii-mob .opisanie{font-weight:700;color:var(--navy)}
.o-kompanii-mob h2{margin:0 0 8px;color:#33363d;font-size:18px}
.o-kompanii-mob .hero-meta{display:flex;flex-wrap:wrap;gap:6px 16px}
.page-wrap>*{min-width:0}   /* широкая таблица (холдинг) больше не раздвигает всю карточку */
.contact-main{flex-wrap:wrap}
.contact-value,.person-card a[href^="tel:"]{white-space:nowrap}
#kRezultatu{position:fixed;left:14px;bottom:18px;z-index:59;border:0;border-radius:999px;padding:10px 16px;
  background:var(--blue);color:#fff;font-weight:650;box-shadow:0 3px 12px rgba(20,30,50,.25);font-size:14px}
#kRezultatu.skryt{display:none}
body.v-kartochke{padding-bottom:64px}   /* плавающие кнопки внизу не закрывают последний блок */
/* фильтры: в карточке и на телефоне свёрнуты под кнопку «Фильтры»; шапка в карточке не закреплена */
.fb-toggle{display:none}
body.v-kartochke .topbar,body.v-kartochke .filterbar{position:static}
body.v-kartochke .fb-toggle{display:inline-flex}
body.v-kartochke .filterbar{min-height:0;padding-top:8px;padding-bottom:8px}
body.v-kartochke .filterbar:not(.razvernut)>:not(input[type=search]):not(button):not(.total-count),
body.v-kartochke .filterbar:not(.razvernut)>button[data-open-filters]{display:none!important}
@media(max-width:760px){
  .fb-toggle{display:inline-flex}
  .filterbar:not(.razvernut)>:not(input[type=search]):not(button):not(.total-count),
  .filterbar:not(.razvernut)>button[data-open-filters]{display:none!important}
  .filterbar .total-count{font-size:13px;align-self:center}
  .direktor-period{flex-wrap:wrap}
  .direktor-ryad select{max-width:100%}
  .page-wrap{padding:0 8px;margin-top:8px}
  .card{padding:12px}
  .company-hero{padding:12px}
  .company-hero h1{font-size:20px}
  .hero-main{gap:8px}
  .hero-opis{display:none}
  .o-kompanii-mob{display:block}
  .section-head{flex-direction:row;flex-wrap:wrap;align-items:center;gap:6px 10px;margin-bottom:8px}
  .section-head>div:first-child{flex:1 1 200px;min-width:0}
  .contacts-section .section-head p{display:none}
  .contact-value{font-size:18px}
  .kholding-tab{font-size:12px}
  #kRezultatu{left:10px;bottom:14px;padding:9px 14px}
  #vidBtn{right:10px;bottom:14px}
}
</style>
<script id="fixA-vid-js">
(function () {
  /* фильтры: одна кнопка раскрывает всю строку */
  var fb = document.querySelector('form.filterbar');
  var b = fb && fb.querySelector('[data-filtry]');
  if (b) b.addEventListener('click', function () {
    var o = fb.classList.toggle('razvernut');
    b.setAttribute('aria-expanded', o ? 'true' : 'false');
  });
  /* к форме результата звонка – из любого места карточки */
  var wc = document.querySelector('.work-card') ||
           (document.querySelector('form[action$="/centro/save"]') || {}).parentNode;
  if (wc && document.querySelector('.company-hero')) {
    var k = document.createElement('button');
    k.type = 'button'; k.id = 'kRezultatu'; k.textContent = 'К результату звонка ↓';
    k.addEventListener('click', function () { wc.scrollIntoView({behavior: 'smooth', block: 'start'}); });
    document.body.appendChild(k);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) {
        es.forEach(function (e) { k.classList.toggle('skryt', e.isIntersecting); });
      }).observe(wc);
    }
  }
})();
</script>
'''

# --- карточка: шапка (название, регион, местное время, статус, база, Битрикс); описание – отдельно
HERO_STARYY = r'''  <section class="company-hero card">
    <div class="hero-main">
      <div>
        <span class="eyebrow"><a href="{{ spisok_ssylka }}">← к списку</a> · Компания {{ pozitsiya }} из {{ total }}
          {% if hidden_companies_n %}
            · <a href="{{ base_path }}/centro?skrytye={{ 0 if pokaz_skrytye else 1 }}">
              {% if pokaz_skrytye %}вернуться к обычному списку{% else %}скрытых предприятий: {{ hidden_companies_n }}{% endif %}</a>
          {% endif %}
        </span>
        <h1>{{ company.predpriyatie or company.name_full or company.name_short or 'Компания' }}</h1>
        {% if company.adres or company.address %}<p>{{ company.adres or company.address }}</p>{% elif not company.opisanie %}<p>Адрес не указан</p>{% endif %}{% if company.opisanie %}<p class="opisanie" style="max-width:900px">{{ company.opisanie }}</p>{% endif %}{% if company.produkciya %}<p class="opis-dop"><b>Продукция:</b> {{ company.produkciya }}</p>{% endif %}{% if company.moshchnosti %}<p class="opis-dop"><b>Мощности:</b> {{ company.moshchnosti }}</p>{% endif %}
      </div>
      <div class="hero-badges">{% if company.bazy %}{% set _op = (company.bazy_opisanie or '').split(' | ') %}{% for b in company.bazy.split(' | ') %}<span class="baza-metka">{{ b }}<span class="baza-vopros" tabindex="0" title="{{ _op[loop.index0] if loop.index0 < _op|length else '' }}">?</span></span>{% endfor %}{% endif %}{% if company.bitrix_kc %}<span class="tag" style="background:#e8f6ee;border-color:#b7e1c7;color:#17663a" title="{{ company.bitrix_kc_info }}"><span class="bitrix-galka">✓</span>Есть контакт в битриксе КЦ</span>{% endif %}
        <span class="tag tag-status">{{ company.status_egrul or company.status or 'Статус не указан' }}</span>
        {% if company.has_signal %}<span class="tag tag-hot">есть повод</span>{% endif %}
        {% if company.has_phone %}<span class="tag tag-buy">есть телефон</span>{% endif %}
        {% if company.has_role_phone %}<span class="tag tag-buy">телефон с ролью</span>{% endif %}
        {% if company.has_tech %}<span class="tag tag-tech">есть тех. ЛПР</span>{% endif %}
      </div>
    </div>
    {% if user.role == 'admin' %}<p class="assignment">Назначено: <b>{{ (company.assigned_user|fio) if company.assigned_user else 'не назначено' }}</b></p>{% endif %}
    {# УБРАТЬ ПРЕДПРИЯТИЕ ЦЕЛИКОМ (пункт 12 задания). Не удаляем: строка
       остаётся в базе, скрывается только из ВАШЕГО списка, с причиной и
       автором, и возвращается по ссылке «показать скрытые». #}
    <form method="post" action="{{ base_path }}/centro/hide" class="hide-company">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="kind" value="company">
      <input type="hidden" name="value" value="{{ company.inn }}">
      {% if hidden_companies and company.inn in hidden_companies %}
        <input type="hidden" name="undo" value="1">
        <button class="sec-btn" title="Вернуть предприятие в список">вернуть предприятие в список</button>
        <span class="hide-why">скрыто: {{ hidden_companies[company.inn].reason or 'без причины' }}</span>
      {% else %}
        <input name="reason" placeholder="почему убираем (не наша машина, ликвидировано…)" maxlength="120">
        <button class="sec-btn sec-danger" title="Убрать предприятие из списка целиком">убрать предприятие</button>
      {% endif %}
    </form>
    <div class="hero-meta">
      <span><b>ИНН</b> {{ company.inn }} <button type="button" class="text-button" data-copy="{{ company.inn }}">копировать</button></span>
      <span><b>Регион</b> {{ company.region or '–' }}</span>{% if company.segment %}<span><b>Сегмент</b> {{ company.segment|replace(' | ', ', ') }}</span>{% endif %}{% if company.otrasl %}<span><b>Отрасль</b> {{ company.otrasl }}</span>{% endif %}{% if company.popadanie %}<span><b>Попадание</b> {{ company.popadanie }}</span>{% endif %}{% if company.holding %}<span><b>Холдинг</b> {{ company.holding }}</span>{% endif %}{% if company.v_baze_obzvona %}<span><b>В базе обзвона</b> {{ company.v_baze_obzvona }}</span>{% endif %}
      <span title="Место в очереди. Считается как важность предприятия плюс надбавки за то, что до него есть чем дозвониться: телефон, закупщик, технический человек, свежий сигнал, факты. Минус 1000, если юрлицо ликвидировано."><b>Очередь</b> {{ '%.1f'|format(company.assignment_score|float) if company.assignment_score is not none else '–' }}</span>{% if company.moy_prioritet %}<span title="Важность самого предприятия: воздух, покупает, свежесть доказательства. Без учёта того, есть ли контакт."><b>Важность</b> {{ company.moy_prioritet }}</span>{% endif %}
      {% if choices.est_oborudovanie %}<span><b>Фактов</b> {{ facts|length }}</span>{% endif %}
      {% if company.verdikt %}<span class="tag tag-verdikt tag-v-{{ 'da' if company.verdikt in ['есть','покупает','планирует'] else ('net' if company.verdikt == 'нет' else 'neyasno') }}" title="{{ company.verdikt_pochemu }}">суд: {{ company.verdikt }}{% if company.verdikt_uverennost %} ({{ company.verdikt_uverennost }}{{ ' %' if company.verdikt_uverennost|int > 3 else ' из 3 голосов' }}){% endif %}</span>{% endif %}
      {% if company.pod_zamenu %}<span class="tag tag-zamena" title="В заключении сказано: подлежит замене, аварийная, изношена или продлён ресурс. Машину придётся менять – это повод звонить сейчас">машина под замену</span>{% endif %}
      {% if company.sostoyaniya_mashin %}<span><b>Состояние</b> {{ company.sostoyaniya_mashin | join(', ') }}</span>{% endif %}
    </div>
  </section>
'''

OPIS_MAKRO = r'''{# Описание и сведения о компании. На ноутбуке – в шапке, как раньше; на телефоне – ПОСЛЕ
   «Контактов» (проверка 08.10: первый номер был через 2–3 экрана описаний). #}
{% macro opis_kompanii() %}
        {% if company.adres or company.address %}<p>{{ company.adres or company.address }}</p>{% elif not company.opisanie %}<p>Адрес не указан</p>{% endif %}{% if company.opisanie %}<p class="opisanie" style="max-width:900px">{{ company.opisanie }}</p>{% endif %}{% if company.produkciya %}<p class="opis-dop"><b>Продукция:</b> {{ company.produkciya }}</p>{% endif %}{% if company.moshchnosti %}<p class="opis-dop"><b>Мощности:</b> {{ company.moshchnosti }}</p>{% endif %}
    <div class="hero-meta">
      {% if company.segment %}<span><b>Сегмент</b> {{ company.segment|replace(' | ', ', ') }}</span>{% endif %}{% if company.get('segment_dop') %}<span><b>Сегмент по доп. ОКВЭД</b> {{ company.get('segment_dop')|replace(' | ', ', ') }}</span>{% endif %}{% if company.otrasl %}<span><b>Отрасль</b> {{ company.otrasl }}</span>{% endif %}{% if company.popadanie %}<span><b>Попадание</b> {{ company.popadanie }}</span>{% endif %}{% if company.holding %}<span><b>Холдинг</b> {{ company.holding }}</span>{% endif %}
      {% set _вбо = (company.v_baze_obzvona or '')|string|trim %}{% if _вбо and _вбо not in ('Meyer', 'нет в базе обзвона') %}<span><b>Есть и в базе обзвона</b> {{ _вбо }}{% if _вбо == 'Компрессор Центр' %} (КЦ){% endif %} <details class="baza-det"><summary><span class="baza-vopros">?</span></summary><span class="baza-opis">Компания значится и в базе обзвона «{{ _вбо }}» – другой панели. Возможно, с ней уже говорили коллеги: перед звонком посмотрите Битрикс.</span></details></span>{% endif %}
      <span title="Место в очереди. Считается как важность предприятия плюс надбавки за то, что до него есть чем дозвониться: телефон, закупщик, технический человек, свежий сигнал, факты. Минус 1000, если юрлицо ликвидировано."><b>Очередь</b> {{ '%.1f'|format(company.assignment_score|float) if company.assignment_score is not none else '–' }}</span>{% if company.moy_prioritet %}<span title="{% if choices.est_oborudovanie %}Важность самого предприятия: воздух, покупает, свежесть доказательства. Без учёта того, есть ли контакт.{% else %}Балл предприятия из базы: выручка, попадание в сегмент, найденные ЛПР. Без надбавок очереди.{% endif %}"><b>Важность</b> {{ company.moy_prioritet }}</span>{% endif %}
      {% if choices.est_oborudovanie %}<span><b>Фактов</b> {{ facts|length }}</span>{% endif %}
      {% if company.verdikt %}<span class="tag tag-verdikt tag-v-{{ 'da' if company.verdikt in ['есть','покупает','планирует'] else ('net' if company.verdikt == 'нет' else 'neyasno') }}" title="{{ company.verdikt_pochemu }}">суд: {{ company.verdikt }}{% if company.verdikt_uverennost %} ({{ company.verdikt_uverennost }}{{ ' %' if company.verdikt_uverennost|int > 3 else ' из 3 голосов' }}){% endif %}</span>{% endif %}
      {% if company.pod_zamenu %}<span class="tag tag-zamena" title="В заключении сказано: подлежит замене, аварийная, изношена или продлён ресурс. Машину придётся менять – это повод звонить сейчас">машина под замену</span>{% endif %}
      {% if company.sostoyaniya_mashin %}<span><b>Состояние</b> {{ company.sostoyaniya_mashin | join(', ') }}</span>{% endif %}
    </div>
{% endmacro %}
'''

HERO_NOVYY = r'''  <section class="company-hero card">
    <div class="hero-main">
      <div>
        <span class="eyebrow"><a href="{{ spisok_ssylka }}">← к списку</a> · Компания {{ pozitsiya }} из {{ total }}
          {% if hidden_companies_n %}
            · <a href="{{ base_path }}/centro?skrytye={{ 0 if pokaz_skrytye else 1 }}">
              {% if pokaz_skrytye %}вернуться к обычному списку{% else %}скрытых предприятий: {{ hidden_companies_n }}{% endif %}</a>
          {% endif %}
        </span>
        <h1>{{ company.predpriyatie or company.name_full or company.name_short or 'Компания' }}</h1>
        {% set _мв = mestnoe_vremya(company.chas_poyas) %}
        <p class="hero-stroka"><span>{{ company.region or 'регион не указан' }}</span><span class="mest-vr{% if _мв.pometka %} nerab{% endif %}" title="Рабочее время – 9:00–18:00 по местному времени компании, пн–пт">местное {{ _мв.vremya }} ({{ _мв.msk }}){% if _мв.pometka %} · {{ _мв.pometka }}{% endif %}{% if not _мв.izvesten %} · пояс не известен, считаем по Москве{% endif %}</span><span>ИНН {{ company.inn }} <button type="button" class="text-button" data-copy="{{ company.inn }}">копировать</button></span></p>
      </div>
      <div class="hero-badges">{% if company.get('pometka_ocheredi') %}<span class="tag tag-pometka" title="Пометка очереди: компания опущена в конец очереди">{{ company.get('pometka_ocheredi') }}</span>{% endif %}{% set _st = company.call_result or 'new' %}<span class="st-metka st-{{ _st }}" title="Результат звонка – как в списке">{{ call_results.get(_st, _st) }}</span>{% if not egrul_deystvuet(company.status_egrul or company.status) %}<span class="tag tag-egrul-net">{{ company.status_egrul or company.status }}</span>{% endif %}{% if company.bazy %}{% set _op = (company.bazy_opisanie or '').split(' | ') %}{% for b in company.bazy.split(' | ') %}{% set _о = (_op[loop.index0] if loop.index0 < _op|length else '')|trim %}{% if _о %}<details class="baza-det"><summary><span class="baza-metka">{{ b }}<span class="baza-vopros">?</span></span></summary><span class="baza-opis">{{ _о }}</span></details>{% else %}<span class="baza-metka">{{ b }}</span>{% endif %}{% endfor %}{% endif %}{% set _бх = company.bitrix_kc_info|bitrix_razbor(company.bitrix_kc, company.get('bitrix_klient_sc'), company.get('bitrix_sdelok')) %}{% if company.bitrix_kc or _бх.est %}<span class="bitrix-blok" title="{{ company.bitrix_kc_info or '' }}"><span class="bitrix-galka">✓</span><b>Битрикс КЦ:</b>{% if _бх.klient_sc %}<span class="klient-sc">Клиент СЦ</span>{% endif %}{% if _бх.sdelok %}<b>{% if _бх.klient_sc %}· {% endif %}{{ _бх.sdelok }}</b>{% elif not _бх.klient_sc %}<b>есть контакт</b>{% endif %}{% if _бх.voronki %}<span class="bitrix-voronki">{% for v, n in _бх.voronki %}{{ v }}{% if n %} ×{{ n }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}</span>{% endif %}</span>{% endif %}
        {% if company.has_signal %}<span class="tag tag-hot">есть повод</span>{% endif %}
        {% if company.has_phone %}<span class="tag tag-buy">есть телефон</span>{% endif %}
        {% if company.has_role_phone %}<span class="tag tag-buy">телефон с ролью</span>{% endif %}
        {% if company.has_tech %}<span class="tag tag-tech">есть тех. ЛПР</span>{% endif %}
      </div>
    </div>
    <div class="hero-opis">{{ opis_kompanii() }}</div>
    {% if user.role == 'admin' %}<p class="assignment">Назначено: <b>{{ (company.assigned_user|fio) if company.assigned_user else 'не назначено' }}</b></p>{% endif %}
  </section>
'''

# «О компании» на телефоне – сразу после «Контактов». Не <section>: скрипт «⚙ Вид»
# работает только с секциями, и на ноутбуке у него появилась бы пустая галочка.
O_KOMPANII_MOB = r'''  <div class="card o-kompanii-mob"><h2>О компании</h2>{{ opis_kompanii() }}</div>

'''

UBRAT_PRED = r'''      {# Убрать предприятие целиком – здесь, а не в шапке: на телефоне шапка стоит прямо над
         первым номером, и кнопка оказывалась рядом с ним (проверка 08.10). С подтверждением. #}
      {% if hidden_companies and company.inn in hidden_companies %}
      <form method="post" action="{{ base_path }}/centro/hide" class="hide-company">
        <input type="hidden" name="inn" value="{{ company.inn }}">
        <input type="hidden" name="kind" value="company">
        <input type="hidden" name="value" value="{{ company.inn }}">
        <input type="hidden" name="undo" value="1">
        <button class="sec-btn" title="Вернуть предприятие в список">вернуть предприятие в список</button>
        <span class="hide-why">скрыто: {{ hidden_companies[company.inn].reason or 'без причины' }}</span>
      </form>
      {% else %}
      <details class="ubrat-pred"><summary>Убрать предприятие из списка…</summary>
      <form method="post" action="{{ base_path }}/centro/hide" class="hide-company" onsubmit="return confirm('Убрать предприятие из вашего списка целиком? Вернуть можно по ссылке «скрытых предприятий» над карточкой.')">
        <input type="hidden" name="inn" value="{{ company.inn }}">
        <input type="hidden" name="kind" value="company">
        <input type="hidden" name="value" value="{{ company.inn }}">
        <input name="reason" placeholder="почему убираем (ликвидировано, не наш профиль…)" maxlength="120">
        <button class="sec-btn sec-danger" title="Убрать предприятие из списка целиком">убрать предприятие</button>
      </form>
      </details>
      {% endif %}
'''

KONTAKT_STARYY = r'''  <article class="contact-card{% if contact.is_purchaser %} is-buyer{% endif %}{% if contact.is_tech %} is-tech{% endif %}{% if hidden and hidden.phone and contact.value in hidden.phone %} is-hidden-by-user{% endif %}">
    <div class="contact-main">
      {% if contact.href %}<a class="contact-value" href="{{ contact.href }}">{{ contact.value }}</a>{% else %}<b class="contact-value">{{ contact.value }}</b>{% endif %}
      <span class="badges">
        {% if contact.is_purchaser %}<span class="tag tag-buy">закупки</span>{% endif %}
        {% if contact.is_tech %}<span class="tag tag-tech">технический ЛПР</span>{% endif %}
        {% if contact.phone_type %}<span class="tag">{{ contact.phone_type }}</span>{% endif %}{% if contact.nomer_ne_lichnyy %}<span class="tag tag-ne-lpr" title="Не ЛПР: путь к ЛПР через этот номер">{{ contact.nomer_ne_lichnyy }}</span>{% endif %}
      </span>
    </div>
    {% if contact.person or contact.role or contact.position %}
      <div class="contact-person">
        <b>{{ contact.person or 'Имя не указано' }}</b>
        {% if contact.position or contact.role %}<span>{{ contact.position or contact.role }}</span>{% endif %}
      </div>
    {% endif %}
    {{ source_link(contact.source, contact.source_url, telefon=True, fragment=contact.fragment or '') }}
    <button type="button" class="copy-button" data-copy="{{ contact.value }}">Копировать</button>
    {# Убрать НОМЕР у этой компании. Ключ – сам номер: id контакта переживает
       не всякую пересборку базы, а номер остаётся собой. #}
    <form method="post" action="{{ base_path }}/centro/hide" class="hide-form">'''

KONTAKT_NOVYY = r'''  {# Номер читаемо (+7 (4872) 00-00-00 доб. 208), ссылка – прежняя contact.href. Должность –
     своя у номера или того же человека из «Людей». Метки «с сайта другого юрлица» и «8-800» –
     если каталог их дал (ключи chuzhoy_istochnik, phone_type / nomer_ne_lichnyy / vid_nomera). #}
  {% set _т = (contact.value|telefon(contact.fragment or '')) if contact.kind == 'phone' else none %}
  {% set _долж = dolzhnost_kontakta(contact, people) %}
  {% set _виды = ((contact.phone_type or '') ~ ' ' ~ (contact.nomer_ne_lichnyy or '') ~ ' ' ~ (contact.vid_nomera or ''))|string %}
  <article class="contact-card{% if contact.is_purchaser %} is-buyer{% endif %}{% if contact.is_tech %} is-tech{% endif %}{% if contact.chuzhoy_istochnik %} is-chuzhoy{% endif %}{% if hidden and hidden.phone and contact.value in hidden.phone %} is-hidden-by-user{% endif %}">
    <div class="contact-main">
      {% if contact.href %}<a class="contact-value" href="{{ contact.href }}">{{ _т.pokaz if (_т and _т.href) else contact.value }}</a>{% else %}<b class="contact-value">{{ _т.pokaz if (_т and _т.href) else contact.value }}</b>{% endif %}
      <span class="badges">
        {% if contact.is_purchaser %}<span class="tag tag-buy">закупки</span>{% endif %}
        {% if contact.is_tech %}<span class="tag tag-tech">технический ЛПР</span>{% endif %}
        {% if contact.phone_type %}<span class="tag{% if '800' in (contact.phone_type|string) %} tag-800{% endif %}">{{ contact.phone_type }}</span>{% endif %}{% if contact.nomer_ne_lichnyy %}<span class="tag tag-ne-lpr{% if '800' in (contact.nomer_ne_lichnyy|string) %} tag-800{% endif %}" title="Не ЛПР: путь к ЛПР через этот номер">{{ contact.nomer_ne_lichnyy }}</span>{% endif %}
        {% if contact.vid_nomera and contact.vid_nomera not in (contact.phone_type, contact.nomer_ne_lichnyy) %}<span class="tag{% if '800' in (contact.vid_nomera|string) %} tag-800{% endif %}">{{ contact.vid_nomera }}</span>{% endif %}
        {% if _т and _т.vosem_sot and '800' not in _виды %}<span class="tag tag-800">8-800</span>{% endif %}
      </span>
    </div>
    {% if contact.chuzhoy_istochnik %}<div class="chuzhoy-metka">{{ contact.chuzhoy_istochnik }}</div>{% endif %}
    {% if contact.person or _долж %}
      <div class="contact-person">
        <b>{{ contact.person or 'Имя не указано' }}</b>
        {% if _долж %}<span>{{ _долж }}</span>{% endif %}
      </div>
    {% endif %}
    {{ source_link(contact.source, contact.source_url, telefon=True, fragment=contact.fragment or '') }}
    <div class="kontakt-niz">
    <button type="button" class="copy-button" data-copy="{{ contact.value }}">Копировать</button>
    {# Убрать НОМЕР у этой компании. Ключ – сам номер: id контакта переживает
       не всякую пересборку базы, а номер остаётся собой. Кнопка – справа внизу, отдельно
       от номера и «Копировать», и с подтверждением (проверка 08.10). #}
    <form method="post" action="{{ base_path }}/centro/hide" class="hide-form"{% if not (hidden and hidden.phone and contact.value in hidden.phone) %} onsubmit="return confirm('Убрать этот номер из карточки компании?')"{% endif %}>'''

KONTAKT_KONEC_STARYY = r'''        <button class="sec-btn" title="Убрать этот контакт только у этой компании">убрать</button>
      {% endif %}
    </form>
  </article>'''
KONTAKT_KONEC_NOVYY = r'''        <button class="sec-btn" title="Убрать этот контакт только у этой компании">убрать номер</button>
      {% endif %}
    </form>
    </div>
  </article>'''

PERSON_MAKRO = r'''
{# Карточка человека. Номер – через telefon: каталог отдаёт номер человека с добавочным,
   склеенным в одну строку цифр («+78310000000105»), и ссылка tel: набирала бы
   несуществующий номер. Теперь tel:+7…,105 и показ «… доб. 105» (проверка 08.10). #}
{% macro person_card(person) %}
        <article class="person-card{% if person.is_tech %} is-tech{% endif %}">
          <b>{{ person.person or 'Имя не указано' }}</b>
          <span>{{ person.position or person.role or 'Роль не указана' }}</span>
          {% if person.phone %}{% set _т = person.phone|telefon %}<a href="{{ _т.href or ('tel:' ~ person.phone) }}">{{ _т.pokaz if _т.href else person.phone }}</a>{% endif %}
          {% if person.email %}<a href="mailto:{{ person.email }}">{{ person.email }}</a>{% endif %}
          {{ source_link(person.source, person.source_url, telefon=True) }}
        </article>
{% endmacro %}
'''

LYUDI_STARYY = r'''  {% if people %}
  <section class="card">
    <div class="section-head"><div><h2>Люди предприятия</h2><p>Технические специалисты и сотрудники с известными должностями.</p></div><span class="counter">{{ people_live|length }}</span></div>
    {% if people_with_role %}
      <div class="people-grid">
      {% for person in people_with_role %}
        <article class="person-card{% if person.is_tech %} is-tech{% endif %}">
          <b>{{ person.person or 'Имя не указано' }}</b>
          <span>{{ person.position or person.role or 'Роль не указана' }}</span>
          {% if person.phone %}<a href="tel:{{ person.phone }}">{{ person.phone }}</a>{% endif %}
          {% if person.email %}<a href="mailto:{{ person.email }}">{{ person.email }}</a>{% endif %}
          {{ source_link(person.source, person.source_url, telefon=True) }}
        </article>
      {% endfor %}
      </div>
    {% endif %}'''

LYUDI_NOVYY = r'''  {% if people %}
  {# Кто уже стоит в «Контактах» (тот же номер с добавочным или то же ФИО) – свёрнут:
     одни и те же люди шли трижды подряд (проверка 08.10). #}
  {% set _лр = lyudi_razdelit(people_with_role, contacts) %}
  <section class="card">
    <div class="section-head"><div><h2>Люди предприятия</h2><p>Технические специалисты и сотрудники с известными должностями.{% if _лр.uzhe %} Кто уже есть в «Контактах» выше – свёрнут.{% endif %}</p></div><span class="counter">{{ people_live|length }}</span></div>
    {% if _лр.novye %}
      <div class="people-grid">
      {% for person in _лр.novye %}{{ person_card(person) }}{% endfor %}
      </div>
    {% endif %}
    {% if _лр.uzhe %}
      <details class="fold"><summary>Уже в «Контактах» выше ({{ _лр.uzhe|length }})</summary>
        <div class="people-grid">
        {% for person in _лр.uzhe %}{{ person_card(person) }}{% endfor %}
        </div>
      </details>
    {% endif %}'''

ISTOCHNIK_STARYY = r'''    {% for z, vazhno in в.zametki %}{% if vazhno %}<em>{{ z }}</em>{% else %}<span class="istochnik-zametka">{{ z }}</span>{% endif %}{% endfor %}
  </div>
{% else %}'''
ISTOCHNIK_NOVYY = r'''    {% for z, vazhno in в.zametki %}{% if vazhno %}<em>{{ z }}</em>{% else %}<span class="istochnik-zametka">{{ z }}</span>{% endif %}{% endfor %}
  </div>
  {# Цитата со страницы и пометка проверки – по нажатию: во всплывающей подсказке их
     на телефоне не открыть (проверка 08.10). #}
  {% if fragment or source %}<details class="citata"><summary>{{ 'Цитата со страницы' if fragment else 'Как проверен источник' }}</summary>{% if fragment %}<q>{{ fragment }}</q>{% endif %}{% if source %}<p class="citata-pometka">{{ source }}</p>{% endif %}</details>{% endif %}
{% else %}'''

FILTR_POISK_STARYY = '''  <input type="search" name="q" value="{{ request.query_params.get('q','') }}" placeholder="Название, ИНН, модель, телефон, человек…">'''
FILTR_POISK_NOVYY = '''  {# сколько фильтров выбрано – число на кнопке «Фильтры», когда строка свёрнута #}
  {% set _фн = namespace(n=0) %}{% for k in ('region', 'segment', 'otrasl', 'perezvon', 'rabochee', 'model', 'sostoyanie', 'verdikt', 'pod_zamenu', 'has_phone', 'has_role_phone', 'assigned_user', 'ot', 'do', 'prichina', 'bez_poyasneniya') %}{% if request.query_params.get(k) %}{% set _фн.n = _фн.n + 1 %}{% endif %}{% endfor %}
  <input type="search" name="q" value="{{ request.query_params.get('q','') }}" placeholder="{{ 'Название, ИНН, модель, телефон, человек…' if choices.est_oborudovanie else 'Название, ИНН, телефон, человек…' }}">'''
FILTR_KNOPKI_STARYY = '''  <button>Найти</button>
  <button type="button" class="secondary" data-open-filters>Все фильтры</button>'''
FILTR_KNOPKI_NOVYY = '''  <button>Найти</button>
  {# на телефоне и в карточке строка фильтров свёрнута: видны поиск, «Найти» и эта кнопка #}
  <button type="button" class="secondary fb-toggle" data-filtry aria-expanded="false">Фильтры{% if _фн.n %} · {{ _фн.n }}{% endif %}</button>
  <button type="button" class="secondary" data-open-filters>Все фильтры</button>'''

OKVED_STARYY = '''        <div><dt>Оборудование по ОКВЭД</dt><dd>{{ company.oborudovanie_po_okved or company.equipment_all or '–' }}</dd></div>'''
OKVED_NOVYY = '''        {% if company.oborudovanie_po_okved or company.equipment_all %}<div><dt>Оборудование по ОКВЭД</dt><dd>{{ company.oborudovanie_po_okved or company.equipment_all }}</dd></div>{% endif %}'''

REKV_KONEC_STARYY = '''      </details>
      {% endif %}
    </section>

    <section class="card">
      <h2>Деньги и деятельность</h2>'''

PROPUSTIT_STARYY = '''<a class="action-button primary" href="{{ base_path }}/centro?inn={{ sled_inn }}{% if query_string %}&{{ query_string }}{% endif %}">Пропустить →</a>'''
PROPUSTIT_NOVYY = '''<a class="action-button propustit" href="{{ base_path }}/centro?inn={{ sled_inn }}{% if query_string %}&{{ query_string }}{% endif %}" title="Перейти к следующей компании без отметки">Пропустить →</a>'''

# --- список
SP_STIL = r'''<style id="fixA-spisok">
/* Исправитель A 08.10: ЛПР и Битрикс текстом, местное время, пояснения по нажатию, телефон. */
.lpr-yach{width:210px;max-width:210px}
.lpr-fio{display:block;font-weight:600;color:var(--navy)}
.lpr-dolzh{display:block}
.lpr-vid{display:inline-block;margin-top:2px;font-size:11px;padding:0 6px;border-radius:999px;border:1px solid var(--line);color:#475467;white-space:nowrap}
.lpr-vid.mob{background:#e8f6ee;border-color:#b7e1c7;color:#17663a}
.lpr-roli{display:block;margin-top:2px}
.bitrix-stroka{display:block;margin-top:5px;font-size:12px;color:#17663a}
.bitrix-stroka .bitrix-galka{width:15px;height:15px;font-size:10px;margin-right:3px}
.och-tab details.baza-det{margin-left:6px}
.och-tab .mest-vr{white-space:normal}
.och-tab .bitrix-voronki{font-size:12px}
.och-tab .bitrix-voronki>summary{cursor:pointer;color:#17663a;text-decoration:underline dotted}
@media(max-width:1400px){.komp-opis{min-width:260px}.komp-lev{flex-basis:220px}}
@media(max-width:760px){
  .ochered-wrap{padding:8px;gap:8px}
  .och-shapka{gap:6px 12px}
  table.och-tab,table.och-tab tbody,table.och-tab tr,table.och-tab td{display:block;width:auto;max-width:none}
  table.och-tab thead{display:none}
  table.och-tab tbody tr{padding:10px 12px;border-bottom:1px solid var(--line)}
  table.och-tab th,table.och-tab td{border-bottom:0;padding:2px 0}
  table.och-tab td.chislo{text-align:left}
  table.och-tab td.och-n,table.och-tab td.och-okved,table.och-tab td.och-ball{display:none}
  table.och-tab td[data-label]::before{content:attr(data-label) ": ";color:var(--muted);font-size:12px}
  .komp-yach{display:block}
  .komp-lev{flex:none}
  .komp-opis{min-width:0;max-width:none;margin-top:4px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .lpr-yach{width:auto;max-width:none;margin-top:4px}
  table.och-tab td.och-vyr,table.och-tab td.och-segm{display:inline-block;vertical-align:top;margin-right:14px}
  .och-shapka>span:last-child{display:none}
  .och-komm,.och-prichina{max-width:none}
}
</style>
'''
SP_STROKA_BAZY_STARYY = '''<a class="nazv" href="{{ ssylka }}">{{ c.predpriyatie or c.name_short or c.inn }}</a>{% if c.bazy %}{% set _op = (c.bazy_opisanie or '').split(' | ') %}{% for b in c.bazy.split(' | ') %}<span class="baza-metka">{{ b }}<span class="baza-vopros" tabindex="0" title="{{ _op[loop.index0] if loop.index0 < _op|length else '' }}">?</span></span>{% endfor %}{% endif %}
          <br><span class="tiho">{{ c.inn }}{% if c.region %} · {{ c.region }}{% endif %}{% if c.status_egrul and (c.status_egrul|upper) != 'ACTIVE' %} · {{ c.status_egrul }}{% endif %}</span>'''
SP_STROKA_BAZY_NOVYY = '''<a class="nazv" href="{{ ssylka }}">{{ c.predpriyatie or c.name_short or c.inn }}</a>{% if c.bazy %}{% set _op = (c.bazy_opisanie or '').split(' | ') %}{% for b in c.bazy.split(' | ') %}{% set _о = (_op[loop.index0] if loop.index0 < _op|length else '')|trim %}{% if _о %}<details class="baza-det"><summary><span class="baza-metka">{{ b }}<span class="baza-vopros">?</span></span></summary><span class="baza-opis">{{ _о }}</span></details>{% else %}<span class="baza-metka">{{ b }}</span>{% endif %}{% endfor %}{% endif %}
          {% if c.get('pometka_ocheredi') %}<br><span class="pometka-och">{{ c.get('pometka_ocheredi') }}</span>{% endif %}
          {% set _мв = mestnoe_vremya(c.chas_poyas) %}<br><span class="tiho">{{ c.inn }}{% if c.region %} · {{ c.region }}{% endif %}</span> <span class="mest-vr{% if _мв.pometka %} nerab{% endif %}" title="Рабочее время – 9:00–18:00 по местному времени, пн–пт">местное {{ _мв.vremya }} ({{ _мв.msk }}){% if _мв.pometka %} · {{ _мв.pometka }}{% endif %}</span>{% if not egrul_deystvuet(c.status_egrul) %}<br><span class="egrul-net">{{ c.status_egrul }}</span>{% endif %}'''
SP_LPR_STARYY = '''        <td class="lpr-yach">{% if c.bitrix_kc %}<span class="bitrix-galka" tabindex="0" title="Есть контакт в битриксе КЦ&#10;{{ c.bitrix_kc_info }}">✓</span>{% endif %}<span title="{{ c.lpr_kratko or '' }}">{{ c.lpr_roli or c.lpr_kratko or '–' }}</span></td>'''
SP_LPR_NOVYY = '''        {# ЛПР текстом, а не во всплывающей подсказке (на телефоне её не открыть): ФИО,
           должность, вид номера; ниже – роли и Битрикс с числом сделок (проверка 08.10). #}
        <td class="lpr-yach och-lpr">{% set _л = c.lpr_kratko|lpr_razbor %}{% if _л.fio or _л.dolzhnost %}{% if _л.fio %}<span class="lpr-fio">{{ _л.fio }}</span>{% endif %}{% if _л.dolzhnost %}<span class="lpr-dolzh">{{ _л.dolzhnost }}</span>{% endif %}{% if _л.vid %}<span class="lpr-vid{% if _л.vid == 'мобильный' %} mob{% endif %}">{{ _л.vid }}</span>{% endif %}{% if _л.eshche %} <span class="tiho">+ ещё {{ _л.eshche }}</span>{% endif %}{% if c.lpr_roli %}<span class="lpr-roli tiho">{{ c.lpr_roli }}</span>{% endif %}{% else %}{{ c.lpr_roli or '–' }}{% endif %}
          {% set _бх = c.bitrix_kc_info|bitrix_razbor(c.bitrix_kc, c.get('bitrix_klient_sc'), c.get('bitrix_sdelok')) %}{% if c.bitrix_kc or _бх.est %}<span class="bitrix-stroka"><span class="bitrix-galka">✓</span>Битрикс КЦ: {% if _бх.klient_sc %}<span class="klient-sc">Клиент СЦ</span>{% if _бх.sdelok %} · {% endif %}{% endif %}{{ _бх.sdelok or ('' if _бх.klient_sc else 'есть контакт') }}</span>{% if _бх.voronki %}<details class="bitrix-voronki"><summary>воронки</summary>{% for v, n in _бх.voronki %}{{ v }}{% if n %} ×{{ n }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}</details>{% endif %}{% endif %}</td>'''

# (файл, старое, новое, имя, признак «уже сделано», обязательная)
PRAVKI = [
    ('C', '<link rel="stylesheet" href="{{ base_path }}/static/css/centro.css">',
     '<link rel="stylesheet" href="{{ base_path }}/static/css/centro.css?v=0810a">',
     'карточка: CSS с меткой версии (браузер не держит старый)', 'centro.css?v=', True),
    ('C', '<body>\n', '<body class="{{ \'v-kartochke\' if company else \'v-spiske\' }}">\n',
     'карточка: класс страницы (карточка/список)', "v-kartochke' if company", True),
    ('C', ISTOCHNIK_STARYY, ISTOCHNIK_NOVYY, 'источник номера: цитата по нажатию', 'class="citata"', True),
    ('C', KONTAKT_STARYY, KONTAKT_NOVYY, 'контакт: номер читаемо, должность, метки, «убрать» отдельно', "dolzhnost_kontakta(contact, people)", True),
    ('C', KONTAKT_KONEC_STARYY, KONTAKT_KONEC_NOVYY, 'контакт: низ карточки номера', 'убрать номер</button>', True),
    ('C', '{% include "_shapka.html" %}\n', PERSON_MAKRO + OPIS_MAKRO + '{% include "_shapka.html" %}\n',
     'макросы: человек, описание компании', '{% macro person_card(person) %}', True),
    ('C', FILTR_POISK_STARYY, FILTR_POISK_NOVYY, 'фильтры: подсказка поиска без «модели», счётчик', '_фн = namespace(n=0)', True),
    ('C', FILTR_KNOPKI_STARYY, FILTR_KNOPKI_NOVYY, 'фильтры: кнопка «Фильтры»', 'class="secondary fb-toggle" data-filtry', True),
    ('C', HERO_STARYY, HERO_NOVYY, 'шапка карточки: статус как в списке, местное время, Битрикс, «?» по нажатию', 'class="hero-stroka"', True),
    ('C', "  {# Снятая привязка значит «человек работает в ДРУГОМ юрлице».", O_KOMPANII_MOB + "  {# Снятая привязка значит «человек работает в ДРУГОМ юрлице».",
     'телефон: «О компании» после «Контактов»', 'o-kompanii-mob"><h2>', True),
    ('C', LYUDI_STARYY, LYUDI_NOVYY, 'люди: добавочный не склеен, повторы свёрнуты', 'lyudi_razdelit(people_with_role, contacts)', True),
    ('C', OKVED_STARYY, OKVED_NOVYY, 'реквизиты: «Оборудование по ОКВЭД» только если есть', "{% if company.oborudovanie_po_okved or company.equipment_all %}<div><dt>Оборудование", True),
    ('C', REKV_KONEC_STARYY, REKV_KONEC_STARYY.replace('      {% endif %}\n    </section>', '      {% endif %}\n' + UBRAT_PRED + '    </section>', 1),
     'реквизиты: «убрать предприятие» с подтверждением', 'class="ubrat-pred"', True),
    ('C', PROPUSTIT_STARYY, PROPUSTIT_NOVYY, '«Пропустить» не как «Сохранить»', 'action-button propustit', False),
    ('C', '\n</body>\n</html>', '\n' + STIL + '</body>\n</html>', 'стили и скрипт исправителя A', 'id="fixA-vid"', True),
    # список
    ('L', '</style>\n<main class="ochered-wrap">', '</style>\n' + SP_STIL + '<main class="ochered-wrap">',
     'список: стили', 'id="fixA-spisok"', True),
    ('L', SP_STROKA_BAZY_STARYY, SP_STROKA_BAZY_NOVYY, 'список: «?» базы по нажатию, местное время, ЕГРЮЛ', 'mestnoe_vremya(c.chas_poyas)', True),
    ('L', '        <td class="chislo tiho">{{ ot + loop.index0 }}</td>', '        <td class="chislo tiho och-n">{{ ot + loop.index0 }}</td>',
     'список: класс №', 'och-n">', True),
    ('L', '''        <td title="{{ c.okved or '' }}">{{ (c.okved or '–')|truncate(60, True, '…') }}</td>''',
     '''        <td class="och-okved" title="{{ c.okved or '' }}">{{ (c.okved or '–')|truncate(60, True, '…') }}</td>''',
     'список: класс ОКВЭД', 'class="och-okved"', True),
    ('L', '        <td class="chislo">{{ dengi(c.vyruchka_rub) }}</td>', '        <td class="chislo och-vyr" data-label="Выручка">{{ dengi(c.vyruchka_rub) }}</td>',
     'список: выручка с подписью на телефоне', 'och-vyr" data-label', True),
    ('L', "        <td>{{ (c.segment or '–')|replace(' | ', ', ') }}", "        <td class=\"och-segm\" data-label=\"Сегмент\">{{ (c.segment or '–')|replace(' | ', ', ') }}",
     'список: сегмент с подписью на телефоне', 'och-segm" data-label', True),
    ('L', SP_LPR_STARYY, SP_LPR_NOVYY, 'список: ЛПР и Битрикс текстом', 'c.lpr_kratko|lpr_razbor', True),
    ('L', "        <td class=\"chislo tiho\">{{ '%.1f'|format(c.assignment_score or 0) }}</td>",
     "        <td class=\"chislo tiho och-ball\">{{ '%.1f'|format(c.assignment_score or 0) }}</td>", 'список: класс балла', 'och-ball">', True),
    ('L', "{% if user.role == 'admin' %}<td>{{ (c.assigned_user|fio) if c.assigned_user else '–' }}</td>{% endif %}",
     "{% if user.role == 'admin' %}<td class=\"och-prod\" data-label=\"Продавец\">{{ (c.assigned_user|fio) if c.assigned_user else '–' }}</td>{% endif %}",
     'список: продавец с подписью на телефоне', 'och-prod', True),
    ('L', "    if (e.target.closest('a')) return;", "    if (e.target.closest('a, details, summary, button')) return;   /* «?» и «воронки» раскрываются, а не уводят в карточку */",
     'список: нажатие на «?» не открывает карточку', "closest('a, details, summary, button')", True),
    # CSS панели (телефон): шапка в две строки, поиск нормальной высоты, ничего шире экрана
    ('S', '@media(max-width:760px){.topbar{align-items:flex-start;flex-direction:column;gap:9px}.topbar nav{display:grid;gap:6px}.user-block{width:100%;justify-content:space-between}.filterbar{align-items:stretch;flex-direction:column}.filterbar input[type=search],.filterbar>input[list]{width:100%;min-width:0}',
     '@media(max-width:760px){.topbar{flex-wrap:wrap;gap:6px 12px;padding:8px 12px;min-height:0}.brand-block{min-width:0}.brand-block strong{font-size:17px}.brand-block span{display:none}.topbar nav{order:3;flex:1 1 100%;display:flex;flex-wrap:nowrap;gap:16px;overflow-x:auto;white-space:nowrap;padding-bottom:3px}.user-block{margin-left:auto;gap:8px;min-width:0}.user-block span{max-width:42vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.filterbar{align-items:stretch;flex-direction:row;flex-wrap:wrap;gap:6px;padding:8px 10px;min-height:0}.filterbar>*{min-width:0;max-width:100%}.filterbar>select,.filterbar>label,.filterbar>input,.filterbar>.direktor-ryad{flex:1 1 100%}.filterbar>button{flex:1 1 auto}.filterbar select{width:100%}.filterbar input[type=search],.filterbar>input[list]{width:100%;min-width:0;flex:1 1 100%}',
     'CSS: телефон – шапка, поиск, фильтры', '.brand-block{min-width:0}', True),
]


def nalozhit(teksty):
    """Правки по якорям на словарь текстов {ключ: текст}. -> (новые тексты, журнал, сделано, надо, ок)."""
    novye = dict(teksty)
    zhurnal, sdelano, nado, ok = [], 0, 0, True
    for kl, staro, novo, imya, priznak, obyaz in PRAVKI:
        nado += 1
        t = novye[kl]
        if priznak in t:
            sdelano += 1
            zhurnal.append('[уже] ' + imya)
            continue
        n = t.count(staro)
        if n != 1:
            zhurnal.append('[ЯКОРЬ: %d]%s %s' % (n, '' if obyaz else ' (необязательная)', imya))
            if obyaz:
                ok = False
            continue
        novye[kl] = t.replace(staro, novo, 1)
        sdelano += 1
        zhurnal.append('[ок] ' + imya)
    nado += 1
    if WEB_METKA in novye['W']:
        sdelano += 1
        zhurnal.append('[уже] web.py: фильтры показа')
    else:
        novye['W'] = novye['W'].rstrip('\n') + '\n' + WEB_BLOK
        sdelano += 1
        zhurnal.append('[ок] web.py: фильтры показа')
    return novye, zhurnal, sdelano, nado, ok


def prochitat():
    # файлы на сервере с CRLF: читаем с переводом строк в \n (якоря – с \n), пишем обратно
    # текстовым режимом Windows – снова CRLF, как правят и прежние скрипты панели
    return {k: io.open(p, encoding='utf-8').read() for k, p in FAJLY.items()}


def zapisat(kuda, teksty, klyuchi):
    for k in klyuchi:
        p = kuda[k] if isinstance(kuda, dict) else os.path.join(kuda, STAGE_PUT[k])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, 'w', encoding='utf-8').write(teksty[k])


# ====================================================================== РЕНДЕР И ПРОВЕРКА (venv)
def render(stage, metka, inny, polnyy):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import sqlite3
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    test_db = os.path.join(KOREN, '_bekap', 'fixA-test-%d.db' % os.getpid())
    zh = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
    kop = sqlite3.connect(test_db)
    zh.backup(kop)
    zh.close()
    kop.close()
    os.environ['CENTRO_SALES_DB'] = test_db          # главная раздаёт новые ИНН – пусть в копию
    os.environ['PARK_OCHERED_SALES_DB'] = test_db
    from app import web
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    from jinja2 import ChoiceLoader, FileSystemLoader
    staryy_loader = web.templates.env.loader
    if stage != '-':
        if WEB_METKA not in io.open(web.__file__, encoding='utf-8').read():
            exec(compile(WEB_BLOK, 'web_blok', 'exec'), web.__dict__)     # сухой прогон: живой web.py не тронут
        novyy_loader = ChoiceLoader([FileSystemLoader(os.path.join(stage, 'templates')), staryy_loader])
    else:
        novyy_loader = staryy_loader

    def loader(nov):
        web.templates.env.loader = novyy_loader if nov else staryy_loader
        web.templates.env.cache.clear() if web.templates.env.cache is not None else None

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    plohih = [0]

    def proverit(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    SKLEYKA = re.compile(r'href="tel:\+7\d{12,}')
    z = zipfile.ZipFile(os.path.join(DROP, 'fixA_html_%s.zip' % metka), 'w', zipfile.ZIP_DEFLATED)
    loader(True)
    vnutr.dependency_overrides[rcs.current_user] = lambda: ADMIN
    with TestClient(vnutr) as kl:
        o = kl.get(PUT + '/centro')
        t = o.text
        z.writestr('admin_list.html', t)
        proverit(o.status_code == 200, 'админ: список %s' % o.status_code)
        proverit('class="mest-vr' in t and 'местное ' in t, 'список: местное время в строках (%d)' % t.count('class="mest-vr'))
        proverit('class="lpr-fio"' in t or 'class="lpr-dolzh"' in t, 'список: ЛПР текстом (ФИО %d, должность %d)' % (t.count('class="lpr-fio"'), t.count('class="lpr-dolzh"')))
        proverit('<b class="total-count">' in t, 'список: счётчик компаний на месте')
        o = kl.get(PUT + '/centro', params={'size': '100', 'bitrix': '1'})
        z.writestr('admin_list_bitrix.html', o.text)
        proverit(o.status_code == 200 and 'class="bitrix-stroka"' in o.text and re.search(r'Битрикс КЦ: (?:<span class="klient-sc">Клиент СЦ</span>(?: · )?)?(?:\d+ сдел|есть контакт)', o.text),
                 'список: Битрикс текстом с числом сделок (%d)' % o.text.count('class="bitrix-stroka"'))
        o = kl.get(PUT + '/centro', params={'size': '100'})
        z.writestr('admin_list100.html', o.text)
        for inn in inny:
            o = kl.get(PUT + '/centro', params={'inn': inn})
            t = o.text
            z.writestr('admin_card_%s.html' % inn, t)
            if o.status_code != 200:
                proverit(False, 'карточка %s: %s' % (inn, o.status_code))
                continue
            i = t.find('<h2>Люди предприятия</h2>')
            lyudi = t[i:t.find('</section>', i)] if i >= 0 else ''
            dob_lyudi = len(re.findall(r'<a href="tel:\+7\d{10},\d+">[^<]*доб\. \d+</a>', lyudi))
            proverit(not SKLEYKA.search(t) and 'class="mest-vr' in t and 'Статус не указан' not in t
                     and 'class="st-metka' in t and 'id="fixA-vid"' in t,
                     'карточка %s: 200, склеенных tel: %d, местное время, статус звонка; «доб.» в «Людях»: %d'
                     % (inn, len(SKLEYKA.findall(t)), dob_lyudi))
        o = kl.get(PUT + '/centro/stats')
        z.writestr('admin_stats.html', o.text)
        proverit(o.status_code == 200, 'статистика (админ): %s' % o.status_code)
        if polnyy:
            # обход ВСЕХ карточек: прежние шаблоны против новых
            import sqlite3 as _s
            kat = _s.connect('file:%s?mode=ro' % r'C:\centro2\data\meyer_baza1.db', uri=True)
            vse = [r[0] for r in kat.execute('select inn from company')]
            sost = {r[0]: r[1] for r in _s.connect(test_db).execute('select inn, call_result from company_state')}
            itog = {}
            for nov in (False, True):
                loader(nov)
                sch = {'kart': 0, 'ne200': 0, 'skleyka': 0, 'kart_skleyka': 0, 'status_ne_ukazan': 0,
                       'dob_v_lyudyah': 0, 'kontakt_bez_dolzh': 0, 'kontakt_s_dolzh': 0, 'mest_vr': 0,
                       'citata_details': 0, 'lyudi_svernuto': 0, 'bitrix_tekst': 0, 'klient_sc': 0,
                       'confirm': 0, 'slitno_pokaz': 0, 'chitaemo_pokaz': 0, 'pometka_och': 0}
                for inn in vse:
                    cs = sost.get(inn)
                    params = {'inn': inn}
                    if cs in ('v_rabote', 'ne_ponravilas', 'dubl'):
                        params['call_status'] = cs
                    o = kl.get(PUT + '/centro', params=params)
                    sch['kart'] += 1
                    if o.status_code != 200:
                        sch['ne200'] += 1
                        continue
                    t = o.text
                    n = len(SKLEYKA.findall(t))
                    sch['skleyka'] += n
                    sch['kart_skleyka'] += 1 if n else 0
                    sch['status_ne_ukazan'] += 'Статус не указан' in t
                    i = t.find('<h2>Люди предприятия</h2>')
                    lyudi = t[i:t.find('</section>', i)] if i >= 0 else ''
                    sch['dob_v_lyudyah'] += len(re.findall(r'<a href="tel:\+7\d{10},\d+">[^<]*доб\. \d+</a>', lyudi))
                    sch['lyudi_svernuto'] += lyudi.count('Уже в «Контактах» выше')
                    i = t.find('contacts-section')
                    kont = t[i:t.find('</section>', i)] if i >= 0 else ''
                    for blok in re.findall(r'<div class="contact-person">(.*?)</div>', kont, re.S):
                        if '<b>' in blok and 'Имя не указано' not in blok:
                            if '<span>' in blok:
                                sch['kontakt_s_dolzh'] += 1
                            else:
                                sch['kontakt_bez_dolzh'] += 1
                    sch['mest_vr'] += 'class="mest-vr' in t
                    sch['citata_details'] += t.count('class="citata"')
                    sch['bitrix_tekst'] += 'class="bitrix-blok"' in t
                    sch['klient_sc'] += 'Клиент СЦ</span>' in t
                    sch['pometka_och'] += 'class="tag tag-pometka"' in t
                    sch['confirm'] += t.count('return confirm(')
                    sch['slitno_pokaz'] += len(re.findall(r'class="contact-value"[^>]*>\+7\d{10}', t))
                    sch['chitaemo_pokaz'] += len(re.findall(r'class="contact-value"[^>]*>(?:\+7 |8 800)', t))
                itog['posle' if nov else 'do'] = sch
            print('   обход всех карточек (до -> после):')
            for k in itog['do']:
                print('      %-18s %6s -> %s' % (k, itog['do'][k], itog['posle'][k]))
            io.open(os.path.join(DROP, 'fixA_obhod_%s.json' % metka), 'w', encoding='utf-8').write(json.dumps(itog, ensure_ascii=False, indent=1))
            proverit(itog['posle']['ne200'] == 0 and itog['posle']['skleyka'] == 0 and itog['posle']['status_ne_ukazan'] == 0,
                     'все карточки: 200, склеенных tel: 0, «Статус не указан»: 0')
            loader(True)
    vnutr.dependency_overrides[rcs.current_user] = lambda: PROD
    with TestClient(vnutr) as kl:
        o = kl.get(PUT + '/centro')
        t = o.text
        z.writestr('sales_list.html', t)
        proverit(o.status_code == 200 and 'class="mest-vr' in t, 'продавец: список %s, местное время' % o.status_code)
        moi = re.findall(r'data-href="[^"]*inn=(\d{10,12})', t)[:3]
        for inn in moi + [i for i in inny if i not in moi]:
            o = kl.get(PUT + '/centro', params={'inn': inn})
            if o.status_code == 404 and inn not in moi:
                continue                                   # не его компания – 404 ожидаем
            z.writestr('sales_card_%s.html' % inn, o.text)
            proverit(o.status_code == 200 and not SKLEYKA.search(o.text) and 'class="mest-vr' in o.text,
                     'продавец: карточка %s %s' % (inn, o.status_code))
        o = kl.get(PUT + '/centro/stats')
        proverit(o.status_code == 403, 'продавец: статистика закрыта (%s)' % o.status_code)
    z.close()
    try:
        os.remove(test_db)
    except OSError:
        pass
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    stage, metka = sys.argv[i + 1], sys.argv[i + 2]
    ost = sys.argv[i + 3:]
    polnyy = '--polnyy' in ost
    inny = [x for x in ost if x.isdigit()] or PRIMERY
    render(stage, metka, inny, polnyy)
    raise SystemExit(0)

SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')


def zapustit_render(stage, metka, dop):
    r = subprocess.run([VENV, os.path.abspath(__file__), '--render', stage, metka] + dop,
                       capture_output=True, timeout=1500, cwd=KOREN, env=SREDA)
    vyvod = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-4000:]
    return r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod, vyvod


# ====================================================================== СУХОЙ ПРОГОН (без замка)
if '--suho' in sys.argv:
    i = sys.argv.index('--suho')
    dop = sys.argv[i + 1:]
    teksty = prochitat()
    novye, zhurnal, sdelano, nado, ok = nalozhit(teksty)
    for x in zhurnal:
        print('   ' + x)
    print('правок: %d из %d%s' % (sdelano, nado, '' if ok else ' – ОБЯЗАТЕЛЬНЫЕ НЕ ВСЕ'))
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    zapisat(STAGE, novye, ['C', 'L', 'W', 'S'])
    with zipfile.ZipFile(os.path.join(DROP, 'fixA_stage.zip'), 'w', zipfile.ZIP_DEFLATED) as zz:
        for k in ('C', 'L', 'W', 'S'):
            zz.writestr(STAGE_PUT[k].replace('\\', '/'), novye[k])
            zz.writestr('do/' + STAGE_PUT[k].replace('\\', '/'), teksty[k])
    if not ok:
        raise SystemExit(1)
    good, vyvod = zapustit_render(STAGE, 'suho', dop)
    io.open(os.path.join(DROP, 'fixA_suho.txt'), 'w', encoding='utf-8').write(vyvod)
    sys.stdout.write(vyvod[-5000:])
    raise SystemExit(0)


# ====================================================================== ПРИМЕНЕНИЕ (под замком)
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


if '--primenit' in sys.argv:
    BEKAP = os.path.join(KOREN, '_bekap', time.strftime('fixA-%Y%m%d-%H%M%S'))
    vzyat_zamok('fixA (вид карточки и списка)')
    try:
        teksty = prochitat()
        novye, zhurnal, sdelano, nado, ok = nalozhit(teksty)
        for x in zhurnal:
            print('   ' + x)
        print('правок: %d из %d' % (sdelano, nado))
        if not ok:
            print('ОБЯЗАТЕЛЬНЫЕ ЯКОРЯ НЕ НАЙДЕНЫ – ничего не записано')
            raise SystemExit(1)
        izm = [k for k in FAJLY if novye[k] != teksty[k]]
        os.makedirs(BEKAP, exist_ok=True)
        for k in FAJLY:
            shutil.copy2(FAJLY[k], os.path.join(BEKAP, os.path.basename(FAJLY[k])))
        print('бэкап: %s; меняются: %s' % (BEKAP, ', '.join(os.path.basename(FAJLY[k]) for k in izm)))
        # 1) web.py – живой процесс его не видит до перезапуска; 2) шаблоны и CSS – в STAGE
        zapisat(FAJLY, novye, ['W'])
        if os.path.isdir(STAGE):
            shutil.rmtree(STAGE, ignore_errors=True)
        zapisat(STAGE, novye, ['C', 'L', 'S'])
        good, vyvod = zapustit_render(STAGE, 'primenit', [])
        io.open(os.path.join(DROP, 'fixA_proverka.txt'), 'w', encoding='utf-8').write(vyvod)
        if not good:
            shutil.copy2(os.path.join(BEKAP, 'web.py'), FAJLY['W'])
            print('ПРОВЕРКА НЕ ПРОШЛА – web.py возвращён из бэкапа, шаблоны не тронуты, перезапуска нет')
            sys.stdout.write(vyvod[-4500:])
            raise SystemExit(1)
        # 3) web.py менялся – остановка -> шаблоны и CSS на место -> запуск; не менялся (фильтры
        #    уже в живом процессе) – шаблоны на место без перезапуска, их процесс перечитывает сам
        if 'W' in izm:
            ostanovit()
            zapisat(FAJLY, novye, ['C', 'L', 'S'])
            kod = zapustit('исправитель A: вид карточки и списка')
            print('перезапущено, вход: %s' % kod)
        else:
            zapisat(FAJLY, novye, [k for k in ('C', 'L', 'S') if k in izm])
            import urllib.request
            try:
                kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            except Exception as e:  # noqa: BLE001
                kod = str(e)[:80]
            print('без перезапуска (web.py не менялся), вход: %s' % kod)
        good2, vyvod2 = zapustit_render('-', 'posle', [])
        io.open(os.path.join(DROP, 'fixA_proverka_posle.txt'), 'w', encoding='utf-8').write(vyvod2)
        if kod != 200 or not good2:
            for k in izm:
                shutil.copy2(os.path.join(BEKAP, os.path.basename(FAJLY[k])), FAJLY[k])
            if 'W' in izm:
                ostanovit()
                kod = zapustit('исправитель A: ОТКАТ')
            print('ПОСЛЕ ПЕРЕЗАПУСКА ПЛОХО – свои файлы возвращены, снова запущено, вход: %s' % kod)
            sys.stdout.write(vyvod2[-3000:])
            raise SystemExit(1)
        print('===== ПРОВЕРКА ДО ЗАПИСИ (fixA_proverka.txt) =====')
        sys.stdout.write(vyvod[-2500:])
        print('===== ПРОВЕРКА ЖИВЫХ ФАЙЛОВ ПОСЛЕ ПЕРЕЗАПУСКА (fixA_proverka_posle.txt) =====')
        sys.stdout.write(vyvod2[-2500:])
    finally:
        otdat_zamok()
