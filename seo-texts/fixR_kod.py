# -*- coding: utf-8 -*-
r"""fixR 13.10: номера Беларуси (+375) – как обычные, с меткой «РБ». Правка кода панели Meyer.

Владелец 13.10: «Белорусские ЛПР с номерами +375 система считает „международными“, поэтому они не попадают
на верхние ступени очереди. = сделай, и пометь что это РБ».

Что меняется (по уникальным якорям, чтение-правка-запись под замком C:\centro2\_zamok.txt):
  services/centro_catalog.py – nomer_rb(): номер Беларуси (+375…, 375… из 12 цифр, внутренний «8 0XX …»,
      «8 10 375 …», 8-801); vid_nomera_po_cifram: мобильные коды 25/29/33/44 – «мобильный», прочие –
      «рабочий» / «рабочий с добавочным», 8-801 – «8-800»; contacts(): записанный номеру РБ вид
      «международный» пересчитывается по цифрам; normalize_phone: «8 029 …» -> «+375 29 …»; _phone_key:
      «8 029 …» и «+375 29 …» – один ключ. Номера других стран и России – как были.
  web.py – показ: «+375 29 000-00-00», ссылка tel:+375…, метка вида «мобильный · РБ» с подсказкой
      «Номер Беларуси (+375): звонок международный»; метки «международный · Беларусь» больше нет;
      список: вид номера ЛПР «мобильный · РБ».
  api/routes_centro_sales.py – строка ЛПР (lpr_kratko) с номером РБ в читаемом виде; ключ номера РБ для
      поиска и сверки повторов.
  services/centro_sales.py – номер от менеджера «8 029 …» -> +375 29 …, показ «+375 29 000-00-00».
  templates/_ochered_spisok.html – подсветка «мобильный» и у «мобильный · РБ».

    python3 zapusk_na_servere.py fixR_kod.py --suho       # копия кода (stage) и копии баз, живое не трогается
    python3 zapusk_na_servere.py fixR_kod.py --primenit   # под замком: проверка на stage -> запись -> перезапуск
"""
import collections
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
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
PORT = 8016
ZAMOK = r'C:\centro2\_zamok.txt'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_bekap', 'fixR-stage')
PRODAVCY = ['meyer%d' % i for i in range(1, 10)]
FAJLY = {'CC': 'services/centro_catalog.py', 'W': 'web.py', 'R': 'api/routes_centro_sales.py',
         'S': 'services/centro_sales.py', 'L': 'templates/_ochered_spisok.html'}
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')

