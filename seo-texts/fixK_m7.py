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
# лес и химия – без (владелец 13.10); «полимеры, гранула» владелец вернул: «пластик в гранулах мы сортируем»
LES_HIM = ('лесопиление', 'деревообработ', 'неорганическая химия', 'удобрения', 'химсырьё', 'синтетический каучук')


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
    if g.startswith('свой:'):
        return 'свой', 3
    if g.startswith('найден агентом'):
        if 'ИНН компании на сайте' in s(chey):
            return 'свой', 4
        return 'свой (по названию)', 1
    if g.startswith('своего сайта нет') and 'сайт холдинга' in s(chey):
        return 'группа', 0
    if g.startswith(('сайта нет', 'своего сайта нет')):
        return 'нет сайта', 0
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
        # владелец 13.10 (через координатора): «деление по компании» – компании, которые сборка вынесла в «Не вошли»
        # с причиной «сайт принадлежит клиенту с активной сделкой Meyer», можно вернуть, если у самой компании сделки нет.
        # Данных о них в сборке мало (лист «Не вошли» + номера/почты в «Снято» без должностей): запись собирается тут.
        seg_eda = {}
        for _, r in pul.iterrows():
            seg_eda.setdefault(s(r['Сегмент']), bool(r['eda']))
        self.vozvrat = {}
        self.vozvrat_eda = {}
        for r in m['N'].to_dict('records'):
            if 'сайт принадлежит клиенту с активной сделкой' not in s(r['Причина']):
                continue
            inn = kl_inn(r['ИНН'])
            if not inn or inn in self.komp:
                continue
            seg = s(r['Сегмент (по допкоду)'])
            z = Pusto({'Название': s(r['Название']), 'ИНН / УНП': s(r['ИНН']), 'Страна': 'Беларусь' if len(inn) == 9 else 'Россия',
                       'Регион': s(r['Регион']), 'Сегмент': seg, 'Сайт': s(r['Сайт']), 'Основной ОКВЭД': s(r['Основной ОКВЭД']),
                       'Сайт: чей': s(r['Причина']), 'Откуда компания': 'лист «Не вошли» сборки MEYER-7: ' + s(r['Причина'])[:300],
                       'Ревизия: профиль': '⚠ ' + s(r['Причина'])[:400], 'inn': inn, 'st': 0, '_vozvrat': 1})
            self.komp[inn] = z
            self.vozvrat[inn] = s(r['Причина'])
            self.vozvrat_eda[inn] = seg_eda.get(seg, bool(re.search(
                r'мяс|молок|сыр|хлеб|кондит|мук|круп|зерн|элеват|овощ|фрукт|масл|корм|кофе|чай|специ|птиц|ягод|крахмал|пищ|опт', seg.lower())))
        self.snyato_vozvrat = collections.defaultdict(list)    # ИНН -> строки «Снято» с причиной сайта клиента
        for r in dop['Снято'].to_dict('records'):
            inn = kl_inn(r['ИНН / УНП'])
            if inn in self.vozvrat and 'сайт принадлежит клиенту с активной сделкой' in s(r['Почему не взят']):
                self.snyato_vozvrat[inn].append(r)


class Pusto(dict):
    """Запись компании без строки в листе «Компании»: отсутствующая колонка – пустая строка."""

    def __missing__(self, k):
        return ''

    @property
    def name(self):
        return None


