# -*- coding: utf-8 -*-
r"""Запись в enrich.db контактов с ДВУХ тендерных площадок, которых у нас не было:
ТЭК-Торг (tektorg.ru) и Tender.pro.

Сбор сырья делают отдельные стадии (они сетевые и долгие, им нужен свой бюджет):
    _tek_orgs.py    — обход листингов ТЭК-Торга -> организаторы + id процедур
    _tek_cards.py   — карточки процедур -> ИНН организатора + контактное лицо
    _tp_collect.py  — Tender.pro: компания по ИНН -> тендеры -> текст комментария
    _tp_llm (песочница) — разбор свободного текста провайдером
Сырьё лежит durable на сервере:
    C:\seostat\drop\drop-storage\tek_cards.json
    C:\seostat\drop\drop-storage\tp_raw.json
    C:\seostat\drop\drop-storage\tp_contacts.json  (после разбора провайдером)

ФОРМА ИСТОЧНИКОВ (снята живьём):

ТЭК-Торг — Next.js с SSR. В `<script id="__NEXT_DATA__">` лежит
`props.pageProps.procedureItem` с ГОТОВЫМИ полями: inn, kpp, organizerName,
contactPerson, contactPhone, contactEmail, dates.datePublished. Разбирать HTML
не нужно. Проверено на примере владельца: АО «РНПК», ИНН 6227007322 ->
«Деркач Надежда Юрьевна», 7-4912-933001, DerkachNY@rnpk.rosneft.ru.
ВНИМАНИЕ: сайт закрыт защитой Variti для чужих IP (бесконечный 307 и страница
«сеанс прерван системой защиты от ботов»), а с сервера владельца открывается
обычным urllib. Гонять только на сервере.

Tender.pro — обычный HTML, карточка `/api/tender/<id>/view_public` без логина,
контакт СВОБОДНЫМ ТЕКСТОМ в блоке «Комментарий:».

ПРИВЯЗКА ЗАКРЫТА ПО УМОЛЧАНИЮ (ловушка «Криогенмаш / Завод криогенного маш-я»):
  * ТЭК-Торг: пишем, только если `procedureItem.inn` РАВЕН ИНН из companies;
  * Tender.pro: ИНН обязан найтись на карточке компании И организатор тендера
    обязан совпасть с этой карточкой (проверено на стадии сбора).

СВЕЖЕСТЬ (правило владельца): до 2 лет — «свежий», 2–3 года — «устаревший»,
старше 3 лет НЕ БЕРЁМ. Дата закупки хранится в source и в people.observed_at.

ДЕДУП ПО ЧЕЛОВЕКУ: один снабженец ведёт десятки закупок — схлопываем по
нормализованному телефону/почте внутри компании, оставляя САМУЮ СВЕЖУЮ закупку
как source_url.

Запуск:  python tender_platforms.py [--apply] [--source tektorg|tenderpro|both]
Без --apply — сухой прогон (ничего не пишет, только считает).
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ИСТОЧНИК = 'both'
for i, a in enumerate(sys.argv):
    if a == '--source' and i + 1 < len(sys.argv):
        ИСТОЧНИК = sys.argv[i + 1]
ТЕК = r'C:\seostat\drop\drop-storage\tek_cards.json'
ТП = r'C:\seostat\drop\drop-storage\tp_contacts.json'
ЖУРНАЛ = r'C:\seostat\drop\tender_platforms_write.jsonl'
СЕЙЧАС = time.time()
ГОД = 365.25 * 86400
ПРЕДЕЛ_ЛЕТ, УСТАР_ЛЕТ = 3.0, 2.0
ГОРЯЧЕЕ = re.compile(
    r'компрессор|воздуходувк|осушител\w+\s+воздух|фильтр|азот\w*|кислород\w*|'
    r'\bМКС\b|мембранн\w+\s+газоразделит|винтов\w+\s+блок|ресивер|'
    r'пневмосет|сжат\w+\s+воздух', re.I)
_ШУМ_ДОМЕН = ('tender.pro', 'tektorg.ru', 'proventus-pro.ru', 'roseltorg.ru')
_ШУМ_ТЕЛ = ('4952151438', '8002503268', '4957348118', '4997058118')


def тел10(s):
    d = re.sub(r'\D', '', s or '')
    return d[-10:] if len(d) >= 10 else ''


def нормтел(s):
    """Развести номер и добавочный, если источник склеил их без разделителя.

    ТЭК-Торг отдаёт contactPhone строкой, и добавочный там то через пробел
    («7-3466-625000 6185»), то ВПРИТЫК («8-346-66742423665» = 8-3466-674242
    доб. 3665). Пятнадцать цифр подряд продажник наберёт и попадёт в никуда —
    ровно та ошибка «номер выглядит рабочим, а он склейка» (передача, 4.7).
    Российский номер это 11 цифр, поэтому хвост сверх одиннадцати — добавочный.
    """
    s = re.sub(r'\s+', ' ', (s or '')).strip(' .,;:')
    if not s:
        return ''
    if re.search(r'доб|вн\.', s, re.I):
        return s[:60]
    d = re.sub(r'\D', '', s)
    if len(d) < 10:
        return ''                       # обрывок — не номер
    if len(d) <= 11:
        return s[:60]
    осн, доб = d[:11], d[11:]
    if len(доб) > 6:
        return ''                       # не разобрать, честнее не писать вовсе
    return f'{осн} доб. {доб}'


def мусор_тел(t):
    d = тел10(t)
    return (not d) or d in _ШУМ_ТЕЛ


def мусор_почта(e):
    e = (e or '').lower().strip()
    if not e or '@' not in e or '.' not in e.split('@')[-1]:
        return True
    dom = e.split('@')[-1]
    return any(dom == d or dom.endswith('.' + d) for d in _ШУМ_ДОМЕН)


def лет(д):
    s = str(д or '')
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        g = m.groups()
    else:
        m2 = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', s)
        if not m2:
            return None
        g = (m2.group(3), m2.group(2), m2.group(1))
    try:
        t = time.mktime((int(g[0]), int(g[1]), int(g[2]), 12, 0, 0, 0, 1, -1))
    except Exception:  # noqa: BLE001
        return None
    return (СЕЙЧАС - t) / ГОД


def свеж(л):
    if л is None:
        return 'неизвестна'
    return 'свежий' if л <= УСТАР_ЛЕТ else ('устаревший' if л <= ПРЕДЕЛ_ЛЕТ
                                            else 'просрочен')


def iso(д):
    s = str(д or '')
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s)
    if m:
        return m.group(1)
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', s)
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else ''


def схлопнуть(находки):
    """Дедуп ПО ЧЕЛОВЕКУ внутри компании. Самая свежая закупка -> source_url."""
    по = {}
    for f in находки:
        ключ = (f.get('email') or '').lower() or тел10(f.get('phone') or '') \
            or (f.get('person') or '').lower()
        if not ключ:
            continue
        было = по.get(ключ)
        if было is None:
            по[ключ] = dict(f, повторов=1)
            continue
        было['повторов'] += 1
        л1, л2 = было.get('лет'), f.get('лет')
        if (л2 is not None) and (л1 is None or л2 < л1):
            для = ('url', 'дата', 'лет', 'свежесть', 'предмет')
            для = {k: f.get(k) for k in для}
            было.update({k: v for k, v in для.items() if v})
        for поле in ('person', 'post', 'phone', 'email'):
            if not было.get(поле) and f.get(поле):
                было[поле] = f[поле]
    return list(по.values())


def main():
    db = EDB.EnrichDB()
    база = {r[0] for r in db.cx.execute('SELECT inn FROM companies')}
    имена = {r[0]: (r[1] or '') for r in
             db.cx.execute('SELECT inn, name FROM companies')}
    по_инн = {}

    # ---------- ТЭК-Торг ----------
    диаг = {'tek_карточек': 0, 'tek_инн_всего': 0, 'tek_инн_в_базе': 0,
            'tek_вне_базы': 0, 'tek_просрочено': 0,
            'tp_записей': 0, 'tp_инн_в_базе': 0, 'tp_низкая_уверенность': 0}
    вне_базы = {}
    if ИСТОЧНИК in ('tektorg', 'both') and os.path.exists(ТЕК):
        d = json.load(open(ТЕК, encoding='utf-8'))
        карт = list((d.get('карточки') or {}).values())
        диаг['tek_карточек'] = len(карт)
        диаг['tek_инн_всего'] = len({x.get('inn') for x in карт if x.get('inn')})
        for x in карт:
            inn = str(x.get('inn') or '')
            if not inn:
                continue
            if inn not in база:
                з = вне_базы.setdefault(inn, {'орг': x.get('орг', ''), 'n': 0,
                                              'person': x.get('person', ''),
                                              'email': x.get('email', '')})
                з['n'] += 1
                диаг['tek_вне_базы'] += 1
                continue
            л = лет(x.get('дата'))
            if л is not None and л > ПРЕДЕЛ_ЛЕТ:
                диаг['tek_просрочено'] += 1
                continue
            по_инн.setdefault(inn, []).append({
                'person': (x.get('person') or '').strip(),
                'post': '', 'phone': нормтел(x.get('phone')),
                'email': (x.get('email') or '').strip().lower(),
                'дата': x.get('дата', ''), 'лет': л, 'свежесть': свеж(л),
                'предмет': x.get('предмет', ''),
                'url': 'https://www.tektorg.ru' + x.get('путь', ''),
                'площадка': 'tektorg'})
        диаг['tek_инн_в_базе'] = len(по_инн)

    # ---------- Tender.pro (после разбора провайдером) ----------
    if ИСТОЧНИК in ('tenderpro', 'both') and os.path.exists(ТП):
        d = json.load(open(ТП, encoding='utf-8'))
        зап = d if isinstance(d, list) else (d.get('контакты') or [])
        диаг['tp_записей'] = len(зап)
        тп_инн = set()
        for x in зап:
            inn = str(x.get('inn') or '')
            if inn not in база:
                continue
            if (x.get('уверенность') or '') == 'низкая' and not x.get('email'):
                диаг['tp_низкая_уверенность'] += 1
                continue
            л = лет(x.get('дата'))
            if л is not None and л > ПРЕДЕЛ_ЛЕТ:
                continue
            тп_инн.add(inn)
            по_инн.setdefault(inn, []).append({
                'person': (x.get('person') or '').strip(),
                'post': (x.get('post') or '').strip(),
                'phone': нормтел(x.get('phone')),
                'email': (x.get('email') or '').strip().lower(),
                'дата': x.get('дата', ''), 'лет': л, 'свежесть': свеж(л),
                'предмет': x.get('предмет', ''), 'url': x.get('url', ''),
                'площадка': 'tenderpro'})
        диаг['tp_инн_в_базе'] = len(тп_инн)

    # ---------- РУБЕЖ: организатор-агент ----------
    # АО «Русская медная компания» (6670061296) зарегистрировано на Tender.pro
    # организатором, но публикует закупки за десяток НЕ своих юрлиц: почты
    # контактов сидят на amurminerals.ru, agrk.ru, careplant.ru, tomgok.ru…
    # Записать их под ИНН РМК — это ровно ошибка «чужие контакты под нашей
    # компанией» (передача, 4.1). Признак: три и более разных почтовых домена и
    # ни одного, который набирает половину. Такие компании пропускаем целиком,
    # а внутри прошедших выкидываем одиночные почты не из главного домена.
    диаг['агентов_отсечено'] = 0
    диаг['чужой_домен_отсечено'] = 0
    for inn in list(по_инн):
        домены = {}
        for f in по_инн[inn]:
            e = (f.get('email') or '').lower()
            if '@' in e:
                d0 = e.split('@')[-1]
                домены[d0] = домены.get(d0, 0) + 1
        if not домены:
            continue
        всего = sum(домены.values())
        глав, макс = max(домены.items(), key=lambda kv: kv[1])
        if len(домены) >= 3 and макс * 2 < всего:
            диаг['агентов_отсечено'] += 1
            print('АГЕНТ пропущен: %s домены %s' % (inn, домены), flush=True)
            del по_инн[inn]
            continue
        оставили = []
        for f in по_инн[inn]:
            e = (f.get('email') or '').lower()
            if '@' in e and e.split('@')[-1] != глав and домены.get(e.split('@')[-1], 0) * 4 < всего:
                диаг['чужой_домен_отсечено'] += 1
                continue
            оставили.append(f)
        по_инн[inn] = оставили

    ст = {'режим': 'ПРИМЕНЯЮ' if ПРИМЕНИТЬ else 'сухой', 'компаний': len(по_инн),
          'находок': sum(len(v) for v in по_инн.values()), 'после_дедупа': 0,
          'людей': 0, 'телефонов': 0, 'почт': 0, 'сигналов': 0,
          'с_ролью': 0, 'технических': 0}
    print('СТАРТ ' + json.dumps(dict(ст, **диаг), ensure_ascii=False), flush=True)
    ж = io.open(ЖУРНАЛ, 'a', encoding='utf-8')
    примеры = []
    for inn, нах in по_инн.items():
        своё = схлопнуть(нах)
        ст['после_дедупа'] += len(своё)
        for f in своё:
            роль_т = f.get('post') or ''
            роль = EDB.EnrichDB._canon_role(роль_т) if роль_т else ''
            src = f"{f['площадка']}:{f['свежесть']}:{iso(f.get('дата'))}"
            if роль and роль != 'общий':
                ст['с_ролью'] += 1
            if роль in EDB.EnrichDB.TECH_ROLES:
                ст['технических'] += 1
            стр = {'inn': inn, 'name': имена.get(inn, '')[:60], **f,
                   'роль': роль, 'src': src}
            ж.write(json.dumps(стр, ensure_ascii=False) + '\n')
            if len(примеры) < 14:
                примеры.append({k: стр.get(k) for k in
                                ('inn', 'name', 'person', 'post', 'phone',
                                 'email', 'дата', 'свежесть', 'url', 'площадка')})
            if not ПРИМЕНИТЬ:
                continue
            if f.get('person'):
                db.add_person(inn, f['person'], post=роль_т,
                              phone=f.get('phone') or '', email=f.get('email') or '',
                              source=src, source_url=f.get('url') or '',
                              observed_at=iso(f.get('дата')))
                ст['людей'] += 1
            if f.get('phone') and not мусор_тел(f['phone']):
                db.cx.execute(
                    'INSERT OR IGNORE INTO phone_contacts'
                    '(inn, phone, person, role, source, source_url, updated_at) '
                    'VALUES(?,?,?,?,?,?,?)',
                    (inn, f['phone'][:60], (f.get('person') or '')[:120],
                     роль or 'снабжение/закупки', src, f.get('url') or '',
                     time.strftime('%Y-%m-%dT%H:%M:%S')))
                ст['телефонов'] += 1
            if f.get('email') and not мусор_почта(f['email']):
                db.add_email(inn, f['email'], role=(роль_т or 'закупки'),
                             person=f.get('person') or '', source=src,
                             source_url=f.get('url') or '')
                ст['почт'] += 1
            if ГОРЯЧЕЕ.search(f.get('предмет') or ''):
                db.add_signal(inn, source=f['площадка'], event_type='закупка',
                              what=(f.get('предмет') or '')[:400],
                              source_url=f.get('url') or '', hotness=2,
                              ts=iso(f.get('дата')))
                ст['сигналов'] += 1
        if ПРИМЕНИТЬ:
            db.cx.commit()
            db.mark_stage(inn, 'tender_platforms', f'контактов {len(своё)}')
    ж.flush()
    os.fsync(ж.fileno())
    ж.close()
    # НЕ в базе — Роснефть-контур и прочие: отдельный файл, это НОВЫЕ лиды
    if вне_базы:
        п = r'C:\seostat\drop\drop-storage\tek_new_leads.json'
        with open(п, 'w', encoding='utf-8') as f:
            json.dump(вне_базы, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        ст['новых_лидов_вне_базы'] = len(вне_базы)
    print('ПРИМЕРЫ ' + json.dumps(примеры, ensure_ascii=False)[:3500], flush=True)
    # цифры ИЗ БАЗЫ, а не из счётчика прогона (между ними чистка и дедуп)
    из_базы = {}
    for имя, зпр in (
            ('людей_в_базе', "SELECT COUNT(*) FROM people WHERE source LIKE 'tektorg%' "
                             "OR source LIKE 'tenderpro%'"),
            ('людей_техЛПР', "SELECT COUNT(*) FROM people WHERE (source LIKE 'tektorg%' "
                             "OR source LIKE 'tenderpro%') AND role IN ('%s')"
                             % "','".join(EDB.EnrichDB.TECH_ROLES)),
            ('телефонов_в_базе', "SELECT COUNT(*) FROM phone_contacts WHERE "
                                 "source LIKE 'tektorg%' OR source LIKE 'tenderpro%'"),
            ('почт_в_базе', "SELECT COUNT(*) FROM emails WHERE source LIKE 'tektorg%' "
                            "OR source LIKE 'tenderpro%'"),
            ('компаний_в_базе', "SELECT COUNT(DISTINCT inn) FROM phone_contacts WHERE "
                                "source LIKE 'tektorg%' OR source LIKE 'tenderpro%'"),
            ('сигналов_в_базе', "SELECT COUNT(*) FROM signals WHERE source IN "
                                "('tektorg','tenderpro')")):
        try:
            из_базы[имя] = db.cx.execute(зпр).fetchone()[0]
        except Exception as ex:  # noqa: BLE001
            из_базы[имя] = 'err:' + repr(ex)[:50]
    print('ИТОГ ' + json.dumps(dict(ст, **диаг), ensure_ascii=False), flush=True)
    print('ИЗ_БАЗЫ ' + json.dumps(из_базы, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
    os._exit(0)
