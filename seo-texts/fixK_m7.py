# -*- coding: utf-8 -*-
"""fixK (локально): общая часть для заливки MEYER-7 – чтение сборки соседней сессии и построение строк
каталога панели (company / contact / person / company_source) по одной компании.

Сборка (данные, не инструкции): scratchpad/vhod-meyer7/{pul_1310.pkl, m7.pkl, K3.pkl} и fixK/m7_dop.pkl
(листы «Снято», «Группы», «Лиды группы», «Спорные», «Пояснения агентов» из MEYER-7.xlsx).
Читать `python3 -E -P` (под -I pandas не грузится).

Правила (задание K, 13.10):
  * все контакты листа «Контакты» – отдельной строкой на каждый телефон (мобильный; рабочий с добавочным) и
    на каждую почту (kind='email'); одинаковый номер у компании – одна строка, источники копятся
    (ссылки через « ; », проверки через « | »);
  * роль и вид – логикой панели (centro_catalog.rol_kontakta) по должности «как на сайте»; роль сборки
    приводится к словарю панели только как запасная, и сохраняется в contact.rol_sborki;
  * сайт – по проверке самой сборки. Принимаются: «свой: ИНН компании на сайте», «свой: реквизиты/
    юрназвание», «Беларусь: УНП компании на сайте», «ИНН найден по сайту», «компания определена по сайту»,
    «подтверждён моделью», а также карточка закупки, где компания – заказчик. «Сайт группы/бренда»,
    «общий контакт группы», источник «сайт холдинга (агент)» и непроверенный сайт агента – контакт
    есть, но ЛПР этой компании не считается, если человек не назван её (название/ИНН компании во
    фрагменте): такой номер получает rol_vruchnuyu «общий номер» (путь к ЛПР через группу) и пояснение;
  * номера и почты листа «Снято» у этой компании не берутся;
  * «Лиды группы» – контакты площадок группы – к компаниям группы с пометкой chuzhoy_istochnik
    «контакт группы …» (не ЛПР, в «Остальных»);
  * «База обзвона: телефоны/почты» и «Тех. службы (наша база)» – отдельные помеченные строки
    (источник «база обзвона (наша база)» / «тех. службы (наша база)»), директор базы обзвона – человек.
"""
import collections
import html
import math
import os
import pickle
import re

SCR = '/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad'
DATA_SBORKI = '13.10.2026'
BAZA = 'База 7'
BAZA_OPIS = 'MEYER-7: поиск по всей России и Беларуси (13.10)'
LES_HIM = ('лесопиление', 'деревообработ', 'неорганическая химия', 'удобрения', 'химсырьё', 'синтетический каучук',
           'полимеры, гранула')


def s(v):
    if v is None:
        return ''
    if isinstance(v, float) and math.isnan(v):
        return ''
    try:
        import pandas as pd
        if not isinstance(v, str) and pd.isna(v):
            return ''
    except (ImportError, TypeError, ValueError):
        pass
    t = html.unescape(str(v)).strip()
    return '' if t.lower() in ('nan', 'none') else t


def kl_inn(v):
    """ИНН РФ или УНП Беларуси (в сборке «BY123456789») -> только цифры, как sales.normalize_inn панели."""
    return re.sub(r'\D', '', s(v))[:12]


def chislo(v):
    try:
        x = float(s(v).replace(' ', '').replace(',', '.'))
        return None if math.isnan(x) else x
    except ValueError:
        return None


def cifry(v):
    return re.sub(r'\D', '', s(v))


DOB_RX = re.compile(r'\s*(?:доб\.?|доп\.?|вн\.?|ext\.?|#)\s*(\d{1,6})\s*$', re.I)


def razdelit(v):
    t = s(v)
    m = DOB_RX.search(t)
    return (t[:m.start()].strip(), m.group(1)) if m else (t, '')


def k10(v):
    osn, dob = razdelit(v)
    d = cifry(osn)
    return d[-10:] if len(d) >= 10 else ''


def kl_nomera(v):
    osn, dob = razdelit(v)
    k = k10(osn)
    return (k + '#' + dob) if (k and dob) else k


