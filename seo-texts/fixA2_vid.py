# -*- coding: utf-8 -*-
"""Исправитель A2: доводка вида карточки панели Meyer под новые данные контактов (08.10).

Агент C переделал контакты (centro_catalog.contacts / rol_kontakta): у контакта теперь
vid_nomera + vid_pochemu, rol_vid, lpr, uroven, lpr_metka, obshchiy_nomer, sprosit, а строки
«спросить у приёмной: ФИО» приходят с kind='sprosit' и пустой ссылкой. Агент D пометил 254
номера со страниц другого юрлица (chuzhoy_istochnik). Что меняется (только показ, базы не
трогаются):
  1. «Спросить у приёмной» (44 строки) – подсказка продавцу «Спросите у приёмной: ФИО,
     должность»: без tel:, без «Копировать», без «убрать номер»; vid_pochemu – по нажатию.
  2. Виды номера – понятными метками: битый номер, «не номер компании: скрытый HTML / ТУ /
     шаблон», «номер только в ссылке tel:», Казахстан, международный, 8-800, «общий с другой
     компанией». Битый и «не номер компании» – номер виден, но без ссылки tel:.
  3. Международный номер читаемо: «+374 00 000-000» (href – полные цифры, как было).
  4. Уровень ЛПР («первое лицо», «техдиректор / главный инженер», …) – рядом с должностью,
     если не повторяет её.
  5. Подпись источника: номер с пометкой chuzhoy_istochnik – «сайт другого юрлица · домен»
     (_vid_istochnika в web.py); сайт уровнем выше сайта компании без пометки – «сайт группы».
  6. Фильтр «Роль ЛПР» – проверяется (пункты = уровни, число у пункта = найдено); правки нет.

Режимы:
  --suho [ИНН…]   без замка, живые файлы не трогаются: правки на КОПИИ шаблонов в
                  C:\\centro2\\_bekap\\fixA2-stage, web.py – в памяти процесса проверки;
                  рендер TestClient-ом на копии базы продаж, полный обход «до -> после»
                  -> на дроп fixA2_suho.txt, fixA2_obhod_suho.json, fixA2_html_suho.zip.
  --primenit      под замком: web.py -> проверка на копиях шаблонов -> остановка панели ->
                  centro.html на место -> запуск -> проверка живых файлов; провал – свои файлы
                  из своей копии этого же прогона и снова запуск.
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
STAGE = os.path.join(KOREN, '_bekap', 'fixA2-stage')
FAJLY = {
    'C': os.path.join(T, 'centro.html'),
    'W': os.path.join(APP, 'web.py'),
}
STAGE_PUT = {'C': r'templates\centro.html', 'W': 'web.py'}
PRIMERY = ['5957004185', '4238013194', '5903154949', '6451402458', '1901124236', '7720802226']
WEB_METKA = '# ------------------------------------------------- вид контакта по данным каталога (исправитель A2'

# ====================================================================== web.py: подпись источника
VID_STARYY = r'''def _vid_istochnika(url, source="", sayt="") -> dict:
    """URL источника номера -> {"podpis": «тендерная площадка Tender.pro», "vid", "domen",
    "zametki": [(текст, важно)]}. sayt – сайт компании из карточки: «сайт компании»
    говорится, только если домен с ним совпал. Пустой URL -> podpis ""."""
    s = str(source or "").lower()
    zametki = []
    if "через сотрудника" in s:
        zametki.append(("выход на ЛПР через сотрудника", False))
    if "не удалось сверить" in s:
        zametki.append(("не сверен со страницей", True))
    if not str(url or "").strip().lower().startswith("http"):
        return {"podpis": "", "vid": "", "domen": "", "zametki": zametki}
    d, pokaz = _domen(url), _domen_pokaz(url)
    if not d:
        return {"podpis": "", "vid": "", "domen": "", "zametki": zametki}
    for kor, (vid, imya) in _TENDER_PLOSHCHADKI.items():
        if d == kor or d.endswith("." + kor):
            return {"podpis": "%s %s" % (vid, imya), "vid": vid, "domen": pokaz, "zametki": zametki}
    if any(a in d for a in _AGREGATORY_VYPISOK):
        return {"podpis": "агрегатор выписок · %s" % pokaz, "vid": "агрегатор", "domen": pokaz,
                "zametki": zametki}
    if "площадка закупок" in s:
        return {"podpis": "площадка закупок · %s" % pokaz, "vid": "тендерная площадка", "domen": pokaz,
                "zametki": zametki}
    if "сайт холдинга" in s:
        # База 6: номер с сайта холдинга, а не самой компании – не «сторонний», но и не свой
        return {"podpis": "сайт холдинга · %s" % pokaz, "vid": "сайт холдинга", "domen": pokaz,
                "zametki": zametki}
    dk = _domen(sayt)
    if dk and (d == dk or d.endswith("." + dk) or dk.endswith("." + d)):
        return {"podpis": "сайт компании · %s" % pokaz, "vid": "сайт компании", "domen": pokaz,
                "zametki": zametki}
    if dk or "стороннего сайта" in s:
        zametki.append(("не сайт компании – уточнить, чей номер", True))
        return {"podpis": "сторонний сайт · %s" % pokaz, "vid": "сторонний сайт", "domen": pokaz,
                "zametki": zametki}
    return {"podpis": "сайт · %s" % pokaz, "vid": "сайт", "domen": pokaz, "zametki": zametki}


'''

VID_NOVYY = r'''def _vid_istochnika(url, source="", sayt="", chuzhoy="") -> dict:
    """URL источника номера -> {"podpis": «тендерная площадка Tender.pro», "vid", "domen",
    "zametki": [(текст, важно)]}. sayt – сайт компании из карточки: «сайт компании»
    говорится, только если домен с ним совпал. Пустой URL -> podpis "".

    chuzhoy – пометка каталога «с сайта другого юрлица: …» (chuzhoy_istochnik, агент D 08.10):
    такой номер подписывается «сайт другого юрлица · домен», даже если домен совпал с сайтом
    компании или стоит над ним (исправитель A2: у 5903154949 сайт компании td.permill.ru,
    а permill.ru – сайт учредителя, и его номера подписывались «сайт компании»). Сайт уровнем
    выше сайта компании без пометки – «сайт группы»: что он её собственный, не доказано."""
    s = str(source or "").lower()
    zametki = []
    if "через сотрудника" in s:
        zametki.append(("выход на ЛПР через сотрудника", False))
    if "не удалось сверить" in s:
        zametki.append(("не сверен со страницей", True))
    if not str(url or "").strip().lower().startswith("http"):
        return {"podpis": "", "vid": "", "domen": "", "zametki": zametki}
    d, pokaz = _domen(url), _domen_pokaz(url)
    if not d:
        return {"podpis": "", "vid": "", "domen": "", "zametki": zametki}
    for kor, (vid, imya) in _TENDER_PLOSHCHADKI.items():
        if d == kor or d.endswith("." + kor):
            return {"podpis": "%s %s" % (vid, imya), "vid": vid, "domen": pokaz, "zametki": zametki}
    if any(a in d for a in _AGREGATORY_VYPISOK):
        return {"podpis": "агрегатор выписок · %s" % pokaz, "vid": "агрегатор", "domen": pokaz,
                "zametki": zametki}
    if str(chuzhoy or "").strip():
        return {"podpis": "сайт другого юрлица · %s" % pokaz, "vid": "сайт другого юрлица",
                "domen": pokaz, "zametki": zametki}
    if "площадка закупок" in s:
        return {"podpis": "площадка закупок · %s" % pokaz, "vid": "тендерная площадка", "domen": pokaz,
                "zametki": zametki}
    if "сайт холдинга" in s:
        # База 6: номер с сайта холдинга, а не самой компании – не «сторонний», но и не свой
        return {"podpis": "сайт холдинга · %s" % pokaz, "vid": "сайт холдинга", "domen": pokaz,
                "zametki": zametki}
    dk = _domen(sayt)
    if dk and (d == dk or d.endswith("." + dk)):
        return {"podpis": "сайт компании · %s" % pokaz, "vid": "сайт компании", "domen": pokaz,
                "zametki": zametki}
    if dk and dk.endswith("." + d):
        return {"podpis": "сайт группы · %s" % pokaz, "vid": "сайт группы", "domen": pokaz,
                "zametki": zametki}
    if dk or "стороннего сайта" in s:
        zametki.append(("не сайт компании – уточнить, чей номер", True))
        return {"podpis": "сторонний сайт · %s" % pokaz, "vid": "сторонний сайт", "domen": pokaz,
                "zametki": zametki}
    return {"podpis": "сайт · %s" % pokaz, "vid": "сайт", "domen": pokaz, "zametki": zametki}


'''

WEB_BLOK = r'''

# ------------------------------------------------- вид контакта по данным каталога (исправитель A2, 08.10)
# Агент C (fixC) дал контакту вид номера (vid_nomera, причина – vid_pochemu), уровень ЛПР
# (uroven, lpr_metka), признак общего номера (obshchiy_nomer) и строки «спросить у приёмной»
# (kind='sprosit', без номера); агент D пометил номера со страниц другого юрлица
# (chuzhoy_istochnik). Здесь – как это показать продавцу: битый номер и «не номер компании»
# видны, но без ссылки tel: (случайно не набрать), международный номер – с пробелами
# («+374 00 000-000»), уровень ЛПР – рядом с должностью, если её не повторяет. Только показ;
# ни одна функция не бросает исключение (ошибка фильтра роняла бы карточку продавцу в 500).
import re as _re_a2

_STRANY_A2 = (("374", "Армения"), ("375", "Беларусь"), ("380", "Украина"), ("373", "Молдова"),
              ("370", "Литва"), ("371", "Латвия"), ("372", "Эстония"), ("992", "Таджикистан"),
              ("993", "Туркменистан"), ("994", "Азербайджан"), ("995", "Грузия"), ("996", "Киргизия"),
              ("998", "Узбекистан"), ("971", "ОАЭ"), ("972", "Израиль"), ("86", "Китай"),
              ("90", "Турция"), ("49", "Германия"), ("48", "Польша"), ("39", "Италия"),
              ("33", "Франция"), ("44", "Великобритания"), ("98", "Иран"), ("91", "Индия"),
              ("82", "Южная Корея"), ("81", "Япония"), ("1", "США / Канада"))
_VIDY_MUSOR_A2 = ("битый номер", "не номер компании")
_VIDY_OBYCHNYE_A2 = ("мобильный", "рабочий", "рабочий с добавочным")
# эти виды говорит своя метка или строка «с сайта другого юрлица: …» – роль их не повторяет
_NE_POVTORYAT_A2 = {"битый номер", "не номер компании", "номер только в ссылке tel:",
                    "с сайта другого юрлица", "международный", "Казахстан", "8-800"}
# «да» в vid_pochemu у строки «спросить у приёмной» – флаг, а не причина
_POCHEMU_PUSTO_A2 = {"да", "нет", "1", "0", "yes", "true", "-", "–"}


def _chislo_a2(x) -> int:
    try:
        return int(float(str(x).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def _mezhd_nomer(raw) -> dict:
    """«+37400000000» -> {"pokaz": «+374 00 000-000», "strana": «Армения»}.
    Номер +7 (Россия, Казахстан) или не номер – pokaz "": им занимается telefon."""
    try:
        s = str(raw or "").strip()
        d = _re_a2.sub(r"\D", "", s)
        if not s.startswith("+") or d.startswith("7") or not 8 <= len(d) <= 15:
            return {"pokaz": "", "strana": ""}
        kod, strana = d[:3], ""
        for k, nz in _STRANY_A2:
            if d.startswith(k):
                kod, strana = k, nz
                break
        o = d[len(kod):]
        n = len(o)
        if n == 7:
            gr = "%s-%s-%s" % (o[:3], o[3:5], o[5:])
        elif n == 8:
            gr = "%s %s-%s" % (o[:2], o[2:5], o[5:])
        elif n == 9:
            gr = "%s %s-%s-%s" % (o[:2], o[2:5], o[5:7], o[7:])
        elif n == 10:
            gr = "%s %s-%s-%s" % (o[:3], o[3:6], o[6:8], o[8:])
        else:
            gr = " ".join(o[i:i + 3] for i in range(0, n, 3))
        return {"pokaz": "+%s %s" % (kod, gr), "strana": strana}
    except Exception:  # noqa: BLE001
        return {"pokaz": "", "strana": ""}


def _kontakt_pochemu(k) -> str:
    try:
        p = " ".join(str(k.get("vid_pochemu") or "").split())
        return "" if p.casefold() in _POCHEMU_PUSTO_A2 else p
    except Exception:  # noqa: BLE001
        return ""


def _ne_nomer_podvid(pochemu) -> str:
    p = str(pochemu or "").casefold()
    if "скрыт" in p or "закомментир" in p:
        return "скрытый HTML"
    if "шаблон" in p:
        return "шаблон сайта"
    if "артикул" in p or "реквизит" in p or _re_a2.search(r"(?<![а-я])ту(?![а-я])", p):
        return "ТУ / артикул"
    return ""


def _uroven_lpr(k, dolzhnost="") -> str:
    """Уровень ЛПР номера или строки «спросить у приёмной» («первое лицо», «техдиректор /
    главный инженер», …) – если это ЛПР и уровень не повторяет должность: «Главный инженер»
    уже говорит «главный инженер», а «Генеральный директор» про «первое лицо» молчит."""
    try:
        if not _chislo_a2(k.get("lpr")):
            return ""
        m = str(k.get("lpr_metka") or "").strip()
        vid = m.split(":", 1)[1].strip() if m.casefold().startswith("лпр:") else str(k.get("rol_vid") or "").strip()
        if vid.startswith("ЛПР "):
            vid = vid[4:].strip()           # «ЛПР со слов продавца» -> «со слов продавца»
        if not vid:
            return ""
        d = str(dolzhnost or "").casefold().replace("ё", "е")
        d = _re_a2.sub(r"(?<![а-я])гл\.\s*", "главный ", d)
        slova = _re_a2.findall(r"[а-яa-z]+", d)
        if _re_a2.search(r"техническ\w* (?:директор|руководител)", d):
            slova.append("техдиректор")
        for chast in vid.casefold().replace("ё", "е").split("/"):
            osnovy = [w[:6] for w in _re_a2.findall(r"[а-яa-z]+", chast) if len(w) > 2]
            if osnovy and all(any(x.startswith(o) for x in slova) for o in osnovy):
                return ""
        return vid
    except Exception:  # noqa: BLE001
        return ""


def _kontakt_vid(k, fragment="") -> dict:
    """Контакт -> {"pokaz": номер для глаз, "href": ссылка tel: ("" у битого и «не номер
    компании»), "musor", "metki": [(текст, css-класс, подсказка)], "pochemu", "pochemu_pro"}."""
    val = str((k or {}).get("value") or "").strip() if isinstance(k, dict) else ""
    try:
        kind = str(k.get("kind") or "").strip().lower()
        href = str(k.get("href") or "").strip()
        vid = str(k.get("vid_nomera") or "").strip()
        tip = str(k.get("phone_type") or "").strip()
        pochemu = _kontakt_pochemu(k)
        metki = []

        def metka(tekst, klass="", title=""):
            if tekst and all(tekst != m[0] for m in metki):
                metki.append((tekst, klass, " ".join(str(title).split())))

        pokaz, musor, pro = val, False, ""
        if kind == "phone":
            t = _telefon(val, fragment)
            mz = _mezhd_nomer(val)
            pokaz = mz["pokaz"] or (t["pokaz"] if t["href"] else val)
            musor = vid in _VIDY_MUSOR_A2
            if vid == "битый номер":
                pro = "битый номер"
                metka(pro, "tag-musor", "Номер с ошибкой – ссылки для звонка нет. " + pochemu)
            elif vid == "не номер компании":
                pro = "не номер компании"
                pod = _ne_nomer_podvid(pochemu)
                metka(pro + (": " + pod if pod else ""), "tag-musor",
                      "Эти цифры – не телефон компании, ссылки для звонка нет. " + pochemu)
            else:
                if vid == "международный" or mz["pokaz"]:
                    pro = "международный"
                    metka(pro + (" · " + mz["strana"] if mz["strana"] else ""), "tag-inostr",
                          "Номер другой страны: звонок международный. " + pochemu)
                elif vid == "Казахстан":
                    pro = "Казахстан"
                    metka(pro, "tag-inostr", "Номер Казахстана (+7 7…): звонок международный. " + pochemu)
                elif vid == "8-800" or tip == "8-800" or t["vosem_sot"]:
                    metka("8-800", "tag-800", "Бесплатная линия 8-800: обычно колл-центр или отдел продаж, не личный номер")
                elif tip in _VIDY_OBYCHNYE_A2:
                    metka(tip)
                elif vid in _VIDY_OBYCHNYE_A2:
                    metka(vid)
                if vid == "номер только в ссылке tel:":
                    pro = "номер только в ссылке tel:"
                    metka(pro, "tag-vnim", "Цифрами на странице этого номера нет – он только в ссылке "
                                           "для звонка, а рядом виден другой. Сверьте со страницей. " + pochemu)
                if vid == "общий с другой компанией" or _chislo_a2(k.get("obshchiy_nomer")):
                    metka("общий с другой компанией", "tag-vnim", "Тот же номер записан у другой компании "
                          "базы: скорее линия площадки или группы, чем личный номер")
        ne_l = str(k.get("nomer_ne_lichnyy") or "").strip()
        if ne_l and ne_l not in _NE_POVTORYAT_A2 and ne_l != vid:
            metka(ne_l, "tag-ne-lpr", "Не ЛПР: путь к ЛПР через этот номер")
        return {"pokaz": pokaz or val, "href": "" if musor else href, "musor": musor, "metki": metki,
                "pochemu": pochemu, "pochemu_pro": pro}
    except Exception:  # noqa: BLE001
        return {"pokaz": val, "href": str((k or {}).get("href") or "") if isinstance(k, dict) else "",
                "musor": False, "metki": [], "pochemu": "", "pochemu_pro": ""}


templates.env.globals["kontakt_vid"] = _kontakt_vid
templates.env.globals["kontakt_pochemu"] = _kontakt_pochemu
templates.env.globals["uroven_lpr"] = _uroven_lpr
templates.env.filters["mezhd_nomer"] = _mezhd_nomer
'''

# ====================================================================== centro.html
KONTAKT_STARYY = r'''{% macro contact_card(contact) %}
  {% if not (hidden and hidden.phone and contact.value in hidden.phone and not pokazat_skrytoe) %}
  {# Номер читаемо (+7 (4872) 00-00-00 доб. 208), ссылка – прежняя contact.href. Должность –
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
    <form method="post" action="{{ base_path }}/centro/hide" class="hide-form"{% if not (hidden and hidden.phone and contact.value in hidden.phone) %} onsubmit="return confirm('Убрать этот номер из карточки компании?')"{% endif %}>
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="kind" value="phone">
      <input type="hidden" name="value" value="{{ contact.value }}">
      {% if hidden and hidden.phone and contact.value in hidden.phone %}
        <input type="hidden" name="undo" value="1">
        <button class="sec-btn" title="Вернуть этот контакт">вернуть</button>
      {% else %}
        <input type="hidden" name="reason" value="убрано продавцом">
        <button class="sec-btn" title="Убрать этот контакт только у этой компании">убрать номер</button>
      {% endif %}
    </form>
    </div>
  </article>
  {% endif %}
{% endmacro %}'''

KONTAKT_NOVYY = r'''{% macro contact_card(contact) %}
  {# Исправитель A2 (08.10): вид контакта по данным каталога (fixC/fixD) – kontakt_vid() в web.py.
     Битый номер и «не номер компании» видны, но без ссылки tel: (случайно не набрать);
     международный – с пробелами; уровень ЛПР – рядом с должностью, если не повторяет её;
     «спросить у приёмной» (kind='sprosit') – подсказка продавцу, а не номер: без tel:,
     без «Копировать» и «убрать номер». #}
  {% set _скрыт = hidden and hidden.phone and contact.value in hidden.phone %}
  {% if not (_скрыт and not pokazat_skrytoe) %}
  {% if contact.kind == 'sprosit' %}
  {% set _долж = (contact.position or contact.role or '')|string|trim %}
  {% set _ур = uroven_lpr(contact, _долж) %}
  {% set _поч = kontakt_pochemu(contact) %}
  <article class="contact-card kontakt-sprosit{% if contact.is_tech %} is-tech{% endif %}{% if _скрыт %} is-hidden-by-user{% endif %}">
    <div class="sprosit-shapka">
      <span class="sprosit-metka">Своего номера нет</span>
      <span class="badges">{% if contact.is_purchaser %}<span class="tag tag-buy">закупки</span>{% endif %}{% if contact.is_tech %}<span class="tag tag-tech">технический ЛПР</span>{% endif %}</span>
    </div>
    <p class="sprosit-tekst">Спросите у приёмной: <b>{{ contact.person or 'имя не указано' }}</b>{% if _долж %}, {{ _долж }}{% endif %}</p>
    {% if _ур %}<span class="uroven-lpr">ЛПР: {{ _ур }}</span>{% endif %}
    {% if _поч %}<details class="vid-pochemu"><summary>Почему без номера</summary><p>{{ _поч }}</p></details>{% endif %}
    {{ source_link(contact.source, contact.source_url, telefon=True, fragment=contact.fragment or '', chuzhoy=contact.chuzhoy_istochnik or '') }}
    {% if _скрыт %}
    <div class="kontakt-niz"><span></span>
    <form method="post" action="{{ base_path }}/centro/hide" class="hide-form">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="kind" value="phone">
      <input type="hidden" name="value" value="{{ contact.value }}">
      <input type="hidden" name="undo" value="1">
      <button class="sec-btn" title="Вернуть эту строку">вернуть</button>
    </form>
    </div>
    {% endif %}
  </article>
  {% else %}
  {% set _в = kontakt_vid(contact, contact.fragment or '') %}
  {% set _долж = dolzhnost_kontakta(contact, people) %}
  {% set _ур = uroven_lpr(contact, _долж) %}
  <article class="contact-card{% if contact.is_purchaser %} is-buyer{% endif %}{% if contact.is_tech %} is-tech{% endif %}{% if contact.chuzhoy_istochnik %} is-chuzhoy{% endif %}{% if _в.musor %} is-musor{% endif %}{% if _скрыт %} is-hidden-by-user{% endif %}">
    <div class="contact-main">
      {% if _в.href %}<a class="contact-value" href="{{ _в.href }}">{{ _в.pokaz }}</a>{% elif _в.musor %}<span class="contact-value nomer-bez-zvonka" title="Ссылки для звонка нет: {{ _в.pochemu_pro }}">{{ _в.pokaz }}</span>{% else %}<b class="contact-value">{{ _в.pokaz }}</b>{% endif %}
      <span class="badges">
        {% if contact.is_purchaser %}<span class="tag tag-buy">закупки</span>{% endif %}
        {% if contact.is_tech %}<span class="tag tag-tech">технический ЛПР</span>{% endif %}
        {% for _тк, _кл, _пд in _в.metki %}<span class="tag{% if _кл %} {{ _кл }}{% endif %}"{% if _пд %} title="{{ _пд }}"{% endif %}>{{ _тк }}</span>{% endfor %}
      </span>
    </div>
    {% if contact.chuzhoy_istochnik %}<div class="chuzhoy-metka">{{ contact.chuzhoy_istochnik }}</div>{% endif %}
    {% if contact.person or _долж or _ур %}
      <div class="contact-person">
        <b>{{ contact.person or 'Имя не указано' }}</b>
        {% if _долж or _ур %}<span>{{ _долж }}{% if _ур %} <span class="uroven-lpr">ЛПР: {{ _ур }}</span>{% endif %}</span>{% endif %}
      </div>
    {% endif %}
    {% if _в.pochemu %}<details class="vid-pochemu"><summary>{% if _в.pochemu_pro %}Почему «{{ _в.pochemu_pro }}»{% else %}Подробнее о номере{% endif %}</summary><p>{{ _в.pochemu }}</p></details>{% endif %}
    {{ source_link(contact.source, contact.source_url, telefon=True, fragment=contact.fragment or '', chuzhoy=contact.chuzhoy_istochnik or '') }}
    <div class="kontakt-niz">
    <button type="button" class="copy-button" data-copy="{{ contact.value }}">Копировать</button>
    {# Убрать НОМЕР у этой компании. Ключ – сам номер: id контакта переживает
       не всякую пересборку базы, а номер остаётся собой. Кнопка – справа внизу, отдельно
       от номера и «Копировать», и с подтверждением (проверка 08.10). #}
    <form method="post" action="{{ base_path }}/centro/hide" class="hide-form"{% if not _скрыт %} onsubmit="return confirm('Убрать этот номер из карточки компании?')"{% endif %}>
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="kind" value="phone">
      <input type="hidden" name="value" value="{{ contact.value }}">
      {% if _скрыт %}
        <input type="hidden" name="undo" value="1">
        <button class="sec-btn" title="Вернуть этот контакт">вернуть</button>
      {% else %}
        <input type="hidden" name="reason" value="убрано продавцом">
        <button class="sec-btn" title="Убрать этот контакт только у этой компании">убрать номер</button>
      {% endif %}
    </form>
    </div>
  </article>
  {% endif %}
  {% endif %}
{% endmacro %}'''

STIL = r'''<style id="fixA2-vid">
/* Исправитель A2 08.10: вид контакта по данным каталога (fixC/fixD). */
.contact-card.kontakt-sprosit{background:#f7f8fc;border:1px dashed #b4bbd9}
.sprosit-shapka{display:flex;justify-content:space-between;align-items:center;gap:6px 8px;flex-wrap:wrap}
.sprosit-metka{font-size:12px;font-weight:700;color:#4b4f9c}
.sprosit-tekst{margin:5px 0 0;font-size:15px;line-height:1.4;color:#1d2433}
.sprosit-tekst b{font-weight:700;color:var(--navy)}
.uroven-lpr{display:inline-block;padding:0 7px;border-radius:999px;background:#eef1fb;border:1px solid #d5daf3;
  color:#3b3f8f;font-size:11px;font-weight:650;line-height:1.6;white-space:nowrap;vertical-align:1px}
.kontakt-sprosit>.uroven-lpr{margin-top:6px}
.contact-person .uroven-lpr{margin-left:4px}
.tag-musor{background:#fdecec;border-color:#f3c2c2;color:#9b1c1c;font-weight:600}
.tag-inostr{background:#eef5ff;border-color:#c5dbf5;color:#1d4f8a;font-weight:600}
.tag-vnim{background:#fff4e0;border-color:#f3d39b;color:#8a5300}
.contact-card.is-musor{background:#fafafa;border-style:dashed}
.contact-value.nomer-bez-zvonka{color:#8a909b;font-weight:650;cursor:default}
details.vid-pochemu{margin-top:6px;font-size:12px;color:#667085}
details.vid-pochemu>summary{cursor:pointer;color:#475467}
details.vid-pochemu p{margin:4px 0 0;padding:5px 8px;background:#f6f7fb;border-left:3px solid #c7cbe8;
  border-radius:4px;color:#33373e;overflow-wrap:anywhere}
@media(max-width:760px){.sprosit-tekst{font-size:16px}}
</style>
'''

PRAVKI = [
    # (файл, старое, новое, имя, признак «уже сделано», обязательная)
    ('C', "{% macro source_link(source, url, label='Источник', telefon=False, fragment='') %}",
     "{% macro source_link(source, url, label='Источник', telefon=False, fragment='', chuzhoy='') %}",
     'источник: параметр chuzhoy у source_link', "fragment='', chuzhoy='') %}", True),
    ('C', "{% set в = url|vid_istochnika(source, _сайт) %}",
     "{% set в = url|vid_istochnika(source, _сайт, chuzhoy) %}",
     'источник: пометка чужого сайта в подписи (1)', "vid_istochnika(source, _сайт, chuzhoy) %}", True),
    ('C', "{{ (а|vid_istochnika(source, _сайт)).podpis }}",
     "{{ (а|vid_istochnika(source, _сайт, chuzhoy)).podpis }}",
     'источник: пометка чужого сайта в подписи (2)', "(а|vid_istochnika(source, _сайт, chuzhoy)).podpis", True),
    ('C', KONTAKT_STARYY, KONTAKT_NOVYY, 'контакт: спросить у приёмной, виды номера, уровень ЛПР',
     "kontakt_vid(contact, contact.fragment or '')", True),
    ('C', "{{ source_link(person.source, person.source_url, telefon=True) }}\n        </article>\n{% endmacro %}",
     "{{ source_link(person.source, person.source_url, telefon=True, chuzhoy=person.chuzhoy_istochnik or '') }}\n        </article>\n{% endmacro %}",
     'человек: подпись чужого сайта', "telefon=True, chuzhoy=person.chuzhoy_istochnik or '') }}\n        </article>", True),
    ('C', "<article class=\"person-card\"><b>{{ person.person or 'Имя не указано' }}</b><span>{{ person.position or person.role or '' }}</span>{{ source_link(person.source, person.source_url, telefon=True) }}</article>",
     "<article class=\"person-card\"><b>{{ person.person or 'Имя не указано' }}</b><span>{{ person.position or person.role or '' }}</span>{{ source_link(person.source, person.source_url, telefon=True, chuzhoy=person.chuzhoy_istochnik or '') }}</article>",
     'привязка снята: подпись чужого сайта', "<span>{{ person.position or person.role or '' }}</span>{{ source_link(person.source, person.source_url, telefon=True, chuzhoy=", True),
    ('C', '</body>\n</html>', STIL + '</body>\n</html>', 'стили исправителя A2', 'id="fixA2-vid"', True),
    ('W', VID_STARYY, VID_NOVYY, 'web.py: подпись «сайт другого юрлица», «сайт группы»',
     'def _vid_istochnika(url, source="", sayt="", chuzhoy="")', True),
]


def nalozhit(teksty):
    """Правки по якорям. -> (новые тексты, журнал, сделано, надо, ок)."""
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
        zhurnal.append('[уже] web.py: вид контакта')
    else:
        novye['W'] = novye['W'].rstrip('\n') + '\n' + WEB_BLOK
        sdelano += 1
        zhurnal.append('[ок] web.py: вид контакта')
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
STAT_PUSTO = ('kart', 'ne200', 'blokov', 'tel_vsego', 'sprosit_dannye', 'sprosit_blokov', 'sprosit_tel',
              'sprosit_kopir', 'sprosit_ubrat', 'sprosit_podskazka', 'sprosit_pochemu', 'musor_dannye',
              'musor_blokov', 'musor_tel', 'mezhd_chitaemo', 'chuzh_blokov', 'chuzh_kak_kompanii',
              'chuzh_kak_chuzhoy', 'uroven', 'tag_musor', 'tag_inostr', 'tag_vnim', 'tag_800', 'tag_ne_lpr',
              'vid_pochemu_details')


def razobrat(t, kont):
    """Счётчики по одной карточке. kont – контакты каталога этой компании."""
    s = dict.fromkeys(STAT_PUSTO, 0)
    i = t.find('contacts-section')
    sek = t[i:t.find('</section>', i)] if i >= 0 else ''
    musor = {x['value'] for x in kont if x.get('vid_nomera') in ('битый номер', 'не номер компании')}
    s['sprosit_dannye'] = sum(1 for x in kont if x.get('kind') == 'sprosit')
    s['musor_dannye'] = len(musor)
    for kl, blok in re.findall(r'<article class="contact-card([^"]*)">(.*?)</article>', sek, re.S):
        s['blokov'] += 1
        tel = 'href="tel:' in blok
        s['tel_vsego'] += tel
        mv = re.search(r'name="value" value="([^"]*)"', blok)
        znach = mv.group(1).replace('&#43;', '+') if mv else ''
        if 'kontakt-sprosit' in kl or 'спросить у приёмной' in blok or 'Спросите у приёмной' in blok:
            s['sprosit_blokov'] += 1
            s['sprosit_tel'] += tel
            s['sprosit_kopir'] += 'copy-button' in blok
            s['sprosit_ubrat'] += 'убрать номер' in blok
            s['sprosit_podskazka'] += 'Спросите у приёмной:' in blok
            s['sprosit_pochemu'] += 'Почему без номера' in blok
        elif znach in musor:
            s['musor_blokov'] += 1
            s['musor_tel'] += tel
        if 'chuzhoy-metka' in blok:
            s['chuzh_blokov'] += 1
            # подпись ссылки, а не строка разборщика в подсказке («сайт компании · номер на живой…»)
            s['chuzh_kak_kompanii'] += 'noreferrer">сайт компании ·' in blok
            s['chuzh_kak_chuzhoy'] += 'noreferrer">сайт другого юрлица ·' in blok
        s['vid_pochemu_details'] += 'class="vid-pochemu"' in blok
    s['mezhd_chitaemo'] = len(re.findall(r'class="contact-value"[^>]*>\+(?!7)\d{1,3} \d', sek))
    s['uroven'] = sek.count('class="uroven-lpr"')
    for k, m in (('tag_musor', 'tag-musor'), ('tag_inostr', 'tag-inostr'), ('tag_vnim', 'tag-vnim'),
                 ('tag_800', 'tag-800'), ('tag_ne_lpr', 'tag-ne-lpr')):
        s[k] = sek.count(m)
    return s


def render(stage, metka, inny, polnyy):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import sqlite3
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    test_db = os.path.join(KOREN, '_bekap', 'fixA2-test-%d.db' % os.getpid())
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
    from app.services import centro_catalog as cc
    from fastapi.testclient import TestClient
    from jinja2 import ChoiceLoader, FileSystemLoader
    staryy_loader = web.templates.env.loader
    web_novyy = WEB_METKA in io.open(web.__file__, encoding='utf-8').read()
    if stage != '-':
        novyy_loader = ChoiceLoader([FileSystemLoader(os.path.join(stage, 'templates')), staryy_loader])
    else:
        novyy_loader = staryy_loader

    def loader(nov):
        web.templates.env.loader = novyy_loader if nov else staryy_loader
        web.templates.env.cache.clear() if web.templates.env.cache is not None else None

    def web_primenit():
        # сухой прогон: живой web.py не тронут – новые функции только в памяти этого процесса
        if not WEB_METKA in io.open(web.__file__, encoding='utf-8').read():
            exec(compile(VID_NOVYY + '\ntemplates.env.filters["vid_istochnika"] = _vid_istochnika\n',
                         'web_vid', 'exec'), web.__dict__)
            exec(compile(WEB_BLOK, 'web_blok', 'exec'), web.__dict__)

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    plohih = [0]

    def proverit(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    z = zipfile.ZipFile(os.path.join(DROP, 'fixA2_html_%s.zip' % metka), 'w', zipfile.ZIP_DEFLATED)
    try:
        z.write(os.path.join(APP, 'static', 'css', 'centro.css'), 'centro.css')
    except OSError:
        pass
    vnutr.dependency_overrides[rcs.current_user] = lambda: ADMIN
    itog = {}
    with TestClient(vnutr) as kl:
        if polnyy:
            # «до»: прежние шаблоны и прежний web.py (в сухом прогоне новые функции ещё не в памяти)
            kat = sqlite3.connect('file:%s?mode=ro' % str(cc.db_path()), uri=True)
            vse = [r[0] for r in kat.execute('select inn from company')]
            sost = {r[0]: r[1] for r in sqlite3.connect(test_db).execute('select inn, call_result from company_state')}
            kont = {inn: cc.contacts(inn) for inn in vse}
            for nov in (False, True):
                if nov:
                    web_primenit()
                loader(nov)
                sch = dict.fromkeys(STAT_PUSTO, 0)
                plohie = []
                for inn in vse:
                    cs = sost.get(inn)
                    params = {'inn': inn}
                    if cs in ('v_rabote', 'ne_ponravilas', 'dubl'):
                        params['call_status'] = cs
                    o = kl.get(PUT + '/centro', params=params)
                    sch['kart'] += 1
                    if o.status_code != 200:
                        sch['ne200'] += 1
                        plohie.append((inn, o.status_code))
                        continue
                    r = razobrat(o.text, kont[inn])
                    for k in STAT_PUSTO:
                        if k not in ('kart', 'ne200'):
                            sch[k] += r[k]
                    if nov and (r['musor_tel'] or r['sprosit_tel'] or r['sprosit_kopir'] or r['sprosit_ubrat']
                                or r['chuzh_kak_kompanii']):
                        plohie.append((inn, 'tel/копир/подпись'))
                sch['plohie'] = plohie[:30]
                itog['posle' if nov else 'do'] = sch
            print('   обход всех карточек (до -> после):')
            for k in STAT_PUSTO:
                print('      %-20s %6s -> %s' % (k, itog['do'][k], itog['posle'][k]))
            if itog['posle']['plohie']:
                print('      плохие: %s' % itog['posle']['plohie'])
            io.open(os.path.join(DROP, 'fixA2_obhod_%s.json' % metka), 'w', encoding='utf-8').write(
                json.dumps(itog, ensure_ascii=False, indent=1))
            p = itog['posle']
            proverit(p['kart'] == len(vse) and p['ne200'] == 0, 'все карточки (админ): %d, не 200: %d' % (p['kart'], p['ne200']))
            proverit(p['musor_tel'] == 0 and p['musor_blokov'] > 0,
                     'битые и «не номер компании»: показано %d, с tel: %d (было %d)' % (p['musor_blokov'], p['musor_tel'], itog['do']['musor_tel']))
            proverit(p['sprosit_blokov'] > 0 and p['sprosit_tel'] == 0 and p['sprosit_kopir'] == 0 and p['sprosit_ubrat'] == 0
                     and p['sprosit_podskazka'] == p['sprosit_blokov'],
                     '«спросить у приёмной»: строк %d (в данных %d), tel: %d, «Копировать»: %d (было %d), «убрать номер»: %d (было %d), подсказка: %d'
                     % (p['sprosit_blokov'], p['sprosit_dannye'], p['sprosit_tel'], p['sprosit_kopir'], itog['do']['sprosit_kopir'],
                        p['sprosit_ubrat'], itog['do']['sprosit_ubrat'], p['sprosit_podskazka']))
            proverit(p['chuzh_kak_kompanii'] == 0 and p['chuzh_kak_chuzhoy'] > 0,
                     'чужие номера: блоков %d, подпись «сайт компании» %d (было %d), «сайт другого юрлица» %d'
                     % (p['chuzh_blokov'], p['chuzh_kak_kompanii'], itog['do']['chuzh_kak_kompanii'], p['chuzh_kak_chuzhoy']))
            # ссылок tel: должно стать меньше ровно на битые/«не номер», у которых она была
            proverit(p['blokov'] == itog['do']['blokov']
                     and itog['do']['tel_vsego'] - p['tel_vsego'] == itog['do']['musor_tel'] + itog['do']['sprosit_tel'],
                     'контактов в карточках: %d -> %d; ссылок tel: %d -> %d (снято у битых/«не номер»: %d)'
                     % (itog['do']['blokov'], p['blokov'], itog['do']['tel_vsego'], p['tel_vsego'], itog['do']['musor_tel']))
        else:
            web_primenit()
        loader(True)
        for inn in inny:
            o = kl.get(PUT + '/centro', params={'inn': inn})
            t = o.text
            z.writestr('admin_card_%s.html' % inn, t)
            if o.status_code != 200:
                proverit(False, 'карточка %s: %s' % (inn, o.status_code))
                continue
            r = razobrat(t, cc.contacts(inn))
            proverit(r['musor_tel'] == 0 and r['sprosit_tel'] == 0 and r['sprosit_kopir'] == 0 and r['chuzh_kak_kompanii'] == 0
                     and 'id="fixA2-vid"' in t,
                     'карточка %s: 200; спросить %d, битых/не номер %d (tel: %d), чужих %d (как чужие %d), уровней ЛПР %d'
                     % (inn, r['sprosit_blokov'], r['musor_blokov'], r['musor_tel'], r['chuzh_blokov'], r['chuzh_kak_chuzhoy'], r['uroven']))
            if inn == '5903154949':
                proverit('сайт другого юрлица · permill.ru' in t, '5903154949: «сайт другого юрлица · permill.ru» есть')
            if inn == '6451402458':
                # номер не держим в файле: берём международный контакт из каталога и сверяем вид
                mzh = [x for x in cc.contacts(inn) if x.get('vid_nomera') == 'международный']
                okm, vid_m = bool(mzh), []
                for x in mzh:
                    cif = re.sub(r'\D', '', str(x.get('value') or ''))
                    pok = web._mezhd_nomer(x.get('value'))['pokaz']
                    vid_m.append(re.sub(r'\d', '0', pok))
                    okm = okm and bool(re.match(r'^\+\d{1,3} \d', pok)) and ('>%s<' % pok) in t \
                        and ('href="tel:+%s"' % cif) in t and ('>+%s<' % cif) not in t
                proverit(okm, '6451402458: международный номер с пробелами (вид %s), href полными цифрами' % ', '.join(vid_m))
            if inn == '5957004185':
                proverit(r['sprosit_blokov'] >= 1 and r['sprosit_podskazka'] == r['sprosit_blokov'], '5957004185: «Спросите у приёмной» – %d' % r['sprosit_blokov'])
        o = kl.get(PUT + '/centro')
        z.writestr('admin_list.html', o.text)
        proverit(o.status_code == 200, 'админ: список %s' % o.status_code)
        # фильтр «Роль ЛПР»: пункты и сколько находит каждый
        m = re.search(r'<select name="rol_lpr">(.*?)</select>', o.text, re.S)
        import html as _h
        opts = [(_h.unescape(v), _h.unescape(tx)) for v, tx in re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(1))] if m else []
        sovp = 0
        for v, tx in opts:
            if not v:
                continue
            mm = re.search(r'–\s*(\d+)\s*$', tx)
            tt = kl.get(PUT + '/centro', params={'rol_lpr': v}).text
            mt = re.search(r'<b class="total-count">(\d+)', tt)
            pok, nai = (int(mm.group(1)) if mm else -1), (int(mt.group(1)) if mt else -2)
            sovp += pok == nai
            print('      «Роль ЛПР» %-32s показано %s, найдено %s' % (v, pok, nai))
        proverit(sovp == len([v for v, _ in opts if v]) and sovp > 0, 'фильтр «Роль ЛПР»: пунктов %d, число совпало у %d' % (len([v for v, _ in opts if v]), sovp))
        o = kl.get(PUT + '/centro/stats')
        proverit(o.status_code == 200, 'статистика (админ): %s' % o.status_code)
    vnutr.dependency_overrides[rcs.current_user] = lambda: PROD
    with TestClient(vnutr) as kl:
        o = kl.get(PUT + '/centro')
        t = o.text
        z.writestr('sales_list.html', t)
        proverit(o.status_code == 200, 'продавец: список %s' % o.status_code)
        moi = re.findall(r'data-href="[^"]*inn=(\d{10,12})', t)[:4]
        for inn in moi + [i for i in inny if i not in moi]:
            o = kl.get(PUT + '/centro', params={'inn': inn})
            if o.status_code == 404 and inn not in moi:
                continue                                   # не его компания – 404 ожидаем
            z.writestr('sales_card_%s.html' % inn, o.text)
            r = razobrat(o.text, cc.contacts(inn)) if o.status_code == 200 else {}
            proverit(o.status_code == 200 and r['musor_tel'] == 0 and r['sprosit_tel'] == 0 and r['chuzh_kak_kompanii'] == 0
                     and 'id="fixA2-vid"' in o.text,
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
    zapisat(STAGE, novye, ['C', 'W'])
    with zipfile.ZipFile(os.path.join(DROP, 'fixA2_stage.zip'), 'w', zipfile.ZIP_DEFLATED) as zz:
        for k in ('C', 'W'):
            zz.writestr(STAGE_PUT[k].replace('\\', '/'), novye[k])
            zz.writestr('do/' + STAGE_PUT[k].replace('\\', '/'), teksty[k])
    if not ok:
        raise SystemExit(1)
    good, vyvod = zapustit_render(STAGE, 'suho', dop)
    io.open(os.path.join(DROP, 'fixA2_suho.txt'), 'w', encoding='utf-8').write(vyvod)
    sys.stdout.write(vyvod[-5500:])
    raise SystemExit(0)


# ====================================================================== ПОЛНАЯ ПРОВЕРКА ЖИВЫХ ФАЙЛОВ (без замка, только чтение)
if '--proverka' in sys.argv:
    good, vyvod = zapustit_render('-', 'proverka', ['--polnyy'])
    io.open(os.path.join(DROP, 'fixA2_proverka_polnaya.txt'), 'w', encoding='utf-8').write(vyvod)
    sys.stdout.write(vyvod[-5500:])
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
    BEKAP = os.path.join(KOREN, '_bekap', time.strftime('fixA2-%Y%m%d-%H%M%S'))
    vzyat_zamok('fixA2 (вид контактов под данные fixC/fixD)')
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
        print('бэкап: %s; меняются: %s' % (BEKAP, ', '.join(os.path.basename(FAJLY[k]) for k in izm) or 'ничего'))
        if not izm:
            raise SystemExit(0)
        # 1) web.py – живой процесс его не видит до перезапуска; 2) шаблон – в STAGE
        zapisat(FAJLY, novye, ['W'])
        if os.path.isdir(STAGE):
            shutil.rmtree(STAGE, ignore_errors=True)
        zapisat(STAGE, novye, ['C'])
        good, vyvod = zapustit_render(STAGE, 'primenit', ['--polnyy'] if '--polnyy' in sys.argv else [])
        io.open(os.path.join(DROP, 'fixA2_proverka.txt'), 'w', encoding='utf-8').write(vyvod)
        if not good:
            shutil.copy2(os.path.join(BEKAP, 'web.py'), FAJLY['W'])
            print('ПРОВЕРКА НЕ ПРОШЛА – web.py возвращён из бэкапа, шаблоны не тронуты, перезапуска нет')
            sys.stdout.write(vyvod[-4500:])
            raise SystemExit(1)
        # 3) web.py менялся – остановка -> шаблон на место -> запуск (иначе живой процесс со
        #    старым web.py получил бы шаблон с неизвестной функцией и отдал продавцу 500)
        if 'W' in izm:
            ostanovit()
            zapisat(FAJLY, novye, ['C'])
            kod = zapustit('исправитель A2: вид контактов')
            print('перезапущено, вход: %s' % kod)
        else:
            zapisat(FAJLY, novye, ['C'])
            import urllib.request
            try:
                kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            except Exception as e:  # noqa: BLE001
                kod = str(e)[:80]
            print('без перезапуска (web.py не менялся), вход: %s' % kod)
        # под замком – быстрая проверка живых файлов (ключевые карточки, список, продавец);
        # полный обход 600 карточек – отдельным прогоном --proverka без замка
        good2, vyvod2 = zapustit_render('-', 'posle', [])
        io.open(os.path.join(DROP, 'fixA2_proverka_posle.txt'), 'w', encoding='utf-8').write(vyvod2)
        if kod != 200 or not good2:
            for k in izm:
                shutil.copy2(os.path.join(BEKAP, os.path.basename(FAJLY[k])), FAJLY[k])
            if 'W' in izm:
                ostanovit()
                kod = zapustit('исправитель A2: ОТКАТ')
            print('ПОСЛЕ ПЕРЕЗАПУСКА ПЛОХО – свои файлы возвращены, снова запущено, вход: %s' % kod)
            sys.stdout.write(vyvod2[-3000:])
            raise SystemExit(1)
        print('===== ПРОВЕРКА ДО ЗАПИСИ (fixA2_proverka.txt) =====')
        sys.stdout.write(vyvod[-2500:])
        print('===== ПРОВЕРКА ЖИВЫХ ФАЙЛОВ ПОСЛЕ ПЕРЕЗАПУСКА (fixA2_proverka_posle.txt) =====')
        sys.stdout.write(vyvod2[-3000:])
    finally:
        otdat_zamok()
