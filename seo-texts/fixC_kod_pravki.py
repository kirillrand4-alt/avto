# -*- coding: utf-8 -*-
"""fixC: правки app/services/centro_catalog.py – роли номеров по смыслу, порядок и вид номера.

Используется серверным fixC_kod.py (под замком) и локальной проверкой. primenit(tekst)
заменяет четыре функции целиком (_shared_phone_keys, role_phone_inns, contacts, persons) –
только если их текущий текст совпадает с ожидаемым (md5), иначе ничего не трогает: значит,
функцию успел поменять другой агент, и править вслепую нельзя. Блок классификатора
(fixC_klass_kod.py) дописывается в конец модуля. Идемпотентно: признак – строка МЕТКА.
"""
import hashlib
import os
import re

METKA = '# ======================================================================= fixC: роли номеров'

ZHDEM_MD5 = {   # тексты функций в живом файле на 08.10 (до правки)
    '_shared_phone_keys': None, 'role_phone_inns': None, 'contacts': None, 'persons': None,
}

NOVYE = {}

NOVYE['_shared_phone_keys'] = '''def _shared_phone_keys(conn) -> set[str]:
    """Ключи телефонов, которые НЕ могут быть личными: «номер#добавочный».

    Первая версия правила была «номер у 2+ разных ИНН — не личный», и 2-я
    сессия показала на замере, что оно ошибается в 18 % случаев, причём в обе
    стороны:
      * «Чикуров В.В.» и «Чикуров Владимир Васильевич» — это ОДИН человек, а
        сравнение строк целиком объявляло их двумя и снимало роль зря;
      * человек реально работает на двух предприятиях (Сидиченко А.А.), и его
        личный мобильный оставался личным, а прежнее правило его снимало.
    Поэтому решает ФАМИЛИЯ, а не число ИНН: две разных фамилии на одном номере
    — это линия площадки; одна фамилия при двух предприятиях — живой человек.
    Номер без имени у 2+ предприятий тоже считаем общим: подтвердить некем.

    fixC 08.10: ключ – номер ВМЕСТЕ с добавочным. Раньше «+7 495 000-00-00 доб. 101» и
    «… доб. 102» были одним ключом, на нём стояли разные фамилии, и у ТМС (7203319557)
    17 человек на общем коммутаторе с личными добавочными теряли роль как «линия».
    """
    by_key: dict[str, dict] = {}
    try:
        # копия номера со страницы ДРУГОГО юрлица (chuzhoy_istochnik) общим номер не делает:
        # она известна как чужая и в счёт «двух компаний» не идёт (Бессоновский)
        chuzh = "chuzhoy_istochnik" in table_columns(conn, "contact")
        for inn, value, person in conn.execute(
                "SELECT inn, value, COALESCE(person,'') FROM contact "
                "WHERE kind='phone' AND COALESCE(value,'')<>''"
                + (" AND TRIM(COALESCE(chuzhoy_istochnik,''))=''" if chuzh else "")):
            k = _phone_key_dob(value)
            if not k:
                continue
            зап = by_key.setdefault(k, {"inns": set(), "fam": set(),
                                        "безымянных": 0})
            зап["inns"].add(str(inn))
            f = _familiya_fixC(person)
            if f:
                зап["fam"].add(f)
            else:
                зап["безымянных"] += 1
    except Exception:  # noqa: BLE001
        return set()
    общие = set()
    for k, з in by_key.items():
        if len(з["fam"]) >= 2:
            общие.add(k)            # разные люди на одном номере — линия
        elif len(з["inns"]) >= 2 and not з["fam"]:
            общие.add(k)            # много предприятий и ни одного имени
    return общие


def _familiya_fixC(person: object) -> str:
    """Фамилия без путаницы с именем: «Сергей Лемтюгов» и «Лемтюгов Сергей» – один человек
    (прежняя _familiya брала первое слово и объявляла их двумя, номер становился «линией»)."""
    w = [x for x in re.sub(r"[^А-Яа-яЁёA-Za-z\s.-]", " ", str(person or "")).replace(".", " ").split() if len(x) > 1]
    for x in w:
        n = x.lower().replace("ё", "е")
        if n not in _IMENA_FIXC and not re.search(r"(?:ович|евич|ич|овна|евна|ична|инична)$", n):
            return n.strip(".-")
    return w[0].lower() if w else ""


def _phone_key_dob(raw: object) -> str:
    """10 цифр номера + «#добавочный», если он есть: у людей на одном коммутаторе ключи разные."""
    osn, dob = _razdelit_dobavochnyy(raw)
    k = _phone_key(osn)
    return (k + "#" + dob) if (k and dob) else k
'''