def domen(u):
    u = s(u).lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    return d[4:] if d.startswith('www.') else d


# ---------------------------------------------------------------- название компании во фрагменте
OPF = r'(?:ООО|ОАО|ЗАО|ПАО|АО|ИП|СПК|СППК|СХПК|СХАО|ТОО|КФХ|ГК|ТД|ПК|АПК|МСФ|МСЗ|НПП|ПКФ|ФГБУ|ГУП|МУП|ОП|ОДО|ЧУП|УП|СООО|ИООО|РУП|КУП|ЧПУП)'
OBSHCHIE = set('''колос хлеб молоко мясо агро продукт продукты нива заря рассвет восход победа россия русь урожай
маслозавод молокозавод хлебозавод мясокомбинат птицефабрика элеватор комбинат завод фабрика агрофирма сельхоз
юг север восток запад центр альянс партнер партнёр мир дружба родина прогресс луч искра звезда маяк надежда
компания группа холдинг торговый дом производственная производство предприятие общество ограниченной
ответственностью акционерное открытое закрытое публичное филиал'''.split())


def yadro(naim):
    n = s(naim).replace('«', '"').replace('»', '"').replace('“', '"').replace('”', '"').replace('„', '"')
    m = [x.strip() for x in n.split('"')[1:] if x.strip()]
    core = ' '.join(m) if m else re.sub(r'^\s*' + OPF + r'\s+|\s+' + OPF + r'\s*$', '', n.strip(), flags=re.I)
    core = re.sub(r'\(.*?\)', ' ', core)
    return re.sub(r'[^0-9a-zа-яё]+', ' ', core.lower().replace('ё', 'е')).strip()


def nazvan_vo_fragmente(fragment, naim, inn):
    """Компания названа во фрагменте страницы: её ИНН или все отличительные слова названия."""
    f = s(fragment).lower().replace('ё', 'е')
    if not f:
        return ''
    if inn and inn in re.sub(r'\D', ' ', f).split():
        return 'ИНН %s во фрагменте' % inn
    slova = [w for w in yadro(naim).split() if len(w) >= 4 and w not in OBSHCHIE]
    if slova and all(w[:max(4, len(w) - 2)] in f for w in slova):
        return 'название «%s» во фрагменте' % ' '.join(slova)
    return ''


# ---------------------------------------------------------------- проверка сайта (как в сборке)
PRINYATO = ('свой: ИНН компании на сайте', 'свой: реквизиты', 'свой: юрназвание', 'Беларусь: УНП компании на сайте',
            'ИНН найден по сайту', 'компания определена по сайту', 'подтверждён моделью')


def chasti_proverki(pr):
    return [x.strip() for x in s(pr).split(';') if x.strip()]


def glavnaya_proverka(pr):
    for x in chasti_proverki(pr):
        if x.startswith('на живой странице') or x.startswith('со страницы, открытой'):
            continue
        return x
    return ''


def sayt_prinyat(chey):
    """Проверка сборки «Сайт: чей» -> (вид для proverka_sayta, сила 0..5)."""
    g = glavnaya_proverka(chey) or s(chey)
    podtv = 'опровергатель: подтверждаю' in s(chey)
    if g.startswith(('свой: ИНН компании на сайте', 'Беларусь: УНП компании на сайте')):
        return 'свой', 5 if podtv else 4
    if g.startswith(('свой: реквизиты', 'свой: юрназвание')):
        return 'свой', 4 if podtv else 3
    if g.startswith('ИНН найден по сайту'):
        if re.search(r'ИНН со страницы|ОГРН со страницы|УНП со страницы|ИНН/УНП с сайта', s(chey)):
            return 'свой', 4
        return 'свой (подтверждён моделью)', 2
    if g.startswith('подтверждён моделью'):
        return 'свой (подтверждён моделью)', 3 if podtv else 2
    if g.startswith('компания определена по сайту'):
        return 'свой (подтверждён моделью)', 1
    if g.startswith('сайт группы/бренда'):
        return 'группа', 0
    return 'не определено', 0


