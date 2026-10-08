# -*- coding: utf-8 -*-
"""fixF2: план доводки данных контактов (повторная проверка панели Meyer 08.10).

Собирается ЛОКАЛЬНО по копии каталога (fixF2_vzyat.py) и сохранённым страницам (кэш агентов
C/D, страница shkxp.ru из проверки prov1). Номера телефонов в этом файле не пишутся: они
берутся из копии каталога и со страниц, а план с номерами кладётся только в scratchpad и на дроп.

    python3 fixF2_plan.py <каталог.db> <страницы-D> <страницы-C> <shkxp.html> <chey.json> <svyazi.json> <выход.json>

Что в плане (применяет fixF2_dannye.py на сервере, каждое значение – только если в живой базе
стоит то же, что было в копии):
  1. ШКХП 3524015320: номера и люди с shkxp.ru – «с сайта другого юрлица: АО «Шадринский КХП»
     (shkxp.ru)» с доказательством; описание (с того же сайта) – нейтральное по checko.
  2. Выбор Сибири 2225132970: «Владимир» – закупщик зерна (объявление «Закупаем пшеницу…»),
     «закупки сырья»; два номера «Офис» – подпись со страницы контактов.
  3. ПК Морошка 9723051780: номера со страницы – у менеджеров закупок грибов/ягод (Екатерина,
     Нелли), не у Плотникова; Плотников – ЛПР без телефона («спросить у приёмной», почта).
  4. Соседние юрлица по тому же юрадресу (Кардаильский КХП ↔ ТД КМЗ, Донецкий БКК ↔ БКК ГРУПП):
     метка «с сайта другого юрлица» снимается (прежняя – в chuzhoy_istochnik_ishodnyy), вместо неё
     svyaz_adres «сайт связанного юрлица (тот же адрес): …»; роль – обычная по подписи. У Кардаиля
     – добавочные руководителей и инженерной службы со страницы (тот же адрес). Альтаир ↔
     Альтаир-Про НЕ смягчается: другой дом (Софийская, 91 и 14) и другое дело (еда и лодки ПВХ).
  5. Дубли одного номера (тот же номер, добавочный и подпись) – rol_vruchnuyu «дубль номера».
  6. «Свой» сайт только по названию и городу – proverka_sayta «свой (по названию)» (прежнее – в
     proverka_sayta_ishodnaya): +5 балла E2 даёт только «свой»/«группа».
"""
import gzip
import html as H
import json
import re
import sqlite3
import sys

KAT, STR_D, STR_C, SHKXP, CHEY, SVYAZI, VYHOD = sys.argv[1:8]
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
indeks_d = json.load(open(STR_D + '/_indeks.json', encoding='utf-8'))
meta_c = json.load(open(STR_C + '/meta.json', encoding='utf-8'))
svyazi = json.load(open(SVYAZI, encoding='utf-8'))
VREMYA = '08.10.2026'


def tekst_html(t):
    t = re.sub(r'(?s)<(script|style)[^>]*>.*?</\1>', ' ', t)
    t = re.sub(r'<br\s*/?>|</(?:p|div|li|tr|td|h\d)>', '\n', t)
    t = H.unescape(re.sub(r'<[^>]+>', ' ', t))
    t = re.sub(r'[ \t\xa0]+', ' ', t)
    return re.sub(r'\n\s*\n+', '\n', t)


def stranica_d(url):
    z = indeks_d[url]
    return tekst_html(gzip.open(STR_D + '/' + z['fajl'], 'rt', encoding='utf-8', errors='replace').read())


def stranica_c(url):
    z = meta_c[url]
    return tekst_html(open(STR_C + '/' + z['fajl'], encoding='utf-8', errors='replace').read())


def cifry10(v):
    d = re.sub(r'\D', '', str(v or '').split('доб')[0])
    return d[-10:]


def kontakt(i):
    return dict(k.execute('SELECT * FROM contact WHERE id=?', (i,)).fetchone())


def kompaniya(inn):
    return dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())


plan = {'vremya': VREMYA, 'kontakty': [], 'lyudi': [], 'novye_lyudi': [], 'novye_kontakty': [], 'kompanii': [],
        'ozhid_rol': {}}


