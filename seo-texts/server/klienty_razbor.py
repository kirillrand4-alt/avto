# -*- coding: utf-8 -*-
r"""Разбор обхода klienty_obhod.py: сайт -> ИНН -> выручка/название (ФНС revexp) -> ОКВЭД (enrich.db: companies, requisites;
checko) -> сегмент Meyer (pilot_otbor.СЕГМ) / КЦ (kc_cel.СЕГМ) -> Excel «клиенты и их закупки». Без моделей.

    python klienty_razbor.py [папка_обхода] [выход.xlsx]
По умолчанию папка C:\sender\server\klienty (все klienty-s*.jsonl), выход — klienty-itog.xlsx там же и копия на дроп.
ИНН без ОКВЭД (нет ни в enrich.db, ни в checko) с выручкой от KLIENTY_CHECKO_OT (по умолчанию 30 млн) — в дроп
klienty-checko-vhod.json: прогнать `CHECKO_VHOD=klienty-checko-vhod.json python fsa_meyer_checko.py` и запустить разбор ещё раз.
Какой ИНН сайта «свой»: на сайте бывает несколько ИНН (банк, разработчик, оператор ПДн). Берём ИНН со страницы реквизитов /
политики / контактов, при равенстве — первый; остальные — в колонку «другие ИНН» (могут быть группой).
"""
import collections, io, json, os, re, shutil, sqlite3, sys, zipfile
import xml.etree.ElementTree as ET
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kc_cel  # noqa: E402
import fsa_klass3_vhod as FK  # noqa: E402  (сегменты Meyer из pilot_otbor без импорта серверных модулей)

WIN = os.name == 'nt'
ПАПКА = sys.argv[1] if len(sys.argv) > 1 else r'C:\sender\server\klienty'
ВЫХОД = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ПАПКА, 'klienty-itog.xlsx')
ДРОП = os.environ.get('KLIENTY_DROP') or r'C:\seostat\drop\drop-storage'
REVEXP = os.environ.get('KLIENTY_REVEXP') or r'C:\sender\_ops\ak\fns\revexp.zip'
ENRICH = os.environ.get('KLIENTY_ENRICH') or r'C:\sender\enrich.db'
CHECKO = os.environ.get('KLIENTY_CHECKO') or r'C:\sender\server\fsa-meyer-checko.jsonl'
CHECKO_OT = float(os.environ.get('KLIENTY_CHECKO_OT', '3e7'))
ЗАКУПКИ_ДА = ('кандидат: своя ЭТП', 'кандидат: страница с лотами', 'внешняя ЭТП', 'ссылка на внешний портал', 'план закупок',
              'страница закупок без лотов')
СИЛА = {'кандидат: своя ЭТП': 6, 'кандидат: страница с лотами': 5, 'внешняя ЭТП': 4, 'план закупок': 4, 'ссылка на внешний портал': 3,
        'страница закупок без лотов': 1}


def свой_инн(r):
    стр = r.get('inn_page') or {}
    def вес(i):
        u = (стр.get(i) or '').lower()
        return 0 if re.search(r'rekvizit|requisit|реквизит', u) else 1 if re.search(r'polit|privacy|policy|oferta|agreement', u) else \
            2 if re.search(r'kontakt|contact', u) else 3
    инн = [i for i in r.get('inn') or [] if len(i) == 10] or list(r.get('inn') or [])
    return sorted(инн, key=lambda i: (вес(i), инн.index(i)))[0] if инн else ''


