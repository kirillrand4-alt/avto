# -*- coding: utf-8 -*-
"""Сводка по трём состояниям предприятия: машина УЖЕ СТОИТ, ПОКУПАЕТ, ПЛАНИРУЕТ купить.

Зачем именно так. Все три вещи у нас собраны, но лежат в разных файлах и разными словами:
износ — в реестре экспертизы промбезопасности, состоявшиеся закупки — в шести выгрузках
площадок, намерения — в планах закупки 223-ФЗ. Продавцу нужна одна строка: предприятие, марка
машины, дата и ссылка, по которой это можно проверить.

Три состояния и чем каждое доказано:

- **есть** — заключение экспертизы промышленной безопасности. Экспертиза делается, когда машина
  выработала назначенный срок службы, поэтому у записи есть **дата окончания продления** —
  государством поставленный срок, а не наша догадка. Марка машины напечатана в тексте объекта.
- **покупает** — состоявшаяся процедура на площадке. Дата публикации, предмет, ссылка на лот.
- **планирует** — позиция плана закупки 223-ФЗ с **датой размещения в будущем**. Единственный
  источник, смотрящий вперёд.

Марка машины вытаскивается шаблоном, и шаблон проверен контрольным набором (`--kontrol`):
он обязан брать `К-500-61-1`, `ЦК-135/8`, `ТВ 175-1,6М-02`, `305ВП-16/70`, `GA90`, `ДЭН-37Ш` и
обязан НЕ брать ИНН, ОГРН, суммы, даты, коды ОКПД (`28.13.23.000`), номера ГОСТ и регномера
закупок. Без такого набора шаблон марки — самый вероятный источник мусора в этой сводке: за
десять цифр подряд у нас уже принимали и координаты векторной графики, и ИНН.

Использование:
    python3 svod_tri_sostoyaniya.py --kontrol     # проверка шаблона марки на эталонах
    python3 svod_tri_sostoyaniya.py              # собрать сводку
"""
import csv
import glob
import os
import re
import urllib.parse
import sys
from collections import Counter, defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
C = os.path.join(BAZA, 'engineers-lens', 'centro')
OUT_FAKTY = os.path.join(BAZA, 'engineers-lens', 'SVOD-tri-sostoyaniya.csv')
OUT_PRED = os.path.join(BAZA, 'engineers-lens', 'SVOD-po-predpriyatiyam.csv')

# Обозначение машины. Русские и латинские серии, цифры с дробями и запятыми, необязательный
# цифровой префикс (305ВП-16/70) и буквенный хвост (ТВ 175-1,6М-02).
MARKA = re.compile(
    r'(?<![\w\-])('
    r'(?:\d{1,3})?[А-ЯЁA-Z]{1,4}[\s\-]?\d{1,4}(?:[,.]\d{1,2})?[А-ЯЁA-Za-z]{0,2}'
    r'(?:[\-/][\dА-ЯЁA-Za-z,.]{1,6}){0,3}'
    r')(?![\w])')
# Что шаблону запрещено: рядом стоит слово, объясняющее, что это не марка.
NE_MARKA_RYADOM = re.compile(r'(?:ИНН|ОГРН|КПП|ОКПД|ОКВЭД|ГОСТ|ТУ|СНиП|СП|руб|₽|№\s*зак|'
                             r'регистрационн|извещени|лот\s*№)\D{0,3}$', re.I)
# Стоп-список: обозначения, которые шаблон берёт, а нашей машиной они не являются. Список
# пришёл от линзы, прогнанной по живым строкам сводки, и каждый пункт там подкреплён ИНН:
# диаметры трубопроводов (DN 100), производительность (100М3/Ч), котлы (БКЗ-420-140-5,
# КВГМ-100-150), подогреватели (2ПНД-1, ПВД-8А), парогенераторы (2ПГ-1), питательные насосы
# (1ПП-10, ПН130), дымососы (ДС-400, 4Д 315-50), турбогенераторы (2ТГ-80-1,4), резервуары
# (РВС-1000), разъединители (0РЭ2500/12КВ), станки (16К14Б), чертёжные номера (2А-3553.00-А).
NE_NASHA_MASHINA = re.compile(
    r'^(?:DN\s?\d|\d+\s?М\s?3|\d+М3|РВС-|БКЗ-|КВГМ-|ПТВМ-|\d?ПВД-|\d?ПНД-|\d?ПСГ-|\d?ПГ-\d|\d?ПП-\d|ПН\d|'
    r'ДС-|ДСП-|\d?Д\s?\d{3}|ТГ-\d|\dТГ-|0РЭ|\d+К\d+[А-ЯЁ]?$|У-\d{3}$|\dУ-\d{3}$)'
    r'|\d+\s?ОБ/МИН|\d+\s?КВ$|\.\d\d-[А-ЯЁ]|\.00-', re.I)


# Само значение не марка, если это дата, сумма, длинное число или одна буква с одной цифрой.
# Серии центробежных машин — те же, что в классификаторе. Нужны здесь ровно для порядка
# показа: центробежная серия важнее случайного обозначения узла.
CENTR_SERIYA_SVOD = re.compile(
    r'^(?:К[\s\-]?\d{3}|ЦК|ЦТК|ВЦ|ТВ[\s\-]?\d|ТГ[\s\-]?\d|ЗТВ|ХТК|ТКА|КТК|Centac|ZH|ZR|'
    r'HIBON|Neuros|STC|RIK|MSG)', re.I)


def marka_godna(s):
    t = s.strip()
    if len(t) < 4:
        return False
    if re.fullmatch(r'[\d.,\s]+', t):                    # только цифры — не марка
        return False
    if re.fullmatch(r'\d{2}\.\d{2}\.\d{2,4}', t):        # дата
        return False
    if len(re.sub(r'\D', '', t)) > 8:                    # ИНН, ОГРН, регномер
        return False
    if not re.search(r'\d', t) or not re.search(r'[А-ЯЁA-Z]', t):
        return False
    if re.fullmatch(r'[А-ЯЁA-Z]{1,4}[\s\-]?\d', t):      # «В 1», «АО 2» — слишком коротко
        return False
    if NE_NASHA_MASHINA.search(t):                       # котёл, насос, дымосос, диаметр трубы
        return False
    return True