# ====================================================================== правки
CC1_STARO = '''def vid_nomera_po_cifram(value: object) -> str:
    """Вид номера по цифрам: мобильный / 8-800 / городской / Казахстан / международный / битый."""
    osn, dob = _razdelit_dobavochnyy(value)
'''
CC1_NOVO = '''# ======================================================================= fixR 13.10: Беларусь
# Владелец 13.10: «белорусские ЛПР с номерами +375 система считает „международными“, поэтому они не
# попадают на верхние ступени очереди – сделай и пометь, что это РБ». Номер Беларуси – обычный номер:
# мобильные коды 25, 29, 33, 44 – «мобильный», прочие (17 Минск, 15х, 16х, 21х, 22х, 23х …) – «рабочий»
# («рабочий с добавочным»), 8-801 – бесплатная линия, как «8-800». Белорусский внутренний формат
# «8 0XX XXX-XX-XX» (11 цифр на «80»: у России кодов на 0 нет) – тот же +375. Метку «РБ» ставит показ (web.py).
_FIXR_RB_MOB = ("25", "29", "33", "44")


def nomer_rb(value: object) -> dict:
    """Номер Беларуси -> {"cifry": «375290000000», "pokaz": «+375 29 000-00-00», "href": «tel:+375290000000»,
    "vid": «мобильный» / «рабочий» / «рабочий с добавочным» / «8-800», "dob"}; не Беларусь -> {}."""
    try:
        osn, dob = _razdelit_dobavochnyy(value)
        s = str(osn or "").strip()
        d = re.sub(r"\\D", "", s)
        plyus = s.startswith("+")
        if len(d) == 12 and d.startswith("375"):
            n = d[3:]
        elif not plyus and len(d) == 11 and d.startswith("80"):
            n = d[2:]
        elif not plyus and len(d) == 15 and d.startswith("810375"):
            n = d[6:]
        elif not plyus and len(d) == 11 and d.startswith("8801"):
            # 8-801 – бесплатная линия Беларуси, набирается только внутри РБ
            return {"cifry": d, "pokaz": "8 801 %s-%s-%s" % (d[4:7], d[7:9], d[9:]) + (" доб. " + dob if dob else ""),
                    "href": "tel:" + d + ("," + dob if dob else ""), "vid": "8-800", "dob": dob}
        else:
            return {}
        if n.startswith("801"):
            vid = "8-800"
        elif n[:2] in _FIXR_RB_MOB:
            vid = "мобильный"
        else:
            vid = "рабочий с добавочным" if dob else "рабочий"
        return {"cifry": "375" + n,
                "pokaz": "+375 %s %s-%s-%s" % (n[:2], n[2:5], n[5:7], n[7:]) + (" доб. " + dob if dob else ""),
                "href": "tel:+375" + n + ("," + dob if dob else ""), "vid": vid, "dob": dob}
    except Exception:  # noqa: BLE001
        return {}


def vid_nomera_po_cifram(value: object) -> str:
    """Вид номера по цифрам: мобильный / 8-800 / городской / Казахстан / международный / битый."""
    _rb = nomer_rb(value)          # fixR 13.10: Беларусь – мобильный / рабочий / 8-800, не «международный»
    if _rb:
        return _rb["vid"]
    osn, dob = _razdelit_dobavochnyy(value)
'''
CC2_STARO = '''def normalize_phone(raw: object) -> str:
    digits = re.sub(r"\\D", "", str(raw or ""))
'''
CC2_NOVO = '''def normalize_phone(raw: object) -> str:
    _rb = nomer_rb(raw)            # fixR 13.10: «8 029 …» -> «+375 29 …»; 8-801 Беларуси – как есть
    if _rb:
        return _rb["cifry"] if _rb["cifry"].startswith("8") else "+" + _rb["cifry"]
    digits = re.sub(r"\\D", "", str(raw or ""))
'''
CC3_STARO = '''        if kind == "phone" and (not vid_n or vid_n in _VIDY_OBYCHNYE):
            vid_n = vid_nomera_po_cifram(value)
'''
CC3_NOVO = '''        if kind == "phone" and (not vid_n or vid_n in _VIDY_OBYCHNYE
                                or (vid_n == "международный" and nomer_rb(value))):
            # fixR 13.10: «международный», записанный номеру Беларуси (+375), пересчитывается по цифрам
            vid_n = vid_nomera_po_cifram(value)
'''
CC4_STARO = '''    d = re.sub(r"\\D", "", _bez_dobavochnogo(raw))
    return d[-10:] if len(d) >= 10 else ""
'''
CC4_NOVO = '''    d = re.sub(r"\\D", "", _bez_dobavochnogo(raw))
    if len(d) == 11 and d.startswith("80"):      # fixR 13.10: Беларусь «8 029 …» = «+375 29 …»
        d = "375" + d[2:]
    return d[-10:] if len(d) >= 10 else ""
'''
W1_STARO = '''def _mezhd_nomer(raw) -> dict:
'''
W1_NOVO = '''# fixR 13.10: номер Беларуси (+375, «8 0XX …», 8-801) – обычный номер с меткой «РБ», не «международный».
_FIXR_RB_TITLE = "Номер Беларуси (+375): звонок международный"
_FIXR_RB_801 = "Бесплатная линия Беларуси 8-801: набирается только из Беларуси; обычно колл-центр, не личный номер"


def _fixR_rb(raw) -> dict:
    """Номер Беларуси -> {"pokaz": «+375 29 000-00-00», "href", "vid", …} (centro_catalog.nomer_rb), иначе {}."""
    try:
        from app.services.centro_catalog import nomer_rb
        return nomer_rb(raw) or {}
    except Exception:  # noqa: BLE001
        return {}


def _fixR_metka_rb(metki) -> None:
    """Метка вида номера Беларуси: «мобильный» -> «мобильный · РБ» с подсказкой; без метки вида – «РБ»."""
    try:
        for i, (tekst, klass, title) in enumerate(metki):
            if tekst in ("мобильный", "рабочий", "рабочий с добавочным", "8-800"):
                metki[i] = (tekst + " · РБ", (klass + " tag-rb") if klass else "tag-inostr tag-rb",
                            _FIXR_RB_801 if tekst == "8-800" else _FIXR_RB_TITLE)
                return
        metki.append(("РБ", "tag-inostr tag-rb", _FIXR_RB_TITLE))
    except Exception:  # noqa: BLE001
        pass


def _mezhd_nomer(raw) -> dict:
'''
W2_STARO = '''        if not s.startswith("+") or d.startswith("7") or not 8 <= len(d) <= 15:
            return {"pokaz": "", "strana": ""}
'''
W2_NOVO = '''        if not s.startswith("+") or d.startswith("7") or not 8 <= len(d) <= 15 or _fixR_rb(s):
            return {"pokaz": "", "strana": ""}       # fixR 13.10: Беларусь показывает telefon, с меткой «РБ»
'''
W3_STARO = '''        d = _re_vid.sub(r"\\D", "", osn)
        if not dob and len(d) > 11 and d[0] in "78":
'''
W3_NOVO = '''        d = _re_vid.sub(r"\\D", "", osn)
        _rb = _fixR_rb(osn)          # fixR 13.10: Беларусь – «+375 29 000-00-00», ссылка tel:+375…
        if _rb:
            return {"pokaz": _rb["pokaz"] + (" доб. " + dob if dob else ""),
                    "href": _rb["href"] + ("," + dob if dob else ""),
                    "mobilnyy": _rb["vid"] == "мобильный", "vosem_sot": _rb["vid"] == "8-800",
                    "dob": dob, "rb": True}
        if not dob and len(d) > 11 and d[0] in "78":
'''
W4_STARO = '''                if vid == "международный" or mz["pokaz"]:
'''
W4_NOVO = '''                if (vid == "международный" and not t.get("rb")) or mz["pokaz"]:     # fixR: +375 – не «международный»
'''
W5_STARO = '''                elif vid in _VIDY_OBYCHNYE_A2:
                    metka(vid)
'''
W5_NOVO = '''                elif vid in _VIDY_OBYCHNYE_A2:
                    metka(vid)
                if t.get("rb"):
                    _fixR_metka_rb(metki)          # fixR 13.10: «мобильный · РБ», подсказка про международный звонок
'''
W6_STARO = '''                                                      ("городской, доб." if t["dob"] else "городской"))
'''
W6_NOVO = '''                                                      ("городской, доб." if t["dob"] else "городской"))
                if t.get("rb"):
                    vid += " · РБ"                 # fixR 13.10: номер Беларуси
'''
R1_STARO = '''        osn = "+7 %s %s-%s-%s" % (d[1:4], d[4:7], d[7:9], d[9:])
'''
R1_NOVO = '''        osn = "+7 %s %s-%s-%s" % (d[1:4], d[4:7], d[7:9], d[9:])
    _rb = catalog.nomer_rb(osn) if hasattr(catalog, "nomer_rb") else {}
    if _rb:
        osn = _rb["pokaz"]                   # fixR 13.10: Беларусь – «+375 29 000-00-00»
'''
R2_STARO = '''def _klyuch_nomera(cifry: str) -> str:
'''
R2_NOVO = '''def _klyuch_nomera(cifry: str) -> str:
    if len(cifry) == 11 and cifry.startswith("80"):     # fixR 13.10: Беларусь «8 029 …» = «+375 29 …»
        cifry = "375" + cifry[2:]
    if len(cifry) == 12 and cifry.startswith("375"):    # fixR 13.10: +375 – последние 10 цифр, как nomer_10
        return cifry[-10:]
'''
S1_STARO = '''    if len(cifry) == 11 and cifry[0] in "78":
        return "+7" + cifry[1:], cifry[1:], dob
'''
S1_NOVO = '''    if len(cifry) == 11 and cifry.startswith("80"):     # fixR 13.10: Беларусь «8 029 …» -> +375 29 …
        cifry = "375" + cifry[2:]
    if len(cifry) == 11 and cifry[0] in "78":
        return "+7" + cifry[1:], cifry[1:], dob
'''
S2_STARO = '''        return "+7 %s %s-%s-%s" % (c[1:4], c[4:7], c[7:9], c[9:11])
'''
S2_NOVO = '''        return "+7 %s %s-%s-%s" % (c[1:4], c[4:7], c[7:9], c[9:11])
    if len(c) == 12 and c.startswith("375"):            # fixR 13.10: «+375 29 000-00-00»
        return "+375 %s %s-%s-%s" % (c[3:5], c[5:8], c[8:10], c[10:])
'''
L1_STARO = "{% if _л.vid == 'мобильный' %} mob{% endif %}"
L1_NOVO = "{% if (_л.vid or '').startswith('мобильный') %} mob{% endif %}"