def main():
    сайты = []
    for f in sorted(os.listdir(ПАПКА)):
        if re.match(r'klienty(-s\d+)?\.jsonl$', f):
            for s in io.open(os.path.join(ПАПКА, f), encoding='utf-8', errors='replace'):
                try:
                    сайты.append(json.loads(s))
                except ValueError:
                    pass
    по_инн = collections.defaultdict(list)
    for r in сайты:
        r['свой_инн'] = свой_инн(r)
        if r['свой_инн']:
            по_инн[r['свой_инн']].append(r)
    print('сайтов с находками', len(сайты), '| с ИНН', sum(1 for r in сайты if r['свой_инн']), '| ИНН', len(по_инн), flush=True)
    # выручка и название — ФНС revexp (все организации РФ)
    фнс = {}
    if os.path.exists(REVEXP):
        with zipfile.ZipFile(REVEXP) as z:
            for n in z.namelist():
                with z.open(n) as fh:
                    for ev, el in ET.iterparse(fh, events=('end',)):
                        if not el.tag.endswith('Документ'):
                            continue
                        i = имя = v = None
                        for ch in el:
                            if 'СведНП' in ch.tag:
                                i, имя = ch.get('ИННЮЛ') or ch.get('ИННФЛ'), ch.get('НаимОрг') or ''
                            elif 'ДохРасх' in ch.tag:
                                v = ch.get('СумДоход')
                        if i in по_инн:
                            try:
                                фнс[i] = (имя, float(v or 0))
                            except ValueError:
                                фнс[i] = (имя, 0.0)
                        el.clear()
    print('ФНС: выручка/название у', len(фнс), flush=True)
    # ОКВЭД, регион, база обзвона — enrich.db; потом checko
    окв, рег, в_базе = {}, {}, set()
    if os.path.exists(ENRICH):
        con = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
        for i, о, р in con.execute('select inn, okved, region from companies'):
            i = str(i or '').strip()
            if i in по_инн:
                в_базе.add(i)
                if о:
                    окв[i] = str(о).split()[0]
                if р:
                    рег[i] = р
        for i, о, оа in con.execute('select inn, okved_main, okved_all from requisites'):
            i = str(i or '').strip()
            if i in по_инн and о and i not in окв:
                окв[i] = str(о).split()[0]
        con.close()
    доп = {}
    if os.path.exists(CHECKO):
        for s in io.open(CHECKO, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
            except ValueError:
                continue
            i = y.get('inn')
            if i in по_инн and y.get('итог') == 'ok':
                if y.get('оквэд') and i not in окв:
                    окв[i] = str(y['оквэд']).split()[0]
                доп[i] = [str(x).split()[0] for x in (y.get('оквэд_все') or [])]
                if y.get('регион') and i not in рег:
                    рег[i] = y['регион']
    print('ОКВЭД у', len(окв), '| в базе обзвона', len(в_базе), flush=True)
    СМ, ИМ = FK.сегменты_meyer()
    строки, нужен_checko = [], []
    for i, рр in по_инн.items():
        имя, выр = фнс.get(i, ('', 0.0))
        о = окв.get(i, '')
        см = FK.сегм(о, доп.get(i, []), СМ, ИМ) if о else ''
        ск = FK.сегм(о, доп.get(i, []), kc_cel.СЕГМ, kc_cel.ИСКЛ) if о else ''
        if not о and (выр >= CHECKO_OT or not выр):
            нужен_checko.append(i)
        лучший = max(рр, key=lambda r: СИЛА.get(r.get('verdict'), 0))
        строки.append({
            'ИНН': i, 'Название (ФНС)': имя, 'Выручка 2025, руб': выр or None, 'ОКВЭД': о, 'Сегмент Meyer': см, 'Сегмент КЦ': ск,
            'Регион': рег.get(i, ''), 'В базе обзвона': 'да' if i in в_базе else '', 'Сайты': ', '.join(r['host'] for r in рр),
            'Страница с ИНН': (лучший.get('inn_page') or {}).get(i, ''),
            'Другие ИНН на сайте': ', '.join(sorted({x for r in рр for x in r.get('inn') or [] if x != i}))[:200],
            'Телефоны': ', '.join(лучший.get('phones') or [])[:200], 'Почты': ', '.join(лучший.get('emails') or [])[:200],
            'Закупки: вердикт': лучший.get('verdict', ''),
            'Закупки: страницы': ' | '.join(p.get('url', '') for p in лучший.get('pages') or [])[:500] or
                                 ' | '.join(l[0] for l in лучший.get('links') or [])[:500],
            'Внешние ЭТП': ', '.join(sorted(лучший.get('ext_etp') or {})),
            'Внешний портал закупок': ' | '.join(l[0] for l in лучший.get('ext_links') or [])[:300],
            'План закупок': ' | '.join(p[0] for p in лучший.get('plans') or [])[:500]})
    строки.sort(key=lambda r: -(r['Выручка 2025, руб'] or 0))
    без_инн = [r for r in сайты if not r['свой_инн'] and r.get('verdict') in ЗАКУПКИ_ДА]
    wb = Workbook(write_only=True)
    жирн, фон = Font(bold=True), PatternFill('solid', fgColor='DDEBF7')

    def лист(имя, шапка, ряды):
        ws = wb.create_sheet(имя)
        cc = []
        for v in шапка:
            c = WriteOnlyCell(ws, value=v)
            c.font, c.fill = жирн, фон
            cc.append(c)
        ws.append(cc)
        for r in ряды:
            ws.append([r.get(k) if r.get(k) not in ('', None) else None for k in шапка])
        ws.freeze_panes = 'C2'
    Ш = list(строки[0].keys()) if строки else ['ИНН']
    лист('Клиенты Meyer', Ш, [r for r in строки if r['Сегмент Meyer']])
    лист('Клиенты КЦ', Ш, [r for r in строки if r['Сегмент КЦ'] and not r['Сегмент Meyer']])
    лист('Закупки (все с ИНН)', Ш, [r for r in строки if r['Закупки: вердикт'] in ЗАКУПКИ_ДА])
    лист('Закупки без ИНН', ['Сайт', 'Вердикт', 'Страницы', 'Внешние ЭТП', 'План закупок'],
         [{'Сайт': r['host'], 'Вердикт': r.get('verdict'), 'Страницы': ' | '.join(p.get('url', '') for p in r.get('pages') or [])[:500],
           'Внешние ЭТП': ', '.join(sorted(r.get('ext_etp') or {})), 'План закупок': ' | '.join(p[0] for p in r.get('plans') or [])[:500]}
          for r in без_инн])
    лист('Все ИНН', Ш, строки)
    св = wb.create_sheet('Сводка')
    for k, v in (('Сайтов с находками (ИНН или закупки)', len(сайты)), ('Сайтов с ИНН', sum(1 for r in сайты if r['свой_инн'])),
                 ('Разных ИНН', len(строки)), ('С выручкой ФНС 2025', sum(1 for r in строки if r['Выручка 2025, руб'])),
                 ('С ОКВЭД', sum(1 for r in строки if r['ОКВЭД'])), ('Клиенты Meyer (по ОКВЭД)', sum(1 for r in строки if r['Сегмент Meyer'])),
                 ('Клиенты КЦ (по ОКВЭД, не Meyer)', sum(1 for r in строки if r['Сегмент КЦ'] and not r['Сегмент Meyer'])),
                 ('Нет в базе обзвона', sum(1 for r in строки if not r['В базе обзвона'])),
                 ('С признаками закупок (с ИНН)', sum(1 for r in строки if r['Закупки: вердикт'] in ЗАКУПКИ_ДА)),
                 ('С признаками закупок без ИНН', len(без_инн)), ('Нужен checko (нет ОКВЭД)', len(нужен_checko))):
        св.append([k, v])
    wb.save(ВЫХОД)
    if WIN and os.path.isdir(ДРОП):
        shutil.copyfile(ВЫХОД, os.path.join(ДРОП, os.path.basename(ВЫХОД)))
        with open(os.path.join(ДРОП, 'klienty-checko-vhod.json'), 'w', encoding='utf-8') as f:
            json.dump(нужен_checko, f)
    print('===ИТОГ===', json.dumps({'ИНН': len(строки), 'Meyer': sum(1 for r in строки if r['Сегмент Meyer']),
                                    'КЦ': sum(1 for r in строки if r['Сегмент КЦ'] and not r['Сегмент Meyer']),
                                    'нужен_checko': len(нужен_checko), 'выход': ВЫХОД}, ensure_ascii=False))


if __name__ == '__main__':
    main()
