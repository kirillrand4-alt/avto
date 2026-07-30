# -*- coding: utf-8 -*-
"""Поиск ИНН по названию организации в базе обзвона, с замером точности.

Зачем. Половина источников даёт название без ИНН: референс-лист Невского завода (475
заказчиков), работодатели hh (310 без ИНН), карточки закупок агрегаторов. Сличение по
названию — ровно то, на чём мы обожглись трижды за 30.07.2026: «Магнитогорский
металлургический комбинат» слепился с «ЗАО «Комбинат хлебопродуктов»» по слову «комбинат»,
потом с «Магнитогорским Гипромезом» по названию города, «Челябинский МК» — с трубопрокатным.

Поэтому здесь два отличия от прежних попыток:

1. **Ищется в базе, где ИНН уже есть** (`master-base.sqlite`, 162 440 юрлиц), а не в двух
   списках названий. То есть результат — идентификатор, а не пара строк.
2. **Точность измеряется на известном ответе.** У 246 предприятий воздушного сегмента ИНН
   известен из реестра ЭПБ. Подаём название, смотрим, вернулся ли верный ИНН. Это слепой
   замер: база и реестр — независимые источники.

Заслоны, каждый из которых поставлен по конкретной ошибке:
- **родовые слова** («комбинат», «завод», «компания», «металлургический») выбрасываются —
  совпадение по ним ничего не значит;
- **названия городов и холдингов** считаются слабым признаком: по ним одиночное совпадение
  не принимается;
- **регион** сверяется, если известен: два «Водоканала» в разных областях — разные юрлица;
- при нескольких кандидатах с равным весом ответ **не выдаётся вовсе** — тёзки бывают, и
  наугад выбранный ИНН хуже пропуска.

Использование:
    python3 inn_po_nazvaniyu.py zamer                     # слепой замер на 246 известных
    python3 inn_po_nazvaniyu.py razresh <names.txt> <out.csv>
"""
import csv
import os
import re
import sqlite3
import sys
from collections import Counter

DIR = os.path.dirname(os.path.abspath(__file__))
BAZA = os.environ.get('MASTER_BASE', '/tmp/claude-0/-home-user-avto/'
                      '520847fd-7699-5483-869b-cf6d49851f67/scratchpad/master-base.sqlite')

FORMY = (r'\b(публичное|акционерное|общество|с ограниченной ответственностью|открытое|'
         r'закрытое|пао|оао|ао|ооо|зао|нао|гуп|муп|мбу|гбу|фгуп|фгбу|сгмуп|мкп|мп|'
         r'имени|им)\b')

# Родовые: встречаются у сотен предприятий, совпадение по ним не признак.
RODOVYE = {
    'комбинат', 'завод', 'заводы', 'компания', 'компании', 'фабрика', 'предприятие',
    'объединение', 'производственное', 'производственный', 'производство', 'холдинг',
    'группа', 'корпорация', 'концерн', 'управление', 'управляющая', 'сервис', 'сервисная',
    'металлургический', 'металлургическая', 'нефтехимический', 'нефтехимическая',
    'химический', 'химическая', 'машиностроительный', 'трубопрокатный', 'горно',
    'целлюлозно', 'бумажный', 'электростанция', 'атомная', 'тепловая', 'генерирующая',
    'энергетическая', 'энергетический', 'промышленный', 'промышленная', 'станция',
    'станций', 'комплекс', 'центр', 'филиал', 'дирекция', 'водоканал', 'водоснабжения',
    'водоотведения', 'коммунальных', 'жилищно',
    # добавлено 30.07.2026 после разбора ошибок на свободном тексте
    'состав', 'составе', 'вошел', 'вошла', 'вошло', 'входит', 'ранее', 'сейчас',
    'газоперерабатывающий', 'газоперерабатывающего', 'глиноземный', 'обогатительный',
    'нефтеперерабатывающий', 'перерабатывающий', 'добыча', 'переработка', 'трансгаз',
}

# Юрлица-спутники: у завода бывают своя поликлиника, санаторий, охрана, столовая.
# Название почти совпадает с заводским, а предприятие это другое.
SPUTNIKI = re.compile(r'\b(чуз|поликлиник|больниц|санатор|профилактор|детск|столов|'
                      r'охран|общепит|жилкомсервис|цбдд|автотранспорт|профсоюз|'
                      r'садоводческ|спортивн|хоккейн|футбольн)', re.I)

# Города и холдинги: признак слабый — по одному такому слову ответ не выдаём.
SLABYE = {
    'магнитогорский', 'челябинский', 'норильский', 'череповецкий', 'кузнецкий', 'омский',
    'нижневартовский', 'тульский', 'липецкий', 'волгоградский', 'саратовский', 'самарский',
    'пермский', 'уфимский', 'казанский', 'новокуйбышевский', 'ангарский', 'тюменский',
    'сургутский', 'барнаульский', 'иркутский', 'красноярский', 'воронежский',
    'белгородский', 'московский', 'ленинградский', 'свердловский', 'кемеровский',
    'западно', 'сибирский', 'уральский', 'восточный', 'южный', 'северный', 'центральный',
    'газпром', 'евраз', 'лукойл', 'роснефть', 'сибур', 'мечел', 'татнефть', 'русал',
    'металлоинвест', 'фосагро', 'еврохим', 'уралхим', 'акрон', 'росатом', 'росэнергоатом',
}