# совпадения «точное название» с активной сделкой Meyer без ИНН – разобраны вручную 13.10 (сделка / регион / профиль)
IMENA = {
    '7017094419': (True, 'сделка 96727 «ГК КДВ групп (Кемерово) Яшкино» – та же группа КДВ (Томск, завод в Яшкино)'),
    '4802024211': (True, 'сделка 79387 «ВИ ФРАЙ ООО (Липецк) производство картофеля фри» – та же компания, тот же регион'),
    '5200000110': (True, 'сделка 153003 «АО "КАРАВАЙ"» без региона – тёзку не отличить, не беру'),
    '3801008303': (True, 'сделка 153003 «АО "КАРАВАЙ"» без региона, та же форма АО – не беру'),
    '2373004971': (False, 'сделка 153003 – АО «КАРАВАЙ», у кандидата ООО (другая форма) – тёзка'),
    '6001002876': (False, 'сделка 135391 «Ударник СПК Чувашия», кандидат – АО в Псковской обл. – тёзка'),
    '2608009307': (True, 'сделка 107711 «Урожайное ООО (Ставрополь…)», кандидат – СХП «Урожайное», ИНН 26 (Ставрополь)'),
    '5427102846': (False, 'сделка 107711 – ставропольское «Урожайное», кандидат – КХ, ИНН 54 (Новосибирская) – тёзка'),
    '2288003247': (True, 'сделка 3609 «Образ жизни (из успешных MEYER)» – тот же клиент, не беру'),
    '6806004040': (False, 'сделка 79455 «АФ Приволье… нешелушённого риса» (рисовод), кандидат – Тамбовская обл. – тёзка'),
    '9404006646': (False, 'сделка 79455 «АФ Приволье» (рис), кандидат – ИНН 94 – тёзка'),
    '2330025409': (False, 'сделка 127353 «Агропродукт ООО Дагестан», кандидат – Краснодарский край – тёзка'),
    '3105003854': (False, 'сделка 127353 «Агропродукт Дагестан», кандидат – Белгородская обл. – тёзка'),
    '9105010210': (False, 'сделка 127353 «Агропродукт Дагестан», кандидат – Крым – тёзка'),
    '5951002008': (False, 'сделка 16070 «Союз-Агро г.Барнаул», кандидат – Пермский край – тёзка'),
    '3905082573': (False, 'сделка 157367 «Агросистема г.Иркутск», кандидат – ИНН 39 (Калининград) – тёзка'),
    '2348036970': (False, 'сделка 157367 «Агросистема г.Иркутск», кандидат – ИНН 23 (Краснодар) – тёзка'),
    '3811467881': (True, 'сделка 157367 «Агросистема ООО г.Иркутск» – НКЦ «Агросистема», Иркутск – не беру'),
    '7444007868': (True, 'сделка 7790 «Лакомка сорт Подсолнечник» без региона – тёзку не отличить, не беру'),
    '3662075910': (True, 'сделка 7790 «Лакомка» без региона – тёзку не отличить, не беру'),
    '5007067613': (False, 'сделка 34885 «… Паритет ООО … (Красноярск…)», кандидат – ИНН 50 – тёзка'),
    '4705083620': (False, 'сделка 106608 «АГРОСОЮЗ ООО Суханов ИП (Белгород) проектировщики», кандидат – СПОК, Ленобласть'),
    '6230109846': (False, 'сделка 106608 «АГРОСОЮЗ… (Белгород)», кандидат – Рязанская обл. – тёзка'),
    '600033917': (True, 'сделка 152872 «Борисовский КХП Беларусь» – та же компания'),
    '591049283': (False, 'сделка 137062 «Полимет (Брянск)», кандидат – белорусский «ПолиМет» – тёзка'),
    '3808290352': (False, 'сделка 156342 «ООО МАКОШЬ … Тула», кандидат – Иркутская обл. – тёзка'),
}


KLIENTY = {}      # ИНН клиента с активной сделкой Meyer -> название (заполняет fixK_otbor/fixK_plan из meyer_all.csv)


def snyat(sb, inn, kl):
    if not kl or inn in getattr(sb, 'vozvrat', {}):
        return False
    st = sb.snyato.get(inn) or ()
    return kl in st or (kl.split('#')[0] + '#') in st or kl.split('#')[0] in st


