# -*- coding: utf-8 -*-
"""Исправитель M (13.10): «продавец» -> «менеджер по продажам» в интерфейсе панели Meyer.

Владелец 13.10: «переименуй „продавец“ в „менеджер по продажам“, а то обидятся ещё».

Что меняется – только текст, который видит человек (HTML, CSV, подписи, подсказки, сообщения):
  * шаблоны (centro.html, _ochered_spisok.html, _statblok.html, centro_stats.html, _shapka.html,
    spisok.html, park_net.html) – каждое видимое вхождение по своему якорю, с падежом и числом
    (продавца -> менеджера по продажам, продавцам -> менеджерам по продажам …);
  * api/routes_centro_sales.py – подписи отбора директора, пункт сортировки, заголовок CSV,
    подпись среза «Откуда номер», сообщение «уже был в контактах (…)»;
  * web.py – фильтр показа `menedzher`: значения ИЗ БАЗ, где слово – часть ключа и менять его
    нельзя (источник номера «от продавца: …» – по этому префиксу его ищут код панели и сверки;
    вид «ЛПР со слов продавца» – ключ уровней ЛПР и значение фильтра «Роль ЛПР»), на экране
    показываются с новым словом, в базе и в значениях фильтров остаются прежними.
НЕ трогаются: комментарии кода и шаблонов, имена переменных, ключи, URL-параметры, колонки БД,
роли пользователей (role='sales'), логины, данные в базах.

Режимы:
  --suho [--polnyy]  без замка: правки на КОПИИ app в C:\\centro2\\_bekap\\fixM-stage; рендер
                     TestClient-ом (копии баз, в копии каталога – пробный номер «от продавца»)
                     «до» (живой код) и «после» (копия) -> fixM_suho.json, fixM_html_*.zip на дроп.
  --primenit         под замком: перечитать живые файлы -> правки -> проверка на копии -> остановка
                     -> запись -> запуск -> проверка живых; провал – свои файлы из бэкапа этого
                     прогона и снова запуск.
"""
import html as _html
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from html.parser import HTMLParser

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
ZAMOK = r'C:\centro2\_zamok.txt'
STAGE = os.path.join(KOREN, '_bekap', 'fixM-stage')
KAT_ZHIVOY = os.path.join(KOREN, 'data', 'meyer_baza1.db')
PRIMERY = ['5251001312', '6382000106', '7203319557', '3254002818', '1829013726', '2245002584']
SINN = '5251001312'          # в копии каталога ему добавляется пробный номер «от продавца»
WEB_METKA = '# ------------------------------------------------- «менеджер по продажам» вместо «продавец» (исправитель M'

WEB_BLOK = r'''

# ------------------------------------------------- «менеджер по продажам» вместо «продавец» (исправитель M, 13.10)
# Владелец 13.10: «переименуй „продавец“ в „менеджер по продажам“». Подписи шаблонов и кода
# переименованы прямо; этот фильтр – только для ПОКАЗА значений из баз, где слово входит в
# ключ: источник номера «от продавца: …» (по префиксу его ищут код панели и сверки) и вид
# «ЛПР со слов продавца» (ключ уровней ЛПР и значение фильтра «Роль ЛПР»). В базе и в
# значениях фильтров они остаются прежними. Исключений не бросает.
import re as _re_menedzher

_MENEDZHER_FORMY = {"ец": "менеджер", "ца": "менеджера", "цу": "менеджеру", "цом": "менеджером",
                    "це": "менеджере", "цы": "менеджеры", "цов": "менеджеров", "цам": "менеджерам",
                    "цами": "менеджерами", "цах": "менеджерах"}
_MENEDZHER_RX = _re_menedzher.compile(
    r"(?<![А-Яа-яЁё])([Пп])родав(ец|ца|цу|цом|це|цы|цов|цам|цами|цах)(?![А-Яа-яЁё])")


def _menedzher(s):
    """«от продавца: …» -> «от менеджера по продажам: …» (падеж и число сохраняются)."""
    try:
        if not isinstance(s, str) or "родав" not in s:
            return s
        return _MENEDZHER_RX.sub(
            lambda m: ("М" if m.group(1) == "П" else "м") + _MENEDZHER_FORMY[m.group(2)][1:] + " по продажам", s)
    except Exception:  # noqa: BLE001
        return s


templates.env.filters["menedzher"] = _menedzher
'''