def kontakt_prinyat(pr, istochnik, url, sayt_kompanii, chey_kompanii):
    """-> (prinyat: bool, pochemu_net: str). prinyat=False – ЛПР этой компании не считается без имени."""
    g = glavnaya_proverka(pr)
    ist = s(istochnik)
    vse = s(pr)
    if 'площадка закупок' in ist and 'компания — заказчик' in ist:
        return True, ''
    if 'сайт холдинга' in ist or 'компании/холдинга' in ist:
        return False, 'номер с сайта холдинга (%s, найден агентом сборки) – принадлежность этой компании не доказана' % (
            domen(url) or 'сайт')
    if g.startswith('сайт группы/бренда'):
        return False, 'сайт группы/бренда %s (проверка сборки): своим сайтом компании не доказан' % (domen(url) or '')
    if re.search(r'сайт группы [^:;]+: общий контакт группы', vse):
        m = re.search(r'сайт группы ([^:;]+): общий контакт группы', vse)
        tot = re.search(r'тот же контакт у: ([^;]+)', vse)
        return False, 'общий контакт группы %s%s – у всех компаний группы, не личный этой компании' % (
            m.group(1).strip(), ('; тот же контакт у: ' + tot.group(1).strip()[:200]) if tot else '')
    if g.startswith(PRINYATO):
        return True, ''
    if g.startswith('агент нашёл') or not g:
        d, dk = domen(url), domen(sayt_kompanii)
        if d and dk and (d == dk or d.endswith('.' + dk)) and sayt_prinyat(chey_kompanii)[0].startswith('свой'):
            return True, ''
        return False, 'номер найден агентом сборки на %s, сайт этой компании не доказан' % (d or 'странице')
    return False, 'проверка сборки: %s' % g[:150]


# ---------------------------------------------------------------- роли сборки -> словарь панели (запасная)
ROL_SBORKI = {
    'Общий номер / приёмная': 'общий/приёмная', 'Продажи': 'продажи', 'Прочее': '', 'Закупки / снабжение': 'закупки',
    'Финансы / бухгалтерия': 'бухгалтерия', 'Кадры': 'кадры', 'Руководитель': 'директор/руководитель',
    'Коммерция / ВЭД': 'продажи', 'Производство': 'производство', 'Качество / лаборатория': 'качество',
    'Техдиректор / главный инженер': 'главный инженер', 'Механик / энергетик / ремонт': 'инженер/механик/энергетик',
    'Закупки сырья / товара': 'закупки сырья', 'Технолог': 'технолог', 'Агрономия / семеноводство': 'агроном',
    'Хранение / элеватор / склад': 'склад', 'Обогащение / горное': 'другое',
}


def pokaz_nomera(v, strana='Россия'):
    """«+7 495 000-00-00 доб. 12» – как в панели; белорусские +375 – как есть."""
    osn, dob = razdelit(v)
    d = cifry(osn)
    if len(d) == 11 and d[0] in '78' and not osn.strip().startswith('+3'):
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


# ---------------------------------------------------------------- загрузка сборки
def zagruzit():
    p = pickle.load(open(os.path.join(SCR, 'vhod-meyer7', 'pul_1310.pkl'), 'rb'))
    m = pickle.load(open(os.path.join(SCR, 'vhod-meyer7', 'm7.pkl'), 'rb'))
    k3 = pickle.load(open(os.path.join(SCR, 'vhod-meyer7', 'K3.pkl'), 'rb'))
    dop = pickle.load(open(os.path.join(SCR, 'fixK', 'm7_dop.pkl'), 'rb'))
    return p, m, k3, dop


