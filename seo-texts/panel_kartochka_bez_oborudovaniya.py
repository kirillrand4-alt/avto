# -*- coding: utf-8 -*-
"""Карточка Meyer без компрессорных блоков + исправление часовых поясов.

1. Владелец: «вот это полностью убери из карточек компаний, оно лишнее для мейера» —
   «Оборудование — что уже известно», «Компрессоры этой компании — характеристики»,
   «Сводка по оборудованию». Плюс «Фактов N» в шапке карточки: у Meyer фактов о машинах
   нет, а «1» там — заглушка, собранная из полей компании (в ней даже всплывала
   расшифровка балла под видом «чем доказано»). Прячется тем же признаком, что и
   компрессорные фильтры: choices.est_oborudovanie — есть ли у базы данные об
   оборудовании вообще. У Meyer нет, у центробежной базы блоки вернулись бы сами.

2. Часовые пояса. Независимая таблица поймала ошибку: «Костромская область» получила +6
   как Омск — «Костр-ОМСК-ая» содержит «омск». Ключевые слова теперь сравниваются только
   С НАЧАЛА СЛОВА: «Омская» совпадает, «Костромская» и «Томская» — нет. И «Московская
   область» попадала в «регион не распознан»: в списке было «москв», а в слове «москов».
   Пояс у неё был верный (+3), неверной была пометка.
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
T = os.path.join(KOREN, 'app', 'templates')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
PORT = 8016
PUT = '/obzvon-meyer'
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('bez-oborud-%Y%m%d-%H%M%S'))

POYASA = [
    (2, ('калининград',)),
    (12, ('камчат', 'чукот')),
    (11, ('магадан', 'сахалин')),
    (10, ('хабаровск', 'приморск', 'владивосток', 'еврейск')),
    (9, ('забайкаль', 'чита', 'читин', 'амурск', 'якут', 'саха')),
    (8, ('иркут', 'бурят')),
    (7, ('новосиб', 'томск', 'кемеров', 'кузбас', 'алтай', 'краснояр', 'хакас', 'тыва')),
    (6, ('омск',)),
    (5, ('башкорт', 'уфа', 'оренбург', 'перм', 'свердлов', 'екатеринбург', 'челябин', 'курган',
         'тюмен', 'ханты', 'югра', 'ямал')),
    (4, ('самар', 'саратов', 'ульянов', 'астрахан', 'удмурт', 'ижевск')),
]
EVROPA = ('москв', 'москов', 'петербург', 'ленинград', 'владимир', 'волгоград', 'вологод', 'воронеж',
          'киров', 'костром', 'краснодар', 'курск', 'нижегород', 'рязан', 'тамбов', 'туль', 'ярослав',
          'калмык', 'крым', 'севастопол', 'татарстан', 'ставропол', 'твер', 'пенз', 'мордов', 'чуваш',
          'марий', 'белгород', 'брянск', 'калуж', 'липец', 'орлов', 'смолен', 'иванов', 'мурман', 'карел',
          'коми', 'архангел', 'ненец', 'новгород', 'псков', 'ростов', 'адыге', 'дагестан', 'ингуш',
          'кабардин', 'карачаев', 'осетия', 'чечен')


def s_nachala(slovo, tekst):
    """Слово стоит С НАЧАЛА слова в тексте: «омск» есть в «омская», но не в «костромская»."""
    return re.search(r'(?<![а-яё])' + re.escape(slovo), tekst) is not None


def poyas(region):
    r = (region or '').casefold()
    for smeshch, slova in POYASA:
        if any(s_nachala(s, r) for s in slova):
            return smeshch, 'по региону'
    if not r:
        return 3, 'по Москве: регион не указан'
    if any(s_nachala(s, r) for s in EVROPA):
        return 3, 'по региону'
    return 3, 'по Москве: регион не распознан'


NEZAV = {'Алтайский край': 7, 'Астраханская область': 4, 'Владимирская область': 3,
         'Волгоградская область': 3, 'Вологодская область': 3, 'Воронежская область': 3,
         'Забайкальский край': 9, 'Камчатский край': 12, 'Кировская область': 3,
         'Костромская область': 3, 'Краснодарский край': 3, 'Красноярский край': 7,
         'Курская область': 3, 'Ленинградская область': 3, 'Москва': 3, 'Московская область': 3,
         'Нижегородская область': 3, 'Новосибирская область': 7, 'Оренбургская область': 5,
         'Пермский край': 5, 'Республика Алтай': 7, 'Республика Башкортостан': 5,
         'Республика Калмыкия': 3, 'Республика Крым': 3, 'Республика Татарстан': 3,
         'Республика Хакасия': 7, 'Рязанская область': 3, 'Санкт-Петербург': 3,
         'Свердловская область': 5, 'Ставропольский край': 3, 'Старица': 3,
         'Тамбовская область': 3, 'Тульская область': 3, 'Удмуртская Республика': 4,
         'Ульяновская область': 4, 'Челябинская область': 5, 'Череповец': 3,
         'Ярославская область': 3}
# Контроль на регионы, которых в Базе 1 нет, но которые придут: ловушки подстрок
KONTROL = {'Омская область': 6, 'Томская область': 7, 'Костромская область': 3,
           'Республика Саха (Якутия)': 9, 'Курганская область': 5, 'Курская область': 3,
           'Ханты-Мансийский автономный округ — Югра': 5, 'Калининградская область': 2,
           'Приморский край': 10, 'Кемеровская область — Кузбасс': 7, 'Иркутская область': 8,
           'Самарская область': 4, 'Пензенская область': 3, 'Тверская область': 3}

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    k = sqlite3.connect(KAT)
    rows = k.execute('select region, chas_poyas, chas_poyas_kak from company').fetchall()
    neverno = [(r, p, NEZAV.get(r)) for r, p, _ in rows if p != NEZAV.get(r)]
    proverit(not neverno, 'пояса всех 65 компаний = независимой таблице %s' % (neverno or ''))
    nerasp = sorted({r for r, _, kak in rows if 'не распознан' in kak})
    proverit(nerasp == ['Старица', 'Череповец'], '«не распознан» только у городов вместо региона: %s' % nerasp)
    kontr = [(r, poyas(r)[0], p) for r, p in KONTROL.items() if poyas(r)[0] != p]
    proverit(not kontr, 'контроль на будущие регионы-ловушки (Омская/Томская/Костромская/Курская…) %s' % (kontr or ''))

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    inn = k.execute('select inn from company limit 1').fetchone()[0]
    with TestClient(vnutr) as kl:
        o = kl.get(PUT + '/centro?inn=' + inn)
    t = o.text
    proverit(o.status_code == 200, 'карточка открывается: %s' % o.status_code)
    for klass, imya in (('equipment-section', 'Оборудование — что уже известно'),
                        ('mashiny-section', 'Компрессоры этой компании — характеристики'),
                        ('summary-card', 'Сводка по оборудованию')):
        proverit('<section class="card %s"' % klass not in t, 'блока «%s» нет' % imya)
    proverit('<b>Фактов</b>' not in t, '«Фактов N» в шапке карточки нет')
    for nado in ('contacts-section', 'class="work-form"', 'Реквизиты и руководство', 'Деньги и деятельность'):
        proverit(nado in t, 'на месте: %s' % nado)
    io.open(r'C:\seostat\drop\drop-storage\centro2-karta-bez-oborud.html', 'w', encoding='utf-8').write(t)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

os.makedirs(BEKAP, exist_ok=True)
log = []

# ---------- 1. пояса заново
shutil.copy2(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
k = sqlite3.connect(KAT)
for inn, region in k.execute('select inn, region from company').fetchall():
    sm, kak = poyas(region)
    k.execute('UPDATE company SET chas_poyas=?, chas_poyas_kak=? WHERE inn=?', (sm, kak, inn))
k.commit()
k.close()
log.append('[ок] часовые пояса пересчитаны (слово с начала)')

# ---------- 2. карточка без компрессорных блоков
C = os.path.join(T, 'centro.html')
t = io.open(C, encoding='utf-8').read()
shutil.copy2(C, os.path.join(BEKAP, 'centro.html'))
for klass in ('equipment-section', 'mashiny-section', 'summary-card'):
    metka = '{# %s: только у баз с данными об оборудовании #}' % klass
    if metka in t:
        log.append('[уже] %s' % klass)
        continue
    m = list(re.finditer(r'(\n  <section class="card %s">.*?\n  </section>)' % re.escape(klass), t, re.S))
    if len(m) != 1:
        log.append('[ЯКОРЬ: %d] %s — не правлю' % (len(m), klass))
        continue
    t = (t[:m[0].start()] + '\n  {% if choices.est_oborudovanie %}' + metka + m[0].group(1)
         + '\n  {% endif %}' + t[m[0].end():])
    log.append('[ок] %s прячется, если у базы нет данных об оборудовании' % klass)
staro = '<span><b>Фактов</b> {{ facts|length }}</span>'
if '{% if choices.est_oborudovanie %}<span><b>Фактов</b>' in t:
    log.append('[уже] «Фактов» в шапке')
elif t.count(staro) == 1:
    t = t.replace(staro, '{% if choices.est_oborudovanie %}' + staro + '{% endif %}', 1)
    log.append('[ок] «Фактов» в шапке прячется')
else:
    log.append('[ЯКОРЬ: %d] «Фактов» — не правлю' % t.count(staro))
io.open(C, 'w', encoding='utf-8').write(t)
for x in log:
    print('   ' + x)
print('бэкап: %s' % BEKAP)

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: карточка без оборудования %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
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