# ---------------------------------------------------------------- контакты одной компании
def istochnik_tekst(ist, pr, rol, lpr_s, pochemu):
    """Источник номера – как у fixJ (усиление 600): «MEYER-7 13.10: <Источник> · <Проверка> · подсказка MEYER-7: …»."""
    podsk = 'подсказка MEYER-7: роль «%s», ЛПР по оборудованию «%s»%s' % (rol, lpr_s, ('; ' + pochemu[:150]) if pochemu else '')
    return ('MEYER-7 13.10: %s · %s · %s' % (ist or 'сайт компании', pr or 'проверка не указана', podsk))[:900]


def kontakty_kompanii(sb, inn, cat):
    """-> (kontakty, lyudi, pochty, zhurnal) в схеме панели (contact только phone, как сейчас в базе; почты – списком
    (адрес, пометка, ЛПР?) для company.pochta, как fixJ). cat – app.services.centro_catalog (rol_kontakta)."""
    c = sb.komp[inn]
    naim, sayt, chey = s(c['Название']), s(c['Сайт']), s(c['Сайт: чей'])
    strana = s(c['Страна']) or 'Россия'
    po_kl = collections.OrderedDict()
    zh = collections.Counter()
    lyudi, pochty = [], []

    def dobavit(kl, row):
        if kl in po_kl:
            st = po_kl[kl]
            for u in s(row['source_url']).split(' ; '):           # источники копятся: ссылки через « ; »
                if u and u not in st['source_url'].split(' ; '):
                    st['source_url'] = (st['source_url'] + ' ; ' + u).strip(' ;')
            if s(row.get('source')) and s(row['source'])[:60] not in s(st.get('source')):
                st['source'] = (s(st.get('source')) + ' | ' + s(row['source']))[:1500]
            for pole in ('person', 'position', 'fragment', 'role'):
                if not s(st.get(pole)) and s(row.get(pole)):
                    st[pole] = row[pole]
            if row.get('_prinyat') and not st.get('_prinyat'):
                st['_prinyat'], st['_pochemu_net'], st['_gruppa_d'] = True, '', ''
            st['_n'] = st.get('_n', 1) + 1
            zh['повтор номера – источники сведены'] += 1
            return
        row['_n'] = 1
        po_kl[kl] = row

    def pochta(mail, pom, lpr=False, ist='MEYER-7'):
        mail = s(mail).strip().strip('.').lower()
        if not mail or '@' not in mail:
            return
        if snyat(sb, inn, '@' + mail):
            zh['почта в «Снято» – не взята'] += 1
            return
        if any(mail == p[0] for p in pochty):
            return
        pochty.append((mail, '%s%s%s' % ('ЛПР: ' if lpr else '', ist, (': ' + pom) if pom else ''), lpr))

    for r in sb.kont.get(inn, []):
        mob, rab, mail = s(r['Мобильный']), s(r['Рабочий']), s(r['E-mail'])
        dob = s(r['Добавочный'])
        dob = dob[:-2] if dob.endswith('.0') else dob
        url = s(r['Ссылка на источник']) or s(r['Сайт'])
        pr, ist = s(r['Проверка']), s(r['Источник'])
        fio, dolzh = s(r['ФИО']), s(r['Должность (как на сайте)'])
        prinyat, pochemu_net = kontakt_prinyat(pr, ist, url, sayt, chey)
        baza = {'inn': inn, 'person': fio or None, 'position': dolzh,
                'role': ROL_SBORKI.get(s(r['Роль']), s(r['Роль']).lower()),
                'source': istochnik_tekst(ist, pr, s(r['Роль']), s(r['ЛПР по оборудованию']), s(r['Почему ЛПР'])),
                'source_url': url, 'fragment': s(r['Фрагмент страницы'])[:1500], 'is_unknown_owner': 0,
                'vid_pochemu': '', 'rol_vruchnuyu': '', 'podpis_stranicy': '',
                '_prinyat': prinyat, '_pochemu_net': pochemu_net, '_gruppa_d': domen(url)}
        est_nomer = False
        for v, tip in ((mob, 'мобильный'), (rab, '')):
            if not v:
                continue
            if tip == '' and dob and not DOB_RX.search(v):
                v = v + ' доб. ' + dob
            val = pokaz_nomera(v, strana)
            kl = kl_nomera(val)
            if not kl:
                zh['номер не разобран'] += 1
                continue
            if snyat(sb, inn, kl):
                zh['номер в «Снято» – не взят'] += 1
                continue
            vid = cat.vid_nomera_po_cifram(val)
            row = dict(baza, value=val, kind='phone', vid_nomera=vid,
                       phone_type=vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий')
            dobavit('t:' + kl, row)
            est_nomer = True
        if mail:
            rk0 = cat.rol_kontakta({'position': dolzh, 'role': baza['role']})
            lpr_m = bool(rk0['lpr']) and (prinyat or bool(nazvan_vo_fragmente(baza['fragment'], naim, inn)))
            pom = ', '.join(v for v in (dolzh or s(r['Роль']), fio) if v)
            if not prinyat and not lpr_m:
                pom += '; ' + pochemu_net[:80]
            pochta(mail, pom, lpr_m)
            if fio and not est_nomer:              # человек только с почтой – в «Люди предприятия»
                lyudi.append({'inn': inn, 'person': fio, 'position': dolzh, 'role': baza['role'], 'phone': '', 'phone_type': '',
                              'email': mail.lower(), 'source_url': url, 'source': baza['source'], 'is_tech': rk0['teh'],
                              'chuzhoy_istochnik': None if lpr_m or prinyat else (
                                  'с сайта группы: %s – человек не назван сотрудником этой компании' % (domen(url) or ist))[:400],
                              'sprosit_u_priemnoy': 'MEYER-7: на странице «%s» – %s; номера нет, есть почта %s' % (
                                  domen(url), ', '.join(v for v in (fio, dolzh) if v), mail.lower())})

    # возвращённые из «Не вошли» (сайт клиента с активной сделкой Meyer): их номера и почты – из «Снято», с меткой
    for r in sb.snyato_vozvrat.get(inn, []):
        v = s(r['Контакт'])
        prich = s(r['Почему не взят'])
        mk = re.search(r'ИНН (\d{9,12})', prich)
        klient = KLIENTY.get(mk.group(1), '') if mk else ''
        metka = ('сайт холдинга с активной сделкой Meyer: %s%s' % (('ИНН ' + mk.group(1)) if mk else 'клиент',
                                                                  (' ' + klient) if klient else ''))[:300]
        sd = re.search(r'(№\d+ MEYER[^;]{0,80})', prich)
        if '@' in v:
            pochta(v, metka + ((' · ' + sd.group(1)) if sd else ''))
            continue
        val = pokaz_nomera(v, strana)
        kl = kl_nomera(val)
        if not kl:
            continue
        vid = cat.vid_nomera_po_cifram(val)
        dobavit('t:' + kl, {'inn': inn, 'value': val, 'kind': 'phone', 'person': None, 'position': '', 'role': '',
                            'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                            'vid_nomera': vid, 'source': ('MEYER-7 13.10: лист «Снято» – %s' % prich)[:900],
                            'source_url': s(r['Ссылка']), 'fragment': s(r['Фрагмент'])[:1500], 'is_unknown_owner': 0,
                            'chuzhoy_istochnik': metka, 'chuzhoy_dokaz': prich[:500], 'vid_pochemu': '', 'rol_vruchnuyu': '',
                            'podpis_stranicy': '', '_prinyat': True, '_pochemu_net': '', '_gruppa_d': ''})
        zh['возврат из «Не вошли»: номер с сайта клиента в сделке (с меткой)'] += 1

    # Лиды группы: контакты площадок группы – к компании группы, не ЛПР этой компании
    for r in sb.lidy.get(inn, []):
        plosh = s(r['Площадка (как на сайте)'])[:160]
        tekst = 'контакт группы «%s»: площадка %s (сайт группы %s) – не эта компания' % (
            s(r['Группа']), ('«%s»' % plosh) if plosh else 'не указана', s(r['Сайт группы']))
        tel = s(r['Телефон'])
        dob = s(r['Доб.'])
        dob = dob[:-2] if dob.endswith('.0') else dob
        if tel:
            val = pokaz_nomera(tel + ((' доб. ' + dob) if dob and not DOB_RX.search(tel) else ''), strana)
            kl = kl_nomera(val)
            if kl and not snyat(sb, inn, kl):
                vid = cat.vid_nomera_po_cifram(val)
                dobavit('t:' + kl, {'inn': inn, 'value': val, 'kind': 'phone', 'person': s(r['ФИО']) or None,
                                    'position': s(r['Должность']), 'role': ROL_SBORKI.get(s(r['Роль']), ''),
                                    'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                                    'vid_nomera': vid, 'source': ('MEYER-7 13.10: лист «Лиды группы» (сайт группы %s) · площадка %s'
                                                                  % (s(r['Сайт группы']), plosh))[:900],
                                    'source_url': s(r['Ссылка']), 'fragment': s(r['Фрагмент'])[:1500], 'is_unknown_owner': 0,
                                    'chuzhoy_istochnik': tekst[:400], 'chuzhoy_dokaz': 'MEYER-7, лист «Лиды группы»: %s' % plosh,
                                    'vid_pochemu': '', 'rol_vruchnuyu': '', 'podpis_stranicy': '', '_prinyat': True,
                                    '_pochemu_net': '', '_gruppa_d': ''})
                zh['лиды группы: номер'] += 1
        if s(r['E-mail']):
            pochta(s(r['E-mail']), 'контакт группы, площадка %s' % (plosh or s(r['Группа'])))
            zh['лиды группы: почта'] += 1

    # База обзвона (наша база): номера, почты; тех. службы (наша база); директор базы обзвона – человек
    for v in [x.strip() for x in s(c['База обзвона: телефоны']).split('|') if x.strip()]:
        val = pokaz_nomera(v, strana)
        kl = kl_nomera(val)
        if not kl or snyat(sb, inn, kl):
            continue
        vid = cat.vid_nomera_po_cifram(val)
        dobavit('t:' + kl, {'inn': inn, 'value': val, 'kind': 'phone', 'person': None, 'position': '', 'role': '',
                            'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                            'vid_nomera': vid, 'source': 'MEYER-7 13.10: база обзвона (наша база), колонка «База обзвона: телефоны»',
                            'source_url': '', 'fragment': '', 'is_unknown_owner': 0, 'vid_pochemu': '', 'rol_vruchnuyu': '',
                            'podpis_stranicy': '', '_prinyat': True, '_pochemu_net': '', '_gruppa_d': ''})
        zh['база обзвона: номер'] += 1
    for v in [x.strip() for x in s(c['База обзвона: почты']).split('|') if x.strip()]:
        m = re.match(r'([^\s()]+@[^\s()]+)\s*(?:\((.*)\))?', v)
        if m:
            pochta(m.group(1), s(m.group(2)), ist='база обзвона')
            zh['база обзвона: почта'] += 1
    for strk in [x.strip() for x in s(c['Тех. службы (наша база)']).split('\n') if x.strip()]:
        m = re.match(r'(.+?)\s+—\s+(.+?)(?:;\s*(.*?))?\s*(\(([^()]*(?:\([^()]*\))?[^()]*)\))?\s*$', strk)
        if not m:
            continue
        fio, dolzh, kont, ist = m.group(1).strip(), m.group(2).strip(), s(m.group(3)), s(m.group(5))
        tel, mail = '', ''
        for x in [y.strip() for y in kont.split(',') if y.strip()]:
            if '@' in x:
                mail = x
            elif len(cifry(x)) >= 10:
                tel = pokaz_nomera(x if x.startswith('+') else '+' + cifry(x), strana)
        dob_m = re.search(r'добавочный (\d{1,6})', ist)
        if tel and dob_m and 'доб.' not in tel:
            tel += ' доб. ' + dob_m.group(1)
        src = 'MEYER-7 13.10: тех. службы (наша база): %s' % (ist or 'источник не указан')
        if mail:
            pochta(mail, '%s, %s' % (dolzh, fio), ist='тех. службы (наша база)')
        if tel and kl_nomera(tel) and not snyat(sb, inn, kl_nomera(tel)):
            vid = cat.vid_nomera_po_cifram(tel)
            dobavit('t:' + kl_nomera(tel), {'inn': inn, 'value': tel, 'kind': 'phone', 'person': fio, 'position': dolzh, 'role': '',
                                            'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                                            'vid_nomera': vid, 'source': src, 'source_url': '', 'fragment': strk[:600],
                                            'is_unknown_owner': 0, 'vid_pochemu': '', 'rol_vruchnuyu': '', 'podpis_stranicy': '',
                                            '_prinyat': True, '_pochemu_net': '', '_gruppa_d': ''})
            zh['тех. службы: номер'] += 1
        else:
            lyudi.append({'inn': inn, 'person': fio, 'position': dolzh, 'role': '', 'phone': '', 'phone_type': '',
                          'email': mail, 'source_url': '', 'source': src, 'is_tech': 0, 'chuzhoy_istochnik': None,
                          'sprosit_u_priemnoy': 'тех. службы (наша база): %s' % (ist or '')})
            zh['тех. службы: человек без номера'] += 1
    dir_bo = s(c['База обзвона: директор'])
    if dir_bo:
        lyudi.append({'inn': inn, 'person': dir_bo, 'position': 'директор', 'role': 'директор/руководитель', 'phone': '',
                      'phone_type': '', 'email': '', 'source_url': '', 'chuzhoy_istochnik': None,
                      'source': 'MEYER-7 13.10: база обзвона (наша база), колонка «База обзвона: директор»', 'is_tech': 0,
                      'sprosit_u_priemnoy': 'директор по базе обзвона (наша база)'})

    # роль по смыслу (логика панели); непринятый сайт без имени компании – как у fixJ: метка «с сайта группы»
    kontakty = []
    for kl, x in po_kl.items():
        rk = cat.rol_kontakta(x)
        if rk['lpr'] and not x.get('_prinyat'):
            nazv = nazvan_vo_fragmente(x.get('fragment'), naim, inn)
            if nazv:
                x['vid_pochemu'] = ('%s; принято: %s' % (x['_pochemu_net'], nazv))[:400]
                zh['непринятый сайт, но компания названа во фрагменте – ЛПР'] += 1
            else:
                x['chuzhoy_istochnik'] = ('с сайта группы: %s – человек не назван сотрудником этой компании'
                                          % (x.get('_gruppa_d') or 'сайт'))[:400]
                x['chuzhoy_dokaz'] = ('MEYER-7: %s; был бы «%s»' % (x['_pochemu_net'], rk['vid']))[:500]
                zh['непринятый сайт: ЛПР не этой компании (метка «с сайта группы»)'] += 1
                rk = cat.rol_kontakta(x)
        elif not x.get('_prinyat') and x.get('_pochemu_net'):
            x['vid_pochemu'] = x['_pochemu_net'][:400]
        x['is_purchaser'], x['is_tech'] = rk['zakup'], rk['teh']
        x['has_role'] = int(bool(rk['lpr']) or rk['vid'] in ('приёмная', 'общий номер', 'техслужба (не ЛПР)', 'без подписи'))
        x['nomer_ne_lichnyy'] = None if rk['lpr'] else rk['vid']
        # role НЕ переписывается видом: при общей должности («руководитель») rol_kontakta решает по role (словарь
        # панели), а вид «первое лицо» в role дал бы «без подписи»
        x['_rol'], x['_lpr'] = rk['vid'], rk['lpr']
        if x['_n'] > 1:
            x['source'] = ('%s · источников: %d' % (x['source'], x['_n']))[:1500]
        kontakty.append(x)
        if s(x.get('person')):
            lyudi.append({'inn': inn, 'person': x['person'], 'position': x.get('position') or '', 'role': x.get('role') or '',
                          'phone': x['value'], 'phone_type': x.get('phone_type') or '', 'email': '',
                          'source_url': (x.get('source_url') or '').split(' ; ')[0], 'source': x.get('source') or '',
                          'is_tech': rk['teh'], 'chuzhoy_istochnik': x.get('chuzhoy_istochnik') or None,
                          'sprosit_u_priemnoy': None})
    # почта человека – в person.email; один человек – одна строка без номера
    po_fio = {}
    for p in lyudi:
        if p['email'] and p['person']:
            po_fio.setdefault(p['person'], p['email'])
    vidali, lyudi2 = set(), []
    for p in sorted(lyudi, key=lambda p: 0 if p['phone'] else 1):
        if not p['email'] and p['person'] in po_fio:
            p['email'] = po_fio[p['person']]
        kk = (cat._kl_fio(p['person']), k10(p['phone']))
        if kk in vidali or (not p['phone'] and any(v[0] == kk[0] for v in vidali)):
            continue
        vidali.add(kk)
        lyudi2.append(p)
    return kontakty, lyudi2, pochty, zh