class Sborka:
    """Индексы сборки по ИНН."""

    def __init__(self, pul, m, k3, dop):
        self.pul = pul
        self.K = m['K']
        self.k3 = k3
        self.komp = {}
        for _, r in k3.iterrows():
            self.komp[kl_inn(r['inn'])] = r
        self.pul_inn = set(kl_inn(x) for x in pul['inn'])
        self.kont = collections.defaultdict(list)
        for r in m['C'].to_dict('records'):
            self.kont[kl_inn(r['ИНН / УНП'])].append(r)
        self.snyato = collections.defaultdict(set)      # ИНН -> ключи номеров / почты
        self.snyato_pochemu = {}
        for r in dop['Снято'].to_dict('records'):
            inn = kl_inn(r['ИНН / УНП'])
            v = s(r['Контакт'])
            kl = ('@' + v.lower()) if '@' in v else kl_nomera(v)
            if kl:
                self.snyato[inn].add(kl)
                if '#' in kl:
                    self.snyato[inn].add(kl.split('#')[0] + '#')
                self.snyato_pochemu[(inn, kl)] = s(r['Почему не взят'])[:200]
        self.gruppy = []          # [{'nazvanie','sayt','inns':[...]}]
        self.gruppa_inn = collections.defaultdict(list)
        for r in dop['Группы'].to_dict('records'):
            inns = re.findall(r'\((?:BY)?(\d{9,12})\)', s(r['Компании группы в списке']))
            g = {'nazvanie': s(r['Группа (головная по выручке)']), 'sayt': s(r['Сайт']), 'inns': inns,
                 'primechanie': s(r['Примечание'])}
            self.gruppy.append(g)
            for i in inns:
                self.gruppa_inn[i].append(len(self.gruppy) - 1)
        self.lidy = collections.defaultdict(list)       # ИНН компании группы -> строки «Лиды группы»
        for r in dop['Лиды группы'].to_dict('records'):
            for i in re.findall(r'\((?:BY)?(\d{9,12})\)', s(r['Компании группы в списке'])):
                self.lidy[i].append(r)
        self.spornye = {kl_inn(r['ИНН']): r for r in dop['Спорные'].to_dict('records')}
        self.poyasneniya = {kl_inn(r['ИНН / УНП']): r for r in dop['Пояснения агентов'].to_dict('records')}


def snyat(sb, inn, kl):
    if not kl:
        return False
    st = sb.snyato.get(inn) or ()
    return kl in st or (kl.split('#')[0] + '#') in st or kl.split('#')[0] in st