PRAVKI = [
    ('CC', 'каталог: nomer_rb и вид номера РБ', CC1_STARO, CC1_NOVO),
    ('CC', 'каталог: normalize_phone для РБ', CC2_STARO, CC2_NOVO),
    ('CC', 'каталог: contacts пересчитывает «международный» у РБ', CC3_STARO, CC3_NOVO),
    ('CC', 'каталог: ключ номера «8 0XX» = +375', CC4_STARO, CC4_NOVO),
    ('W', 'показ: помощники РБ', W1_STARO, W1_NOVO),
    ('W', 'показ: РБ не «международный»', W2_STARO, W2_NOVO),
    ('W', 'показ: telefon для РБ', W3_STARO, W3_NOVO),
    ('W', 'показ: ветка «международный» без РБ', W4_STARO, W4_NOVO),
    ('W', 'показ: метка «· РБ»', W5_STARO, W5_NOVO),
    ('W', 'список: вид номера ЛПР «· РБ»', W6_STARO, W6_NOVO),
    ('R', 'строка ЛПР: номер РБ читаемо', R1_STARO, R1_NOVO),
    ('R', 'ключ номера РБ', R2_STARO, R2_NOVO),
    ('S', 'номер от менеджера «8 029 …»', S1_STARO, S1_NOVO),
    ('S', 'показ номера от менеджера +375', S2_STARO, S2_NOVO),
    ('L', 'список: подсветка мобильного РБ', L1_STARO, L1_NOVO),
]


