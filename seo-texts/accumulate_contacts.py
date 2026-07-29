# -*- coding: utf-8 -*-
"""Накопитель контактов по компаниям: собрать всё найденное в одну таблицу с приоритетом.

Правило владельца: **отовсюду тянуть контакты по компании, и если компания засветилась
ещё где-то — у нас уже есть контакт**. Ключ склейки — ИНН. У каждого поля своя ссылка на
источник и своя дата наблюдения.

Приоритет считается, а не проверяется звонком. Дата наблюдения входит в оценку: она
говорит «когда мы это видели», а не «когда подтвердили», поэтому свежесть снижает риск
протухания, но не заменяет проверку. Для ранжирования обзвона этого достаточно.

Формула приоритета — произведение четырёх множителей, каждый со своим смыслом:

  role      — насколько человек влияет на решение о покупке машины;
  contact   — насколько до него реально дозвониться (мобильный лучше приёмной);
  fresh     — насколько свежо наблюдение (связка «человек–роль» живёт недолго:
              замерено 6 человек из 20 на месте через 5 лет);
  company   — насколько компания готова покупать: число компрессоров с истекающим
              в ближайшие 12 месяцев сроком заключения ЭПБ, по её ИНН. **Центробежные
              считаются отдельно и весят кратно больше**: это самые дорогие машины,
              счёт на миллионы против мелочи у поршневых. Правило владельца:
              «из тех, кто уже купил, особенно ценны те, кто купил центробежные».

Запуск:
    python3 seo-texts/accumulate_contacts.py
Выход:
    seo-texts/engineers-lens/contacts-accumulator.csv
"""
import csv
import datetime
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))
LENS = os.path.join(DIR, 'engineers-lens')
OUT = os.path.join(LENS, 'contacts-accumulator.csv')
EPB = os.path.join(LENS, 'epb-kompressor-expiring.csv')
EPB_CENTRO = os.path.join(LENS, 'epb-centro-expiring.csv')
ROSSETI = os.path.join(LENS, 'harvest-rosseti-volga.csv')

TODAY = datetime.date(2026, 7, 29)   # дата прогона; вынесена явно, чтобы результат воспроизводился

COLS = ['inn', 'organization', 'person', 'role', 'role_group', 'phone', 'phone_type',
        'email', 'email_type', 'source', 'source_url', 'observed_at', 'proof_level',
        'epb_expiring', 'epb_centro', 'score', 'note']

# --- роли: вес по влиянию на решение о покупке компрессора ---------------------------
ROLE_RULES = [
    (r'главн\w+ инженер|технически\w+ директор|директор по производству', 'инженер', 3.0),
    (r'главн\w+ (?:механик|энергетик)|начальник\w* (?:компрессорн|цеха|производств)', 'инженер', 2.7),
    (r'заместител\w+ главного инженера|заместител\w+ директора[^,]{0,40}(?:производ|техни)', 'инженер', 2.5),
    (r'директор филиала|генеральн\w+ директор|^директор$|руководитель', 'руководитель', 2.0),
    (r'заместител\w+ директора', 'руководитель', 1.6),
    (r'контактн\w+ лицо|закупк|специалист по закупкам', 'закупщик', 1.0),
]


def role_weight(role):
    r = (role or '').lower()
    for pat, group, w in ROLE_RULES:
        if re.search(pat, r):
            return group, w
    return 'прочее', 0.8


# --- телефон: насколько это прямой путь к человеку ------------------------------------
def phone_weight(phone, ptype):
    if not phone:
        return 0.4
    p = re.sub(r'\D', '', phone)
    if re.match(r'^7?9\d{9}$', p):        # мобильный
        return 3.0
    if ptype == 'мобильный':
        return 3.0
    if 'доб' in (phone or '').lower():    # добавочный — конкретный человек
        return 2.2
    if ptype == 'прямой':
        return 2.0
    return 1.2                            # приёмная или общий номер отдела


def email_weight(email):
    """Именная почта = путь к человеку. Общая (zakupki@, info@) = путь в отдел."""
    if not email:
        return 0.0
    local = email.split('@')[0].lower()
    if local in ('zakupki', 'info', 'office', 'mail', 'priem', 'adm', 'secretary', 'tender'):
        return 0.1
    if re.search(r'\d$', local) or '_' in local or '.' in local or len(local) > 5:
        return 0.5
    return 0.3


