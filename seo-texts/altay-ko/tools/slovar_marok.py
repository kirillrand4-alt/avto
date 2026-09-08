# -*- coding: utf-8 -*-
"""Словарь марок центробежных машин: марка -> среда. Пункт 9 владельца.

ЗАЧЕМ. Среда в тексте заключения названа далеко не всегда: из 5 238 центробежных машин
реестра ЭПБ у 2 626 её нет вовсе. А владельцу нужна ВОЗДУШНАЯ. Но марка сама по себе среду
знает: К-905 это воздушный компрессор химкомбината, НЦ-16/76 — нагнетатель природного газа
для ГПА. Значит по маркам, где среда названа, можно закрыть те, где не названа.

КАК СТРОИТСЯ, и почему это не выдумка. Для каждой марки считаем, в скольких строках рядом с
ней среда названа воздухом и в скольких газом. Вердикт ставится ТОЛЬКО при двух условиях:
свидетельств не меньше пяти и перевес не меньше четырёх пятых. Всё остальное остаётся
«неизвестна» — притворяться, что мы знаем, хуже, чем признать, что нет.

Источники: реестр ЭПБ (объект заключения) и факты панели (предмет закупки). Марка из закупки
и марка из заключения — независимые свидетельства, они складываются.
"""
import collections, csv, json, os, re, sys

csv.field_size_limit(10 ** 7)
MARKA = re.compile(r'\b([А-ЯЁA-Z]{1,6}[\-–]?\d{1,4}(?:[\-–/][\d,\.]{1,6})*(?:[А-ЯЁA-Z]{0,3})?)\b')
SLOVO = re.compile(r'компрессор|воздуходувк|нагнетател|турбокомпрессор|газодувк|турбина', re.I)
# НЕ МАРКА. Первый прогон вынес в «самые частые воздушные» строки `А67-00348-0001` и
# `А39-00790-0007` — это регистрационные номера ОПО в Ростехнадзоре, они стоят в тексте
# заключения рядом с машиной и по форме похожи на марку. Ещё ловились «В-1», «В-2» —
# позиционные обозначения, а не марки. Поэтому: отдельно отсекаем формат реестра ОПО и
# требуем, чтобы у марки была либо буквенная приставка из двух и более букв, либо
# составной номер через дефис или дробь.
NE_MARKA = re.compile(r'^(инв|зав|поз|тех|рег|ОПО|II|III|IV|№)', re.I)
REG_OPO = re.compile(r'^[А-ЯЁA-Z]\d{2}-\d{4,6}-\d{3,5}$')


def pohozhe_na_marku(v):
    if REG_OPO.match(v):
        return False
    bukv = len(re.match(r'^[А-ЯЁA-Z]*', v).group(0))
    sostavnoy = v.count('-') + v.count('/') >= 1 and len(re.sub(r'\D', '', v)) >= 3
    return bukv >= 2 or sostavnoy
GAZ = re.compile(r'синтез-газ|синтез газ|природн\w*\s*газ|попутн\w*\s*газ|нефтян\w*\s*газ|'
                 r'\bГПА\b|газоперекачив|азот\w*|кислород\w*|аммиак|водород|этилен|пропилен|'
                 r'углекислот|сероводород|\bхлор\b|\bметан\b|циркуляционн\w*\s*газ|'
                 r'коксов\w*\s*газ|доменн\w*\s*газ|конвертируем\w*\s*газ|'
                 r'технологическ\w*\s*газ|газов\w*\s', re.I)
VOZDUH = re.compile(r'воздух|воздушн|воздуходувк|турбовоздуходувк|пневмо|дутьев', re.I)
MIN_SVID, PEREVES = 5, 0.8


def marki_iz(tekst):
    """Марки, стоящие рядом со словом машины. Окно 140 знаков — дальше начинается чужая."""
    out = set()
    for m in SLOVO.finditer(tekst or ''):
        for mm in MARKA.finditer(tekst[m.start():m.start() + 140]):
            v = mm.group(1)
            if len(v) < 3 or not re.search(r'\d', v) or NE_MARKA.match(v):
                continue
            if not pohozhe_na_marku(v):
                continue
            out.add(v.replace('–', '-').upper())
    return out


def sobrat(puti):
    svid = collections.defaultdict(collections.Counter)
    vsego = collections.Counter()
    for put, pole_obj in puti:
        if not os.path.exists(put):
            print(f'  НЕТ ФАЙЛА: {put}', file=sys.stderr)
            continue
        n = 0
        for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'):
            ob = r.get(pole_obj) or ''
            if not ob:
                continue
            g, v = bool(GAZ.search(ob)), bool(VOZDUH.search(ob))
            for mk in marki_iz(ob):
                vsego[mk] += 1
                if g and not v:
                    svid[mk]['газ'] += 1
                elif v and not g:
                    svid[mk]['воздух'] += 1
                elif g and v:
                    svid[mk]['оба'] += 1
            n += 1
        print(f'  прочитано {n} строк из {os.path.basename(put)}', file=sys.stderr)
    return svid, vsego


def vydat(svid, vsego):
    slovar = {}
    for mk, c in svid.items():
        vzd, gz = c['воздух'], c['газ']
        vs = vzd + gz
        if vs < MIN_SVID:
            itog, pochemu = 'неизвестна', f'свидетельств мало: воздух {vzd}, газ {gz}'
        elif vzd >= vs * PEREVES:
            itog, pochemu = 'воздух', f'воздух {vzd} из {vs}'
        elif gz >= vs * PEREVES:
            itog, pochemu = 'газ', f'газ {gz} из {vs}'
        else:
            itog, pochemu = 'смешанная', f'воздух {vzd}, газ {gz} — марка ставится и так, и так'
        slovar[mk] = {'sreda': itog, 'pochemu': pochemu, 'vstrechalas': vsego[mk],
                      'vozduh': vzd, 'gaz': gz}
    return slovar


if __name__ == '__main__':
    svid, vsego = sobrat([('EPB-NASHI-MASHINY.csv', 'obekt'),
                          ('FAKTY-s-priznakom-musora.csv', 'citata'),
                          ('BAZA-CENTROBEZHNIKI-OBSHCHAYA-dop3.csv', 'osnovanie_roli')])
    sl = vydat(svid, vsego)
    st = collections.Counter(v['sreda'] for v in sl.values())
    print(f'\nмарок всего: {len(sl)} | {dict(st)}', file=sys.stderr)
    json.dump(sl, open('SLOVAR-MAROK.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open('SLOVAR-MAROK.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['marka', 'sreda', 'pochemu', 'vstrechalas', 'vozduh', 'gaz'])
        for mk, v in sorted(sl.items(), key=lambda x: -x[1]['vstrechalas']):
            w.writerow([mk, v['sreda'], v['pochemu'], v['vstrechalas'], v['vozduh'], v['gaz']])
    print('воздушные марки, чаще всего встречающиеся:', file=sys.stderr)
    for mk, v in sorted(sl.items(), key=lambda x: -x[1]['vstrechalas'])[:60]:
        if v['sreda'] == 'воздух':
            print(f"  {v['vstrechalas']:>4}  {mk:<18} {v['pochemu']}", file=sys.stderr)