def nl_kak_v(t, x):
    return x.replace('\n', '\r\n') if t.count('\r\n') * 2 > t.count('\n') else x


def nalozhit(teksty):
    novye = dict(teksty)
    zh, ok = [], True
    for kl, imya, staro, novo in PRAVKI:
        t = novye[kl]
        st, nv = nl_kak_v(t, staro), nl_kak_v(t, novo)
        if t.count(nv) == 1 and ('fixR' in nv or kl == 'L'):
            zh.append('[уже] ' + imya)
            continue
        n = t.count(st)
        if n != 1:
            zh.append('[ЯКОРЬ НАЙДЕН %d РАЗ] %s' % (n, imya))
            ok = False
            continue
        novye[kl] = t.replace(st, nv, 1)
        zh.append('[ок] ' + imya)
    return novye, zh, ok


def prochitat(koren_app):
    return {k: io.open(os.path.join(koren_app, *p.split('/')), encoding='utf-8', newline='').read() for k, p in FAJLY.items()}


def zapisat(koren_app, teksty, klyuchi):
    for k in klyuchi:
        p = os.path.join(koren_app, *FAJLY[k].split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, 'w', encoding='utf-8', newline='') as f:
            f.write(teksty[k])


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


# ====================================================================== снимок и проверка (venv)
def rb_po_cifram(v):
    """Независимо от кода панели: номер Беларуси по цифрам (для сравнения «до/после»)."""
    t = re.sub(r'\s*(?:доб\.?|доп\.?|вн\.?|ext\.?|#)\s*\d{1,6}\s*$', '', str(v or '').strip(), flags=re.I)
    d = re.sub(r'\D', '', t)
    pl = t.startswith('+')
    return bool((len(d) == 12 and d.startswith('375')) or (not pl and len(d) == 11 and d.startswith(('80', '8801')))
                or (not pl and len(d) == 15 and d.startswith('810375')))


