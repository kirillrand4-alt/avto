# -*- coding: utf-8 -*-
"""Люди из карточек закупок, чей ПРЕДМЕТ нам не нужен. Мысль владельца, и она верна.

Обход страниц компаний без слова-фильтра дал 131 039 закупок, из которых про машины 1,0 %.
Я объявил остальное мусором — и был неправ наполовину. Строка про канцтовары бесполезна как
факт о МАШИНЕ, но карточка этой закупки содержит контактное лицо ПРЕДПРИЯТИЯ, а человек нужен
нам независимо от того, что закупали. Мусор по предмету не равен мусору по людям.

ПОЧЕМУ НЕ ПОДРЯД. Непрошенных карточек 131 093, и спросить их все — это девять часов скачивания
и десятки тысяч оплаченных разборов. При этом карточки висят на 99 предприятиях, и контактных
лиц там не десятки тысяч, а десятки: одни и те же снабженцы повторяются из карточки в карточку.
Поэтому берётся ВЫБОРКА на предприятие с правилом остановки: качаем, пока новые фамилии
появляются, и прекращаем, когда `--vsuhuyu` карточек подряд не дали никого нового.

ПОРЯДОК — ОТ ПОЛЕЗНОГО К МЕНЕЕ ПОЛЕЗНОМУ, и это не вкусовщина, а прямая мера успеха проекта:
    1. предприятия, где НЕТ НИ ОДНОГО человека            — 20 879 карточек на 35 предприятиях
    2. человек есть, но личного номера нет                — 39 889 на 32
    3. есть и человек, и личный номер                     — 70 325 на 32
Третья группа берётся последней и только если осталось время: там прибавка минимальна.

Заслон от повторной оплаты: журнал `tp-lica-sprosheno.txt` ведётся отдельно от результата.
Карточка, честно разобранная и не давшая людей, следов в результате не оставляет, и без журнала
спрашивалась бы заново. Однажды это уже стоило 3 300 оплаченных повторов.

Выход дописывается в `tp-kartochki.csv`, откуда его берёт `tenderpro_lica.py` — то есть модуль
не заводит свой конвейер, а кормит существующий.

Использование:
    python3 tp_lyudi_iz_musora.py --gruppa 1            # только предприятия без людей
    python3 tp_lyudi_iz_musora.py --gruppa 1,2 --na-predpriyatie 60
    python3 tp_lyudi_iz_musora.py --plan                # только показать план, ничего не качая
"""
import csv
import os
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tenderpro_harvest as T  # noqa: E402

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
OUT = os.path.join(L, 'centro', 'tenderpro')
KART = os.path.join(OUT, 'tp-kartochki.csv')
ZHURNAL = os.path.join(OUT, 'tp-lica-sprosheno.txt')
LICA = os.path.join(OUT, 'tp-lica.csv')
SPISKI = [os.path.join(OUT, 'tp-spisok-po-kompaniyam-vsyo.csv'),
          os.path.join(OUT, 'tp-spisok-po-kompaniyam.csv')]
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
PANEL = os.path.join(L, 'VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv')
COLS = ['tender_id', 'company_id', 'company', 'predmet', 'sozdan', 'organizator',
        'est_teh', 'telefony_razmetka', 'telefony_tekst', 'pochty', 'comment']