NOVYE['role_phone_inns'] = '''def role_phone_inns() -> set[str]:
    """ИНН компаний, где есть телефон НАСТОЯЩЕГО ЛПР (метка «телефон с ролью»).

    fixC 08.10: роль решает rol_kontakta() – по смыслу должности, а не по слову и не по
    «непустой должности». Прежнее правило (любая должность длиннее 3 знаков) давало метку
    167 из 169 компаний Базы 3 за текст «мобильный с сайта, без подписи», а закупщику
    молока или горячей линии – за слова «закупки» и «качество». Номер, общий у двух
    компаний, роль больше не теряет (у «Азбуки сыра» это линия снабжения), а номер со
    страницы другого юрлица, мусор и битые номера ЛПР не бывают.
    """
    with connect() as conn:
        columns = table_columns(conn, "contact")
        if not columns or "kind" not in columns:
            return set()
        rows = _rows(conn, "SELECT * FROM contact WHERE kind='phone'")
    return {str(r.get("inn")) for r in rows if r.get("inn") and rol_kontakta(r)["lpr"]}
'''

NOVYE['contacts'] = '''def contacts(inn: str) -> list[dict]:
    """Контакты карточки: наверху ЛПР по уровням владельца, ниже – «Остальные номера».

    fixC 08.10 (проверка панели продавцами):
      * роль – по смыслу должности (rol_kontakta): закупщик сырья, продажи, кадры,
        бухгалтерия, факс, экскурсии, доставка, горячая линия – не ЛПР и не наверху;
      * порядок наверху – первое лицо → техдиректор/главный инженер → главный механик/
        энергетик → производство → главный технолог → снабжение → коммерческий директор;
      * ЛПР без телефона (ФИО и должность есть на странице) – отдельной строкой
        «спросить у приёмной: ФИО» без номера, в своём уровне;
      * номер, общий у двух компаний, больше НЕ теряет роль и должность (прежде у
        снабжения «Азбуки сыра» стиралось всё, и номер уходил вниз без подписи);
      * вид номера: мобильный / рабочий / 8-800 / Казахстан / международный / битый /
        не номер компании / только в ссылке tel: – в ключе vid_nomera, причина в vid_pochemu;
      * номер со страницы другого юрлица (chuzhoy_istochnik) – не ЛПР, внизу, с меткой.
    Без ЛПР наверху остаются пути к ним: приёмная, общий номер, номер без подписи,
    техслужба. Неличные номера уходят в «Остальные», приёмная там первой.
    """
    with connect() as conn:
        columns = table_columns(conn, "contact")
        if not columns:
            return []
        rows = _rows(conn, "SELECT * FROM contact WHERE inn=? ORDER BY id", (inn,))
        shared = _shared_phone_keys(conn)
        sprosit = _sprosit_u_priemnoy(conn, inn)

    result: list[dict] = []
    for row in rows:
        item = dict(row)
        kind = str(item.get("kind") or "").strip().lower()
        value = str(item.get("value") or "").strip()
        rk = rol_kontakta(row) if kind == "phone" else {
            "vid": "почта" if kind == "email" else "другое", "lpr": 0, "uroven": 0,
            "teh": 0, "zakup": 0, "musor": 0}
        obshchiy = kind == "phone" and _phone_key_dob(value) in shared
        if kind == "phone":
            # добавочный сохраняется в показе: раньше «+7 495 000-00-00 доб. 212»
            # превращалось в «+78310000000212», и продавец добавочного не видел
            osn, dob = _razdelit_dobavochnyy(value)
            value = (normalize_phone(osn) or osn) + (" доб. " + dob if dob else "")
        dolzh = str(item.get("position") or "").strip()
        if dolzh == "мобильный с сайта, без подписи":       # это не должность
            dolzh = ""
        item["kind"] = kind
        item["value"] = value
        item["person"] = str(item.get("person") or "").strip()
        item["position"] = dolzh
        item["role"] = str(dolzh or item.get("role") or "").strip()
        item["source"] = str(item.get("source") or "").strip()
        item["source_url"] = safe_source_url(item.get("source_url"))
        item["href"] = contact_href(kind, value)
        item["chuzhoy_istochnik"] = str(item.get("chuzhoy_istochnik") or "").strip()
        vid_n = str(item.get("vid_nomera") or "").strip()
        if kind == "phone" and (not vid_n or vid_n in _VIDY_OBYCHNYE):
            vid_n = vid_nomera_po_cifram(value)
        if vid_n in ("8-800", "международный", "Казахстан") or vid_n in _VIDY_OBYCHNYE:
            item["phone_type"] = vid_n          # fixC2: вид по цифрам и в phone_type
        if obshchiy and vid_n in _VIDY_OBYCHNYE | {"8-800"}:
            vid_n = "общий с другой компанией"
        item["vid_nomera"] = vid_n
        item["vid_pochemu"] = str(item.get("vid_pochemu") or "").strip()
        item["obshchiy_nomer"] = int(obshchiy)
        item["rol_vid"] = rk["vid"]
        item["lpr"] = rk["lpr"]
        item["uroven"] = rk["uroven"]
        item["lpr_metka"] = ("ЛПР: " + rk["vid"]) if rk["lpr"] else ""
        item["is_tech"] = rk["teh"]
        item["is_purchaser"] = rk["zakup"]
        item["is_unknown_owner"] = int(bool(item.get("is_unknown_owner")))
        item["nomer_ne_lichnyy"] = "" if rk["lpr"] else rk["vid"]
        item["sprosit"] = 0
        result.append(item)

    # ЛПР без телефона – «спросить у приёмной: ФИО, должность»
    imena = {_kl_fio(x["person"]) for x in result if x["person"]}
    for p in sprosit:
        rk = rol_kontakta({"position": p.get("position"), "role": p.get("role"),
                           "chuzhoy_istochnik": p.get("chuzhoy_istochnik")})
        if not rk["lpr"] or _kl_fio(p.get("person")) in imena:
            continue
        imena.add(_kl_fio(p.get("person")))
        fio = str(p.get("person") or "").strip()
        primech = str(p.get("sprosit_u_priemnoy") or "").strip()
        result.append({
            "id": "p%s" % p.get("id"), "inn": inn, "kind": "sprosit",
            "value": "спросить у приёмной: " + fio, "href": "", "person": fio,
            "position": str(p.get("position") or "").strip(),
            "role": str(p.get("position") or p.get("role") or "").strip(),
            "phone_type": "", "vid_nomera": "без номера: спросить у приёмной",
            "vid_pochemu": primech, "source": str(p.get("source") or "").strip(),
            "source_url": safe_source_url(p.get("source_url")), "fragment": "",
            "chuzhoy_istochnik": "", "obshchiy_nomer": 0, "rol_vid": rk["vid"],
            "lpr": 1, "uroven": rk["uroven"], "lpr_metka": "ЛПР: " + rk["vid"],
            "is_tech": rk["teh"], "is_purchaser": rk["zakup"], "is_unknown_owner": 0,
            "nomer_ne_lichnyy": "", "sprosit": 1, "has_role": 1})

    est_lpr = any(x["lpr"] and x["kind"] == "phone" for x in result)
    for x in result:
        naverh = bool(x["lpr"]) or (
            not est_lpr and x["kind"] == "phone" and x["rol_vid"] in _PUTI_K_LPR
            and x["vid_nomera"] not in _VIDY_NE_PUT)
        x["has_role"] = int(naverh)
        if not naverh and not x["nomer_ne_lichnyy"]:
            x["nomer_ne_lichnyy"] = x["rol_vid"] or "без роли"

    def _mob(x):
        return 0 if x.get("vid_nomera") == "мобильный" or str(x.get("phone_type")) == "мобильный" else 1

    def _zam(x):
        return 1 if re.search(r"(?i)заместител|\\bзам\\.|помощник|и\\.\\s?о\\.", x.get("position") or "") else 0

    def kl_verh(x):
        if x["uroven"]:
            u = x["uroven"]
        else:
            u = 10 + (_PUTI_K_LPR.index(x["rol_vid"]) if x["rol_vid"] in _PUTI_K_LPR else 9)
        # внутри уровня: сначала названные, номера одного человека рядом (мобильный первым)
        return (u, _zam(x), x["sprosit"], 0 if x["person"] else 1, _kl_fio(x["person"]), _mob(x), str(x.get("id")))

    def kl_niz(x):
        i = PORYADOK_OSTALNYH.index(x["rol_vid"]) if x["rol_vid"] in PORYADOK_OSTALNYH else len(PORYADOK_OSTALNYH) - 4
        return (i, 0 if x["person"] else 1, _mob(x), str(x.get("id")))

    verh = sorted([x for x in result if x["has_role"]], key=kl_verh)
    niz = sorted([x for x in result if not x["has_role"]], key=kl_niz)
    return verh + niz


def _sprosit_u_priemnoy(conn, inn: str) -> list[dict]:
    """Люди предприятия без телефона (ЛПР со страницы: «спросить у приёмной»)."""
    try:
        kol = table_columns(conn, "person")
        if not kol:
            return []
        uslov = ["inn=?", "TRIM(COALESCE(phone,''))=''", "TRIM(COALESCE(person,''))<>''"]
        if "privyazka_snyata" in kol:
            uslov.append("COALESCE(privyazka_snyata,0)=0")
        if "chuzhoy_istochnik" in kol:
            uslov.append("TRIM(COALESCE(chuzhoy_istochnik,''))=''")
        return _rows(conn, "SELECT * FROM person WHERE " + " AND ".join(uslov) + " ORDER BY id", (inn,))
    except Exception:  # noqa: BLE001
        return []
'''