def render(koren_app, kat, sales_db, metka, proverki):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение
    sys.path.insert(0, koren_app)
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = sales_db
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        if os.path.normcase(os.path.abspath(os.environ.get(k, '') or 'x')) == os.path.normcase(KAT):
            os.environ[k] = kat
    from app import web
    from app.services import centro_catalog as cat
    assert os.path.normcase(os.path.dirname(web.__file__)).startswith(os.path.normcase(koren_app)), web.__file__
    assert os.path.normcase(str(cat.db_path())) == os.path.normcase(kat), str(cat.db_path())
    _orig = cat._shared_phone_keys
    _m = {}

    def _memo(conn):
        if 'k' not in _m:
            _m['k'] = _orig(conn)
        return _m['k']
    cat._shared_phone_keys = _memo
    k = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
    k.row_factory = sqlite3.Row
    komp = {r['inn']: dict(r) for r in k.execute('SELECT inn, strana, predpriyatie, lpr_kratko FROM company')}
    k.close()
    s = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    s.close()
    sn = {'web': web.__file__, 'kontakty': {}, 'lyudi': {}, 'tier': {}, 'spisok': {}}
    for inn in komp:
        items = cat.contacts(inn)
        rows = []
        for x in items:
            if x.get('kind') not in ('phone', 'sprosit'):
                continue
            kv = web._kontakt_vid(x, x.get('fragment') or '')
            rows.append([str(x.get('id')), x.get('value'), x.get('vid_nomera'), x.get('phone_type'), x.get('rol_vid'),
                         x.get('lpr'), x.get('has_role'), x.get('nomer_ne_lichnyy'), x.get('href'),
                         kv.get('pokaz'), kv.get('href'), [list(m) for m in kv.get('metki') or []]])
        sn['kontakty'][inn] = rows
        tel = [x for x in items if x.get('kind') == 'phone']
        lpr = [x for x in tel if x['lpr']]
        mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
        sn['tier'][inn] = 4 if any(x['person'] for x in mob) else 3 if mob else 2 if lpr else 1
        sn['lyudi'][inn] = [[str(p.get('id')), p.get('phone'), web._telefon(p.get('phone')).get('pokaz'),
                             web._telefon(p.get('phone')).get('href')] for p in cat.persons(inn) if p.get('phone')]
        sn['spisok'][inn] = web._lpr_razbor(komp[inn].get('lpr_kratko')).get('vid')
    io.open(os.path.join(KOREN, '_bekap', 'fixR-snimok-%s.json' % metka), 'w', encoding='utf-8').write(
        json.dumps(sn, ensure_ascii=False))
    print('снимок %s: компаний %d, строк контактов %d' % (metka, len(sn['kontakty']), sum(len(v) for v in sn['kontakty'].values())))
    if not proverki:
        print('ПЛОХИХ ПРОВЕРОК: 0')
        return 0
    # ---------------- проверки
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    from app.services import centro_sales as sales
    from app.api import routes_centro_sales as rcs
    P = {'+375 29 000-00-00': 'мобильный', '+375 44 000-00-00': 'мобильный', '+375 25 000-00-00': 'мобильный',
         '+375 33 000-00-00': 'мобильный', '+375 17 000-00-00': 'рабочий', '+375 152 00-00-00': 'рабочий',
         '+375 17 000-00-00 доб. 12': 'рабочий с добавочным', '8 029 000-00-00': 'мобильный', '8 017 000-00-00': 'рабочий',
         '375290000000': 'мобильный', '8 801 000-00-00': '8-800', '+7 900 000-00-00': 'мобильный',
         '+7 495 000-00-00': 'рабочий', '8 495 000-00-00 доб. 5': 'рабочий с добавочным', '8 800 000-00-00': '8-800',
         '+7 700 000-00-00': 'Казахстан', '+374 00 000-000': 'международный', '+380 00 000-00-00': 'международный',
         '8 10 375 29 000-00-00': 'мобильный'}
    for n, v in P.items():
        ok(cat.vid_nomera_po_cifram(n) == v, 'вид «%s» = %s (%s)' % (n, cat.vid_nomera_po_cifram(n), v))
    for n, v in (('8 029 000-00-00', '+375290000000'), ('+375 29 000-00-00', '+375290000000'),
                 ('+7 900 000-00-00', '+79000000000'), ('8 495 000-00-00', '+74950000000'), ('8 801 000-00-00', '88010000000')):
        ok(cat.normalize_phone(n) == v, 'normalize_phone «%s» = %s' % (n, cat.normalize_phone(n)))
    ok(cat._phone_key('8 029 000-00-01') == cat._phone_key('+375 29 000-00-01'), 'ключ «8 029 …» = «+375 29 …»')
    ok(cat._phone_key('+7 900 000-00-01') == '9000000001', 'ключ российского как был')
    t = web._telefon('+375 29 000-00-00')
    ok(t['pokaz'] == '+375 29 000-00-00' and t['href'] == 'tel:+375290000000' and t['mobilnyy'], 'telefon РБ: %s' % t)
    t = web._telefon('8 017 000-00-00 доб. 12')
    ok(t['pokaz'] == '+375 17 000-00-00 доб. 12' and t['href'] == 'tel:+375170000000,12', 'telefon РБ с доб.: %s' % t)
    t = web._telefon('+7 900 000-00-00')
    ok(t['pokaz'] == '+7 900 000-00-00' and t['href'] == 'tel:+79000000000' and not t.get('rb'), 'telefon России: %s' % t)
    ok(web._mezhd_nomer('+374 00 000-000')['strana'] == 'Армения' and not web._mezhd_nomer('+375 29 000-00-00')['pokaz'],
       'Армения – международный, Беларусь – нет')
    kv = web._kontakt_vid({'kind': 'phone', 'value': '+375290000000', 'href': 'tel:+375290000000',
                           'vid_nomera': 'мобильный', 'phone_type': 'мобильный'})
    ok(kv['pokaz'] == '+375 29 000-00-00' and kv['href'] == 'tel:+375290000000'
       and any(m[0] == 'мобильный · РБ' and 'Номер Беларуси (+375): звонок международный' in m[2] for m in kv['metki'])
       and not any('международный' in m[0] for m in kv['metki']), 'kontakt_vid РБ: %s' % kv['metki'])
    kv = web._kontakt_vid({'kind': 'phone', 'value': '+375290000000', 'href': 'tel:+375290000000',
                           'vid_nomera': 'международный', 'phone_type': 'международный'})
    ok(not any('международный' in m[0] for m in kv['metki']) and any('РБ' in m[0] for m in kv['metki']),
       'kontakt_vid РБ при старом виде «международный»: %s' % kv['metki'])
    ok(web._lpr_razbor('Тестов Т.Т. · директор · +375 29 000-00-00')['vid'] == 'мобильный · РБ', 'список: вид ЛПР РБ')
    ok(web._lpr_razbor('Тестов Т.Т. · директор · +7 900 000-00-00')['vid'] == 'мобильный', 'список: вид ЛПР России')
    ok(sales.razobrat_nomer('8 029 000-00-00') == ('+375290000000', '5290000000', ''), 'номер от менеджера «8 029»: %s'
       % (sales.razobrat_nomer('8 029 000-00-00'),))
    ok(sales.razobrat_nomer('+7 900 000-00-00') == ('+79000000000', '9000000000', ''), 'номер от менеджера России')
    ok(sales.nomer_pokaz('+375290000000') == '+375 29 000-00-00' and sales.nomer_pokaz('+79000000000') == '+7 900 000-00-00',
       'nomer_pokaz РБ и России')
    ok(rcs._fixE2_pokaz('+375290000000') == '+375 29 000-00-00' and rcs._fixE2_pokaz('+79000000000') == '+7 900 000-00-00',
       'строка ЛПР: номер РБ и России')
    ok(rcs._klyuch_nomera('375290000001') == '5290000001' and rcs._klyuch_nomera('80290000001') == '5290000001'
       and rcs._klyuch_nomera('79000000001') == '9000000001', 'ключ номера в поиске')
    # ---- страницы
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(PRODAVCY, 1):
        USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
    kto = {'u': USERS['meyer_admin']}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    rb_inn = [i for i in sorted(komp) if any(rb_po_cifram(r[1]) for r in sn['kontakty'][i] if r[1])]
    by_inn = [i for i in rb_inn if str(komp[i].get('strana') or '') == 'Беларусь']
    ne_by_rb = [i for i in rb_inn if i not in by_inn]
    mob_lpr = [i for i in by_inn if any(rb_po_cifram(r[1]) and r[5] and r[2] == 'мобильный' for r in sn['kontakty'][i])]
    bez_mob = [i for i in by_inn if i not in mob_lpr]
    print('   компаний с номерами РБ: %d (белорусских %d, прочих %d); белорусских с ЛПР на мобильном РБ: %d'
          % (len(rb_inn), len(by_inn), len(ne_by_rb), len(mob_lpr)))
    rus = [i for i in sorted(komp) if i not in rb_inn and len(i) == 10][:2]
    arm = [i for i in komp if any(r[2] == 'международный' and not rb_po_cifram(r[1]) for r in sn['kontakty'][i])][:2]
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats')):
            o = get(u)
            ok(o.status_code == 200, 'админ: %s %s' % (nazv, o.status_code))
        for p in PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code == 200, '%s: главная %s' % (p, o.status_code))
        o = get('/centro/stats', 'meyer2')
        ok(o.status_code in (403, 303, 302), 'meyer2: статистика закрыта (%s)' % o.status_code)
        o = get('/centro/stats', params={'user': 'meyer1'})
        ok(o.status_code == 200, 'админ: статистика, очередь meyer1 %s' % o.status_code)
        for inn in mob_lpr[:5] + bez_mob[:2] + ne_by_rb[:2]:
            for kak in ('meyer_admin', vlad.get(inn)):
                if not kak:
                    continue
                o = get('/centro', kak, params={'inn': inn})
                h = o.text
                ok(o.status_code == 200 and 'tag-rb' in h and 'Номер Беларуси (+375): звонок международный' in h
                   and 'международный · Беларусь' not in h and 'href="tel:+375' in h
                   and re.search(r'\+375 \d\d \d{3}-\d\d-\d\d', h) is not None,
                   'карточка %s (%s) у %s: %s; «· РБ» %d, «мобильный · РБ» %d, «международный» %d' % (
                       inn, (komp[inn].get('predpriyatie') or '')[:22], kak, o.status_code, h.count('· РБ'),
                       h.count('мобильный · РБ'), h.count('>международный')))
        for inn in rus:
            o = get('/centro', params={'inn': inn})
            ok(o.status_code == 200 and 'tag-rb' not in o.text, 'карточка России %s: %s, без «РБ»' % (inn, o.status_code))
        for inn in arm:
            o = get('/centro', params={'inn': inn})
            ok(o.status_code == 200 and '>международный' in o.text, 'карточка с номером другой страны %s: %s, «международный» на месте'
               % (inn, o.status_code))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    raise SystemExit(1 if render(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3], sys.argv[i + 4], '--proverki' in sys.argv) else 0)