def izm_kontakt(c, novoe, pochemu, rol=None):
    """c – строка contact из копии; novoe – {поле: значение}; ozhid – прежние значения этих полей."""
    plan['kontakty'].append({'id': c['id'], 'inn': c['inn'], 'value': c['value'],
                             'ozhid': {p: c.get(p) for p in novoe}, 'novoe': novoe, 'pochemu': pochemu})
    if rol:
        plan['ozhid_rol']['k%s' % c['id']] = rol


def izm_chelovek(p, novoe, pochemu):
    plan['lyudi'].append({'id': p['id'], 'inn': p['inn'], 'person': p['person'],
                          'ozhid': {x: p.get(x) for x in novoe}, 'novoe': novoe, 'pochemu': pochemu})


def izm_kompaniya(c, novoe, pochemu):
    plan['kompanii'].append({'inn': c['inn'], 'ozhid': {p: c.get(p) for p in novoe}, 'novoe': novoe, 'pochemu': pochemu})


# ====================================================================== 1. ШКХП
INN = '3524015320'
st = tekst_html(open(SHKXP, encoding='utf-8', errors='replace').read())
assert 'АО ШКХП' in st and 'Шадринск' in st and 'Третьяков' in st, 'страница shkxp.ru не та'
kmp = kompaniya(INN)
assert 'Шексна' in kmp['adres']
ruk = (svyazi.get(INN) or {}).get('ruk') or {}
METKA_SHKXP = 'с сайта другого юрлица: АО «Шадринский КХП» (shkxp.ru)'
DOKAZ_SHKXP = ('shkxp.ru/contacts – сайт Шадринского комбината хлебопродуктов: в подвале «© 2026 АО ШКХП», адрес '
               '«г. Шадринск, ул. Труда 14» (Курганская обл.), раздел «Акционерам»; Третьяков Е. И. там – в «Отделе '
               'закупа сырья». ООО «ШКХП» (ИНН %s) – Вологодская обл., рп. Шексна, руководитель по checko %s; '
               'сайт компании в каталоге – sheksnakhp.ru (домен не открывается); страница https://shkxp.ru/contacts/ '
               '(проверено %s, fixF2)' % (INN, ruk.get('fio') or 'Гусев Д. П.', VREMYA))
for r in k.execute("SELECT * FROM contact WHERE inn=? AND source_url LIKE '%shkxp.ru%'", (INN,)).fetchall():
    c = dict(r)
    izm_kontakt(c, {'chuzhoy_istochnik': METKA_SHKXP, 'chuzhoy_dokaz': DOKAZ_SHKXP},
                'номер со страницы другого юрлица (Шадринский КХП), не ООО «ШКХП» (Шексна)', rol='с сайта другого юрлица')
for r in k.execute("SELECT * FROM person WHERE inn=? AND source_url LIKE '%shkxp.ru%'", (INN,)).fetchall():
    izm_chelovek(dict(r), {'chuzhoy_istochnik': METKA_SHKXP}, 'человек со страницы другого юрлица (Шадринский КХП)')
ok = (svyazi.get(INN) or {}).get('okved_osn') or [kmp['okved'], '']
uchr = [u['naim'] for u in (svyazi.get(INN) or {}).get('uchrediteli') or [] if u.get('vid') == 'org']