NOVYE['persons'] = '''def persons(inn: str) -> list[dict]:
    with connect() as conn:
        columns = table_columns(conn, "person")
        if not columns:
            return []
        rows = _rows(
            conn,
            "SELECT * FROM person WHERE inn=? "
            "ORDER BY COALESCE(is_tech,0) DESC, CASE WHEN COALESCE(role,'')<>'' THEN 0 ELSE 1 END, id",
            (inn,),
        )
    result: list[dict] = []
    for row in rows:
        role = str(row.get("role") or "").strip()
        position = str(row.get("position") or row.get("dolzhnost") or "").strip()
        # fixC 08.10: добавочный не склеивается с номером («+78310000000105» набирал
        # несуществующий номер) – «+7… доб. 105», как у контактов
        osn, dob = _razdelit_dobavochnyy(row.get("phone") or row.get("nomer_10cifr"))
        tel = normalize_phone(osn)
        chuzhoy = str(row.get("chuzhoy_istochnik") or "").strip()
        rk = rol_kontakta({"position": position, "role": role, "chuzhoy_istochnik": chuzhoy})
        result.append(
            {
                **row,
                "person": row.get("person") or row.get("fio") or "",
                "position": position,
                "role": role,
                "phone": (tel + (" доб. " + dob if dob else "")) if tel else "",
                "email": row.get("email") or row.get("pochta") or "",
                "source": row.get("source") or row.get("istochnik") or "",
                "source_url": safe_source_url(row.get("source_url") or row.get("ssylka")),
                "is_tech": int(bool(row.get("is_tech") or str(row.get("tehLPR") or "").casefold() == "да")),
                "has_role": int(_meaningful_role(role) or _meaningful_role(position)),
                "rol_vid": rk["vid"],
                "lpr": rk["lpr"],
                "chuzhoy_istochnik": chuzhoy,
                # человек со страницы другого юрлица – в свёрнутый блок «привязка снята»
                "privyazka_snyata": int(bool(row.get("privyazka_snyata")) or bool(chuzhoy)),
            }
        )
    return result
'''