def zapustit_render(koren_app, kat, sales_db, metka, proverki):
    r = subprocess.run([VENV, os.path.abspath(__file__), '--render', koren_app, kat, sales_db, metka]
                       + (['--proverki'] if proverki else []), capture_output=True, timeout=1500, cwd=KOREN, env=SREDA)
    v = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        v += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:]
    return r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in v, v


def sravnit(metka_do, metka_posle):
    do = json.load(io.open(os.path.join(KOREN, '_bekap', 'fixR-snimok-%s.json' % metka_do), encoding='utf-8'))
    po = json.load(io.open(os.path.join(KOREN, '_bekap', 'fixR-snimok-%s.json' % metka_posle), encoding='utf-8'))
    itog = collections.Counter()
    plohie, rb_vid = [], collections.Counter()
    for inn, rows in do['kontakty'].items():
        p_rows = {r[0]: r for r in po['kontakty'].get(inn, [])}
        if set(p_rows) != {r[0] for r in rows}:
            plohie.append('%s: другой набор контактов' % inn)
            continue
        for r in rows:
            q = p_rows[r[0]]
            if rb_po_cifram(r[1]) or rb_po_cifram(q[1]):
                itog['РБ'] += 1
                rb_vid['%s -> %s' % (r[2], q[2])] += 1
                continue
            itog['не РБ'] += 1
            if r != q:
                plohie.append('%s/%s: %s -> %s' % (inn, r[0], r[2:9], q[2:9]))
            else:
                itog['не РБ совпало'] += 1
    for inn, rows in do['lyudi'].items():
        p_rows = {r[0]: r for r in po['lyudi'].get(inn, [])}
        for r in rows:
            q = p_rows.get(r[0])
            if rb_po_cifram(r[1]):
                itog['люди РБ'] += 1
                continue
            itog['люди не РБ'] += 1
            if r != q:
                plohie.append('человек %s/%s изменился' % (inn, r[0]))
    for inn, v in do['spisok'].items():
        if v != po['spisok'].get(inn) and 'РБ' not in str(po['spisok'].get(inn)):
            plohie.append('список %s: %s -> %s' % (inn, v, po['spisok'].get(inn)))
    tier = collections.Counter((do['tier'][i], po['tier'].get(i)) for i in do['tier'] if do['tier'][i] != po['tier'].get(i))
    return itog, plohie, rb_vid, tier


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