RCS = r'api\routes_centro_sales.py'
W = 'web.py'
# (файл относительно app, было, стало, что это)
RUCHNYE = [
    (RCS, '        chasti.append("продавец: " + _fio_dlya_shablona(params.get("kto_p")))',
          '        chasti.append("менеджер по продажам: " + _fio_dlya_shablona(params.get("kto_p")))',
     'описание отбора директора над списком'),
    (RCS, '            chasti.append("продавец: " + _fio_dlya_shablona(p.get("kto_p")))',
          '            chasti.append("менеджер по продажам: " + _fio_dlya_shablona(p.get("kto_p")))',
     'описание отбора из статистики над списком'),
    (RCS, '    ("", "порядок очереди (как у продавца)"),',
          '    ("", "порядок очереди (как у менеджера по продажам)"),', 'пункт сортировки списка'),
    (RCS, '"Последний комментарий", "Балл очереди", "Продавец",',
          '"Последний комментарий", "Балл очереди", "Менеджер по продажам",', 'заголовок колонки CSV'),
    (RCS, '"от продавца" if str(r["source"] or "").startswith("от продавца")   # fixB',
          '"от менеджера по продажам" if str(r["source"] or "").startswith("от продавца")   # fixB',
     'подпись среза «Откуда номер» в статистике (префикс-ключ «от продавца» в startswith не тронут)'),
    (RCS, 'return r[0], "уже был в контактах (от продавца)"',
          'return r[0], "уже был в контактах (от менеджера по продажам)"',
     'итог добавления номера в каталог (виден в карточке)'),
    (RCS, 'c.get("otrasl") or "", c.get("lpr_roli") or "",',
          'c.get("otrasl") or "", templates.env.filters.get("menedzher", str)(c.get("lpr_roli") or ""),',
     'CSV «Роли ЛПР»: показ вида «ЛПР со слов продавца» новым словом'),
    (r'templates\centro.html',
     "{% macro source_link(source, url, label='Источник', telefon=False, fragment='', chuzhoy='', svyaz='') %}\n",
     "{% macro source_link(source, url, label='Источник', telefon=False, fragment='', chuzhoy='', svyaz='') %}\n"
     "{% set source = source|menedzher %}{# fixM 13.10: «от продавца: …» в базе – ключ, на экране – новое слово #}\n",
     'карточка: строка источника номера «от продавца: …»'),
    (r'templates\centro.html',
     '<span>{{ _долж }}{% if _ур %} <span class="uroven-lpr">ЛПР: {{ _ур }}</span>{% endif %}</span>',
     '<span>{{ _долж|menedzher }}{% if _ур %} <span class="uroven-lpr">ЛПР: {{ _ур|menedzher }}</span>{% endif %}</span>',
     'карточка: должность/уровень ЛПР номера («ЛПР со слов продавца»)'),
    (r'templates\centro.html',
     "{% if request.query_params.get('rol_lpr') == value %}selected{% endif %}>{{ value }} – {{ n }}</option>",
     "{% if request.query_params.get('rol_lpr') == value %}selected{% endif %}>{{ value|menedzher }} – {{ n }}</option>",
     'фильтр «Роль ЛПР»: подпись (значение фильтра прежнее)'),
    (r'templates\_ochered_spisok.html', '{% set _л = c.lpr_kratko|lpr_razbor %}',
     '{% set _л = c.lpr_kratko|menedzher|lpr_razbor %}', 'список: ЛПР строкой (должность «ЛПР со слов продавца»)'),
    (r'templates\_ochered_spisok.html', '<span class="lpr-roli tiho">{{ c.lpr_roli }}</span>',
     '<span class="lpr-roli tiho">{{ c.lpr_roli|menedzher }}</span>', 'список: роли ЛПР'),
    (r'templates\_ochered_spisok.html', "{% else %}{{ c.lpr_roli or '–' }}{% endif %}",
     "{% else %}{{ (c.lpr_roli or '–')|menedzher }}{% endif %}", 'список: роли ЛПР без ФИО'),
    (r'templates\centro_stats.html', '<td>{{ z.znach }}</td>', '<td>{{ z.znach|menedzher }}</td>',
     'статистика: значения срезов («Роль ЛПР», «Откуда номер»)'),
]