# ПРИОРИТЕТ ПО ПРЕДМЕТУ ВНУТРИ ПРЕДПРИЯТИЯ. Вопрос владельца: будет ли модуль относить предмет
# к инженерной службе или возьмёт канцтовары наравне. Сперва не относил — брал свежие подряд.
#
# ЗАМЕР на 2 705 уже разобранных карточках (доля карточек, давших ТЕХНИЧЕСКОГО человека с
# личным мобильным — прямая мера успеха проекта):
#     машина / оборудование   2 600 карточек → 22,0 %
#     прочее                    101 карточка →  6,9 %
# Втрое хуже. Выборка «прочего» мала, и честно сказать, сколько дадут канцтовары, нельзя —
# их не разобрано НИ ОДНОЙ: прежний обход качал только карточки по машинным словам. Поэтому
# порядок ставится по измеренному направлению, а не по уверенному числу, и канцтовары не
# выбрасываются совсем — они уходят в хвост и будут спрошены последними. Когда их наберётся
# хотя бы сотня, замер повторить и порядок пересмотреть.
#
# Почему предмет вообще что-то говорит о человеке: карточку ведёт куратор закупки. У ремонта
# компрессора это человек технической службы («Вопросы технического характера: заместитель
# главного механика…»), у канцтоваров — снабженец. Нам нужен первый.
VES_PREDMETA = [
    (1, re.compile(r'компрессор|насос|турбин|воздуходувк|нагнетател|газодувк|электродвигател|'
                   r'редуктор|подшипник|запчаст|запасн\w+ част|ремонт|техническ\w+ обслуж|'
                   r'модерниз|монтаж|наладк|диагностиров|экспертиз\w+ промышленн|'
                   r'капитальн\w+ ремонт|агрегат|установк', re.I)),
    (2, re.compile(r'электроэнерг|теплоснаб|водоснаб|котельн|трансформат|кабел|электроснаб|'
                   r'газоснаб|очистн\w+ сооружен|аэротенк|воздухораздел', re.I)),
    (3, re.compile(r'строительств|проектн|изыскател|дорожн|благоустрой', re.I)),
    (5, re.compile(r'канцеляр|бумаг|картридж|мебел|спецодежд|моющ|уборк|питани|продукт|'
                   r'подарочн|сувенир|страхован|аудит|консультац|обучени|медицинск|'
                   r'охран\w+ услуг|аренд|связ|лизинг|програмн', re.I)),
]


def ves(predmet):
    """Чем меньше число, тем раньше карточка будет спрошена. 4 — всё, что не опознано:
    оно идёт ПОСЛЕ машин и энергетики, но ПЕРЕД заведомой хозчастью."""
    for v, rx in VES_PREDMETA:
        if rx.search(predmet or ''):
            return v
    return 4


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def gruppa_predpriyatiya(inn, ochered, s_chelovekom, s_lichnym):
    if inn not in ochered:
        return 4
    if inn not in s_chelovekom:
        return 1
    if inn not in s_lichnym:
        return 2
    return 3