def kopii_baz(papka, metka):
    ts, tk = os.path.join(papka, 't_sales_%s.db' % metka), os.path.join(papka, 't_kat_%s.db' % metka)
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    return tk, ts


def proverit_stage(novye, izm, papka, vyvod):
    """Снимок «до» (живой код) и «после» (stage) на одной копии баз + проверки на stage."""
    sdelat_stage(novye, izm)
    tk, ts = kopii_baz(papka, 'stage')
    g0, v0 = zapustit_render(KOREN, tk, ts, 'do-' + VREMYA, False)
    g1, v1 = zapustit_render(STAGE, tk, ts, 'posle-' + VREMYA, True)
    vyvod.append('----- снимок «до» (живой код)\n' + v0[-1500:])
    vyvod.append('----- stage: снимок «после» и проверки\n' + v1)
    if not (g0 and g1):
        return False, None
    itog, plohie, rb_vid, tier = sravnit('do-' + VREMYA, 'posle-' + VREMYA)
    vyvod.append('----- сравнение «до/после»: %s\n   вид номеров РБ: %s\n   ступень (по контактам) было->стало: %s\n'
                 '   РАСХОЖДЕНИЙ у не-РБ: %d %s' % (dict(itog), dict(rb_vid), dict(tier), len(plohie), plohie[:10]))
    for f in (tk, ts):
        try:
            os.remove(f)
        except OSError:
            pass
    return (not plohie and itog['не РБ'] == itog['не РБ совпало'] and itog['не РБ'] > 0), itog