def marki_iz(text):
    out = []
    for m in MARKA.finditer(text or ''):
        if NE_MARKA_RYADOM.search((text or '')[max(0, m.start() - 16):m.start()]):
            continue
        s = m.group(1).strip()
        if marka_godna(s) and s not in out:
            out.append(s)
    return out


KONTROL = [
    # (строка, ожидаем ли марку)
    ('компрессор центробежный К-500-61-1 поз. 1/4, зав. № 489', True),
    ('Центробежный кислородный компрессор КТК-12,5/35 ст. № 4', True),
    ('воздуходувка ТВ 175-1,6М-02', True),
    ('компрессор 305ВП-16/70', True),
    ('Поставка запасных частей для компрессора Atlas Copco GA90', True),
    ('Ремонт компрессоров: ДЭН-37Ш', True),
    ('ремонт центробежного компрессора ЦК-135/8', True),
    ('Выключатель вакуумный ВГГ-10/63-5000 У3', True),
    ('ИНН 7743013670 КПП 774301001', False),
    ('ОГРН 1083801006860', False),
    ('ОКПД2 28.13.23.000 Компрессоры для холодильного оборудования', False),
    ('Начальная цена договора 824 617,55 руб', False),
    ('извещение № 32616181237 от 06.07.2026', False),
    ('Поставка компрессоров', False),
    ('Сервисное обслуживание турбокомпрессора', False),
]


def kontrol():
    osh = 0
    print('КОНТРОЛЬ шаблона марки:')
    for s, ozh in KONTROL:
        got = marki_iz(s)
        ok = bool(got) == ozh
        osh += 0 if ok else 1
        print(f'  {"ок  " if ok else "МИМО"} ожидал {"марку" if ozh else "ничего":6} '
              f'получил {str(got)[:40]:42} ← {s[:52]!r}')
    print(f'ошибок: {osh} из {len(KONTROL)}')
    return osh


NASH = re.compile(r'компрессор|воздуходув|нагнетател|турбоагрегат|турбокомпрессор|газодув|'
                  r'компрессорн\w+\s+(?:станц|установ|цех|агрегат)', re.I)
NE_NASH = re.compile(r'турбонаддув|\bТКР\b|для\s+двигател|автомобил|холодильн\w+\s+(?:агрегат|'
                     r'машин)|кондиционер|насос(?!н\w+\s+станц)', re.I)


def nash_predmet(r, pred):
    """Предмет про нашу машину? Флаг площадки в приоритете, ключевые слова — запасной путь."""
    flag = (r.get('centrobezhnyy_predmet') or r.get('centro_priznak') or '').strip().lower()
    if flag in ('1', 'да', 'true', 'yes'):
        return True
    if flag in ('0', 'нет', 'false', 'no'):
        return bool(NASH.search(pred)) and not NE_NASH.search(pred)
    return bool(NASH.search(pred)) and not NE_NASH.search(pred)


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) if os.path.exists(p) else []