_KLASS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixC_klass_kod.py')

DOP = '''

# fixC: вспомогательное для contacts()
_VIDY_OBYCHNYE = {"мобильный", "рабочий", "рабочий с добавочным"}
_VIDY_NE_PUT = {"международный", "Казахстан", "битый номер", "не номер компании",
                "номер только в ссылке tel:"}
# без ЛПР наверху – пути к нему: приёмная, общий номер, номер без подписи, техслужба
_PUTI_K_LPR = ["приёмная", "общий номер", "техслужба (не ЛПР)", "без подписи"]
_KODY_3 = set("""301 302 341 342 343 345 346 347 349 351 352 353 365 381 382 383 384 385 388 390 391
394 395 401 411 413 415 416 421 423 424 426 427 471 472 473 474 475 481 482 483 484 485 486 487
491 492 493 494 495 496 498 499 800 811 812 813 814 815 816 817 818 820 821 831 833 834 835 836
841 842 843 844 845 846 847 848 851 855 856 857 861 862 863 865 866 867 869 871 872 873 877 878
879""".split())


_IMENA_FIXC = set("""александр алексей анатолий андрей антон аркадий арсений артем артур борис вадим валентин
валерий василий виктор виталий владимир владислав вячеслав геннадий георгий герман глеб григорий даниил данил
денис дмитрий евгений егор иван игорь илья кирилл константин лев леонид максим марат матвей михаил никита
николай олег павел петр роман руслан рустам семен сергей станислав степан тимофей тимур федор филипп эдуард
юрий яков ярослав ильдар айдар азат ринат рамиль ильнур булат фарид альберт магомед мурат ислам акиф
александра алена алина алла анастасия анна антонина валентина валерия вера вероника виктория галина дарья
диана евгения екатерина елена елизавета жанна зинаида инна ирина карина кира кристина ксения лариса лидия
любовь людмила маргарита марина мария надежда наталья наталия нина оксана ольга полина раиса регина светлана
софия софья тамара татьяна ульяна эльвира юлия яна гульшат гульнара альбина лилия эльмира""".split())


def _kl_fio(f: object) -> str:
    """Ключ человека: фамилия + первая буква имени («Соловей Е.В.» = «Соловей Евгений»)."""
    w = re.sub(r"[^А-Яа-яЁё ]", " ", str(f or "")).replace("ё", "е").replace("Ё", "Е").split()
    if not w:
        return ""
    fam = _familiya_fixC(" ".join(w))
    drugie = [x for x in w if x.lower() != fam]
    return (fam + " " + (drugie[0][0].lower() if drugie else "")).strip()
'''