# ---------------------------------------------------------------- контакты одной компании
def kontakty_kompanii(sb, inn, cat):
    """-> (kontakty, lyudi, zhurnal) в схеме панели. cat – app.services.centro_catalog (для rol_kontakta)."""
    c = sb.komp[inn]
    naim, sayt, chey = s(c['Название']), s(c['Сайт']), s(c['Сайт: чей'])
    strana = s(c['Страна']) or 'Россия'
    po_kl = collections.OrderedDict()
    zh = collections.Counter()
    lyudi = []

    def dobavit(kl, row):
        if kl in po_kl:
            st = po_kl[kl]
            # источники копятся: ссылки через « ; », проверки и источники – через « | »
            for u in s(row['source_url']).split(' ; '):
                if u and u not in st['source_url'].split(' ; '):
                    st['source_url'] = (st['source_url'] + ' ; ' + u).strip(' ;')
            for pole in ('source', 'proverka_sborki'):
                if s(row.get(pole)) and s(row.get(pole)) not in s(st.get(pole)):
                    st[pole] = (s(st.get(pole)) + ' | ' + s(row.get(pole))).strip(' |')
            # имя и должность – у кого есть
            for pole in ('person', 'position', 'fragment', 'lpr_sborki', 'lpr_pochemu'):
                if not s(st.get(pole)) and s(row.get(pole)):
                    st[pole] = row[pole]
            if row.get('_prinyat') and not st.get('_prinyat'):
                st['_prinyat'], st['_pochemu_net'] = True, ''
            st['istochnikov'] = st.get('istochnikov', 1) + 1
            zh['повтор номера/почты – источники сведены'] += 1
            return
        row['istochnikov'] = 1
        po_kl[kl] = row

    for r in sb.kont.get(inn, []):
        mob, rab, mail = s(r['Мобильный']), s(r['Рабочий']), s(r['E-mail']).strip().strip('.')
        dob = s(r['Добавочный'])
        dob = dob[:-2] if dob.endswith('.0') else dob
        url = s(r['Ссылка на источник'])
        pr, ist = s(r['Проверка']), s(r['Источник'])
        prinyat, pochemu_net = kontakt_prinyat(pr, ist, url, sayt, chey)
        baza = {'inn': inn, 'person': s(r['ФИО']) or None, 'position': s(r['Должность (как на сайте)']),
                'role': ROL_SBORKI.get(s(r['Роль']), s(r['Роль']).lower()),
                'source': ' · '.join(x for x in (ist or 'сайт компании', 'сборка MEYER-7 ' + DATA_SBORKI) if x),
                'source_url': url, 'fragment': s(r['Фрагмент страницы'])[:600], 'is_unknown_owner': 0,
                'proverka_sborki': pr[:900], 'rol_sborki': s(r['Роль']), 'lpr_sborki': s(r['ЛПР по оборудованию']),
                'lpr_pochemu': s(r['Почему ЛПР'])[:500], '_prinyat': prinyat, '_pochemu_net': pochemu_net}
        for v, tip in ((mob, 'мобильный'), (rab, '')):
            if not v:
                continue
            if tip == '' and dob and not DOB_RX.search(v):
                v = v + ' доб. ' + dob
            val = pokaz_nomera(v, strana)
            kl = kl_nomera(val)
            if not kl and not cifry(val):
                continue
            if snyat(sb, inn, kl):
                zh['номер в «Снято» – не взят'] += 1
                continue
            vid = cat.vid_nomera_po_cifram(val)
            row = dict(baza, value=val, kind='phone',
                       phone_type=tip or (vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800',
                                                         'международный', 'Казахстан') else 'рабочий'))
            dobavit('t:' + (kl or cifry(val)), row)
        if mail and '@' in mail:
            if snyat(sb, inn, '@' + mail.lower()):
                zh['почта в «Снято» – не взята'] += 1
                continue
            dobavit('e:' + mail.lower(), dict(baza, value=mail, kind='email', phone_type=''))

    # Лиды группы: контакты площадок группы – к компании группы, не ЛПР
    for r in sb.lidy.get(inn, []):
        plosh = s(r['Площадка (как на сайте)'])[:160]
        gr = s(r['Группа'])
        tekst = 'контакт группы «%s»: площадка %s (сайт группы %s) – не эта компания, звонить через группу' % (
            gr, ('«%s»' % plosh) if plosh else 'не указана', s(r['Сайт группы']))
        baza = {'inn': inn, 'person': s(r['ФИО']) or None, 'position': s(r['Должность']),
                'role': ROL_SBORKI.get(s(r['Роль']), s(r['Роль']).lower()),
                'source': 'сайт группы · лист «Лиды группы» сборки MEYER-7 ' + DATA_SBORKI,
                'source_url': s(r['Ссылка']), 'fragment': s(r['Фрагмент'])[:600], 'is_unknown_owner': 0,
                'chuzhoy_istochnik': tekst[:400], 'chuzhoy_dokaz': 'лист «Лиды группы»: %s' % plosh,
                'rol_sborki': s(r['Роль']), '_prinyat': True, '_pochemu_net': ''}
        tel = s(r['Телефон'])
        dob = s(r['Доб.'])
        dob = dob[:-2] if dob.endswith('.0') else dob
        if tel:
            val = pokaz_nomera(tel + ((' доб. ' + dob) if dob and not DOB_RX.search(tel) else ''), strana)
            kl = kl_nomera(val)
            if not snyat(sb, inn, kl):
                vid = cat.vid_nomera_po_cifram(val)
                dobavit('t:' + (kl or cifry(val)), dict(baza, value=val, kind='phone',
                                                         phone_type=vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий'))
                zh['лиды группы: номер'] += 1
        mail = s(r['E-mail'])
        if mail and '@' in mail and not snyat(sb, inn, '@' + mail.lower()):
            dobavit('e:' + mail.lower(), dict(baza, value=mail, kind='email', phone_type=''))
            zh['лиды группы: почта'] += 1

    # База обзвона: телефоны и почты; тех. службы (наша база)
    for v in [x.strip() for x in s(c['База обзвона: телефоны']).split('|') if x.strip()]:
        val = pokaz_nomera(v, strana)
        kl = kl_nomera(val)
        if not kl or snyat(sb, inn, kl):
            continue
        row = {'inn': inn, 'value': val, 'kind': 'phone', 'person': None, 'position': '', 'role': '',
               'phone_type': cat.vid_nomera_po_cifram(val), 'source': 'база обзвона (наша база) · сборка MEYER-7 ' + DATA_SBORKI,
               'source_url': '', 'fragment': '', 'is_unknown_owner': 0, '_prinyat': True, '_pochemu_net': '',
               'rol_sborki': 'база обзвона'}
        if row['phone_type'] not in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800'):
            row['phone_type'] = 'рабочий'
        dobavit('t:' + kl, row)
        zh['база обзвона: номер'] += 1
    for v in [x.strip() for x in s(c['База обзвона: почты']).split('|') if x.strip()]:
        m = re.match(r'([^\s()]+@[^\s()]+)\s*(?:\((.*)\))?', v)
        if not m:
            continue
        mail, zamet = m.group(1).strip('.'), s(m.group(2))
        if snyat(sb, inn, '@' + mail.lower()):
            continue
        dobavit('e:' + mail.lower(), {'inn': inn, 'value': mail, 'kind': 'email', 'person': None, 'position': '',
                                      'role': '', 'phone_type': '', 'source': 'база обзвона (наша база) · сборка MEYER-7 ' + DATA_SBORKI,
                                      'source_url': '', 'fragment': '', 'is_unknown_owner': 0, 'vid_pochemu': zamet[:300],
                                      '_prinyat': True, '_pochemu_net': '', 'rol_sborki': 'база обзвона'})
        zh['база обзвона: почта'] += 1
    for strk in [x.strip() for x in s(c['Тех. службы (наша база)']).split('\n') if x.strip()]:
        m = re.match(r'(.+?)\s+—\s+(.+?)(?:;\s*(.*?))?\s*(\(([^()]*(?:\([^()]*\))?[^()]*)\))?\s*$', strk)
        if not m:
            continue
        fio, dolzh, kont, ist = m.group(1).strip(), m.group(2).strip(), s(m.group(3)), s(m.group(5))
        tel = ''
        mail = ''
        for x in [y.strip() for y in kont.split(',') if y.strip()]:
            if '@' in x:
                mail = x
            elif len(cifry(x)) >= 10:
                tel = pokaz_nomera(x if x.startswith('+') else '+' + cifry(x), strana)
        dob_m = re.search(r'добавочный (\d{1,6})', ist)
        if tel and dob_m and 'доб.' not in tel:
            tel += ' доб. ' + dob_m.group(1)
        src = 'тех. службы (наша база): %s · сборка MEYER-7 %s' % (ist or 'источник не указан', DATA_SBORKI)
        if tel and not snyat(sb, inn, kl_nomera(tel)):
            vid = cat.vid_nomera_po_cifram(tel)
            dobavit('t:' + kl_nomera(tel), {'inn': inn, 'value': tel, 'kind': 'phone', 'person': fio, 'position': dolzh,
                                            'role': '', 'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                                            'source': src, 'source_url': '', 'fragment': strk[:600], 'is_unknown_owner': 0,
                                            '_prinyat': True, '_pochemu_net': '', 'rol_sborki': 'тех. службы (наша база)'})
            zh['тех. службы: номер'] += 1
        else:
            lyudi.append({'inn': inn, 'person': fio, 'position': dolzh, 'role': '', 'phone': '', 'phone_type': '',
                          'email': mail, 'source_url': '', 'source': src, 'is_tech': 0, 'sprosit_u_priemnoy': 'тех. службы (наша база)'})
            zh['тех. службы: человек без номера'] += 1
    dir_bo = s(c['База обзвона: директор'])
    if dir_bo:
        lyudi.append({'inn': inn, 'person': dir_bo, 'position': 'директор', 'role': 'директор/руководитель', 'phone': '',
                      'phone_type': '', 'email': '', 'source_url': '',
                      'source': 'база обзвона (наша база): директор · сборка MEYER-7 ' + DATA_SBORKI, 'is_tech': 0,
                      'sprosit_u_priemnoy': 'директор по базе обзвона'})

    # роль по смыслу (логика панели); непринятый сайт без имени компании – ЛПР не считается
    kontakty = []
    for kl, x in po_kl.items():
        if x['kind'] == 'phone':
            rk = cat.rol_kontakta(x)
            if rk['lpr'] and not x.get('_prinyat'):
                nazv = nazvan_vo_fragmente(x.get('fragment'), naim, inn)
                if nazv:
                    x['vid_pochemu'] = ('%s; принято: %s' % (x['_pochemu_net'], nazv))[:400]
                    zh['непринятый сайт, но компания названа – ЛПР'] += 1
                else:
                    x['rol_vruchnuyu'] = 'общий номер'
                    x['vid_pochemu'] = ('%s; был бы ЛПР «%s» – не считается ЛПР этой компании (правило 13.10: человек '
                                        'не назван её)' % (x['_pochemu_net'], rk['vid']))[:500]
                    zh['непринятый сайт: ЛПР -> общий номер (путь через группу)'] += 1
                    rk = cat.rol_kontakta(x)
            elif not x.get('_prinyat') and x.get('_pochemu_net'):
                x['vid_pochemu'] = x['_pochemu_net'][:400]
            x['is_purchaser'], x['is_tech'] = rk['zakup'], rk['teh']
            x['has_role'] = int(bool(rk['lpr']) or rk['vid'] in ('приёмная', 'общий номер', 'техслужба (не ЛПР)', 'без подписи'))
            x['nomer_ne_lichnyy'] = None if rk['lpr'] else rk['vid']
            # role НЕ переписывается видом: при общей должности («руководитель») rol_kontakta решает по role,
            # а вид «первое лицо» в role дал бы «без подписи»; role остаётся в словаре панели (_PO_ROLI)
            x['_rol'] = rk['vid']
            x['_lpr'] = rk['lpr']
        else:
            x['is_purchaser'] = x['is_tech'] = x['has_role'] = 0
            x['nomer_ne_lichnyy'] = 'почта'
            x['_rol'], x['_lpr'] = 'почта', 0
            if not x.get('_prinyat') and x.get('_pochemu_net'):
                x['vid_pochemu'] = x['_pochemu_net'][:400]
        kontakty.append(x)
    # люди: с номером (строки телефонов) и только с почтой; почта человека – в person.email.
    # Человек с непринятого сайта (без имени компании) – с пометкой chuzhoy_istochnik: в «привязка снята»,
    # «спросить у приёмной» по нему не строится.
    po_fio = collections.OrderedDict()
    for x in kontakty:
        f = s(x.get('person'))
        if not f:
            continue
        p = po_fio.get(f)
        if p is None:
            ne_nash = s(x.get('chuzhoy_istochnik')) or (
                x.get('_pochemu_net') if (not x.get('_prinyat') and not nazvan_vo_fragmente(x.get('fragment'), naim, inn)) else '')
            p = {'inn': inn, 'person': f, 'position': x.get('position') or '', 'role': x.get('role') or '',
                 'phone': '', 'phone_type': '', 'email': '', 'source_url': (x.get('source_url') or '').split(' ; ')[0],
                 'source': x.get('source') or '', 'is_tech': x.get('is_tech') or 0, 'sprosit_u_priemnoy': None,
                 'chuzhoy_istochnik': s(ne_nash)[:400] or None}
            po_fio[f] = p
        if x['kind'] == 'phone' and not p['phone']:
            p['phone'], p['phone_type'] = x['value'], x.get('phone_type') or ''
        if x['kind'] == 'email' and not p['email']:
            p['email'] = x['value']
        if not p['position'] and x.get('position'):
            p['position'] = x['position']
    for p in po_fio.values():
        if not p['phone']:
            p['sprosit_u_priemnoy'] = 'на странице есть только почта' if p['email'] else None
    lyudi = list(po_fio.values()) + lyudi
    return kontakty, lyudi, zh