def toks(s):
    s = re.sub(r'[«»"\'()]', ' ', (s or '').lower().replace('ё', 'е'))
    s = re.sub(FORMY, ' ', s)
    return [w for w in re.sub(r'[^а-яa-z0-9 -]', ' ', s).split() if len(w) > 3]


def silnye(ws):
    return {w for w in ws if w not in RODOVYE and w not in SLABYE and len(w) >= 6}


def zagruzit():
    c = sqlite3.connect(BAZA)
    c.row_factory = sqlite3.Row
    ind = {}
    zapisi = {}
    for r in c.execute('select inn,name,name_obzvon,region from master'):
        inn = r['inn']
        ws = set(toks(r['name'])) | set(toks(r['name_obzvon']))
        zapisi[inn] = (r['name'] or r['name_obzvon'] or '', r['region'] or '', ws)
        for w in silnye(ws):
            ind.setdefault(w, set()).add(inn)
    print(f'база: {len(zapisi)} юрлиц, сильных слов в индексе {len(ind)}', file=sys.stderr)
    return zapisi, ind


def naiti(nazvanie, region, zapisi, ind):
    """Вернуть (inn, pochemu) либо (None, причина отказа)."""
    ws = set(toks(nazvanie))
    s = silnye(ws)
    if not s:
        return None, 'в названии нет ни одного сильного слова'
    kand = Counter()
    for w in s:
        for inn in ind.get(w, ()):
            kand[inn] += 1
    if not kand:
        return None, 'сильных слов нет в базе'
    # регион отсекает тёзок из разных областей
    if region:
        rt = set(toks(region))
        if rt:
            otbor = {i: n for i, n in kand.items()
                     if not zapisi[i][1] or rt & set(toks(zapisi[i][1]))}
            if otbor:
                kand = Counter(otbor)
    top = kand.most_common()
    luchshiy, ves = top[0]
    ravnyh = sum(1 for _, v in top if v == ves)
    if ravnyh > 1:
        return None, f'кандидатов с равным весом {ravnyh} — наугад не выдаём'
    if SPUTNIKI.search(zapisi[luchshiy][0]):
        return None, 'кандидат — юрлицо-спутник (поликлиника, охрана, профсоюз и т. п.)'
    # Симметрия: совпасть должно не только слово из запроса, но и заметная доля
    # сильных слов самого кандидата. Без этого «вошёл в состав Новолипецкого»
    # притягивало ООО «Чистый состав» по единственному слову «состав».
    kand_silnye = silnye(zapisi[luchshiy][2])
    obshchie = s & zapisi[luchshiy][2]
    if kand_silnye and len(obshchie) / len(kand_silnye) < 0.5:
        return None, (f'односторонний матч: совпало {len(obshchie)} из '
                      f'{len(kand_silnye)} сильных слов кандидата')
    return luchshiy, 'совпало: ' + ','.join(sorted(obshchie))


def zamer():
    """Слепой замер: названия из реестра ЭПБ, ИНН оттуда же как правильный ответ."""
    zapisi, ind = zagruzit()
    etalon = {}
    for f in ('engineers-lens/centro/epb-vozdushnye.csv',
              'engineers-lens/centro/epb-centro-vse.csv'):
        p = os.path.join(DIR, f)
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            i = (r.get('inn_zakazchika') or '').strip()
            n = (r.get('zakazchik') or '').strip()
            if i and n:
                etalon.setdefault(i, n)
    print(f'контрольных пар «название → ИНН»: {len(etalon)}', file=sys.stderr)
    verno = nverno = otkaz = net_v_baze = 0
    oshibki = []
    for inn, nazv in etalon.items():
        if inn not in zapisi:
            net_v_baze += 1
            continue
        got, pochemu = naiti(nazv, '', zapisi, ind)
        if got is None:
            otkaz += 1
        elif got == inn:
            verno += 1
        else:
            nverno += 1
            if len(oshibki) < 8:
                oshibki.append((nazv, inn, got, zapisi[got][0], pochemu))
    est = verno + nverno + otkaz
    print(f'\nиз {len(etalon)} названий в базе есть {est}, отсутствует {net_v_baze}')
    print(f'  верно      {verno}')
    print(f'  НЕВЕРНО    {nverno}')
    print(f'  отказ      {otkaz}')
    if verno + nverno:
        print(f'  точность на выданных ответах: {100 * verno // (verno + nverno)} %')
    print('\nошибки:')
    for nazv, pravda, got, gotname, pochemu in oshibki:
        print(f'   «{nazv[:34]}» → {got} {gotname[:30]} (верно {pravda}); {pochemu[:40]}')


def razreshit(path, out):
    zapisi, ind = zagruzit()
    imena = [l.strip() for l in open(path, encoding='utf-8') if l.strip()]
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['nazvanie', 'inn', 'nazvanie_v_baze', 'region', 'pochemu'])
        n = 0
        for im in imena:
            got, pochemu = naiti(im, '', zapisi, ind)
            w.writerow([im, got or '', zapisi[got][0] if got else '',
                        zapisi[got][1] if got else '', pochemu])
            n += bool(got)
    print(f'разрешено {n} из {len(imena)} → {out}', file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: inn_po_nazvaniyu.py zamer | razresh <names.txt> <out.csv>')
    if sys.argv[1] == 'zamer':
        zamer()
    else:
        razreshit(sys.argv[2], sys.argv[3])