AVTO = [
    ('templates/_statblok.html', 45, 'Продавец', ' <label>Продавец', ' <label>Менеджер по продажам'),
    ('templates/_statblok.html', 47, 'продавцы', '="">все продавцы</option', '="">все менеджеры по продажам</option'),
    ('templates/_statblok.html', 64, 'Продавец', 'pan="2">Продавец</th>', 'pan="2" title="Менеджер по продажам">Менеджер</th>'),
    ('templates/_statblok.html', 72, 'продавцы', '<td>Все продавцы</td>{{ ', '<td title="Все менеджеры по продажам">Все менеджеры</td>{{ '),
    ('templates/_statblok.html', 77, 'продавцов', '="tiho">продавцов нет</td', '="tiho">менеджеров по продажам нет</td'),
    ('templates/_statblok.html', 84, 'продавец', 'то, что продавец видит (', 'то, что менеджер по продажам видит ('),
    ('templates/_ochered_spisok.html', 114, 'продавца', 'очередь продавца: больше', 'очередь менеджера по продажам: больше'),
    ('templates/_ochered_spisok.html', 114, 'Продавец', "' %}<th>Продавец</th>{% ", '\' %}<th title="Менеджер по продажам">Менеджер</th>{% '),
    ('templates/_ochered_spisok.html', 132, 'продавца', 'очереди продавца её нет;', 'очереди менеджера по продажам её нет;'),
    ('templates/_ochered_spisok.html', 142, 'Продавец', '-label="Продавец">{{ (c.', '-label="Менеджер по продажам">{{ (c.'),
    ('templates/centro_stats.html', 54, 'продавцам', ' <h2>По продавцам: за пер', ' <h2>По менеджерам по продажам: за пер'),
    ('templates/centro_stats.html', 70, 'продавцу', 'ывается продавцу, за кот', 'ывается менеджеру по продажам, за кот'),
    ('templates/centro_stats.html', 72, 'Продавец', ' <thead><tr><th>Продавец</th><th>Не дозв', ' <thead><tr><th>Менеджер по продажам</th><th>Не дозв'),
    ('templates/centro_stats.html', 75, 'продавцы', ' class="itog"{% endif %}><td>{% if s.itog %}Все продавцы{% else %}{{ s.kto|fio }}{% endif %}</td><td><b>', ' class="itog"{% endif %}><td>{% if s.itog %}Все менеджеры по продажам{% else %}{{ s.kto|fio }}{% endif %}</td><td><b>'),
    ('templates/centro_stats.html', 76, 'Продавцов', 'pan="5">Продавцов нет.</t', 'pan="5">Менеджеров по продажам нет.</t'),
    ('templates/centro_stats.html', 92, 'продавцам', 'азов по продавцам <span c', 'азов по менеджерам по продажам <span c'),
    ('templates/centro_stats.html', 93, 'продавец', 'kto %}, продавец {{ d.kt', 'kto %}, менеджер по продажам {{ d.kt'),
    ('templates/centro_stats.html', 95, 'Продавец', '    <thead><tr><th>Продавец</th><th>Отмечено компан', '    <thead><tr><th>Менеджер по продажам</th><th>Отмечено компан'),
    ('templates/centro_stats.html', 98, 'продавцы', ' class="itog"{% endif %}><td>{% if s.itog %}Все продавцы{% else %}{{ s.kto|fio }}{% endif %}</td><td>{{ ', ' class="itog"{% endif %}><td>{% if s.itog %}Все менеджеры по продажам{% else %}{{ s.kto|fio }}{% endif %}</td><td>{{ '),
    ('templates/centro_stats.html', 99, 'Продавцов', 'pan="9">Продавцов нет.</t', 'pan="9">Менеджеров по продажам нет.</t'),
    ('templates/centro_stats.html', 104, 'продавца', 'у этого продавца. «В ден', 'у этого менеджера по продажам. «В ден'),
    ('templates/centro_stats.html', 106, 'Продавец', '    <thead><tr><th>Продавец</th><th>Отмечено</th><t', '    <thead><tr><th>Менеджер по продажам</th><th>Отмечено</th><t'),
    ('templates/centro_stats.html', 109, 'продавцы', 'if t.itog %}Все продавцы{% else %}{{ t.k', 'if t.itog %}Все менеджеры по продажам{% else %}{{ t.k'),
    ('templates/centro_stats.html', 146, 'Продавец', '/th><th>Продавец</th><th', '/th><th>Менеджер по продажам</th><th'),
    ('templates/centro_stats.html', 163, 'продавца', 'ний без продавца</span><', 'ний без менеджера по продажам</span><'),
    ('templates/centro_stats.html', 164, 'продавцах', 'на двух продавцах</span><', 'на двух менеджерах по продажам</span><'),
    ('templates/centro_stats.html', 176, 'продавцам', 'аченные продавцам. Скрыты', 'аченные менеджерам по продажам. Скрыты'),
    ('templates/centro_stats.html', 176, 'продавцом', 'Скрытые продавцом позже в', 'Скрытые менеджером по продажам позже в'),
    ('templates/centro_stats.html', 195, 'Продавец', 'ometka">Продавец видит э', 'ometka">Менеджер по продажам видит э'),
    ('templates/centro_stats.html', 199, 'Продавец', ' <thead><tr><th>Продавец</th><th>ИНН</th', ' <thead><tr><th>Менеджер по продажам</th><th>ИНН</th'),
    ('templates/centro_stats.html', 209, 'продавцам', ' <h2>По продавцам</h2>', ' <h2>По менеджерам по продажам</h2>'),
    ('templates/centro_stats.html', 210, 'продавца', 'ь этого продавца в том ж', 'ь этого менеджера по продажам в том ж'),
    ('templates/centro_stats.html', 214, 'Продавец', '    <th>Продавец</th><th', '    <th>Менеджер по продажам</th><th'),
    ('templates/centro_stats.html', 214, 'продавцу', 'h>Видно продавцу</th><th', 'h>Видно менеджеру по продажам</th><th'),
    ('templates/centro_stats.html', 238, 'продавца', 'Очередь продавца {{ vybr', 'Очередь менеджера по продажам {{ vybr'),
    ('templates/centro_stats.html', 239, 'продавца', ', что у продавца: наверх', ', что у менеджера по продажам: наверх'),
    ('templates/centro_stats.html', 242, 'продавец', 'ваются: продавец их тоже', 'ваются: менеджер по продажам их тоже'),
    ('templates/centro_stats.html', 261, 'продавца', 'У этого продавца нет наз', 'У этого менеджера по продажам нет наз'),
    ('templates/centro.html', 149, 'продавцом', '"убрано продавцом">', '"убрано менеджером по продажам">'),
    ('templates/centro.html', 179, 'продавца', 'очередь продавца: больше', 'очередь менеджера по продажам: больше'),
    ('templates/centro.html', 237, 'продавцы', '="">Все продавцы</option', '="">Все менеджеры по продажам</option'),
    ('templates/centro.html', 239, 'продавца', ' %}>Без продавца · {{ ch', ' %}>Без менеджера по продажам · {{ ch'),
    ('templates/centro.html', 241, 'продавцы', 'которым продавцы ставили', 'которым менеджеры по продажам ставили'),
    ('templates/centro.html', 247, 'продавца', '», а от продавца ни слов', '», а от менеджера по продажам ни слов'),
    ('templates/centro.html', 250, 'продавца', 'очереди продавца">{% for', 'очереди менеджера по продажам">{% for'),
    ('templates/centro.html', 374, 'продавца', 'очереди продавца её нет"', 'очереди менеджера по продажам её нет"'),
    ('templates/centro.html', 416, 'продавца', ' одного продавца.</p></d', ' одного менеджера по продажам.</p></d'),
    ('templates/centro.html', 628, 'продавцом', '"убрано продавцом с карто', '"убрано менеджером по продажам с карто'),
    ('templates/centro.html', 740, 'продавца', 'онок за продавца{% if co', 'онок за менеджера по продажам{% if co'),
    ('templates/centro.html', 740, 'продавца', '– форма продавца</summar', '– форма менеджера по продажам</summar'),
    ('templates/centro.html', 1144, 'продавца', 'второго продавца свои.</', 'второго менеджера по продажам свои.</'),
    ('templates/spisok.html', 83, 'Продавец', ' <label>Продавец', ' <label>Менеджер по продажам'),
    ('templates/spisok.html', 118, 'Продавец', '    <th>Продавец</th>', '    <th>Менеджер по продажам</th>'),
    ('templates/_shapka.html', 27, 'продавец', "' else 'продавец' }}</sp", "' else 'менеджер по продажам' }}</sp"),
    ('templates/park_net.html', 22, 'продавцам', '        продавцам в «Цент', '        менеджерам по продажам в «Цент'),
]