# ---------------------------------------------------------------- флаги ЛПР (копия fixH_zamena.flagi / fixF2_dannye)
def pokaz(cat, v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    d = re.sub(r'\D', '', osn)
    if len(d) == 11 and d[0] == '7':
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


def flagi(cat, items):
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    sprosit = [x for x in items if x['kind'] == 'sprosit']
    roli = list(dict.fromkeys(x['rol_vid'] for x in lpr))
    fio_lpr = {cat._kl_fio(x['person']) for x in lpr if x['person']}
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]
    if lpr:
        l0 = (fio_mob or mob or lpr)[0]
        kr = ' · '.join(v for v in (l0['person'], l0['position'] or l0['rol_vid'], pokaz(cat, l0['value'])) if v)
        if len(lpr) > 1:
            kr += ' (+ ещё %d)' % (len(lpr) - 1)
    elif sprosit:
        s0 = sprosit[0]
        kr = '%s · %s (без номера – спросить у приёмной)' % (s0['person'], s0['position'] or s0['rol_vid'])
    else:
        put_ = [x for x in tel if x['has_role']]
        if put_:
            p0 = put_[0]
            kr = ('ЛПР не найден, через приёмную: %s' if p0['rol_vid'] in ('приёмная', 'общий номер')
                  else 'ЛПР не найден, номер с сайта: %s') % pokaz(cat, p0['value'])
            n_mob = sum(1 for x in tel if x['vid_nomera'] == 'мобильный')
            if n_mob:
                kr += ' (мобильных без ЛПР: %d)' % n_mob
        else:
            kr = 'ЛПР не найден' + (', номера только неличные: %d' % len(tel) if tel else ', номеров нет')
    return {'has_tech': int(any(x['is_tech'] for x in lpr)), 'n_tech': sum(1 for x in lpr if x['is_tech']),
            'has_purchaser': int(any(x['is_purchaser'] for x in lpr)), 'n_purchaser': sum(1 for x in lpr if x['is_purchaser']),
            'lpr_mobilnyy': int(bool(mob)), 'lpr_s_fio': len(fio_lpr), 'lpr_roli': ', '.join(roli), 'lpr_kratko': kr,
            'n_phones': len(tel), 'has_phone': int(bool(tel))}


def search_blob(cat, inn, c, items, lpr_kratko):
    return ' '.join(str(v) for v in (
        inn, c.get('predpriyatie'), c.get('region'), c.get('okvedy_vse'), c.get('segment'), c.get('segment_meyer7'),
        c.get('opisanie'), c.get('produkciya'), c.get('holding'), c.get('sayt'), lpr_kratko, c.get('adres'), c.get('direktor'),
        ' '.join('%s %s %s %s' % (x.get('person') or '', x.get('position') or '', x.get('rol_vid') or '',
                                  cat._phone_key(x.get('value'))) for x in items if x['kind'] in ('phone', 'sprosit'))) if v).lower()