def fresh_weight(observed_at):
    """Связка «человек–роль» живёт мало. Замер: 6 из 20 на месте через 5 лет,
    3 из 7 через 2,8 года. Поэтому спад заметный, но не обрыв."""
    try:
        d = datetime.date.fromisoformat(observed_at)
    except Exception:  # noqa: BLE001
        return 0.5
    months = (TODAY - d).days / 30.44
    if months <= 3:
        return 1.0
    if months <= 12:
        return 0.85
    if months <= 24:
        return 0.6
    if months <= 48:
        return 0.35
    return 0.2


def company_weight(n_all, n_centro):
    """Парк на исходе срока. Два слагаемых, потому что машины неравноценны.

    Центробежные — главный признак. Это самое дорогое оборудование, замена считается
    миллионами, и решение принимают на уровне главного инженера, а не снабженца.
    Поэтому у них вес втрое против общего числа компрессоров.

    Корень, а не линейный рост: Томскнефтехим с 95 машинами не должен задавить
    Невинномысский Азот с одной центробежной, но преимущество обязано остаться.
    """
    base = min(n_all, 100) ** 0.5 / 3.0 if n_all else 0.0
    centro = min(n_centro, 40) ** 0.5 if n_centro else 0.0
    return 1.0 + base + centro


def _count_by_inn(path):
    counts = {}
    if not os.path.exists(path):
        return counts
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f, delimiter=';'):
            inn = (r.get('inn_zakazchika') or '').strip()
            if inn:
                counts[inn] = counts.get(inn, 0) + 1
    return counts


def load_epb():
    """ИНН -> (всего компрессоров, из них центробежных) с истекающим сроком ЭПБ."""
    return _count_by_inn(EPB), _count_by_inn(EPB_CENTRO)