def main():
    if '--kontrol' in sys.argv:
        sys.exit(1 if kontrol() else 0)
    if kontrol():
        sys.exit('шаблон марки не проходит контроль — сводку не собираю')

    fakty = []
    # Счётчик молчаливых потерь. Строка без ИНН уходила в никуда, не оставляя следа, и узнать
    # об этом можно было только отдельным аудитом. Теперь любая такая строка считается и
    # печатается в конце — молчаливых потерь в этом модуле больше нет.
    poteri = defaultdict(int)

    # 1. ЕСТЬ: реестр заключений экспертизы промбезопасности, ВСЕ выгрузки.
    #
    # Прежде здесь стоял фильтр «в тексте объекта есть слово воздуш/воздухо», и он выбрасывал
    # **половину основного файла воздушного сегмента (215 ИНН из 431)**: у части машин
    # воздушность известна по обозначению серии, а не по слову в тексте. Плюс мимо сводки шли
    # целиком `epb-centro-vse`, `epb-processy`, `epb-uzly`, `epb-modeli-nzl` — от 60 до 84 %
    # их ИНН. Теперь строка не выбрасывается, а **помечается средой**: воздух, газ или неясно.
    # Приоритет владельца (воздух важнее газа) выражается сортировкой, а не потерей данных.
    GAZ = re.compile(r'природн\w+\s+газ|газовый|газообразн|ЦБН|ЛПУМГ|УКПГ|этан|аммиак|кислород|'
                     r'азот|водород|пропан|сероводород|нефтян\w+\s+газ', re.I)
    VOZD = re.compile(r'воздуш|воздухо|турбовозд|пневмо', re.I)
    epb_fajly = sorted(set(
        [os.path.join(C, x) for x in ('epb-vozdushnye.csv', 'epb-centro-vse.csv',
                                      'epb-centro-ochishchennyy.csv', 'epb-processy.csv',
                                      'epb-uzly.csv', 'epb-problemnye.csv')]
        + glob.glob(os.path.join(C, 'dop', 'epb-*.csv'))))
    vidano = set()
    for p in epb_fajly:
        for r in chitat(p):
            inn = (r.get('inn_zakazchika') or '').strip()
            ob = r.get('obekt') or ''
            if not inn or not re.fullmatch(r'\d{10}|\d{12}', inn):
                continue
            klyuch = (inn, (r.get('nomer') or '').strip(), ob[:60])
            if klyuch in vidano:      # одно заключение попадает в несколько выгрузок
                continue
            vidano.add(klyuch)
            sreda = ('воздух' if VOZD.search(ob) and not GAZ.search(ob)
                     else 'газ или иная среда' if GAZ.search(ob)
                     else 'среда не названа')
            fakty.append({
                'inn': inn, 'predpriyatie': (r.get('zakazchik') or '').strip()[:120],
                'sostoyanie': 'есть', 'sreda': sreda, 'marki': ' | '.join(marki_iz(ob)[:4]),
                # ВАЖНО: в колонке `srok` лежит СОСТОЯНИЕ срока, а не дата — `expired`,
                # `expiring`, `active`. Самой даты окончания продления в нашей выгрузке нет,
                # она на странице заключения. Раньше я подавал это как «дату, поставленную
                # государством»; честно — это поставленный государством СТАТУС.
                'data': (r.get('data') or '').strip(),
                'chto_za_data': 'дата заключения экспертизы',
                'srok_sluzhby': {'expired': 'срок ИСТЁК', 'expiring': 'срок ИСТЕКАЕТ в ближайший год',
                                 'active': 'срок действует'}.get((r.get('srok') or '').strip(),
                                                                 (r.get('srok') or '').strip()),
                'vyvod_ekspertizy': (r.get('vyvod') or '').strip(),
                'chem_dokazano': f'заключение ЭПБ № {(r.get("nomer") or "").strip()}',
                'tekst': re.sub(r'\s+', ' ', ob)[:300],
                'ssylka': (r.get('istochnik') or '').strip()[:200],
                'istochnik': 'реестр заключений ЭПБ, monitor-pb.ru',
            })

    # 2. ПОКУПАЕТ: состоявшиеся процедуры площадок
    ploshchadki = [
        ('Портал поставщиков Москвы', 'portal-postavshchikov-centro.csv', 'zakazchik_inn', 'zakazchik',
         'predmet', 'data_nachala', 'ssylka'),
        ('РТС-тендер', 'rts-tender-centro.csv', 'zakazchik_inn', 'zakazchik', 'predmet',
         'data_publikacii', 'ssylka'),
        # У Росэлторга колонка ИНН заказчика пуста во всех 1 834 строках, ИНН есть только у
        # организатора — 659 штук, и они терялись целиком. Организатор на этой площадке чаще
        # всего и есть заказчик, но пометка «организатор» в состоянии обязательна.
        ('Росэлторг', 'roseltorg-centro.csv', 'organizator_inn', 'organizator', 'predmet',
         'data_okonchaniya', 'ssylka'),
        ('ЭТП ГПБ', 'etpgpb-loty-centro.csv', 'inn_zakazchikov', 'zakazchiki', 'predmet',
         'data_publikacii', 'ssylka'),
    ]
    for nazv, fajl, k_inn, k_zak, k_pred, k_data, k_ssyl in ploshchadki:
        for r in chitat(os.path.join(C, fajl)):
            pred = r.get(k_pred) or ''
            # Отбор по предмету нужен, иначе в марки попадает любое оборудование: у Россетей
            # это ВЛ-220 и ПС 110 (линии и подстанции), у БГК — паровые турбины ПТ-60-130/13.
            # Но **строка не выбрасывается**: непрофильная процедура становится состоянием
            # «есть на площадке» и марки у неё не берутся. Молчаливый выброс уже стоил нам
            # 94 заказчиков Портала и 72 заказчиков РТС, которых потом искал аудит.
            nash = nash_predmet(r, pred)
            # Пустая колонка ИНН заказчика — это не «нет данных», а «данные в соседней колонке».
            # Замер 03.08: у ЭТП ГПБ 221 строка без ИНН заказчика, и у 84 из них ИНН ЕСТЬ у
            # организатора. Для Росэлторга этот урок усвоен ещё вчера (см. список выше), для
            # ЭТП ГПБ нет, и 84 строки уезжали в пустоту. Организатор — не всегда заказчик,
            # поэтому название дополняется пометкой, а не подменяется молча.
            najdeno = re.findall(r'\b(\d{10}|\d{12})\b', r.get(k_inn) or '')
            ot_organizatora = False
            if not najdeno and k_inn != 'organizator_inn':
                najdeno = re.findall(r'\b(\d{10}|\d{12})\b', r.get('inn_organizatora')
                                     or r.get('organizator_inn') or '')
                ot_organizatora = bool(najdeno)
            if not najdeno:
                poteri[f'{nazv}: ИНН не нашёлся ни у заказчика, ни у организатора'] += 1
            for inn in najdeno:
                fakty.append({
                    'inn': inn,
                    'predpriyatie': ((r.get('organizator') or '').strip()[:110] + ', организатор'
                                     if ot_organizatora
                                     else (r.get(k_zak) or '').strip()[:120]),
                    'sostoyanie': 'покупает' if nash else 'есть на площадке',
                    'marki': ' | '.join(marki_iz(pred)[:4]) if nash else '',
                    'data': (r.get(k_data) or '').strip(), 'chto_za_data': 'дата процедуры',
                    'chem_dokazano': f'процедура {(r.get("nomer") or r.get("reestrovyy_nomer") or "").strip()}',
                    'tekst': re.sub(r'\s+', ' ', pred)[:300],
                    'ssylka': (r.get(k_ssyl) or '').strip()[:200],
                    'istochnik': nazv,
                })

    # Tender.pro: ИНН лежит отдельным справочником, соединяется по company_id
    po_cid = {r['company_id']: r for r in chitat(os.path.join(C, 'tenderpro', 'tp-inn.csv'))}
    tp_vzyato = set()
    for r in chitat(os.path.join(C, 'tenderpro', 'tp-spisok.csv')):
        tp_vzyato.add((r.get('tender_id') or '').strip())
        c = po_cid.get(r.get('company_id')) or {}
        inn = (c.get('inn') or '').strip()
        if not re.fullmatch(r'\d{10}|\d{12}', inn):
            continue
        pred = r.get('predmet') or ''
        nash = nash_predmet(r, pred)
        fakty.append({
            'inn': inn, 'predpriyatie': (r.get('company') or '').strip()[:120],
            'sostoyanie': 'покупает' if nash else 'есть на площадке',
            'marki': ' | '.join(marki_iz(pred)[:4]) if nash else '',
            'data': (r.get('sozdan') or '').strip(), 'chto_za_data': 'дата процедуры',
            'chem_dokazano': f'тендер {r.get("tender_id")}',
            'tekst': re.sub(r'\s+', ' ', pred)[:300],
            'ssylka': f'https://www.tender.pro/api/tender/{r.get("tender_id")}/view_public',
            'istochnik': 'Tender.pro',
        })

    # Tender.pro, обход ПО СТРАНИЦАМ КОМПАНИЙ. Отдельный источник, потому что берётся иначе:
    # обход выше идёт по десяти ключевым словам и упирается в них, а страница компании
    # показывает всё, что она закупала. Замер 03.08 по семи крупнейшим: по словам 2 651 тендер,
    # на страницах порядка 152 000 — взята примерно одна пятидесятая.
    #
    # ИНН берётся из `inn_vladelca`, а НЕ из `inn` (по какой странице нашли). Разница не
    # косметическая: 623 закупки со страницы «РУСАЛ Менеджмент» принадлежат 21 отдельному
    # юрлицу, и приписать их управляющей компании — отправить продавца не туда. Точность
    # раскладки проверена на 4 127 строках с известным ответом: расхождений ноль
    # (`tp_vladelcy_zakupok.py`).
    for r in chitat(os.path.join(C, 'tenderpro', 'tp-zakupki-po-vladelcam.csv')):
        tid = (r.get('tender_id') or '').strip()
        inn = (r.get('inn_vladelca') or '').strip()
        if tid in tp_vzyato or not re.fullmatch(r'\d{10}|\d{12}', inn):
            continue
        tp_vzyato.add(tid)
        pred = r.get('predmet') or ''
        nash = nash_predmet(r, pred)
        fakty.append({
            'inn': inn,
            'predpriyatie': (r.get('vladelec_nazvanie') or r.get('company') or '').strip()[:120],
            'sostoyanie': 'покупает' if nash else 'есть на площадке',
            'marki': ' | '.join(marki_iz(pred)[:4]) if nash else '',
            'data': (r.get('sozdan') or '').strip(), 'chto_za_data': 'дата процедуры',
            'chem_dokazano': f'тендер {tid}',
            'tekst': re.sub(r'\s+', ' ', pred)[:300],
            'ssylka': f'https://www.tender.pro/api/tender/{tid}/view_public',
            'istochnik': 'Tender.pro, страница компании',
        })

    # Tender.pro, страница компании БЕЗ СЛОВА-ФИЛЬТРА — всё, что предприятие вообще закупало.
    # Здесь единственное место во всём модуле, где вход фильтруется ПО ПРЕДМЕТУ, и на то есть
    # причина: у одной компании бывает 170 000 закупок, из них про машины доли процента, и
    # затаскивать канцтовары и спецодежду в базу фактов о компрессорах бессмысленно — они не
    # доказывают ничего и раздувают всё, что читает базу.
    # Отброшенное НЕ пропадает молча: сырой файл лежит на диске целиком, а число отброшенных
    # печатается. Если заслон окажется слишком строгим, это будет видно числом, а не догадкой.
    for r in chitat(os.path.join(C, 'tenderpro', 'tp-spisok-po-kompaniyam-vsyo.csv')):
        tid = (r.get('tender_id') or '').strip()
        inn = (r.get('inn') or '').strip()
        pred = r.get('predmet') or ''
        if tid in tp_vzyato or not re.fullmatch(r'\d{10}|\d{12}', inn):
            continue
        if not nash_predmet(r, pred):
            poteri['Tender.pro, вся страница компании: предмет не про машину'] += 1
            continue
        tp_vzyato.add(tid)
        fakty.append({
            'inn': inn, 'predpriyatie': (r.get('predpriyatie') or r.get('company') or '').strip()[:120],
            'sostoyanie': 'покупает',
            'marki': ' | '.join(marki_iz(pred)[:4]),
            'data': (r.get('sozdan') or '').strip(), 'chto_za_data': 'дата процедуры',
            'chem_dokazano': f'тендер {tid}',
            'tekst': re.sub(r'\s+', ' ', pred)[:300],
            'ssylka': f'https://www.tender.pro/api/tender/{tid}/view_public',
            'istochnik': 'Tender.pro, страница компании целиком',
        })

    # 2-бис. Заказчики и организаторы площадок, у которых в файле НЕТ предмета лота.
    # Это не «покупает компрессор», а слабее: «эта организация проводит закупки на площадке,
    # где мы нашли центробежный предмет». Раньше такие ИНН выпадали целиком — 15 814 из ЭТП ГПБ
    # и 2 796 из Сбербанк-АСТ. Состояние названо честно, чтобы его не путали с процедурой.
    # У Сбербанк-АСТ рядом с ИНН-файлом лежит агрегат по лотам: у 956 организаторов предмет
    # хотя бы одного лота центробежный. Число лотов кладём в текст факта — прежде туда шёл
    # голый ОКВЭД, и самая ценная часть выгрузки (10 079 лотов) не доезжала до базы никак.
    sber_loty = {}
    for r in chitat(os.path.join(C, 'sber-organizatory-polnye.csv')):
        n = (r.get('organizator') or '').strip()
        if n and (r.get('centro_predmet') or '') == 'да':
            sber_loty[n] = (r.get('lotov_centro') or '').strip()
    spiski_zakazchikov = [
        ('ЭТП ГПБ', 'etpgpb-zakazchiki-inn.csv'),
        ('Сбербанк-АСТ', 'sber-organizatory-inn.csv'),
        ('ТЭК-Торг', 'tektorg-loty.csv'),
        ('ТЭК-Торг, контакты', 'tektorg-kontakty-centro.csv'),
        ('вакансии hh', 'hh-rabotodateli-inn.csv'),
    ]
    for nazv, fajl in spiski_zakazchikov:
        for r in chitat(os.path.join(C, fajl)):
            inn = ''
            for k, v in r.items():
                v = (v or '').strip()
                if 'inn' not in (k or '').lower() and k != 'ИНН':
                    continue
                # У ТЭК-Торга ИНН пишется с хвостом состояния: «3801009466_del» — организация
                # исключена из словаря площадки. Прежняя проверка `fullmatch` такую строку
                # отвергала целиком, и вместе с хвостом терялся сам ИНН. Ликвидированная
                # организация — тоже факт, и она не повод выбрасывать её контактных людей.
                m = re.fullmatch(r'(\d{10}|\d{12})(?:_\w+)?', v)
                if m:
                    inn = m.group(1)
                    break
            if not inn:
                continue
            nazvanie = (r.get('nazvanie_egrul') or r.get('zakazchik') or r.get('organizator')
                        or r.get('nazvanie') or r.get('company') or '').strip()[:120]
            # Лоты ТЭК-Торга лежали в этом списке наравне с голыми перечнями организаций и
            # получали слабейшее состояние «есть на площадке», хотя предмет лота в файле ЕСТЬ.
            # Замер 03.08: из 3 901 лота у 281 предмет центробежный, и все 281 числились
            # «просто присутствует на площадке», без марок. Это та же ошибка, что была с
            # Росэлторгом: сильный факт, прочитанный как слабый.
            pred_lota = (r.get('predmet') or '').strip()
            pokupaet = bool(pred_lota) and nash_predmet(r, pred_lota)
            fakty.append({
                'inn': inn, 'predpriyatie': nazvanie,
                'sostoyanie': ('движение по вакансиям' if 'hh' in fajl
                               else 'покупает' if pokupaet else 'есть на площадке'),
                'marki': ' | '.join(marki_iz(pred_lota)[:4]) if pokupaet else '',
                'data': (r.get('data_publikacii') or r.get('data_sbora') or '').strip(),
                'chto_za_data': ('дата процедуры' if (r.get('data_publikacii') or '').strip()
                                 else 'когда мы это увидели'),
                'chem_dokazano': (f'{nazv}: у организатора {sber_loty[(r.get("nazvanie") or "").strip()]} '
                                  f'лотов по центробежным поисковым словам в архиве площадки'
                                  if nazv == 'Сбербанк-АСТ' and (r.get('nazvanie') or '').strip() in sber_loty
                                  else f'{nazv}: процедура {(r.get("reestrovyy_nomer") or "").strip()}'
                                  if pokupaet and (r.get('reestrovyy_nomer') or '').strip()
                                  else f'{nazv}: организация в выгрузке по нашему предмету'),
                'tekst': re.sub(r'\s+', ' ', (r.get('predmet') or r.get('okved') or ''))[:200],
                # Ссылки не было у 22 185 фактов из 89 757, и почти всё — чтение колонки,
                # которой в источнике нет. У ЭТП ГПБ адрес страницы заказчика собирается из
                # slug: колонка ssylka там не появлялась никогда, а код её честно читал и
                # получал пусто. У hh ссылка строится из имени работодателя.
                'ssylka': ((f'https://etpgpb.ru/customers/{(r.get("slug") or "").strip()}/'
                            if nazv == 'ЭТП ГПБ' and (r.get('slug') or '').strip() else '')
                           or (f'https://hh.ru/search/vacancy?text='
                               f'{urllib.parse.quote((r.get("employer") or "")[:60])}'
                               if nazv == 'вакансии hh' and (r.get('employer') or '').strip()
                               else '')
                           or (r.get('ssylka') or '').strip())[:200],
                'istochnik': nazv,
            })

    # 2-трис. Водоканалы — целый целевой сегмент, выпадал почти полностью (633 ИНН из 683).
    # Состояние «целевой сегмент»: машина у них почти наверняка есть (воздуходувка очистных
    # сооружений), но экспертиза ей не нужна, поэтому в реестре ЭПБ их нет.
    for r in chitat(os.path.join(C, 'dop', 'vodokanaly.csv')):
        inn = ''
        for k, v in r.items():
            v = (v or '').strip()
            if ('inn' in (k or '').lower() or k == 'ИНН') and re.fullmatch(r'\d{10}|\d{12}', v):
                inn = v
                break
        if not inn:
            continue
        fakty.append({
            'inn': inn,
            # Три опечатки в именах колонок подряд, и все тихие.
            # Код читал `nazvanie`, которого в справочнике нет вовсе, поэтому 683 водоканала
            # уезжали в базу БЕЗ НАЗВАНИЯ и продавец видел пустую строку вместо предприятия.
            # Взял `name` — стало лучше, но заполнен он только у 111 из 683. Полное имя лежит
            # в `name_obzvon` (681 из 683), и оно же короче и читабельнее: «ГУП „Мосводосток"»
            # против «ГОСУДАРСТВЕННОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ...». Берём его первым.
            # Та же беда со ссылкой: читалось `sayt`, а колонка называется `site`.
            'predpriyatie': (r.get('name_obzvon') or r.get('name')
                             or r.get('zakazchik') or '').strip()[:120],
            'sostoyanie': 'целевой сегмент, водоканал', 'sreda': 'воздух',
            'marki': '', 'data': '', 'chto_za_data': '',
            'chem_dokazano': 'справочник водоканалов: воздуходувка очистных сооружений',
            'tekst': re.sub(r'\s+', ' ', (r.get('okved') or r.get('region') or ''))[:200],
            'ssylka': (r.get('site') or r.get('sayt') or '').strip()[:200],
            'istochnik': 'справочник водоканалов',
        })

    # 3. ПЛАНИРУЕТ: позиции плана закупки 223-ФЗ, только годные и только с датой в будущем
    for r in chitat(os.path.join(C, 'plany-zakupki-chistye.csv')):
        if (r.get('brak') or '').strip():
            continue
        inn = (r.get('inn') or '').strip()
        if not re.fullmatch(r'\d{10}|\d{12}', inn):
            continue
        pred = r.get('predmet_bez_proekta') or r.get('predmet') or ''
        nash = nash_predmet(r, pred)
        v_budushchem = (r.get('data_v_budushchem') or '').strip() in ('1', 'да', 'True')
        fakty.append({
            'inn': inn, 'predpriyatie': (r.get('zakazchik') or '').strip()[:120],
            'sostoyanie': ('планирует' if v_budushchem else 'планировал') if nash
                          else 'план не по нашему предмету',
            'marki': ' | '.join(marki_iz(pred)[:4]) if nash else '',
            'data': (r.get('planiruemaya_data_razmeshcheniya') or '').strip(),
            'chto_za_data': 'когда планируют разместить закупку',
            'chem_dokazano': f'план {(r.get("plan_reg_nomer") or "").strip()} позиция '
                             f'{(r.get("nomer_pozicii") or "").strip()}, сумма '
                             f'{(r.get("summa") or "").strip()}',
            'tekst': re.sub(r'\s+', ' ', pred)[:300],
            'ssylka': (r.get('ssylka') or '').strip()[:200],
            'istochnik': 'план закупки 223-ФЗ, ЕИС',
        })


    # 4. ПОТЕРЯННЫЕ ИСТОЧНИКИ — найдены сверкой «что в файлах против что в базе» 03.08.
    # Аудит всех 50 файлов centro/ показал: у семи нет колонки ИНН, и склейка по ИНН молча
    # проносила их мимо базы ЦЕЛИКОМ, около 5 700 строк. Среди потерянного — референс-лист
    # Невского завода (кому и какая машина поставлена: готовое «есть» с маркой и годом),
    # 1 201 центробежный лот Фабриканта и 47 машинных закупок Портала поставщиков с
    # контактными лицами. Названия разрешены в ИНН справочником ЕГРЮЛ (dadata_inn.py),
    # разрешение лежит в centro/poteryannye-inn.csv и переиспользуется при пересборке.
    #
    # Правило приёмки — по уроку 30.07, когда «Магнитогорский металлургический» слипался с
    # «Магнитогорским Гипромезом», а пивзавод с водоканалом: kandidatov == 1 принимается;
    # kandidatov > 1 принимается ТОЛЬКО если этот ИНН уже есть в базе с другой стороны
    # (подтверждение двумя независимыми источниками); ликвидированные юрлица и остальная
    # неоднозначность уходят в OTSEV-inn-neodnoznachno.csv с причиной, а не пропадают.
    razreshenie = {}
    for r in chitat(os.path.join(C, 'poteryannye-inn.csv')):
        n = (r.get('nazvanie') or '').strip()
        if n and re.fullmatch(r'\d{10}|\d{12}', (r.get('inn') or '').strip()):
            razreshenie[n] = r
    uzhe_v_baze = {x['inn'] for x in fakty}
    otsev_inn = []

    def inn_po_imeni(imya, otkuda):
        r = razreshenie.get((imya or '').strip())
        if not r:
            return '', None
        status = (r.get('status') or '').upper()
        if 'LIQUIDAT' in status or 'ЛИКВИД' in status:
            otsev_inn.append({'nazvanie': imya, 'inn': r['inn'], 'istochnik': otkuda,
                              'prichina': f'юрлицо ликвидировано ({r.get("status")})'})
            return '', None
        kand = (r.get('kandidatov') or '1').strip()
        if kand not in ('', '1') and r['inn'] not in uzhe_v_baze:
            otsev_inn.append({'nazvanie': imya, 'inn': r['inn'], 'istochnik': otkuda,
                              'prichina': f'кандидатов {kand}, ИНН не подтверждён второй стороной'})
            return '', None
        return r['inn'], r

    # 4а. Фабрикант: лоты с центробежным предметом. Дата и ссылка на процедуру есть в строке.
    for r in chitat(os.path.join(C, 'fabrikant-centro.csv')):
        if (r.get('centrobezhnyy_predmet') or '') != 'да':
            continue
        imya = (r.get('zakazchik') or r.get('organizator') or '').strip()
        inn, rr = inn_po_imeni(imya, 'Фабрикант')
        if not inn:
            continue
        pred = r.get('predmet') or ''
        nash = nash_predmet(r, pred)
        fakty.append({
            'inn': inn, 'predpriyatie': ((rr.get('nazvanie_egrul') or imya) or '').strip()[:120],
            'sostoyanie': 'покупает' if nash else 'есть на площадке',
            'marki': ' | '.join(marki_iz(pred)[:4]) if nash else '',
            'data': (r.get('data_publikacii') or '').strip()[:10], 'chto_za_data': 'дата процедуры',
            'chem_dokazano': f'Фабрикант, процедура {(r.get("nomer") or "").strip()}'
                             f' (ИНН по справочнику ЕГРЮЛ)',
            'tekst': re.sub(r'\s+', ' ', pred)[:300],
            'ssylka': (r.get('ssylka') or '').strip()[:200],
            'istochnik': 'Фабрикант',
        })

    # 4б. Референс-лист Невского завода: машина ПОСТАВЛЕНА заказчику, серия в модели, год в
    # строке. Это «есть» из уст изготовителя. Год бывает 1947-м — записи не выбрасываем по
    # возрасту (правило владельца), дата подписана тем, чем является.
    for r in chitat(os.path.join(C, 'istochnik-nzl-referencii-kompressory.csv')):
        if (r.get('strana') or '').strip() not in ('Россия', 'РФ', 'Российская Федерация'):
            continue
        imya = (r.get('zakazchik') or '').strip()
        inn, rr = inn_po_imeni(imya, 'референс-лист НЗЛ')
        if not inn:
            continue
        model = (r.get('model') or '').strip()
        fakty.append({
            'inn': inn, 'predpriyatie': ((rr.get('nazvanie_egrul') or imya) or '').strip()[:120],
            'sostoyanie': 'есть', 'marki': ' | '.join(marki_iz(model)[:4]) or model[:40],
            'data': (r.get('god_postavki') or '').strip(),
            'chto_za_data': 'год поставки машины заводом-изготовителем',
            'chem_dokazano': 'референс-лист Невского завода (ИНН по справочнику ЕГРЮЛ)',
            'tekst': re.sub(r'\s+', ' ',
                            f'{model} {r.get("zakazchik_i_obekt") or ""} {r.get("hvost_stroki") or ""}')[:300],
            'ssylka': (r.get('istochnik') or '').strip()[:200],
            'istochnik': 'референс-лист Невского завода',
        })

    # 4в. Декларации соответствия ФСА: берём только строки, где декларант НЕ изготовитель —
    # изготовитель декларирует свою продукцию, это конкурент, а не покупатель. Но и декларант
    # часто перепродавец, поэтому состояние слабое, очередь этим не двигаем.
    for r in chitat(os.path.join(C, 'istochnik-fsa-centro-deklaranty.csv')):
        dek = (r.get('deklarant') or '').strip()
        if not dek or dek == (r.get('izgotovitel') or '').strip():
            continue
        inn, rr = inn_po_imeni(dek, 'декларации ФСА')
        if not inn:
            continue
        fakty.append({
            'inn': inn, 'predpriyatie': ((rr.get('nazvanie_egrul') or dek) or '').strip()[:120],
            'sostoyanie': 'есть на площадке', 'marki': '',
            'data': (r.get('data') or '').strip(), 'chto_za_data': 'дата декларации',
            'chem_dokazano': f'декларация соответствия {(r.get("nomer") or "").strip()}, '
                             f'декларант не изготовитель — возможно эксплуатант или перепродавец',
            'tekst': re.sub(r'\s+', ' ', r.get('produkt') or '')[:300],
            'ssylka': (r.get('url_kartochki') or '').strip()[:200],
            'istochnik': 'декларации соответствия ФСА',
        })

    # 4г. Портал поставщиков, машинные закупки с контактным лицом в карточке.
    for r in chitat(os.path.join(C, 'istochnik-portal-postavshchikov-kompressory.csv')):
        imya = (r.get('zakazchik') or '').strip()
        inn, rr = inn_po_imeni(imya, 'Портал поставщиков, машины')
        if not inn:
            continue
        pred = r.get('predmet') or ''
        nash = nash_predmet(r, pred)
        lico = (r.get('kontaktnoe_lico') or '').strip()
        fakty.append({
            'inn': inn, 'predpriyatie': ((rr.get('nazvanie_egrul') or imya) or '').strip()[:120],
            'sostoyanie': 'покупает' if nash else 'есть на площадке',
            'marki': ' | '.join(marki_iz(pred)[:4]) if nash else '',
            'data': (r.get('data_sbora') or '').strip(), 'chto_za_data': 'когда мы это увидели',
            'chem_dokazano': f'закупка {(r.get("id") or "").strip()} Портала поставщиков'
                             + (f'; контактное лицо в карточке: {lico}' if lico else ''),
            'tekst': re.sub(r'\s+', ' ', pred)[:300],
            'ssylka': (r.get('url_kartochki') or '').strip()[:200],
            'istochnik': 'Портал поставщиков Москвы',
        })

    # 4д. Казанькомпрессормаш: список заказчиков завода. ИНН сопоставлены раньше по токенам —
    # привязка слабая (урок про «вложение названий»), поэтому честно пишем способ в основание.
    # Серию машины список не называет: у ККМ есть и винтовые 6ВВ — центробежность НЕ утверждаем,
    # кроме строк, где источник называет винтовую серию прямо (тогда так и пишем).
    for r in chitat(os.path.join(C, 'kazankompressormash-zakazchiki.csv')):
        inn = (r.get('nash_inn') or '').strip()
        if not re.fullmatch(r'\d{10}|\d{12}', inn):
            continue
        ist = (r.get('istochniki') or '').strip()
        vint = 'screw' in ist.lower()
        fakty.append({
            'inn': inn, 'predpriyatie': (r.get('nashe_nazvanie') or '').strip()[:120],
            'sostoyanie': 'есть', 'marki': '',
            'data': '', 'chto_za_data': '',
            'chem_dokazano': f'список заказчиков Казанькомпрессормаша ({ist}); '
                             f'сопоставление по названию — привязка слабая',
            'tekst': ('винтовые компрессоры серии 6ВВ производства ККМ' if vint else
                      'компрессорное оборудование производства Казанькомпрессормаш, серия не названа'),
            'ssylka': '', 'istochnik': 'заказчики Казанькомпрессормаша',
        })

    # 4е. Сбербанк-АСТ, размеченная выборка лотов: 97 строк с предметом, номером и датой —
    # единственный кусок сберовской выгрузки, где предмет лота сохранён построчно.
    for r in chitat(os.path.join(C, 'sberbank-ast-organizatory.csv')):
        inn = (r.get('inn_dadata') or '').strip()
        if not re.fullmatch(r'\d{10}|\d{12}', inn):
            continue
        if (r.get('score_sopostavleniya') or '') not in ('1.0', '1'):
            continue
        pred = r.get('predmet_lota') or ''
        nash = nash_predmet(r, pred)
        fakty.append({
            'inn': inn, 'predpriyatie': (r.get('egrul_nazvanie') or '').strip()[:120],
            'sostoyanie': 'покупает' if nash else 'есть на площадке',
            'marki': ' | '.join(marki_iz(pred)[:4]) if nash else '',
            'data': (r.get('data_publikacii') or '').strip()[:10], 'chto_za_data': 'дата процедуры',
            'chem_dokazano': f'Сбербанк-АСТ, лот {(r.get("nomer") or "").strip()}',
            'tekst': re.sub(r'\s+', ' ', pred)[:300],
            'ssylka': '', 'istochnik': 'Сбербанк-АСТ',
        })

    if otsev_inn:
        with open(os.path.join(BAZA, 'engineers-lens', 'OTSEV-inn-neodnoznachno.csv'), 'w',
                  encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['nazvanie', 'inn', 'istochnik', 'prichina'],
                               delimiter=';')
            w.writeheader()
            for r in otsev_inn:
                w.writerow(r)
        print(f'ИНН-неоднозначных отложено: {len(otsev_inn)} → OTSEV-inn-neodnoznachno.csv')

    cols = ['inn', 'predpriyatie', 'sostoyanie', 'sreda', 'marki', 'srok_sluzhby', 'vyvod_ekspertizy',
            'data', 'chto_za_data', 'chem_dokazano', 'tekst', 'ssylka', 'istochnik']
    with open(OUT_FAKTY, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in sorted(fakty, key=lambda x: (x['inn'], x['sostoyanie'])):
            w.writerow(r)

    # Сводка по предприятию: в каких состояниях оно есть и есть ли к кому звонить
    lyudi = defaultdict(list)
    for r in chitat(os.path.join(C, 'tenderpro', 'tp-lyudi-dlya-obzvona.csv')):
        if r.get('inn'):
            lyudi[r['inn']].append(r)
    # МАРКИ СЧИТАЮТСЯ, А НЕ ПРОСТО СОБИРАЮТСЯ В МНОЖЕСТВО. Причина — дефект, который нашла
    # первая сессия у себя в фильтре панели, а я проверил у себя и нашёл тот же:
    # строка марок предприятия строилась `sorted(marki)[:8]`, то есть ПО АЛФАВИТУ с обрезкой.
    # Латиница и цифры идут первыми, и кириллические серии до отсечки не доживали.
    # Замер: 17 995 марок есть в фактах и отсутствуют в колонке предприятия. «К-345-92-1»
    # встречается в 114 фактах у 11 предприятий и не показан ни у одного.
    # Теперь порядок по ЧАСТОТЕ, и центробежные серии впереди прочих: продавцу важнее увидеть
    # «К-250-61-5», чем «1TD-205» только потому, что тот начинается с цифры.
    po_inn = defaultdict(lambda: {'sost': set(), 'marki': Counter(), 'daty': {}, 'nazv': '',
                                  'n': 0})
    for r in fakty:
        d = po_inn[r['inn']]
        d['sost'].add(r['sostoyanie'])
        if r.get('sreda'):
            d.setdefault('sreda', set()).add(r['sreda'])
        d['nazv'] = d['nazv'] or r['predpriyatie']
        d['n'] += 1
        for m in (r['marki'] or '').split('|'):
            if m.strip():
                d['marki'][m.strip()] += 1
        if r['data']:
            d['daty'][r['sostoyanie']] = max(d['daty'].get(r['sostoyanie'], ''), r['data'])
        if r.get('srok_sluzhby'):
            d.setdefault('srok', set()).add(r['srok_sluzhby'])
        if r.get('vyvod_ekspertizy'):
            d.setdefault('vyvod', set()).add(r['vyvod_ekspertizy'])

    cols2 = ['inn', 'predpriyatie', 'est', 'pokupaet', 'planiruet', 'na_ploshchadke',
             'vodokanal_segment', 'vakansii', 'sreda', 'sostoyaniy',
             'marki', 'marok_vsego', 'srok_sluzhby', 'vyvod_ekspertizy', 'data_zakluchenia',
             'data_zakupki', 'kogda_planiruet',
             'tehnicheskih_lyudey', 's_telefonom', 'kto']
    with open(OUT_PRED, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols2, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for inn, d in sorted(po_inn.items(), key=lambda x: (-len(x[1]['sost']), -x[1]['n'])):
            L = lyudi.get(inn) or []
            teh = [x for x in L if x['rol'] == 'техническая']
            w.writerow({
                'inn': inn, 'predpriyatie': d['nazv'],
                'est': '1' if 'есть' in d['sost'] else '',
                'pokupaet': '1' if 'покупает' in d['sost'] else '',
                'planiruet': '1' if 'планирует' in d['sost'] else '',
                'na_ploshchadke': '1' if 'есть на площадке' in d['sost'] else '',
                'vodokanal_segment': '1' if 'целевой сегмент, водоканал' in d['sost'] else '',
                'vakansii': '1' if 'движение по вакансиям' in d['sost'] else '',
                'sreda': ' | '.join(sorted(d.get('sreda') or [])),
                'sostoyaniy': len(d['sost'] & {'есть', 'покупает', 'планирует'}),
                'marki': ' | '.join(m for m, _ in sorted(
                    d['marki'].items(),
                    key=lambda x: (0 if CENTR_SERIYA_SVOD.match(x[0]) else 1, -x[1], x[0]))[:25]),
                'marok_vsego': len(d['marki']),
                'srok_sluzhby': ' | '.join(sorted(d.get('srok') or [])),
                'vyvod_ekspertizy': ' | '.join(sorted(d.get('vyvod') or []))[:60],
                'data_zakluchenia': d['daty'].get('есть', ''),
                'data_zakupki': d['daty'].get('покупает', ''),
                'kogda_planiruet': d['daty'].get('планирует', ''),
                'tehnicheskih_lyudey': len(teh),
                's_telefonom': sum(1 for x in teh if x['telefony']),
                'kto': ' | '.join(f'{x["imya"]} ({x["dolzhnost"][:40]}) {x["telefony"][:40]}'
                                  for x in teh[:3]),
            })

    # Отчёт цифрами ИЗ ЗАПИСАННЫХ ФАЙЛОВ
    f1 = chitat(OUT_FAKTY)
    f2 = chitat(OUT_PRED)
    import collections
    print(f'\nфактов: {len(f1)}, предприятий: {len(f2)}')
    print('по состояниям:', dict(collections.Counter(x['sostoyanie'] for x in f1)))
    print(f'  фактов с распознанной маркой: {sum(1 for x in f1 if x["marki"])}')
    print(f'предприятий в трёх состояниях сразу: {sum(1 for x in f2 if x["sostoyaniy"] == "3")}')
    print(f'  в двух: {sum(1 for x in f2 if x["sostoyaniy"] == "2")}')
    print(f'  с техническим человеком и телефоном: {sum(1 for x in f2 if x["s_telefonom"] not in ("", "0"))}')
    if poteri:
        print('ПОТЕРЯНО МОЛЧА (строк, у которых не нашлось ИНН нигде):')
        for k, v in sorted(poteri.items(), key=lambda x: -x[1]):
            print(f'  {v:>6}  {k}')
    print(f'→ {OUT_FAKTY}\n→ {OUT_PRED}')


if __name__ == '__main__':
    main()
