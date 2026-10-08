# -*- coding: utf-8 -*-
"""Одна шкала сегментов, «Отрасль» и единое написание регионов (владелец 08.10: «да»).

СЕГМЕНТ – шкала ТЗ («1 экспортёры … 6 ягоды»), ею размечены Базы 1–4. У Базы 6 были свои
названия («переработка молока», «мясокомбинаты»…) – они переводятся в шкалу ТЗ по основному
ОКВЭД тем же соответствием «ОКВЭД -> сегмент», что в самих файлах 2–4 (их колонка «Сегмент по
основному ОКВЭД», 61 код; для кода вне таблицы – по самому длинному совпадающему началу кода,
иначе раздел 10/11/46.3 – «3 пищевые»). Исходный сегмент сохраняется в segment_ishodnyy.
ОТРАСЛЬ – новое поле у всех компаний по основному ОКВЭД (молоко, сыры, мясо и птица, хлеб и
выпечка…): так детализация Базы 6 не теряется и есть у всех баз. Фильтр, колонка, срез.
РЕГИОН – официальное название субъекта («г Москва», «Москва» -> «Москва»; «Белгородская обл» ->
«Белгородская область»; город вместо региона -> его регион). Исходное – в region_ishodnyy.
Часовой пояс пересчитывается по новому написанию.
Скрипт повторяемый: после следующей заливки его можно прогнать ещё раз.
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
T = os.path.join(APP, 'templates')
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'

OKVED_TZ = json.loads(r'''__OKVED_TZ__''')  # перед запуском подставляется seo-texts/okved_segment_tz.json

OTRASLI = [  # (начало кода, отрасль) – самое длинное совпадение побеждает
    ('10.11', 'мясо и птица'), ('10.12', 'мясо и птица'), ('10.13', 'мясо и птица'),
    ('10.2', 'рыба и морепродукты'), ('10.3', 'овощи, фрукты, ягоды, орехи'), ('10.4', 'масла и жиры'),
    ('10.51.4', 'сыры'), ('10.5', 'молоко и мороженое'), ('10.61', 'мука, крупы, зерно'), ('10.62', 'крахмал'),
    ('10.71', 'хлеб и выпечка'), ('10.72', 'печенье, сухари, мучные кондитерские'), ('10.73', 'макароны'),
    ('10.81', 'сахар'), ('10.82', 'кондитерские изделия'), ('10.83', 'чай и кофе'),
    ('10.84', 'специи, соусы, соль'), ('10.85', 'готовая еда'), ('10.86', 'детское и диетическое питание'),
    ('10.89', 'прочие пищевые продукты'), ('10.9', 'корма'), ('11', 'напитки'),
    ('52.10', 'зерно, семена, элеваторы'), ('46.21', 'зерно, семена, элеваторы'), ('01.1', 'зерно, семена, элеваторы'),
    ('01.6', 'зерно, семена, элеваторы'), ('01.2', 'сады, ягоды, орехи'), ('01.4', 'животноводство'),
    ('01', 'сельское хозяйство'), ('46.3', 'оптовая торговля продуктами'), ('46', 'оптовая торговля'),
    ('47', 'розничная торговля'),
]

REGIONY = [  # (регулярка по нижнему регистру, официальное название) – порядок важен
    (r'санкт|петербург', 'Санкт-Петербург'), (r'севастопол', 'Севастополь'),
    (r'(?<![а-яё])москв', 'Москва'), (r'московск', 'Московская область'),
    (r'ленинградск', 'Ленинградская область'),
    (r'ханты|югра|нижневартовск|сургут', 'Ханты-Мансийский автономный округ – Югра'),
    (r'ямало', 'Ямало-Ненецкий автономный округ'), (r'ненецк', 'Ненецкий автономный округ'),
    (r'чукот', 'Чукотский автономный округ'), (r'еврейск', 'Еврейская автономная область'),
    (r'республика алтай|респ\w*\.? алтай|алтай респ', 'Республика Алтай'), (r'алтайск', 'Алтайский край'),
    (r'адыге', 'Республика Адыгея'), (r'башкор|(?<![а-яё])уфа', 'Республика Башкортостан'),
    (r'бурят', 'Республика Бурятия'), (r'дагестан', 'Республика Дагестан'), (r'ингуш', 'Республика Ингушетия'),
    (r'кабардин', 'Кабардино-Балкарская Республика'), (r'калмык', 'Республика Калмыкия'),
    (r'карачаев', 'Карачаево-Черкесская Республика'), (r'карел|рауталахти', 'Республика Карелия'),
    (r'(?<![а-яё])коми(?![а-яё])', 'Республика Коми'), (r'крым', 'Республика Крым'),
    (r'марий', 'Республика Марий Эл'), (r'мордов', 'Республика Мордовия'),
    (r'сахалин', 'Сахалинская область'), (r'саха|якут', 'Республика Саха (Якутия)'),
    (r'осетия', 'Республика Северная Осетия – Алания'), (r'татарстан|казань|мамадыш', 'Республика Татарстан'),
    (r'(?<![а-яё])тыва|(?<![а-яё])тува', 'Республика Тыва'), (r'удмурт|ижевск', 'Удмуртская Республика'),
    (r'хакас', 'Республика Хакасия'), (r'чечен|мескер', 'Чеченская Республика'),
    (r'чуваш|чебоксар|пархикас', 'Чувашская Республика'),
    (r'донецк', 'Донецкая Народная Республика'), (r'луганск', 'Луганская Народная Республика'),
    (r'забайкал|(?<![а-яё])чита', 'Забайкальский край'), (r'камчат', 'Камчатский край'),
    (r'краснодар|кубан', 'Краснодарский край'), (r'краснояр', 'Красноярский край'),
    (r'(?<![а-яё])перм', 'Пермский край'), (r'примор|владивосток', 'Приморский край'),
    (r'ставропол', 'Ставропольский край'), (r'хабаров', 'Хабаровский край'),
    (r'амурск', 'Амурская область'), (r'архангел', 'Архангельская область'), (r'астрахан', 'Астраханская область'),
    (r'белгород', 'Белгородская область'), (r'брянск', 'Брянская область'), (r'владимир', 'Владимирская область'),
    (r'волгоград', 'Волгоградская область'), (r'вологод|череповец', 'Вологодская область'),
    (r'воронеж', 'Воронежская область'), (r'запорож', 'Запорожская область'), (r'иванов', 'Ивановская область'),
    (r'иркут', 'Иркутская область'), (r'калининград', 'Калининградская область'),
    (r'калуж|кондрово', 'Калужская область'), (r'кемеров|кузбас', 'Кемеровская область – Кузбасс'),
    (r'(?<![а-яё])киров', 'Кировская область'), (r'костром', 'Костромская область'), (r'курган', 'Курганская область'),
    (r'(?<![а-яё])курск', 'Курская область'), (r'липец', 'Липецкая область'), (r'магадан', 'Магаданская область'),
    (r'мурман', 'Мурманская область'), (r'нижегород|нижн\w* новгород', 'Нижегородская область'),
    (r'новгород', 'Новгородская область'), (r'новосиб', 'Новосибирская область'),
    (r'(?<![а-яё])омск', 'Омская область'), (r'оренбург', 'Оренбургская область'),
    (r'орловск|(?<![а-яё])ор[её]л(?![а-яё])', 'Орловская область'), (r'пенз|сурск', 'Пензенская область'),
    (r'псков', 'Псковская область'), (r'ростов', 'Ростовская область'), (r'рязан', 'Рязанская область'),
    (r'самар', 'Самарская область'), (r'саратов', 'Саратовская область'),
    (r'свердлов|екатеринбург', 'Свердловская область'), (r'смолен', 'Смоленская область'),
    (r'тамбов', 'Тамбовская область'), (r'твер|старица', 'Тверская область'),
    (r'(?<![а-яё])томск', 'Томская область'), (r'(?<![а-яё])туль|(?<![а-яё])тула(?![а-яё])', 'Тульская область'),
    (r'тюмен', 'Тюменская область'), (r'ульянов', 'Ульяновская область'), (r'херсон', 'Херсонская область'),
    (r'челябин', 'Челябинская область'), (r'ярослав', 'Ярославская область'),
]

POYASA = [
    (2, ('калининград',)), (12, ('камчат', 'чукот')), (11, ('магадан', 'сахалин')),
    (10, ('хабаровск', 'приморск', 'владивосток', 'еврейск')),
    (9, ('забайкаль', 'чита', 'читин', 'амурск', 'якут', 'саха (')), (8, ('иркут', 'бурят')),
    (7, ('новосиб', 'томск', 'кемеров', 'кузбас', 'алтай', 'краснояр', 'хакас', 'тыва')), (6, ('омск',)),
    (5, ('башкорт', 'уфа', 'оренбург', 'перм', 'свердлов', 'екатеринбург', 'челябин', 'курган',
         'тюмен', 'ханты', 'югра', 'ямал')),
    (4, ('самар', 'саратов', 'ульянов', 'астрахан', 'удмурт', 'ижевск')),
]


def s_nachala(slovo, tekst):
    return re.search(r'(?<![а-яё])' + re.escape(slovo), tekst) is not None


def poyas(region):
    r = (region or '').casefold()
    for smeshch, slova in POYASA:
        if any(s_nachala(sl, r) for sl in slova):
            return smeshch, 'по региону'
    if not r:
        return 3, 'по Москве: регион не указан'
    if any(re.search(rx, r) for rx, _ in REGIONY):
        return 3, 'по региону'
    return 3, 'по Москве: регион не распознан'


def region_norm(raw):
    r = (raw or '').strip().lower()
    if not r:
        return ''
    for rx, imya in REGIONY:
        if re.search(rx, r):
            return imya
    return (raw or '').strip()


def po_kodu(kod, tablica):
    kod = (kod or '').strip()
    luchshiy = ''
    for nachalo in tablica:
        if (kod == nachalo or kod.startswith(nachalo + '.') or (len(nachalo) <= 2 and kod.startswith(nachalo))) \
                and len(nachalo) > len(luchshiy):
            luchshiy = nachalo
    return luchshiy


def segment_tz(kod):
    k = po_kodu(kod, OKVED_TZ)
    if k:
        return OKVED_TZ[k]
    if re.match(r'(10|11)\.|46\.3', kod or ''):
        return '3 пищевые'
    return ''


def otrasl(kod):
    # отрасли заданы началом кода («10.5» – молоко: ловит 10.51, 10.52…): самое длинное начало побеждает
    kod = (kod or '').strip()
    luchshee = max((n for n, _ in OTRASLI if kod.startswith(n)), key=len, default='')
    return dict(OTRASLI)[luchshee] if luchshee else 'прочее'


TZ = re.compile(r'^\d ')

# ====================================================================== проверка
if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import collections
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
    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    rows = k.execute('select inn, segment, otrasl, region, region_ishodnyy, segment_ishodnyy, chas_poyas, bazy from company').fetchall()
    ne_tz = [r for r in rows if not all(TZ.match(x.strip()) for x in (r[1] or '').split('|') if x.strip())]
    proverit(not ne_tz, 'сегменты только по шкале ТЗ (вне шкалы: %d %s)' % (len(ne_tz), [r[1] for r in ne_tz[:5]]))
    proverit(all(r[2] for r in rows), 'отрасль у всех: %d' % sum(1 for r in rows if r[2]))
    reg = collections.Counter(r[3] for r in rows)
    print('      регионов было %d, стало %d; не распознано: %s' % (
        len({r[4] for r in rows}), len(reg), sorted({r[3] for r in rows if r[3] and r[3] not in dict(REGIONY).values()})))
    kros = collections.Counter((r[5], r[2]) for r in rows if r[5])
    print('      База 6: прежний сегмент -> отрасль: %s' % sorted(kros.items(), key=lambda x: -x[1])[:10])
    print('      отрасли: %s' % collections.Counter(r[2] for r in rows).most_common())
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}

    def chislo(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1
    with TestClient(vnutr) as kl:
        t = kl.get(PUT + '/centro').text
        proverit('name="otrasl"' in t, 'фильтр «Отрасль» на главной')
        opcii = re.findall(r'<select name="segment"[^>]*>(.*?)</select>', t, re.S)
        proverit(opcii and 'переработка молока' not in opcii[0], 'в фильтре «Сегмент» одна шкала')
        for o_, n_ in collections.Counter(r[2] for r in rows).most_common(4):
            proverit(chislo(kl.get(PUT + '/centro', params={'otrasl': o_}).text) == n_, 'отрасль «%s»: %d' % (o_, n_))
        for r_, n_ in reg.most_common(3):
            proverit(chislo(kl.get(PUT + '/centro', params={'region': r_}).text) == n_, 'регион «%s»: %d' % (r_, n_))
        st = kl.get(PUT + '/centro/stats?stat_ot=2026-10-01')
        proverit(st.status_code == 200 and '<h3>Отрасль' in st.text, 'статистика: срез «Отрасль»')
        inn6 = next(r[0] for r in rows if r[5])
        o = kl.get(PUT + '/centro?inn=' + inn6)
        proverit(o.status_code == 200 and '<b>Отрасль</b>' in o.text, 'карточка: отрасль в шапке')
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ====================================================================== данные
B = os.path.join(KOREN, '_bekap', time.strftime('segmenty-regiony-%Y%m%d-%H%M%S'))
os.makedirs(B, exist_ok=True)
k = sqlite3.connect(KAT)
d = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
k.backup(d)
d.close()
kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
for imya in ('otrasl', 'segment_ishodnyy', 'region_ishodnyy'):
    if imya not in kol:
        k.execute('ALTER TABLE company ADD COLUMN %s TEXT' % imya)
n_seg = n_reg = n_poyas = 0
for inn, segm, okv, reg, reg_ish, seg_ish, poyas_star in k.execute(
        'select inn, segment, okved, region, region_ishodnyy, segment_ishodnyy, chas_poyas from company').fetchall():
    obnov = {'otrasl': otrasl(okv)}
    chasti = [x.strip() for x in (segm or '').split('|') if x.strip()]
    if chasti and not all(TZ.match(x) for x in chasti):
        tz = segment_tz(okv)
        obnov.update({'segment': tz, 'segment_osn': tz, 'segment_ishodnyy': seg_ish or segm})
        n_seg += 1
    ish = reg_ish or reg or ''
    nov = region_norm(ish)
    obnov['region_ishodnyy'] = ish
    if nov != (reg or ''):
        obnov['region'] = nov
        n_reg += 1
    sm, kak = poyas(nov)
    if sm != poyas_star:
        n_poyas += 1
    obnov['chas_poyas'], obnov['chas_poyas_kak'] = sm, kak
    k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % kk for kk in obnov), list(obnov.values()) + [inn])
k.commit()
print('данные: сегмент переведён в шкалу ТЗ у %d, регион выровнен у %d, пояс изменился у %d' % (n_seg, n_reg, n_poyas))

# ====================================================================== код и шаблоны
log = []
nado = sdelano = 0


def pravka(p, staro, novo, imya, priznak):
    global nado, sdelano
    nado += 1
    t = io.open(p, encoding='utf-8').read()
    if priznak in t:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    if t.count(staro) != 1:
        log.append('[ЯКОРЬ: %d] %s' % (t.count(staro), imya))
        return
    b = os.path.join(B, os.path.basename(p))
    if not os.path.exists(b):
        shutil.copy2(p, b)
    io.open(p, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    sdelano += 1
    log.append('[ок] ' + imya)


pravka(RCS, '''        if segment and segment not in [s.strip() for s in str(company.get("segment") or "").split("|")]:
            continue
''', '''        if segment and segment not in [s.strip() for s in str(company.get("segment") or "").split("|")]:
            continue
        otrasl_f = params.get("otrasl", "").strip()        # отрасль по основному ОКВЭД
        if otrasl_f and str(company.get("otrasl") or "") != otrasl_f:
            continue
''', 'фильтр: отрасль', 'otrasl_f = params.get("otrasl"')
pravka(RCS, '''    choices["segment"] = sorted(счёт_сегм.items())
''', '''    choices["segment"] = sorted(счёт_сегм.items())
    _otr: dict = {}
    for company in vidimye_vladeltsu:
        if company.get("otrasl"):
            _otr[company["otrasl"]] = _otr.get(company["otrasl"], 0) + 1
    choices["otrasl"] = sorted(_otr.items(), key=lambda x: -x[1])
''', 'счётчики отраслей', 'choices["otrasl"] = sorted(')
pravka(RCS, '''_RAZREZY = (("segment", "Сегмент", "segment"), ''', '''_RAZREZY = (("segment", "Сегмент", "segment"), ("otrasl", "Отрасль", "otrasl"), ''',
       'статистика: срез «Отрасль»', '("otrasl", "Отрасль", "otrasl")')
pravka(RCS, '''        elif pole == "bitrix":
            v = ["да" if row.get("bitrix_kc") else "нет"]''', '''        elif pole == "otrasl":
            v = [str(row.get("otrasl") or "").strip()] if str(row.get("otrasl") or "").strip() else []
        elif pole == "bitrix":
            v = ["да" if row.get("bitrix_kc") else "нет"]''', 'статистика: значения отрасли', 'elif pole == "otrasl":')
C = os.path.join(T, 'centro.html')
pravka(C, '''  <select name="perezvon" title=''', '''  {% if choices.otrasl %}<select name="otrasl" title="Отрасль по основному ОКВЭД"><option value="">Все отрасли</option>{% for value, n in choices.otrasl %}<option value="{{ value }}" {% if request.query_params.get('otrasl') == value %}selected{% endif %}>{{ value }} – {{ n }}</option>{% endfor %}</select>{% endif %}
  <select name="perezvon" title=''', 'главная: фильтр «Отрасль»', '<select name="otrasl" title="Отрасль по основному ОКВЭД">')
pravka(C, '''          <label>Роль ЛПР<select name="rol_lpr">''', '''          <label>Отрасль<select name="otrasl"><option value="">Любая</option>{% for value, n in choices.otrasl %}<option value="{{ value }}" {% if request.query_params.get('otrasl') == value %}selected{% endif %}>{{ value }} – {{ n }}</option>{% endfor %}</select></label>
          <label>Роль ЛПР<select name="rol_lpr">''', 'все фильтры: «Отрасль»', '<label>Отрасль<select name="otrasl">')
pravka(C, '''{% if company.segment %}<span><b>Сегмент</b> {{ company.segment|replace(' | ', ', ') }}</span>{% endif %}''',
       '''{% if company.segment %}<span><b>Сегмент</b> {{ company.segment|replace(' | ', ', ') }}</span>{% endif %}{% if company.otrasl %}<span><b>Отрасль</b> {{ company.otrasl }}</span>{% endif %}''',
       'карточка: отрасль', '<span><b>Отрасль</b> {{ company.otrasl }}</span>')
L = os.path.join(T, '_ochered_spisok.html')
pravka(L, '''<td>{{ (c.segment or '–')|replace(' | ', ', ') }}</td>''',
       '''<td>{{ (c.segment or '–')|replace(' | ', ', ') }}{% if c.otrasl %}<br><span class="tiho">{{ c.otrasl }}</span>{% endif %}</td>''',
       'список: отрасль под сегментом', "{% if c.otrasl %}<br><span class=\"tiho\">{{ c.otrasl }}</span>")
for x in log:
    print('   ' + x)
print('правок: %d из %d; бэкап %s' % (sdelano, nado, B))
if sdelano != nado:
    print('НЕ ВСЕ ПРАВКИ – перезапуск не делаю')
    raise SystemExit(1)
sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: сегменты, отрасль, регионы %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg, stderr=subprocess.STDOUT,
                 creationflags=0x00000008 | 0x00000200, close_fds=True, env=sreda)
time.sleep(10)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True, timeout=900, cwd=KOREN, env=sreda)
print(r.stdout.decode('utf-8', 'replace')[-3500:])
if r.returncode:
    print(r.stderr.decode('utf-8', 'replace')[-2500:])