PAPKA = os.path.join(KOREN, '_bekap', 'fixR-kod-' + VREMYA)
os.makedirs(PAPKA, exist_ok=True)
if '--suho' in sys.argv:
    teksty = prochitat(APP)
    novye, zh, vse_ok = nalozhit(teksty)
    print('\n'.join('   ' + x for x in zh))
    if not vse_ok:
        print('ЯКОРЯ НЕ НАЙДЕНЫ – ничего не делаю')
        raise SystemExit(4)
    izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
    vyvod = []
    good, itog = proverit_stage(novye, izm, PAPKA, vyvod)
    t = '\n'.join(vyvod)
    io.open(os.path.join(DROP, 'fixR-kod-suho-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
    print(t[-5000:])
    print('СУХОЙ ПРОГОН: %s (живые файлы не тронуты; меняются: %s)' % ('ОК' if good else 'ЕСТЬ ПЛОХОЕ', ', '.join(FAJLY[k_] for k_ in izm)))
    raise SystemExit(0)

if '--primenit' in sys.argv:
    vzyat_zamok('fixR (номера Беларуси +375: код каталога, показа, списка)')
    vyvod = []
    try:
        teksty = prochitat(APP)
        novye, zh, vse_ok = nalozhit(teksty)
        print('\n'.join('   ' + x for x in zh))
        if not vse_ok:
            print('ЯКОРЯ НЕ НАЙДЕНЫ – живые файлы не тронуты')
            raise SystemExit(4)
        izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
        if not izm:
            print('правки уже стоят – файлы не меняю')
            raise SystemExit(0)
        for k_ in izm:                                  # копия прежних файлов – только свои
            dst = os.path.join(PAPKA, 'app', *FAJLY[k_].split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(APP, *FAJLY[k_].split('/')), dst)
        good, itog = proverit_stage(novye, izm, PAPKA, vyvod)
        if not good:
            t = '\n'.join(vyvod)
            io.open(os.path.join(DROP, 'fixR-kod-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
            print(t[-4500:])
            print('ПРОВЕРКА НА STAGE НЕ ПРОШЛА – живые файлы не тронуты')
            raise SystemExit(5)
        for k_ in izm:
            if io.open(os.path.join(APP, *FAJLY[k_].split('/')), encoding='utf-8', newline='').read() != teksty[k_]:
                print('ФАЙЛ %s ИЗМЕНИЛСЯ ЗА ВРЕМЯ ПРОГОНА – не пишу' % FAJLY[k_])
                raise SystemExit(6)
        ostanovit()
        zapisat(APP, novye, izm)
        kod = zapustit('исправитель R: номера Беларуси +375')
        vyvod.append('записано: %s; перезапуск, вход: %s' % (', '.join(FAJLY[k_] for k_ in izm), kod))
        tk, ts = kopii_baz(PAPKA, 'zhivoy')
        g2, v2 = zapustit_render(KOREN, tk, ts, 'zhivoy-' + VREMYA, True)
        vyvod.append('----- живой код после перезапуска: проверки\n' + v2[-3000:])
        for f in (tk, ts):
            try:
                os.remove(f)
            except OSError:
                pass
        if kod != 200 or not g2:
            for k_ in izm:
                shutil.copy2(os.path.join(PAPKA, 'app', *FAJLY[k_].split('/')), os.path.join(APP, *FAJLY[k_].split('/')))
            ostanovit()
            kod2 = zapustit('исправитель R: ОТКАТ своих файлов')
            vyvod.append('ПОСЛЕ ЗАПИСИ ПЛОХО – свои файлы возвращены из %s, перезапуск, вход: %s' % (PAPKA, kod2))
        else:
            vyvod.append('ПРИМЕНЕНО: %s; копия прежних файлов: %s' % (', '.join(FAJLY[k_] for k_ in izm), PAPKA))
        t = '\n'.join(vyvod)
        io.open(os.path.join(DROP, 'fixR-kod-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
        print(t[-5000:])
    finally:
        otdat_zamok()