def dengi(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ''
    if v < 1e6:
        return ''
    return (('%.1f' % (v / 1e9)).replace('.', ',') + ' млрд руб.') if v >= 1e9 else (('%.1f' % (v / 1e6)).replace('.', ',') + ' млн руб.')


opis = '; '.join(x for x in (
    ('%s, ОКВЭД %s' % (ok[1], ok[0])) if ok[1] else ('ОКВЭД %s' % ok[0]),
    'юрадрес: %s' % kmp['adres'],
    ('выручка %s за %s г.' % (dengi(kmp['vyruchka_rub']), kmp['fin_god'])) if dengi(kmp['vyruchka_rub']) else '') if x) + ' (данные checko)'
if uchr:
    opis += '. Учредитель – %s (по checko).' % re.sub(r'"([^"]+)"', r'«\1»', uchr[0].replace('ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО ', 'ОАО '))
novoe_c = {'opisanie': opis}
if not kmp.get('opisanie_ishodnoe'):
    novoe_c['opisanie_ishodnoe'] = kmp['opisanie']
izm_kompaniya(kmp, novoe_c, 'описание было с сайта Шадринского КХП (мука овсяная/кукурузная, shkxp.ru) – заменено нейтральным по checko')

# ====================================================================== 2. Выбор Сибири
INN = '2225132970'
for r in k.execute('SELECT * FROM contact WHERE inn=?', (INN,)).fetchall():
    c = dict(r)
    fr = c.get('fragment') or ''
    if re.search(r'(?i)закупаем пшениц', fr) and 'Владимир' in fr and (c.get('person') or '') == 'Владимир':
        dolzh = 'Отдел закупа зерна (на сайте: «Закупаем пшеницу 3 и 4 класс! Звонить по телефону … Владимир»)'
        izm_kontakt(c, {'position': dolzh, 'podpis_stranicy': 'Отдел закупа; объявление «ЗАКУПАЕМ Пшеницу 4 класс!!!»'},
                    'закупщик зерна (объявление о закупке пшеницы), не ЛПР по оборудованию', rol='закупки сырья')
        for p in k.execute('SELECT * FROM person WHERE inn=? AND person=?', (INN, 'Владимир')).fetchall():
            izm_chelovek(dict(p), {'position': dolzh}, 'закупщик зерна (объявление о закупке пшеницы)')
# «Офис» – подпись со страницы контактов (номера без подписи)
st = stranica_c('https://пряниковъ.рф/kontakty') if 'https://пряниковъ.рф/kontakty' in meta_c else ''
if not st:
    fr = next(dict(r)['fragment'] for r in k.execute("SELECT fragment FROM contact WHERE inn=? AND fragment LIKE '%Офис%'", (INN,)))
    st = fr
ofis = set()
for m in re.finditer(r'(?i)офис\s*(?:\[tel:[^\]]*\])?\s*(\+?[78][\d\s()\-]{9,18}\d)', st):
    ofis.add(cifry10(m.group(1)))
for r in k.execute('SELECT * FROM contact WHERE inn=?', (INN,)).fetchall():
    c = dict(r)
    if cifry10(c['value']) in ofis and not (c.get('position') or '').strip():
        izm_kontakt(c, {'position': 'Офис', 'podpis_stranicy': 'Офис (страница «Контакты»)'},
                    'подпись номера на странице контактов – «Офис»', rol='общий номер')

# ====================================================================== 3. ПК Морошка
INN = '9723051780'
st = stranica_c('http://moroshka.ru/kontakty/')
m = re.search(r'Отдел закупок:\s*\n\s*(Менеджер отдела закупок \([^)]*\)):?\s*\n\s*(\w+):\s+(\w+):\s*\n\s*(\+7 \(\d{3}\) [\d-]{9})\s+(\+7 \(\d{3}\) [\d-]{9})\s*\n\s*(\S+@\S+)\s+(\S+@\S+)\s*\n\s*'
              r'Руководитель отдела закупок\s*:\s*\n\s*(\w+ \w+):\s*\n\s*(\S+@\S+)', st)
assert m, 'блок «Отдел закупок» на странице Морошки не разобран'
dolzh_m, imya1, imya2, tel1, tel2, pochta1, pochta2, ruk_fio, ruk_pochta = m.groups()
po_nomeru = {cifry10(tel1): (imya1, pochta1), cifry10(tel2): (imya2, pochta2)}
for r in k.execute('SELECT * FROM contact WHERE inn=?', (INN,)).fetchall():
    c = dict(r)
    kk = cifry10(c['value'])
    if kk in po_nomeru:
        imya, pochta = po_nomeru[kk]
        izm_kontakt(c, {'person': imya, 'position': dolzh_m,
                        'podpis_stranicy': 'Отдел закупок: %s: %s (%s). Руководитель отдела закупок %s – только почта %s'
                                           % (dolzh_m, imya, pochta, ruk_fio, ruk_pochta)},
                    'номер на странице – у менеджера закупок сырья %s (колонка «%s:»), не у руководителя отдела %s'
                    % (imya, imya, ruk_fio), rol='закупки сырья')
plan['novye_lyudi'].append({
    'inn': INN, 'person': ruk_fio, 'position': 'Руководитель отдела закупок', 'phone': '', 'email': ruk_pochta,
    'source_url': 'http://moroshka.ru/kontakty/',
    'source': 'страница сайта · разбор подписей 08.10 (fixF2): ЛПР без телефона на странице – спросить у приёмной',
    'sprosit_u_priemnoy': 'почта: %s' % ruk_pochta, 'ozhid_rol': 'снабжение'})

# ====================================================================== 4. соседние юрлица по тому же адресу
SOSEDI = {
    '3623007585': {
        'svyaz': 'сайт связанного юрлица (тот же адрес): ООО ТД «Кардаильский мукомольный завод» (ИНН 3623007578), kardail.ru',
        'dokaz': ('юрадрес тот же (Воронежская обл., с. Пески, ул. 2-я Советская, 1); генеральный директор КХП по checko '
                  'Трущелева И. С. на этой же странице – начальник юридического отдела ТД КМЗ (доб. 540): одна площадка, '
                  'номера – номера завода (проверено %s, fixF2)' % VREMYA),
    },
    '9303024328': {
        'svyaz': 'сайт связанного юрлица (тот же адрес): ООО «БКК ГРУПП» (ИНН 9303035680), bkkgrp.ru',
        'dokaz': ('юрадрес тот же (Донецк, ул. Кобозева, 5); на сайте – история того же Донецкого булочно-кондитерского '
                  'комбината; номера – номера комбината (проверено %s, fixF2)' % VREMYA),
    },
}
# ожидаемая роль после снятия метки – по подписи номера (проверка перед commit)
ROL_PO_PODPISI = {'Отдел снабжения': 'снабжение', 'Приемная': 'приёмная', 'Старший менеджер отдела продаж': 'продажи',
                  'Менеджер по продажам': 'продажи', 'Финансовый директор': 'бухгалтерия / финансы',
                  'Горячая линия, лаборатория мельницы': 'горячая линия', 'Коммерческая служба': 'продажи'}
for INN, z in SOSEDI.items():
    kmp = kompaniya(INN)
    for r in k.execute("SELECT * FROM contact WHERE inn=? AND TRIM(COALESCE(chuzhoy_istochnik,''))<>''", (INN,)).fetchall():
        c = dict(r)
        novoe = {'chuzhoy_istochnik': '', 'chuzhoy_istochnik_ishodnyy': c['chuzhoy_istochnik'], 'svyaz_adres': z['svyaz']}
        if not (c.get('vid_pochemu') or '').strip():
            novoe['vid_pochemu'] = z['svyaz'] + '; ' + z['dokaz']
        izm_kontakt(c, novoe, 'соседнее юрлицо по тому же юрадресу – не «чужой» сайт, а связанный: роль по подписи',
                    rol=ROL_PO_PODPISI.get((c.get('position') or '').strip()))
    izm_kompaniya(kmp, {'proverka_sayta': 'связанное юрлицо (тот же адрес)', 'proverka_sayta_ishodnaya': kmp['proverka_sayta']},
                  'сайт соседнего юрлица по тому же юрадресу')

# Кардаиль: подписи и добавочные со страницы «Реквизиты и контакты»
INN = '3623007585'
st = stranica_d('https://kardail.ru/contacts/')
assert 'ИНН: 3623007578' in st and 'Трущелева Ирина Сергеевна' in st
m = re.search(r'(\+7 \(\d{3}\) [\d-]{9})\s*-\s*Секретарь, приёмная директора', st)
osnovnoy = m.group(1)
for r in k.execute('SELECT * FROM contact WHERE inn=?', (INN,)).fetchall():
    c = dict(r)
    if cifry10(c['value']) == cifry10(osnovnoy) and not (c.get('position') or '').strip() and 'доб' not in c['value']:
        izm_kontakt(c, {'position': 'Секретарь, приёмная директора',
                        'podpis_stranicy': 'Реквизиты и контакты: «%s - Секретарь, приёмная директора»' % osnovnoy},
                    'подпись номера на странице «Реквизиты и контакты»', rol='приёмная')
OZHID_NOVYE = {'505': 'первое лицо', '577': 'первое лицо', '530': 'техдиректор / главный инженер',
               '535': 'главный механик / энергетик'}
LYUDI_K = [  # (ФИО, должность в карточке, добавочный, ручная роль или None, как на странице)
    ('Владисенко Александр Валерьевич', 'Генеральный директор ООО ТД «Кардаильский мукомольный завод»', '505', None,
     'Генеральный директор Владисенко Александр Валерьевич'),
    ('Эланукаев Яхъя Абумуслимович', 'Исполнительный директор ООО ТД «Кардаильский мукомольный завод»', '577', None,
     'Исполнительный директор Эланукаев Яхъя Абумуслимович'),
    ('Трущелева Ирина Сергеевна', 'Генеральный директор ООО «Кардаильский КХП» (по checko); на сайте ТД КМЗ – '
     'начальник юридического отдела', '540', 'первое лицо', 'Начальник юридического отдела Трущелева Ирина Сергеевна'),
    ('', 'Главный инженер', '530', None, 'Главный инженер'),
    ('Михайлов Юрий Александрович', 'Главный энергетик', '535', None, 'Главный энергетик Михайлов Юрий Александрович'),
]
for fio, dolzh, dob, ruch, na_str in LYUDI_K:
    i = st.find(na_str)
    assert i >= 0, na_str
    kusok = st[i:i + 160]
    assert re.search(r'доб\.\s*%s\b' % dob, kusok), (na_str, kusok)
    pochemu = ('добавочный %s со страницы «Реквизиты и контакты» kardail.ru (ООО ТД «Кардаильский мукомольный завод», '
               'тот же юрадрес, что у КХП): набрать %s (секретарь, приёмная директора) и добавочный' % (dob, osnovnoy))
    if dob == '530':
        pochemu += '; тот же добавочный 530 на странице указан и у отдела снабжения'
    plan['novye_kontakty'].append({
        'inn': INN, 'value': '%s доб. %s' % (re.sub(r'[()]', '', osnovnoy), dob), 'person': fio, 'position': dolzh,
        'source': 'страница сайта связанного юрлица (тот же адрес) · добавочный со страницы 08.10 (fixF2)',
        'source_url': 'https://kardail.ru/contacts/', 'fragment': re.sub(r'\s+', ' ', kusok)[:200],
        'svyaz_adres': SOSEDI[INN]['svyaz'], 'vid_pochemu': pochemu, 'rol_vruchnuyu': ruch,
        'podpis_stranicy': na_str, 'ozhid_rol': ruch or OZHID_NOVYE[dob]})

# ====================================================================== 5. дубли одного номера
import collections  # noqa: E402


def kl_dob(v):
    osn, _, dob = str(v or '').partition('доб')
    return cifry10(osn) + '#' + re.sub(r'\D', '', dob)


gr = collections.defaultdict(list)
for r in k.execute("SELECT * FROM contact WHERE kind='phone' ORDER BY id"):
    c = dict(r)
    if cifry10(c['value']):
        gr[(c['inn'], kl_dob(c['value']))].append(c)
for (inn, _), v in gr.items():
    if len(v) < 2:
        continue
    for c in v[1:]:
        p0 = v[0]
        if all((c.get(p) or '') == (p0.get(p) or '') for p in ('person', 'position', 'role', 'chuzhoy_istochnik')) \
                and not (c.get('rol_vruchnuyu') or '').strip():
            izm_kontakt(c, {'rol_vruchnuyu': 'дубль номера',
                            'vid_pochemu': 'тот же номер с тем же добавочным и той же подписью уже есть в карточке '
                                           '(контакт id %s) – запись задвоена при сборке' % p0['id']},
                        'дубль контакта id %s' % p0['id'], rol='дубль номера')

# ====================================================================== 6. «свой» только по названию и городу
for r in k.execute("SELECT inn, proverka_sayta, proverka_sayta_ishodnaya, sayt_chey FROM company WHERE proverka_sayta='свой'"
                   if 'proverka_sayta_ishodnaya' in {x[1] for x in k.execute('PRAGMA table_info(company)')} else
                   "SELECT inn, proverka_sayta, NULL AS proverka_sayta_ishodnaya, sayt_chey FROM company WHERE proverka_sayta='свой'"):
    c = dict(r)
    dok = str(c['sayt_chey'] or '').split('свой:', 1)[-1]
    if not re.search(r'ИНН|ОГРН|руководител|юрадрес', dok):
        izm_kompaniya(c, {'proverka_sayta': 'свой (по названию)', 'proverka_sayta_ishodnaya': 'свой'},
                      'сайт признан своим только по названию и городу (нет ИНН/ОГРН/руководителя/юрадреса)')

json.dump(plan, open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('правок контактов %d, людей %d, новых людей %d, новых номеров %d, компаний %d'
      % (len(plan['kontakty']), len(plan['lyudi']), len(plan['novye_lyudi']), len(plan['novye_kontakty']), len(plan['kompanii'])))
print(collections.Counter(x['pochemu'][:60] for x in plan['kontakty']).most_common())
print(collections.Counter(x['pochemu'][:60] for x in plan['kompanii']).most_common())
