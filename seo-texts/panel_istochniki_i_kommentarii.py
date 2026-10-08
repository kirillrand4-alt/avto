# -*- coding: utf-8 -*-
"""Понятные подписи источника номера + статус/причина/комментарий раздельно.

1. Владелец: «сделай понятные подписи, откуда номер телефона (сайт компании, тендерная
   площадка)». В карточке у номера стояла строка разборщика: «подпись со страницы ·
   сверено со страницей 05.10: верно», «витрина ЛПР 2-й сессии: …». Теперь подпись
   берётся из АДРЕСА ссылки: тендерная площадка (Tender.pro, B2B-Center…), госзакупки
   (ЕИС), агрегатор выписок, сторонний сайт (разборщик пометил «контакт со стороннего
   сайта»), иначе сайт компании. Исходная строка разборщика не выбрасывается: она в
   подсказке при наведении на строку. Отдельно выводятся две пометки, полезные на звонке:
   «выход на ЛПР через сотрудника» и «не сверен со страницей».
   Только для номеров и людей (contact_card, «Люди предприятия»): у новостей и реквизитов
   незнакомый домен не значит «сайт компании», там подпись прежняя.

2. Владелец: «комментарии сделай, чтобы было визуально видно: компания не понравилась,
   подпричина «нету ФТС», и видно, что именно оставил человек в комментарии, сейчас оно
   сливается». Причина пишется в тело комментария первой строкой («Причина: X. текст»),
   и в списке всё шло одной серой плашкой. Теперь в ячейке «Статус»: цветная метка
   статуса, строка «причина: X» и отдельно плашка «комментарий: текст – автор». Разбор
   тела – по списку причин (PRICHINY_NE_PONRAVILAS + снятая «дубль» для старых записей),
   а не по первой точке: в тексте причины точек нет, а в тексте человека они бывают.
   То же разделение – в истории комментариев карточки.
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
APP = os.path.join(KOREN, 'app')
T = os.path.join(APP, 'templates')
WEB = os.path.join(APP, 'web.py')
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('istochniki-komm-%Y%m%d-%H%M%S'))

WEB_KOD = r'''

# ------------------------------------------------- вид источника номера
# Владелец 08.10: «сделай понятные подписи, откуда номер телефона (сайт компании,
# тендерная площадка)». Вид определяется по АДРЕСУ ссылки, строка разборщика
# («подпись со страницы · сверено со страницей 05.10: верно») уходит в подсказку.
# Применяется только к номерам и людям: у них ссылка ведёт на страницу, где номер
# стоит, и незнакомый домен – это сайт предприятия, если разборщик не пометил
# «контакт со стороннего сайта». У новостей и реквизитов это не так.
_TENDER_PLOSHCHADKI = {
    "zakupki.gov.ru": ("госзакупки", "ЕИС"),
    "torgi.gov.ru": ("госторги", "torgi.gov.ru"),
    "zakupki.mos.ru": ("госзакупки", "Портал поставщиков Москвы"),
    "tender.pro": ("тендерная площадка", "Tender.pro"),
    "b2b-center.ru": ("тендерная площадка", "B2B-Center"),
    "rts-tender.ru": ("тендерная площадка", "РТС-тендер"),
    "sberbank-ast.ru": ("тендерная площадка", "Сбербанк-АСТ"),
    "roseltorg.ru": ("тендерная площадка", "Росэлторг"),
    "fabrikant.ru": ("тендерная площадка", "Фабрикант"),
    "etp-ets.ru": ("тендерная площадка", "ЭТП НЭП"),
    "tektorg.ru": ("тендерная площадка", "ТЭК-Торг"),
    "otc.ru": ("тендерная площадка", "OTC.ru"),
    "zakazrf.ru": ("тендерная площадка", "АГЗ РТ"),
    "etpgpb.ru": ("тендерная площадка", "ЭТП ГПБ"),
    "lot-online.ru": ("тендерная площадка", "Лот-онлайн"),
    "onlinecontract.ru": ("тендерная площадка", "Онлайн-контракт"),
    "bidzaar.com": ("тендерная площадка", "Bidzaar"),
    "tenderguru.ru": ("тендерная площадка", "TenderGuru"),
    "rostender.info": ("тендерная площадка", "Ростендер"),
    "b2b-energo.ru": ("тендерная площадка", "B2B-Energo"),
    "gazneftetorg.ru": ("тендерная площадка", "Газнефтеторг"),
    "etprf.ru": ("тендерная площадка", "ЭТП РФ"),
    "zakupki.rosatom.ru": ("тендерная площадка", "Росатом"),
    "tenderplan.ru": ("тендерная площадка", "Тендерплан"),
}
# тот же список, что АГРЕГАТОРЫ в centro.html (там – пометка «вторые руки»)
_AGREGATORY_VYPISOK = ("checko.ru", "inndex.ru", "companies.rbc.ru", "b2book.ru",
                       "b2b.house", "companium.ru", "zachestnyibiznes.ru", "star-pro.ru",
                       "ofcheck.ru", "credinform", "rusprofile", "list-org.com", "sbis.ru",
                       "audit-it.ru")


def _domen(url) -> str:
    u = str(url or "").strip()
    if not u.startswith("http"):
        return ""
    d = u.split("//", 1)[1].split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].lower()
    return d[4:] if d.startswith("www.") else d


def _vid_istochnika(url, source="") -> dict:
    """URL источника номера -> {"podpis": «тендерная площадка Tender.pro», "vid", "domen",
    "zametki": [(текст, важно)]}. Пустой URL -> podpis "" (шаблон покажет как раньше)."""
    s = str(source or "").lower()
    zametki = []
    if "через сотрудника" in s:
        zametki.append(("выход на ЛПР через сотрудника", False))
    if "не удалось сверить" in s:
        zametki.append(("не сверен со страницей", True))
    d = _domen(url)
    if not d:
        return {"podpis": "", "vid": "", "domen": "", "zametki": zametki}
    for kor, (vid, imya) in _TENDER_PLOSHCHADKI.items():
        if d == kor or d.endswith("." + kor):
            return {"podpis": "%s %s" % (vid, imya), "vid": vid, "domen": d, "zametki": zametki}
    if any(a in d for a in _AGREGATORY_VYPISOK):
        return {"podpis": "агрегатор выписок · %s" % d, "vid": "агрегатор", "domen": d,
                "zametki": zametki}
    if "стороннего сайта" in s:
        zametki.append(("не сайт компании – уточнить, чей номер", True))
        return {"podpis": "сторонний сайт · %s" % d, "vid": "сторонний сайт", "domen": d,
                "zametki": zametki}
    return {"podpis": "сайт компании · %s" % d, "vid": "сайт компании", "domen": d,
            "zametki": zametki}


templates.env.filters["vid_istochnika"] = _vid_istochnika
'''

RCS_KOD = r'''


# Владелец 08.10: «комментарии сделай, чтобы было визуально видно: компания не
# понравилась, подпричина «нету ФТС», и видно, что именно оставил человек». Причина
# лежит в теле комментария первой строкой («Причина: X. текст», см. save()); шаблон
# показывает её отдельно от текста человека. Разбор – по списку причин, а не по первой
# точке: в тексте человека точки бывают. «дубль» снят из причин, но старые записи с ним
# могли остаться – разбираются тоже.
def _razbor_kommentariya(body) -> dict:
    s = str(body or "")
    for p in list(PRICHINY_NE_PONRAVILAS) + ["дубль"]:
        nachalo = "Причина: %s" % p
        if s.startswith(nachalo) and (len(s) == len(nachalo) or s[len(nachalo)] == "."):
            return {"prichina": p, "tekst": s[len(nachalo):].lstrip(".").strip()}
    return {"prichina": "", "tekst": s.strip()}


templates.env.filters["razbor_komm"] = _razbor_kommentariya
'''

# ---------------------------------------------------------------- проверка
if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from collections import Counter
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from app import web
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    v = web._vid_istochnika
    for url, src, nado in (
            ('https://www.tender.pro/api/x', 'tender.pro · не удалось сверить', 'тендерная площадка Tender.pro'),
            ('https://zakupki.gov.ru/epz/order/1', '', 'госзакупки ЕИС'),
            ('https://checko.ru/company/x', '', 'агрегатор выписок · checko.ru'),
            ('http://kras-oil.ru/', 'подпись со страницы · сверено со страницей 05.10: верно', 'сайт компании · kras-oil.ru'),
            ('https://shkxp.ru/k', 'сайт:руководство · проверить: контакт со стороннего сайта (shkxp.ru)', 'сторонний сайт · shkxp.ru'),
            ('https://саянскиймясокомбинат.рф/kontaktyi', 'подпись со страницы', 'сайт компании · саянскиймясокомбинат.рф'),
            ('https://eportel.ru.tender.pro.fake.ru/', '', 'сайт компании · eportel.ru.tender.pro.fake.ru'),
            ('', 'подпись со страницы', '')):
        proverit(v(url, src)['podpis'] == nado, 'вид %-40s -> %r' % (url[:40], v(url, src)['podpis']))
    proverit(v('https://www.tender.pro/', 'не удалось сверить: ошибка')['zametki'] == [('не сверен со страницей', True)],
             'пометка «не сверен» из строки разборщика')

    k = sqlite3.connect(KAT)
    for tabl in ('contact', 'person'):
        c = Counter(v(u, s)['vid'] or '(без ссылки)' for u, s in k.execute(
            'select source_url, source from "%s"' % tabl))
        print('      %s по видам: %s' % (tabl, dict(c.most_common())))
    inn_tender = k.execute("select inn from contact where source_url like '%tender.pro%' limit 1").fetchone()[0]
    inn_storon = k.execute("select inn from contact where source like '%стороннего сайта%' limit 1").fetchone()[0]

    r = rcs._razbor_kommentariya
    for body, nado in (('Причина: нету ФТС и не надо (для хол). тест', ('нету ФТС и не надо (для хол)', 'тест')),
                       ('Причина: неверно указан номер', ('неверно указан номер', '')),
                       ('Причина: клиент не выходит на связь (3 звонка/2 письма). Звонил 3 раза. Писал.',
                        ('клиент не выходит на связь (3 звонка/2 письма)', 'Звонил 3 раза. Писал.')),
                       ('Причина: дубль. старое', ('дубль', 'старое')),
                       ('Причина: неверно указан номерок', ('', 'Причина: неверно указан номерок')),
                       ('просто текст', ('', 'просто текст'))):
        o = r(body)
        proverit((o['prichina'], o['tekst']) == nado, 'разбор %r -> %r / %r' % (body[:45], o['prichina'], o['tekst']))

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    with TestClient(vnutr) as kl:
        for inn, nado in ((inn_tender, 'тендерная площадка Tender.pro'), (inn_storon, 'сторонний сайт · ')):
            o = kl.get(PUT + '/centro?inn=' + inn)
            t = o.text
            ssylki = re.findall(r'<div class="source-line"[^>]*>.*?</div>', t, re.S)
            vidno = ' '.join(re.sub(r'<[^>]+>', ' ', s) for s in ssylki)
            proverit(o.status_code == 200 and nado in vidno, 'карточка %s: «%s» видно' % (inn, nado.strip()))
            proverit('подпись со страницы' not in vidno and 'сверено со страницей' not in vidno,
                     'строка разборщика ушла из текста (%d вхождений в подсказках)' % t.count('title="подпись со страницы'))
            io.open(os.path.join(DROP, 'centro2-karta-istochnik-%s.html' % inn), 'w', encoding='utf-8').write(t)
        # список: вкладка «не понравилась»
        o = kl.get(PUT + '/centro?call_status=ne_ponravilas')
        t = o.text
        io.open(os.path.join(DROP, 'centro2-spisok-nepon.html'), 'w', encoding='utf-8').write(t)
        proverit(o.status_code == 200, 'список «не понравилась»: %s' % o.status_code)
        n_metok = t.count('class="st-metka st-ne_ponravilas"')
        n_prich = t.count('class="och-prichina"')
        n_komm = t.count('class="och-komm"')
        print('      меток статуса %d, строк причины %d, плашек комментария %d' % (n_metok, n_prich, n_komm))
        proverit(n_metok >= 1 and n_prich >= 1, 'статус меткой и причина отдельной строкой')
        m = re.search(r'<div class="och-prichina">(.*?)</div>', t, re.S)
        print('      причина: %r' % (re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip() if m else None))
        m = re.search(r'<div class="och-komm"[^>]*>(.*?)</div>', t, re.S)
        print('      комментарий: %r' % (re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip() if m else None))
        proverit('Причина: ' not in re.sub(r'title="[^"]*"', '', t.split('<table class="och-tab">')[-1]),
                 'в видимом тексте списка нет склеенного «Причина: …»')
        o = kl.get(PUT + '/centro')
        proverit(o.status_code == 200, 'вся очередь: %s' % o.status_code)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ---------------------------------------------------------------- правки
os.makedirs(BEKAP, exist_ok=True)
log = []
nado = sdelano = 0


def pravka(p, staro, novo, imya, priznak, vse=False):
    global nado, sdelano
    nado += 1
    t = io.open(p, encoding='utf-8').read()
    if priznak in t:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    n = t.count(staro)
    if n == 0 or (n != 1 and not vse):
        log.append('[ЯКОРЬ: %d] %s – не правлю' % (n, imya))
        return
    b = os.path.join(BEKAP, os.path.basename(p))
    if not os.path.exists(b):
        shutil.copy2(p, b)
    io.open(p, 'w', encoding='utf-8').write(t.replace(staro, novo) if vse else t.replace(staro, novo, 1))
    sdelano += 1
    log.append('[ок] %s%s' % (imya, (' (%d)' % n) if vse else ''))


# код: фильтры
pravka(WEB, 'templates.env.globals["count_ru"] = count_ru\n',
       'templates.env.globals["count_ru"] = count_ru\n' + WEB_KOD, 'фильтр vid_istochnika', '_vid_istochnika')
t = io.open(RCS, encoding='utf-8').read()
if '_razbor_kommentariya' in t:
    sdelano += 1
    log.append('[уже] фильтр razbor_komm')
else:
    shutil.copy2(RCS, os.path.join(BEKAP, 'routes_centro_sales.py'))
    io.open(RCS, 'w', encoding='utf-8').write(t.rstrip('\n') + '\n' + RCS_KOD)
    sdelano += 1
    log.append('[ок] фильтр razbor_komm')
nado += 1

C = os.path.join(T, 'centro.html')
# 1. макрос источника: ветка для номеров и людей
pravka(C, "{% macro source_link(source, url, label='Источник') %}\n",
       "{% macro source_link(source, url, label='Источник', telefon=False) %}\n"
       "{% if telefon and (url or '').startswith('http') %}\n"
       "  {# Номер и человек: подпись по виду источника (сайт компании, тендерная площадка,\n"
       "     госзакупки, агрегатор, сторонний сайт) – владелец 08.10. Строка разборщика\n"
       "     не выброшена: она в подсказке при наведении. #}\n"
       "  {% set в = url|vid_istochnika(source) %}\n"
       "  <div class=\"source-line\" title=\"{{ source or '' }}\">\n"
       "    <span>{{ label }}:</span>\n"
       "    {% for а in (url or '').replace(';', ' ').split() if а.startswith('http') %}\n"
       "      <a href=\"{{ а }}\" target=\"_blank\" rel=\"noopener noreferrer\">{{ (а|vid_istochnika(source)).podpis }} ↗</a>{% if not loop.last %}<span> · </span>{% endif %}\n"
       "    {% endfor %}\n"
       "    {% for z, vazhno in в.zametki %}{% if vazhno %}<em>{{ z }}</em>{% else %}<span class=\"istochnik-zametka\">{{ z }}</span>{% endif %}{% endfor %}\n"
       "  </div>\n"
       "{% else %}\n",
       'макрос источника: ветка для номеров', 'telefon=False) %}')
pravka(C, "      <em>ссылки нет</em>\n    {% endif %}\n  </div>\n{% endmacro %}",
       "      <em>ссылки нет</em>\n    {% endif %}\n  </div>\n{% endif %}\n{% endmacro %}",
       'макрос источника: закрытие ветки', "{% endif %}\n  </div>\n{% endif %}\n{% endmacro %}")
pravka(C, '{{ source_link(contact.source, contact.source_url) }}',
       '{{ source_link(contact.source, contact.source_url, telefon=True) }}',
       'номера: подпись по виду источника', 'source_link(contact.source, contact.source_url, telefon=True)')
pravka(C, '{{ source_link(person.source, person.source_url) }}',
       '{{ source_link(person.source, person.source_url, telefon=True) }}',
       'люди: подпись по виду источника', 'source_link(person.source, person.source_url, telefon=True)', vse=True)
# 2. история комментариев в карточке
pravka(C, '<time>{{ item.created_at }}</time><p>{{ item.body }}</p></article>',
       '<time>{{ item.created_at }}</time>{% set rk = item.body|razbor_komm %}'
       '{% if rk.prichina %}<p class="komm-prichina">причина: <b>{{ rk.prichina }}</b></p>{% endif %}'
       '{% if rk.tekst %}<p class="komm-tekst">{{ rk.tekst }}</p>{% endif %}</article>',
       'карточка: причина и текст раздельно', 'komm-prichina')
pravka(C, '.hide-company{margin:8px 0 0;',
       '.istochnik-zametka{color:#667085}\n'
       '.comments .komm-prichina{margin:4px 0 0;color:#9b1c1c;font-size:13px}\n'
       '.comments .komm-prichina b{font-weight:650}\n'
       '.comments .komm-tekst{margin:4px 0;padding:4px 8px;background:#f6f7fb;border-left:3px solid #c7cbe8;border-radius:4px}\n'
       '.hide-company{margin:8px 0 0;', 'карточка: стили', '.istochnik-zametka{')

# 3. список: ячейка «Статус»
L = os.path.join(T, '_ochered_spisok.html')
pravka(L, "        <td>{{ call_results.get(c.call_result or 'new', c.call_result or 'Новый') }}\n",
       "        <td>{% set _st = c.call_result or 'new' %}<span class=\"st-metka st-{{ _st }}\">{{ call_results.get(_st, _st) }}</span>\n",
       'список: статус цветной меткой', 'class="st-metka st-')
staro = ('          {% if km %}<div class="och-komm" title="{{ km.body }}">{{ km.body|truncate(120, True, \'…\') }}'
         '{% if user.role == \'admin\' %}<span class="tiho"> – {{ km.username|fio }}'
         '{% if (km.created_at or \'\')[:10] != (c.last_contact_at or \'\')[:10] %}, {{ (km.created_at or \'\')[:10] }}{% endif %}'
         '</span>{% endif %}</div>{% endif %}</td>')
novo = ('          {% if km %}{% set rk = km.body|razbor_komm %}'
        '{% set kto %}{% if user.role == \'admin\' %}<span class="tiho"> – {{ km.username|fio }}'
        '{% if (km.created_at or \'\')[:10] != (c.last_contact_at or \'\')[:10] %}, {{ (km.created_at or \'\')[:10] }}{% endif %}'
        '</span>{% endif %}{% endset %}\n'
        '            {% if rk.prichina %}<div class="och-prichina"><span class="och-podpis">причина:</span> {{ rk.prichina }}'
        '{% if not rk.tekst %}{{ kto }}{% endif %}</div>{% endif %}\n'
        '            {% if rk.tekst %}<div class="och-komm" title="{{ rk.tekst }}"><span class="och-podpis">комментарий:</span> '
        '{{ rk.tekst|truncate(120, True, \'…\') }}{{ kto }}</div>{% endif %}\n'
        '          {% endif %}</td>')
pravka(L, staro, novo, 'список: причина и комментарий раздельно', 'class="och-prichina"')
pravka(L, '.komp-yach{display:flex;',
       '.st-metka{display:inline-block;padding:2px 8px;border-radius:5px;font-size:12px;font-weight:600;\n'
       '  white-space:nowrap;background:#f0f1f3;border:1px solid #d1d4db;color:#525a69}\n'
       '.st-metka.st-new{padding:0;border:0;background:none;font-weight:400;color:inherit;font-size:13px}\n'
       '.st-metka.st-ne_ponravilas{background:#fdecec;border-color:#f3c2c2;color:#9b1c1c}\n'
       '.st-metka.st-v_rabote{background:#e8f6ee;border-color:#b7e1c7;color:#17663a}\n'
       '.och-prichina{margin-top:5px;max-width:300px;font-size:12px;line-height:1.35;color:#9b1c1c;font-weight:600}\n'
       '.och-podpis{color:var(--muted);font-weight:400;font-size:11px}\n'
       '.komp-yach{display:flex;', 'список: стили метки и причины', '.st-metka{')
for x in log:
    print('   ' + x)
print('правок внесено: %d из %d' % (sdelano, nado))
print('бэкап: %s' % BEKAP)
if sdelano != nado:
    print('НЕ ВСЕ ПРАВКИ ВНЕСЕНЫ – перезапуск не делаю')
    raise SystemExit(1)

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: источники номеров и комментарии %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=sreda)
time.sleep(10)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=900, cwd=KOREN, env=sreda)
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
