# -*- coding: utf-8 -*-
"""Приём потока `park_ingest_3d.jsonl` 3-й сессии.

У неё в потоке 1 118 строк на 1 039 предприятий, у КАЖДОЙ строки две и более ссылки —
это ровно то, чего требует владелец. Её счётчик говорит «новых для парка 836», мой прибор
по моему парку — 241: она считает новизну по своей базе, я по своей, числа меряют разное
и оба верны.

Что делаю сверх её данных: из ссылки-поиска вытаскиваю реестровый номер и строю адрес
КАРТОЧКИ закупки (11 знаков — 223-ФЗ, 19 — 44-ФЗ). Форма проверена на 12 живых ссылках:
номер и предмет видны на странице. Все её ссылки тоже сохраняю — правило владельца
«ссылок несколько = строк несколько».
"""
import sqlite3, json, os, re, time, importlib.util, collections

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
INN = re.compile(r'^\d{10}$|^\d{12}$')
_NOMER = re.compile(r'searchString=(\d{11,19})\b')

KANON = [
    (r'мкс|модульн\w*компрессорн', 'МКС'), (r'\bпкс\b|передвижн\w*компрессорн', 'ПКС'),
    (r'\bгпа\b|газоперекачив', 'ГПА'), (r'\bвру\b|воздухораздел', 'ВРУ'),
    (r'генератор\w*кислород|кислородн\w*(станци|установк)', 'генератор кислорода'),
    (r'генератор\w*азот|азотн\w*(станци|установк)', 'генератор азота'),
    (r'турбокомпрессор', 'турбокомпрессор'), (r'нагнетател', 'нагнетатель'),
    (r'воздуходувк|газодувк', 'воздуходувка'), (r'осушител', 'осушитель'),
    (r'ресивер|воздухосборник', 'ресивер'),
    (r'компрессорн\w*(станци|установк)', 'компрессорная станция'),
    (r'компрессор|компримирован|сжат\w*воздух', 'компрессор'),
]
_SERVIS = re.compile(r'ремонт|обслуживан|запчаст|запасн\w*част|зип|масл|фильтр|'
                     r'диагностик|экспертиз|поверк|наладк')


def bp(t):
    return re.sub(r'\s+', '', (t or '').lower().replace('ё', 'е'))


def kartochka(n):
    if len(n) == 11:
        return ('https://zakupki.gov.ru/223/purchase/public/purchase/info/'
                'common-info.html?regNumber=' + n)
    return ('https://zakupki.gov.ru/epz/order/notice/ea44/view/'
            'common-info.html?regNumber=' + n)


vs = pr = ot = 0
pri = collections.Counter()
inny, novye, ssyl = set(), set(), 0
bylo = {r[0] for r in cur.execute('select distinct inn from fakt where v_parke=1')}
for ln in open(os.path.join(D, 'park_ingest_3d.jsonl'), encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    vs += 1
    x = json.loads(ln)
    inn = (x.get('inn') or '').strip()
    predmet = (x.get('predmet') or '').strip()
    if not INN.match(inn):
        pri['ИНН не разобран'] += 1; ot += 1; continue
    if not predmet:
        pri['пустой предмет'] += 1; ot += 1; continue
    n = bp(predmet)
    tip = next((k for rx, k in KANON if re.search(rx, n)), None) or (x.get('vid') or '').strip()
    if not tip:
        pri['тип не определился'] += 1; ot += 1; continue
    vid = 'расходник' if _SERVIS.search(n) else 'машина'
    ssylki = [s.strip() for s in (x.get('istochniki') or '').split('|') if s.strip().startswith('http')]
    nomera = [m.group(1) for s in ssylki for m in [_NOMER.search(s)] if m]
    if nomera:
        ssylki.insert(0, kartochka(nomera[0]))
    if not ssylki:
        pri['нет ни одной ссылки'] += 1; ot += 1; continue
    dedup = '|'.join([inn, tip, '', '', '', nomera[0] if nomera else predmet[:40]])
    cur.execute(
        'insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
        'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
        'pochemu,uverennost,kto,karantin,dedup,ts,v_parke,vid_fakta) '
        'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)',
        (inn, (x.get('predpriyatie') or '')[:200], tip,
         'закупка' if vid == 'машина' else 'сервис', '', '', '', '', '', '', '', '',
         2, 'E: закупка из потока 3-й сессии, класс машины отсюда не следует', predmet[:500],
         'поток 3-й сессии park_ingest_3d: ЕИС, у строки две и более ссылки',
         'vysokaya', '3-я сессия, поток 3d; принято 1-й', '', dedup,
         time.strftime('%Y-%m-%d %H:%M:%S'), vid))
    row = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
    if row:
        for u in ssylki[:6]:
            raz = pb.razbor_url(u)
            if raz:
                cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,'
                            'etap,pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                            (row[0], u, raz[0], raz[1],
                             'карточка закупки' if 'common-info' in u else 'ссылка потока 3-й',
                             raz[2], '', ''))
                ssyl += cur.rowcount
    inny.add(inn)
    if inn not in bylo:
        novye.add(inn)
    pr += 1
if pr + ot != vs:
    pri['!НЕ СОШЛОСЬ'] = vs - pr - ot
cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'ПОТОК 3-й СЕССИИ park_ingest_3d',
             vs, pr, ot, json.dumps(dict(pri), ensure_ascii=False)))
p.commit()
print('строк на входе %d | принято %d | брак %d %s' % (vs, pr, ot, dict(pri)))
print('предприятий %d | НОВЫХ ДЛЯ ПАРКА %d | ссылок добавлено %d' % (len(inny), len(novye), ssyl))
q = lambda s: cur.execute(s).fetchone()[0]
print('база: фактов %d | в парке %d | ИНН %d' % (
    q('select count(*) from fakt'), q('select count(*) from fakt where v_parke=1'),
    q('select count(distinct inn) from fakt where v_parke=1')))
p.close()