# --- собранное за сессию: каждая строка наблюдена лично, ссылка ведёт к источнику -----
SEED = [
    # ТЭК-Торг, секции Роснефти и интернет-магазина. Карточки открыты без входа.
    dict(inn='3801009466', organization='АО «АНХК»', person='Коробицына Александра Павловна',
         role='контактное лицо закупки (ремонт компрессора 305ВП-20/35)',
         phone='8-3955-577328', phone_type='прямой', email='KorobitsynaAP@anhk.rosneft.ru',
         source='ТЭК-Торг', source_url='https://www.tektorg.ru/rosneft/procedures/19359821',
         observed_at='2026-07-29', proof_level='1',
         note='ремонт поршневого компрессора 305ВП-20/35 НПП АО «АНХК»'),
    dict(inn='3801009466', organization='АО «АНХК»', person='Бутакова Марина Валерьевна',
         role='контактное лицо закупки (ЗПЧ для поршневого компрессора)',
         phone='7-3955-577596', phone_type='прямой', email='mv_butakova@anhk.rosneft.ru',
         source='ТЭК-Торг', source_url='https://www.tektorg.ru/rosneft/procedures/19440401',
         observed_at='2026-07-29', proof_level='1',
         note='вторая закупщица того же ИНН — ростер, а не одна фамилия'),
    dict(inn='', organization='ООО «Харампурнефтегаз»', person='Захарова Людмила Григорьевна',
         role='контактное лицо закупки', phone='7-34936-59999 доб. 15215', phone_type='прямой',
         email='ZakharovaLG@kharampurneftegaz.ru', source='ТЭК-Торг',
         source_url='https://www.tektorg.ru/rosneft/procedures/19446134',
         observed_at='2026-07-29', proof_level='1', note=''),
    dict(inn='', organization='АО «НК «Роснефть» — Кубаньнефтепродукт»',
         person='Попова Елена Владимировна', role='контактное лицо закупки',
         phone='8-861-202-75-15', phone_type='прямой', email='e_popova1@knp.rosneft.ru',
         source='ТЭК-Торг', source_url='https://www.tektorg.ru/market/procedures/19461551',
         observed_at='2026-07-29', proof_level='1', note='процедура опубликована 22.07.2026'),
    dict(inn='', organization='ООО «РН-Ведомственная охрана»', person='Тхагушева Марина',
         role='контактное лицо закупки', phone='+7 928 232 10 23', phone_type='мобильный',
         email='mi_tkhagusheva@rn-vo.rosneft.ru', source='ТЭК-Торг',
         source_url='https://www.tektorg.ru/market/procedures/19463349',
         observed_at='2026-07-29', proof_level='1', note='единственный мобильный в выборке ТЭК-Торга'),
    dict(inn='', organization='ООО «Башнефть-Строй»', person='Фаизов Динар Рауфович',
         role='контактное лицо закупки', phone='8 (347) 262-17-63', phone_type='прямой',
         email='FAIZOVDR@bn.rosneft.ru', source='ТЭК-Торг',
         source_url='https://www.tektorg.ru/market/procedures/19464108',
         observed_at='2026-07-29', proof_level='1',
         note='схема почты отличается от соседних дочек того же холдинга'),
    dict(inn='', organization='АО «НК «Роснефть»-Мурманскнефтепродукт»',
         person='Комиссаров Антон Владимирович', role='контактное лицо закупки',
         phone='48-70-00 доб. 147', phone_type='прямой', email='av_komissarov@mnp.rosneft.ru',
         source='ТЭК-Торг', source_url='https://www.tektorg.ru/market/procedures/19464942',
         observed_at='2026-07-29', proof_level='1', note=''),

    # ЭТП ГПБ. Карточки открыты без регистрации, документы скачиваются.
    dict(inn='', organization='АО «Газпром газораспределение Тула»',
         person='Яковлева Ольга Борисовна', role='контактное лицо закупки',
         phone='+7 4872 25-24-00 доб. 1132', phone_type='прямой',
         email='YakovlevaOB@tulaoblgaz.ru', source='ЭТП ГПБ',
         source_url='https://etpgpb.ru/procedures/etp/472436-kompressor/',
         observed_at='2026-07-29', proof_level='1',
         note='в карточке техническая часть ТЗ на компрессор Remeza 10/15В'),
    dict(inn='', organization='АО «РКЦ «Прогресс»', person='Готовцева Ольга Владимировна',
         role='контактное лицо закупки', phone='+7 846 920-00-16', phone_type='отдел',
         email='zakupki@samspace.ru', source='ЭТП ГПБ',
         source_url='https://etpgpb.ru/procedures/etp/290673-kompressor/',
         observed_at='2026-07-29', proof_level='1', note='закупка 2019 года, контакт архивный'),
    dict(inn='', organization='АО «РКЦ «Прогресс»', person='Гурина Екатерина Владимировна',
         role='контактное лицо закупки', phone='+7 846 228-54-30', phone_type='отдел',
         email='zakupki@samspace.ru', source='ЭТП ГПБ',
         source_url='https://etpgpb.ru/procedures/etp/591686-kompressor/',
         observed_at='2026-07-29', proof_level='1', note=''),
    dict(inn='', organization='ФГУП «НПЦ» (завод «Звезда»)', person='Иванова Елена Владимировна',
         role='контактное лицо закупки', phone='+7 48235 4-49-36', phone_type='отдел',
         email='zakupki@zavod-zvezda.ru', source='ЭТП ГПБ',
         source_url='https://etpgpb.ru/procedures/etp/196892-kompressory-i-zip-dlya-kompressorov/',
         observed_at='2026-07-29', proof_level='1', note='закупка 2018 года'),
    dict(inn='', organization='ФГУП «НПЦ» (завод «Звезда»)', person='Матросова Наталия Николаевна',
         role='контактное лицо закупки', phone='+7 48235 4-49-36', phone_type='отдел',
         email='zakupki@zavod-zvezda.ru', source='ЭТП ГПБ',
         source_url='https://etpgpb.ru/procedures/etp/218068-kompressory-i-zip-dlya-kompressorov/',
         observed_at='2026-07-29', proof_level='1', note=''),

    # РТС-тендер: контакт лежит прямо в выдаче вместе с ИНН и КПП.
    dict(inn='6234147017', organization='МКУ г. Рязани «Муниципальный центр торгов»',
         person='Савичева Светлана Петровна', role='контактное лицо (организатор)',
         phone='8-4912-502476', phone_type='отдел', email='zakupki44@mctrzn.ru',
         source='РТС-тендер', source_url='https://www.rts-tender.ru/poisk/search?keywords=компрессор',
         observed_at='2026-07-29', proof_level='1',
         note='организатор, а не заказчик — по 44-ФЗ это уполномоченный орган'),
    dict(inn='9001023536', organization='ГУП «Автотранс Запорожской области»',
         person='Внуков Алексей Игоревич', role='контактное лицо (организатор)',
         phone='7-990-2601917', phone_type='мобильный', email='adm@gupatz.ru',
         source='РТС-тендер', source_url='https://www.rts-tender.ru/poisk/search?keywords=компрессор',
         observed_at='2026-07-29', proof_level='1', note=''),

    # Фабрикант: в карточке ФИО, мобильный, почта и ИНН обеих сторон.
    dict(inn='3000009496', organization='ООО «ПРОФИ» (организатор торгов)',
         person='Ковалева Евгения Сергеевна', role='контактное лицо',
         phone='8-996-427-07-14', phone_type='мобильный', email='profi-tver@inbox.ru',
         source='Фабрикант', source_url='https://www.fabrikant.ru/procedure/search?query=компрессор',
         observed_at='2026-07-29', proof_level='1',
         note='карточка не компрессорная — проверена структура полей'),

    # e-disclosure: карточка компании по ИНН отдаёт руководителя и его телефон.
    dict(inn='1658008723', organization='ПАО «Казаньоргсинтез»', person='Сафин Айрат Фоатович',
         role='руководитель', phone='(843) 533-98-10', phone_type='приёмная', email='',
         source='e-disclosure', source_url='https://www.e-disclosure.ru/portal/company.aspx?id=938',
         observed_at='2026-07-29', proof_level='1', note='49 компрессоров с истекающим сроком ЭПБ'),
    dict(inn='4823006703', organization='ПАО «НЛМК»', person='Каратаев Сергей Михайлович',
         role='руководитель', phone='(4742) 444-006', phone_type='приёмная', email='',
         source='e-disclosure', source_url='https://www.e-disclosure.ru/portal/company.aspx?id=2509',
         observed_at='2026-07-29', proof_level='1', note='7 центробежных с истекающим сроком'),
    dict(inn='0277014204', organization='ПАО «Уфаоргсинтез»', person='Каширин Николай Павлович',
         role='руководитель', phone='(347) 249-49-20', phone_type='приёмная', email='',
         source='e-disclosure', source_url='https://www.e-disclosure.ru/portal/company.aspx?id=2017',
         observed_at='2026-07-29', proof_level='1', note='69 компрессоров с истекающим сроком'),

    # Гриф «УТВЕРЖДАЮ» на титульном листе ТЗ. Подпись была только в скане.
    dict(inn='', organization='ПАО «Коршуновский ГОК» (группа «Мечел»)', person='Квятковский П. Л.',
         role='директор департамента по операционной деятельности',
         phone='', phone_type='', email='', source='ТЗ на ЭТП ГПБ (скан, гриф УТВЕРЖДАЮ)',
         source_url='https://etpgpb.ru/procedures/etp/937258-postavka-kompressornoy-ustanovki/',
         observed_at='2024-04-03', proof_level='1',
         note='ТЗ на компрессорную установку для электровоза ВЛ-41, 2 шт; дата — дата подписи'),

    # Арбитраж: обезличивание пропустило должностное лицо внутри цитаты документа.
    dict(inn='', organization='АО «Востсибнефтегаз»', person='Клюшин М. Г.',
         role='заместитель генерального директора по производству — главный инженер',
         phone='', phone_type='', email='', source='Арбитраж (sudact)',
         source_url='https://sudact.ru/arbitral/doc/1tYr6mQ4AZNO/',
         observed_at='2026-07-29', proof_level='2',
         note='дело о поставке компрессоров; телефона в решении нет; инициалы без отчества'),

    # Вебархив: текущие и прежние держатели роли с датами снимков.
    dict(inn='', organization='Филиал ПАО «Россети Волга» — «Мордовэнерго»',
         person='Федоськин Михаил Петрович', role='заместитель директора — главный инженер',
         phone='(8342) 28-00-59', phone_type='приёмная', email='priem@moren.ru',
         source='Вебархив (снимок 19.05.2026)',
         source_url='https://web.archive.org/web/20260519/https://www.rossetivolga.ru/ru/o_kompanii/filiali/filial_oao__mrsk_volgi_____mordovenergo_/menedzhment_filiala/',
         observed_at='2026-05-19', proof_level='1', note='сменил Галишникова'),
    dict(inn='', organization='Филиал ПАО «Россети Волга» — «Мордовэнерго»',
         person='Галишников Сергей Николаевич', role='директор филиала',
         phone='(8342) 28-00-59', phone_type='приёмная', email='priem@moren.ru',
         source='Вебархив (снимок 19.05.2026)',
         source_url='https://web.archive.org/web/20260519/https://www.rossetivolga.ru/ru/o_kompanii/filiali/filial_oao__mrsk_volgi_____mordovenergo_/menedzhment_filiala/',
         observed_at='2026-05-19', proof_level='1',
         note='в 2021 был главным инженером — вырос внутри, тёплый контакт'),
    dict(inn='', organization='Филиал ПАО «Россети Волга» — «Пензаэнерго»',
         person='Кузнецов Александр Павлович', role='заместитель директора — главный инженер',
         phone='', phone_type='', email='', source='Вебархив (снимок 17.02.2026)',
         source_url='https://web.archive.org/web/20260217/https://www.rossetivolga.ru/ru/o_kompanii/filiali/filial_oao__mrsk_volgi_____penzaenergo_/menedzhment_filiala/',
         observed_at='2026-02-17', proof_level='1', note='сменил Кожевникова М. А.'),
    dict(inn='', organization='Филиал ПАО «Россети Волга» — «Ульяновские РС»',
         person='Кожуров Егор Сергеевич', role='заместитель директора — главный инженер',
         phone='', phone_type='', email='', source='Вебархив (снимок 26.02.2026)',
         source_url='https://web.archive.org/web/20260226/https://www.rossetivolga.ru/ru/o_kompanii/filiali/filial__ulyanovskie_raspredelitelnie_seti_/menedzhment_filiala/',
         observed_at='2026-02-26', proof_level='1',
         note='держит роль с 2023 — редкий стабильный случай'),
]