def main():
    hochu = {int(x) for x in dovod('--gruppa', '1').split(',')}
    na_predpriyatie = dovod('--na-predpriyatie', 60)
    vsuhuyu = dovod('--vsuhuyu', 15)      # столько карточек подряд без новой фамилии — стоп
    threads = dovod('--threads', 6)

    ochered = {r['inn'] for r in chitat(OCHERED)}
    panel = chitat(PANEL)
    s_chelovekom = {r['inn'] for r in panel if (r.get('chelovek') or '').strip()}
    s_lichnym = {r['inn'] for r in panel if (r.get('lichnyy_nomer') or '').strip()}

    # уже спрошенные карточки — ни одна не идёт повторно
    sprosheno = set()
    if os.path.exists(ZHURNAL):
        sprosheno |= {l.strip() for l in open(ZHURNAL, encoding='utf-8') if l.strip()}
    for r in chitat(LICA):
        sprosheno.add((r.get('tender_id') or '').strip())
    uzhe_skachano = {(r.get('tender_id') or '').strip() for r in chitat(KART)}

    po_inn = defaultdict(list)
    vidano = set()
    for put in SPISKI:
        for r in chitat(put):
            t = (r.get('tender_id') or '').strip()
            i = (r.get('inn') or '').strip()
            if not t or not i or t in vidano or t in sprosheno or t in uzhe_skachano:
                continue
            vidano.add(t)
            po_inn[i].append(r)

    plan = []
    for inn, rows in po_inn.items():
        g = gruppa_predpriyatiya(inn, ochered, s_chelovekom, s_lichnym)
        if g in hochu:
            # Сначала по весу предмета, внутри веса — свежие вперёд: в новых чаще указан
            # работающий человек, а не уволившийся. Дата в формате ДД.ММ.ГГГГ, поэтому
            # сортируется по перевёрнутому виду, иначе «31.01.2016» окажется свежее «01.02.2026».
            def kogda(x):
                d = (x.get('sozdan') or '').strip()
                m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', d)
                return f'{m.group(3)}{m.group(2)}{m.group(1)}' if m else d
            rows.sort(key=lambda x: (ves(x.get('predmet')), [-int(c) for c in kogda(x)[:8]
                                                              if c.isdigit()]))
            plan.append((g, inn, rows[:na_predpriyatie]))
    plan.sort(key=lambda x: (x[0], -len(x[2])))

    vsego = sum(len(r) for _, _, r in plan)
    print(f'предприятий в плане: {len(plan)}, карточек к скачиванию: {vsego} '
          f'(из {len(vidano)} доступных непрошенных)', file=sys.stderr)
    for g in sorted(hochu):
        n = [p for p in plan if p[0] == g]
        print(f'  группа {g}: предприятий {len(n)}, карточек {sum(len(r) for _, _, r in n)}',
              file=sys.stderr)
    if '--plan' in sys.argv or not plan:
        return

    novyy = not os.path.exists(KART) or os.path.getsize(KART) == 0
    cols = COLS
    if not novyy:
        with open(KART, encoding='utf-8-sig') as f0:
            bylo = (csv.DictReader(f0, delimiter=';').fieldnames or [])
        cols = COLS + [c for c in bylo if c not in COLS]
    f = open(KART, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    lock = threading.Lock()
    sch = {'скачано': 0, 'с телефоном': 0, 'с техническим словом': 0, 'пустых': 0,
           'остановлено правилом': 0, 'сбоев': 0}

    def odno_predpriyatie(zadacha):
        g, inn, rows = zadacha
        vzyato, podryad_bez_novogo, familii = [], 0, set()
        for r in rows:
            tid = r['tender_id']
            try:
                h = T.vzyat(T.CARD_URL % tid)
            except Exception:  # noqa: BLE001
                with lock:
                    sch['сбоев'] += 1
                continue
            if not h or h.startswith('__ОШИБКА__'):
                with lock:
                    sch['сбоев'] += 1
                continue
            i = h.find('Комментарий:')
            com = ''
            if i > 0:
                j = h.find('<!-- div -->', h.find('tender-comment__wrapper', i))
                com = h[i:j if j > i else i + 4000]
            txt = T.bez_tegov(com)
            tel_r = [t.strip() for t in T.CALLTO.findall(com)]
            tel_t = [t for t in T.telefony_iz_teksta(txt) if t.strip() not in tel_r]
            est_teh = bool(T.TEH_SLOVO.search(txt)) if hasattr(T, 'TEH_SLOVO') else \
                bool(re.search(r'технич|энергетик|механик|главн\w+ инженер|КИП', txt, re.I))
            # правило остановки: считаем НОВЫЕ фамилии, а не строки. Фамилия — слово с большой
            # буквы длиной от четырёх букв рядом с телефоном; грубо, но для счётчика хватает.
            novye = {x for x in re.findall(r'\b([А-ЯЁ][а-яё]{3,})\b', txt)} - familii
            if novye:
                familii |= novye
                podryad_bez_novogo = 0
            else:
                podryad_bez_novogo += 1
            vzyato.append({'tender_id': tid, 'company_id': r.get('company_id') or '',
                           'company': r.get('company') or '', 'predmet': r.get('predmet') or '',
                           'sozdan': r.get('sozdan') or '', 'organizator': '',
                           'est_teh': 'да' if est_teh else '',
                           'telefony_razmetka': ' | '.join(tel_r),
                           'telefony_tekst': ' | '.join(tel_t),
                           'pochty': ' | '.join(T.POCHTA.findall(txt)) if hasattr(T, 'POCHTA')
                           else ' | '.join(re.findall(r'[\w.\-]+@[\w.\-]+\.\w+', txt)),
                           'comment': txt[:2000]})
            with lock:
                sch['скачано'] += 1
                if tel_r or tel_t:
                    sch['с телефоном'] += 1
                if est_teh:
                    sch['с техническим словом'] += 1
                if not (tel_r or tel_t or est_teh):
                    sch['пустых'] += 1
            if podryad_bez_novogo >= vsuhuyu:
                with lock:
                    sch['остановлено правилом'] += 1
                break
            time.sleep(0.4)
        return inn, vzyato

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for n, (inn, vzyato) in enumerate(pool.map(odno_predpriyatie, plan), 1):
            with lock:
                for row in vzyato:
                    w.writerow(row)
                f.flush()
                print(f'  {n}/{len(plan)} ИНН {inn}: +{len(vzyato)} карточек, {sch}',
                      file=sys.stderr, flush=True)
    f.close()
    print(f'готово: {sch}\n→ {KART}', file=sys.stderr)
    print('СЛЕДУЮЩИЙ ШАГ: python3 tenderpro_lica.py — он разберёт скачанное провайдером. '
          'Карточки без телефона и без технического слова он пропустит сам, платить за них '
          'не придётся.', file=sys.stderr)


if __name__ == '__main__':
    main()