PRAVKI = [(f.replace('/', '\\'), a, b, 'видимый текст, стр. %d: %s' % (n, sl)) for f, n, sl, a, b in AVTO] + RUCHNYE
FAJLY = sorted({p[0] for p in PRAVKI} | {W})


def prochitat(koren):
    return {f: io.open(os.path.join(koren, f), encoding='utf-8').read() for f in FAJLY}


def nalozhit(teksty):
    """Правки по якорям. -> (новые тексты, журнал [(файл, строка, было, стало, итог, что)], ок)."""
    novye = dict(teksty)
    zhurnal, ok = [], True
    for f, staro, novo, chto in PRAVKI:
        t = novye[f]
        n = t.count(staro)
        if novo in t:                      # уже сделано (новое может содержать старое – проверяется первым)
            zhurnal.append((f, t.count('\n', 0, t.index(novo)) + 1, staro, novo, 'уже', chto))
        elif n == 1:
            i = t.index(staro)
            stroka = t.count('\n', 0, i) + 1
            novye[f] = t.replace(staro, novo, 1)
            zhurnal.append((f, stroka, staro, novo, 'ок', chto))
        else:
            zhurnal.append((f, 0, staro, novo, 'ЯКОРЬ: %d' % n, chto))
            ok = False
    if WEB_METKA in novye[W]:
        zhurnal.append((W, 0, '', 'фильтр menedzher', 'уже', 'web.py: фильтр показа'))
    else:
        novye[W] = novye[W].rstrip('\n') + '\n' + WEB_BLOK
        zhurnal.append((W, novye[W].count('\n', 0, novye[W].index(WEB_METKA)) + 1, '', 'фильтр menedzher', 'ок',
                        'web.py: фильтр показа значений из баз'))
    return novye, zhurnal, ok