def load_rosseti():
    """Собранное ранее через страницы «Руководство» — уже с провенансом."""
    rows = []
    if not os.path.exists(ROSSETI):
        return rows
    with open(ROSSETI, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f, delimiter=';'):
            rows.append(dict(
                inn='', organization=r.get('organization', ''), person=r.get('person', ''),
                role=r.get('role', ''), phone=r.get('phone', ''),
                phone_type='прямой' if 'прямой' in (r.get('note') or '') else 'приёмная',
                email=r.get('email', ''), source='Страница «Руководство»',
                source_url=r.get('source_url', ''), observed_at=r.get('observed_at', ''),
                proof_level=r.get('proof_level', ''), note=r.get('note', '')))
    return rows


def main():
    epb, epb_centro = load_epb()
    rows = load_rosseti() + SEED
    out = []
    for r in rows:
        inn = (r.get('inn') or '').strip()
        n = epb.get(inn, 0)
        nc = epb_centro.get(inn, 0)
        group, rw = role_weight(r.get('role'))
        pw = phone_weight(r.get('phone'), r.get('phone_type'))
        ew = email_weight(r.get('email'))
        fw = fresh_weight(r.get('observed_at'))
        cw = company_weight(n, nc)
        score = round(rw * (pw + ew) * fw * cw, 2)
        email = r.get('email') or ''
        local = email.split('@')[0].lower() if email else ''
        etype = ('общая' if local in ('zakupki', 'info', 'office', 'mail', 'priem', 'adm',
                                      'secretary', 'tender') else 'именная') if email else ''
        out.append({
            'inn': inn, 'organization': r.get('organization', ''), 'person': r.get('person', ''),
            'role': r.get('role', ''), 'role_group': group, 'phone': r.get('phone', ''),
            'phone_type': r.get('phone_type', ''), 'email': email, 'email_type': etype,
            'source': r.get('source', ''), 'source_url': r.get('source_url', ''),
            'observed_at': r.get('observed_at', ''), 'proof_level': r.get('proof_level', ''),
            'epb_expiring': n, 'epb_centro': nc, 'score': score,
            'note': r.get('note', ''),
        })

    out.sort(key=lambda x: -x['score'])
    with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';')
        w.writeheader()
        w.writerows(out)

    orgs = len({(x['inn'] or x['organization']) for x in out})
    with_phone = sum(1 for x in out if x['phone'])
    print(f'записей {len(out)}, организаций {orgs}, с телефоном {with_phone}')
    print(f'-> {OUT}')
    print('\nтоп-10 по приоритету:')
    for x in out[:10]:
        print(f"  {x['score']:6.2f}  {x['person'][:28]:28} | {x['role_group']:12} | "
              f"{x['organization'][:32]:32} | ЭПБ {x['epb_expiring']:3} "
              f"| центроб. {x['epb_centro']}")


if __name__ == '__main__':
    main()