def blok():
    kod = open(_KLASS, encoding='utf-8').read()
    # проверка кода города – в общем классификаторе вида номера
    kod = kod.replace('''    if d[1] not in "3489":
        return "битый номер"''', '''    if d[1] not in "3489":
        return "битый номер"
    if d[1] in "348" and d[1:4] not in _KODY_3:
        return "битый номер"''')
    # личный номер ЛПР «от продавца» (результат звонка «Получен личный номер ЛПР»)
    kod = kod.replace('''    uroven = ROLI_LPR.get(vid, 0)
    return {"vid": vid,''', '''    if (str(item.get("source") or "").startswith("от продавца") and vid not in ROLI_LPR
            and vid not in VIDY_MUSOR and vid not in ("с сайта другого юрлица", "номер только в ссылке tel:")):
        vid = "ЛПР со слов продавца"
    uroven = ROLI_LPR.get(vid, 0)
    return {"vid": vid,''')
    kod = kod.replace('''    "производство": 4, "главный технолог": 5, "снабжение": 6, "коммерческий директор": 7,
}''', '''    "производство": 4, "главный технолог": 5, "снабжение": 6, "коммерческий директор": 7,
    "ЛПР со слов продавца": 7,
}''')
    # битый по цифрам – не ЛПР, даже если колонку vid_nomera ещё не заполнили
    kod = kod.replace('''    elif str(item.get("vid_nomera") or "").strip() in VIDY_MUSOR | {"номер только в ссылке tel:"}:
        vid = str(item.get("vid_nomera")).strip()''', '''    elif str(item.get("vid_nomera") or "").strip() in VIDY_MUSOR | {"номер только в ссылке tel:"}:
        vid = str(item.get("vid_nomera")).strip()
    elif item.get("value") and vid_nomera_po_cifram(item.get("value")) == "битый номер":
        vid = "битый номер"''')
    assert kod.count('_KODY_3') == 1 and 'ЛПР со слов продавца' in kod and 'vid_nomera_po_cifram(item.get' in kod
    return kod + DOP


def _najti_funkciyu(t, imya):
    m = re.search(r'^def %s\(' % re.escape(imya), t, re.M)
    if not m:
        return None
    sled = re.search(r'^(?:def |class |_[A-Za-zА-Яа-яЁё0-9_]+\s*=|# ====|[A-Za-zА-Яа-яЁё_]+\s*=)', t[m.end():], re.M)
    kon = m.end() + sled.start() if sled else len(t)
    return m.start(), kon


def md5(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def primenit(t, zhdem=None):
    """-> (новый текст, журнал). Если функция изменилась (md5 не тот) – исключение."""
    zhurnal = []
    if METKA in t:
        return t, ['[уже] правки fixC в файле есть']
    for imya, novyy in NOVYE.items():
        a, b = _najti_funkciyu(t, imya)
        staryy = t[a:b]
        if zhdem and zhdem.get(imya) and md5(staryy.rstrip()) != zhdem[imya]:
            raise RuntimeError('функция %s изменилась после разбора (md5 %s) – не правлю' % (imya, md5(staryy.rstrip())))
        t = t[:a] + novyy.rstrip() + '\n\n\n' + t[b:].lstrip('\n')
        zhurnal.append('[ок] %s заменена (%d -> %d строк)' % (imya, staryy.count('\n'), novyy.count('\n')))
    t = t.rstrip('\n') + '\n' + blok()
    zhurnal.append('[ок] классификатор ролей дописан в конец модуля')
    return t, zhurnal


if __name__ == '__main__':
    import sys
    src = sys.argv[1]
    t = open(src, encoding='utf-8').read()
    for imya in NOVYE:
        a, b = _najti_funkciyu(t, imya)
        print(imya, md5(t[a:b].rstrip()), t[a:b].count('\n'))
    if len(sys.argv) > 2:
        nt, zh = primenit(t)
        open(sys.argv[2], 'w', encoding='utf-8').write(nt)
        print('\n'.join(zh))