def zapisat(koren, teksty, klyuchi):
    for f in klyuchi:
        p = os.path.join(koren, f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, 'w', encoding='utf-8').write(teksty[f])


def sdelat_stage(novye):
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    shutil.copytree(APP, os.path.join(STAGE, 'app'),
                    ignore=shutil.ignore_patterns('__pycache__', 'dokaz', '*.pyc', '*.db', '*.log'))
    zapisat(os.path.join(STAGE, 'app'), novye, FAJLY)


# ====================================================================== видимый текст страницы
SLOVO = re.compile(r'[Пп]родав\w*')
SLOVO_PRODAVEC = re.compile(r'(?<![А-Яа-яЁё])[Пп]родав(?:ец|ца|цу|цом|це|цы|цов|цам|цами|цах)(?![А-Яа-яЁё])')
VIDNYE_ATR = {'title', 'placeholder', 'aria-label', 'alt', 'data-label', 'label'}


class Vidimoe(HTMLParser):
    """Текст, который видит человек: узлы текста, подсказки/плейсхолдеры, подписи кнопок,
    строки скриптов (они вставляют HTML). Без комментариев HTML/CSS/JS и без значений
    скрытых полей и пунктов выбора (это ключи, их не видно)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.kuski, self.v = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k, v in attrs:
            if k in VIDNYE_ATR and v:
                self.kuski.append(v)
        if tag == 'input' and (a.get('type') or '').lower() in ('submit', 'button') and a.get('value'):
            self.kuski.append(a['value'])
        if tag in ('style', 'script'):
            self.v = tag

    def handle_endtag(self, tag):
        if tag in ('style', 'script'):
            self.v = None

    def handle_data(self, d):
        if self.v == 'style':
            return
        if self.v == 'script':
            d = re.sub(r'/\*.*?\*/', ' ', d, flags=re.S)
            d = re.sub(r'(?<![:\'"\\])//[^\n]*', ' ', d)
        self.kuski.append(d)


def vidimyy_tekst(h):
    p = Vidimoe()
    try:
        p.feed(h)
        p.close()
    except Exception:  # noqa: BLE001
        pass
    return ' \n '.join(p.kuski)


def nayti(tekst):
    out = []
    for m in SLOVO.finditer(tekst):
        out.append(' '.join(tekst[max(0, m.start() - 60): m.end() + 40].split()))
    return out


# ====================================================================== РЕНДЕР (venv-процесс)
def render(koren_app, metka, polnyy):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение, chdir в KOREN
    sys.path.insert(0, koren_app)
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    pid = os.getpid()
    # копия базы продаж: GET главной может раздать новые ИНН – пусть в копию
    test_sales = os.path.join(KOREN, '_bekap', 'fixM-sales-%d.db' % pid)
    zh = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
    kop = sqlite3.connect(test_sales)
    zh.backup(kop)
    zh.close()
    kop.close()
    # копия каталога с пробным номером «от продавца» (так его пишет панель, когда менеджер
    # сохраняет «Получен личный номер ЛПР» с неопознанной должностью)
    test_kat = os.path.join(KOREN, '_bekap', 'fixM-kat-%d.db' % pid)
    zk = sqlite3.connect('file:%s?mode=ro' % KAT_ZHIVOY, uri=True)
    kk = sqlite3.connect(test_kat)
    zk.backup(kk)
    zk.close()
    kol_c = [r[1] for r in kk.execute('pragma table_info(contact)')]
    kol_k = [r[1] for r in kk.execute('pragma table_info(company)')]
    stroka = {'inn': SINN, 'value': '+7 495 000-00-00', 'kind': 'phone', 'person': 'Тестов Тест Тестович',
              'role': 'ЛПР со слов продавца', 'position': None, 'phone_type': 'рабочий',
              'source': 'от продавца: Тестов Т., 13.10 · личный номер ЛПР со слов продавца',
              'source_url': None, 'is_purchaser': 0, 'is_tech': 0, 'has_role': 1, 'is_unknown_owner': 0,
              'istochniki': 'от продавца', 'istochnikov': 1}
    pol = [k for k in stroka if k in kol_c]
    try:
        kk.execute('insert into contact(%s) values(%s)' % (','.join(pol), ','.join('?' * len(pol))), [stroka[k] for k in pol])
        oshibka_vstavki = ''
    except Exception as e:  # noqa: BLE001
        oshibka_vstavki = repr(e)[:200]
    if 'lpr_roli' in kol_k:
        kk.execute("update company set lpr_roli = trim(coalesce(lpr_roli,'') || case when coalesce(lpr_roli,'')='' then '' else ', ' end || 'ЛПР со слов продавца') where inn=?", (SINN,))
    if 'lpr_kratko' in kol_k:
        kk.execute("update company set lpr_kratko = 'Тестов Тест Тестович · ЛПР со слов продавца · +7 495 000-00-00' where inn=?", (SINN,))
    kk.commit()
    kk.close()
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = test_sales
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        if os.path.normcase(os.path.abspath(os.environ.get(k, '') or 'x')) == os.path.normcase(KAT_ZHIVOY):
            os.environ[k] = test_kat
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    from app import web
    assert os.path.normcase(os.path.dirname(web.__file__)).startswith(os.path.normcase(koren_app)), web.__file__
    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    itog = {'metka': metka, 'web': web.__file__, 'stranicy': [], 'plohih': 0, 'proverki': []}
    z = zipfile.ZipFile(os.path.join(DROP, 'fixM_html_%s.zip' % metka), 'w', zipfile.ZIP_DEFLATED)

    def proverit(u, t):
        itog['proverki'].append(('ОК ' if u else 'ПЛОХО') + ' ' + t)
        if not u:
            itog['plohih'] += 1

    def stranica(kl, kto, imya, url, params=None):
        o = kl.get(PUT + url, params=params or {})
        t = o.content.decode('utf-8-sig', 'replace')
        if o.status_code == 200:
            z.writestr('%s_%s.%s' % (kto, imya, 'csv' if url.endswith('.csv') else 'html'), t)
        vid = t if url.endswith('.csv') else vidimyy_tekst(t)
        hits = nayti(vid)
        itog['stranicy'].append({'kto': kto, 'imya': imya, 'url': url, 'params': params or {}, 'kod': o.status_code,
                                 'prodav_vidno': len(hits), 'prodavec_vidno': len(SLOVO_PRODAVEC.findall(vid)),
                                 'gde': hits[:12], 'v_kode_stranicy': len(SLOVO.findall(t))})
        return o.status_code, t, vid

    vnutr.dependency_overrides[rcs.current_user] = lambda: ADMIN
    with TestClient(vnutr) as kl:
        stranica(kl, 'admin', 'spisok', '/centro')
        stranica(kl, 'admin', 'spisok100', '/centro', {'size': '100'})
        k, t, vid = stranica(kl, 'admin', 'spisok_sinn', '/centro', {'q': SINN})
        stranica(kl, 'admin', 'spisok_bez', '/centro', {'assigned_user': '__net__'})
        stranica(kl, 'admin', 'spisok_kto', '/centro', {'kto_p': 'meyer2', 'ot': '2026-10-01', 'do': '2026-10-13'})
        for inn in PRIMERY:
            k, t, vid = stranica(kl, 'admin', 'card_%s' % inn, '/centro', {'inn': inn})
            if inn == SINN:
                kart_sinn = vid
        stranica(kl, 'admin', 'stats', '/centro/stats')
        stranica(kl, 'admin', 'stats_vse_meyer2', '/centro/stats', {'stat_vse': '1', 'user': 'meyer2'})
        stranica(kl, 'admin', 'csv', '/centro/vygruzka.csv')
        stranica(kl, 'admin', 'admin', '/centro/admin')
        stranica(kl, 'admin', 'park', '/centro/park')
        stranica(kl, 'admin', 'park_inn', '/centro/park/%s' % SINN)
        stranica(kl, 'admin', 'spisok_park', '/centro/spisok')
        if polnyy:
            kat = sqlite3.connect('file:%s?mode=ro' % test_kat, uri=True)
            vse = [r[0] for r in kat.execute('select inn from company')]
            kat.close()
            sost = {r[0]: r[1] for r in sqlite3.connect(test_sales).execute('select inn, call_result from company_state')}
            ob = {'kart': 0, 'ne200': [], 'prodav': {}}
            for inn in vse:
                params = {'inn': inn}
                if sost.get(inn) in ('v_rabote', 'ne_ponravilas', 'dubl'):
                    params['call_status'] = sost[inn]
                o = kl.get(PUT + '/centro', params=params)
                ob['kart'] += 1
                if o.status_code != 200:
                    ob['ne200'].append([inn, o.status_code])
                    continue
                h = nayti(vidimyy_tekst(o.text))
                if h:
                    ob['prodav'][inn] = h[:6]
            itog['obhod'] = ob
    vnutr.dependency_overrides[rcs.current_user] = lambda: PROD
    with TestClient(vnutr) as kl:
        k, t, vid = stranica(kl, 'sales', 'spisok', '/centro')
        moi = re.findall(r'data-href="[^"]*inn=(\d{10,12})', t)[:2]
        for inn in moi:
            stranica(kl, 'sales', 'card_%s' % inn, '/centro', {'inn': inn})
        stranica(kl, 'sales', 'stats', '/centro/stats')
        stranica(kl, 'sales', 'csv', '/centro/vygruzka.csv')
        stranica(kl, 'sales', 'spisok_park', '/centro/spisok')
    z.close()
    proverit(not oshibka_vstavki, 'пробный номер в копии каталога вставлен %s' % oshibka_vstavki)
    if hasattr(web, '_menedzher'):
        f = web._menedzher
        proverit(f('от продавца: Тестов Т. · ЛПР со слов продавца') == 'от менеджера по продажам: Тестов Т. · ЛПР со слов менеджера по продажам'
                 and f('Продавцами') == 'Менеджерами по продажам' and f(None) is None and f('') == ''
                 and f('продажи, продавать') == 'продажи, продавать', 'фильтр menedzher: падежи, None, «продажи»/«продавать» не трогает')
        proverit('от менеджера по продажам: Тестов Т.' in kart_sinn and 'со слов продавца' not in kart_sinn,
                 'карточка %s: пробный номер – «от менеджера по продажам», «со слов продавца» не видно' % SINN)
    for s in itog['stranicy']:
        if s['kto'] == 'sales' and s['imya'] in ('stats', 'csv'):
            proverit(s['kod'] == 403, 'менеджер: %s закрыта, как и раньше (%s)' % (s['imya'], s['kod']))
        elif s['imya'] in ('park', 'park_inn', 'spisok_park', 'admin'):
            pass                                   # сравниваются «до/после» снаружи
        else:
            proverit(s['kod'] == 200, '%s %s %s: %s' % (s['kto'], s['imya'], s['params'] or '', s['kod']))
    for p in (test_sales, test_kat):
        try:
            os.remove(p)
        except OSError:
            pass
    return itog


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    koren_app, metka = sys.argv[i + 1], sys.argv[i + 2]
    itog = render(koren_app, metka, '--polnyy' in sys.argv)
    io.open(os.path.join(DROP, 'fixM_render_%s.json' % metka), 'w', encoding='utf-8').write(
        json.dumps(itog, ensure_ascii=False, indent=1))
    print('ПЛОХИХ ПРОВЕРОК: %d' % itog['plohih'])
    raise SystemExit(0)

SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')


def zapustit_render(koren_app, metka, dop=()):
    r = subprocess.run([VENV, os.path.abspath(__file__), '--render', koren_app, metka] + list(dop),
                       capture_output=True, timeout=1500, cwd=KOREN, env=SREDA)
    vyvod = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-4000:]
    try:
        itog = json.loads(io.open(os.path.join(DROP, 'fixM_render_%s.json' % metka), encoding='utf-8').read())
    except Exception:  # noqa: BLE001
        itog = None
    return r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod, vyvod, itog


def sravnit(do, posle):
    """Коды страниц «до» и «после» совпадают; видимых «продавец/…» после – 0."""
    plohie, stroki = [], []
    kody_do = {(s['kto'], s['imya']): s for s in (do or {}).get('stranicy', [])}
    for s in posle['stranicy']:
        d = kody_do.get((s['kto'], s['imya']))
        stroki.append('%-6s %-18s код %s -> %s; видимых «продавец…»: %s -> %s' % (
            s['kto'], s['imya'], d['kod'] if d else '?', s['kod'], d['prodavec_vidno'] if d else '?', s['prodavec_vidno']))
        if d and d['kod'] != s['kod']:
            plohie.append('код %s %s: %s -> %s' % (s['kto'], s['imya'], d['kod'], s['kod']))
        if s['prodavec_vidno']:
            plohie.append('видно «продавец…» %s %s: %s' % (s['kto'], s['imya'], s['gde'][:3]))
    return plohie, stroki


def zhurnal_v_fajl(zhurnal, imya):
    rows = [{'fajl': f, 'stroka': n, 'bylo': a, 'stalo': b, 'itog': it, 'chto': c} for f, n, a, b, it, c in zhurnal]
    io.open(os.path.join(DROP, imya), 'w', encoding='utf-8').write(json.dumps(rows, ensure_ascii=False, indent=1))


# ====================================================================== СУХОЙ ПРОГОН (без замка)
if '--suho' in sys.argv:
    teksty = prochitat(APP)
    novye, zhurnal, ok = nalozhit(teksty)
    zhurnal_v_fajl(zhurnal, 'fixM_inventar_suho.json')
    sch = {}
    for f, n, a, b, it, c in zhurnal:
        sch.setdefault(f, {}).setdefault(it, 0)
        sch[f][it] += 1
    for f in sorted(sch):
        print('   %-36s %s' % (f, sch[f]))
    plohie_ya = [x for x in zhurnal if x[4].startswith('ЯКОРЬ')]
    for x in plohie_ya:
        print('   ЯКОРЬ НЕ НАЙДЕН: %s %r' % (x[0], x[2][:90]))
    if not ok:
        raise SystemExit(1)
    sdelat_stage(novye)
    g1, v1, do = zapustit_render(KOREN, 'do')
    g2, v2, posle = zapustit_render(STAGE, 'posle', ['--polnyy'] if '--polnyy' in sys.argv else [])
    print('до: %s' % v1.strip()[-300:])
    print('после: %s' % v2.strip()[-1500:])
    if posle:
        plohie, stroki = sravnit(do, posle)
        for s in stroki:
            print('   ' + s)
        for p in posle['proverki']:
            print('   ' + p)
        if 'obhod' in posle:
            ob = posle['obhod']
            print('   обход карточек: %d, не 200: %s, с «продав…» в видимом тексте: %d' % (ob['kart'], ob['ne200'][:5], len(ob['prodav'])))
            for inn, h in list(ob['prodav'].items())[:8]:
                print('      %s: %s' % (inn, h[:2]))
        print('НЕСОВПАДЕНИЙ/ОСТАТКОВ: %d %s' % (len(plohie), plohie[:6]))
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
    BEKAP = os.path.join(KOREN, '_bekap', time.strftime('fixM-%Y%m%d-%H%M%S'))
    vzyat_zamok('fixM (менеджер по продажам)')
    try:
        teksty = prochitat(APP)
        novye, zhurnal, ok = nalozhit(teksty)
        zhurnal_v_fajl(zhurnal, 'fixM_inventar.json')
        for f, n, a, b, it, c in zhurnal:
            if it != 'ок':
                print('   [%s] %s %r' % (it, f, a[:80]))
        print('правок: ок %d, уже %d, всего %d' % (sum(x[4] == 'ок' for x in zhurnal), sum(x[4] == 'уже' for x in zhurnal), len(zhurnal)))
        if not ok:
            print('ЯКОРЯ НЕ НАЙДЕНЫ – ничего не записано')
            raise SystemExit(1)
        izm = [f for f in FAJLY if novye[f] != teksty[f]]
        os.makedirs(BEKAP, exist_ok=True)
        for f in izm:
            os.makedirs(os.path.dirname(os.path.join(BEKAP, f)), exist_ok=True)
            shutil.copy2(os.path.join(APP, f), os.path.join(BEKAP, f))
        print('бэкап: %s; меняются: %s' % (BEKAP, ', '.join(izm)))
        if not izm:
            raise SystemExit(0)
        g0, v0, do = zapustit_render(KOREN, 'primenit_do')
        sdelat_stage(novye)
        g1, v1, proverka = zapustit_render(STAGE, 'primenit')
        plohie, stroki = sravnit(do, proverka) if proverka else (['нет итога'], [])
        if not g1 or plohie:
            print('ПРОВЕРКА НА КОПИИ НЕ ПРОШЛА – живые файлы не тронуты')
            print(v1[-2500:])
            print(plohie[:8])
            raise SystemExit(1)
        py = [f for f in izm if f.endswith('.py')]
        if py:
            ostanovit()
            zapisat(APP, novye, izm)
            kod = zapustit('исправитель M: менеджер по продажам')
        else:
            zapisat(APP, novye, izm)
            import urllib.request
            try:
                kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            except Exception as e:  # noqa: BLE001
                kod = str(e)[:80]
        print('записано, перезапуск: %s, вход: %s' % ('да' if py else 'нет', kod))
        g2, v2, posle = zapustit_render(KOREN, 'posle_zhivoy')
        plohie2, stroki2 = sravnit(do, posle) if posle else (['нет итога'], [])
        if kod != 200 or not g2 or plohie2:
            for f in izm:
                shutil.copy2(os.path.join(BEKAP, f), os.path.join(APP, f))
            if py:
                ostanovit()
                kod = zapustit('исправитель M: ОТКАТ')
            print('ПОСЛЕ ЗАПИСИ ПЛОХО – свои файлы возвращены из %s, вход: %s' % (BEKAP, kod))
            print(v2[-2500:])
            print(plohie2[:8])
            raise SystemExit(1)
        for s in stroki2:
            print('   ' + s)
        for p in posle['proverki']:
            print('   ' + p)
        print('ГОТОВО: живые файлы проверены после перезапуска')
    finally:
        otdat_zamok()
