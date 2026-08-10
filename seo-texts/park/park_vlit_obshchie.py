# -*- coding: utf-8 -*-
"""Приём ОБЩИХ ЗАПРОСОВ ПО ТИПУ машины в park.db.

Владелец спросил прямо: «а общие запросы по типу винтовой компрессор используете?» —
не использовали, собирали по маркам. А марку в объявлении называют не всегда: «Ремонт
винтового компрессора», «Поставка компрессорной установки», «Услуги по обслуживанию
компрессорной станции» — машина есть, марки нет.

Тип берём из предмета закупки по тем же 13 каноническим типам, что и везде.
Вид факта:
  машина     — покупка, поставка, монтаж, аренда самой машины;
  расходник  — ремонт, обслуживание, запчасти, масло, фильтры (машина всё равно ЕСТЬ,
               иначе нечего обслуживать);
  узел       — трубопровод обвязки, ресивер, осушитель, влагоотделитель как отдельная позиция.
Сила факта 2: закупка доказывает машину, но не её класс — ранг ставится позже по сумме.

Две ссылки на факт, как требует владелец: карточка закупки и поиск по реестровому номеру.
"""
import sqlite3, json, re, os, time, importlib.util, collections

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
INN = re.compile(r'^\d{10}$|^\d{12}$')
FAYL = os.path.join(D, 'park_obshchie_inn.jsonl')


def bp(t):
    return re.sub(r'\s+', '', (t or '').lower().replace('ё', 'е'))


KANON = [
    (r'мкс|модульн\w*компрессорн', 'МКС'),
    (r'\bпкс\b|передвижн\w*компрессорн|дизельн\w*компрессорн', 'ПКС'),
    (r'\bгпа\b|газоперекачив', 'ГПА'),
    (r'\bвру\b|воздухораздел', 'ВРУ'),
    (r'генератор\w*кислород|кислородн\w*(станци|установк|генератор)', 'генератор кислорода'),
    (r'генератор\w*азот|азотн\w*(станци|установк|генератор)', 'генератор азота'),
    (r'турбокомпрессор', 'турбокомпрессор'),
    (r'нагнетател', 'нагнетатель'),
    (r'воздуходувк|газодувк', 'воздуходувка'),
    (r'осушител', 'осушитель'),
    (r'ресивер|воздухосборник', 'ресивер'),
    (r'компрессорн\w*(станци|установк)', 'компрессорная станция'),
    (r'компрессор|компримирован|сжат\w*воздух', 'компрессор'),
]
PRINCIP = [(r'винтов', 'винтовой'), (r'поршнев', 'поршневой'),
           (r'центробежн', 'центробежный'), (r'безмаслян', 'безмасляный')]
# ремонт/сервис/ЗИП доказывают машину не хуже покупки — она уже стоит у предприятия
_SERVIS = re.compile(r'ремонт|обслуживан|техническоеобслуживан|запчаст|запасн\w*част|'
                     r'зип|масл|фильтр|диагностик|экспертиз|поверк|наладк|модернизац')
_UZEL = re.compile(r'трубопровод|обвязк|влагоотделител|маслоотделител|концев\w*холодильник|'
                   r'воздухосборник|буферн\w*емкост')


def razobrat(predmet):
    n = bp(predmet)
    tip = next((k for rx, k in KANON if re.search(rx, n)), None)
    if not tip:
        return None, None, None
    princip = next((k for rx, k in PRINCIP if re.search(rx, n)), '')
    if _UZEL.search(n) and tip in ('компрессор', 'компрессорная станция'):
        vid = 'узел'
    elif _SERVIS.search(n):
        vid = 'расходник'
    else:
        vid = 'машина'
    return tip, vid, princip


vs = pr = ot = kt = km = 0
pri = collections.Counter()
inny, novye = set(), set()
if not os.path.exists(FAYL):
    raise SystemExit('нет файла %s — сначала снять ИНН с карточек' % FAYL)
bylo_inn = {r[0] for r in cur.execute('select distinct inn from fakt where v_parke=1')}
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    vs += 1
    try:
        r = json.loads(ln)
    except Exception:
        pri['строка не разобралась'] += 1
        ot += 1
        continue
    inn = (r.get('inn') or '').strip()
    nomer = (r.get('nomer') or '').strip()
    predmet = (r.get('predmet') or '').strip()
    url = (r.get('url_kartochki') or '').strip()
    if not INN.match(inn):
        pri['ИНН с карточки не снялся'] += 1; ot += 1; continue
    if not url:
        pri['нет адреса карточки'] += 1; ot += 1; continue
    if not predmet:
        pri['пустой предмет закупки'] += 1; ot += 1; continue
    if r.get('nomer_na_stranice') is False:
        pri['номера закупки нет на странице — карточка чужая'] += 1; ot += 1; continue
    tip, vid, princip = razobrat(predmet)
    if not tip:
        pri['тип машины из предмета не определился'] += 1; ot += 1; continue
    dedup = '|'.join([inn, tip, '', '', '', nomer])
    cur.execute(
        'insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
        'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
        'pochemu,uverennost,kto,karantin,dedup,ts,v_parke,vid_fakta,princip) '
        'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)',
        (inn, (r.get('org_imya') or r.get('zakazchik_iz_lenty') or '')[:200], tip,
         'закупка' if vid == 'машина' else ('сервис' if vid == 'расходник' else 'узел'),
         '', '', '', '', '', (r.get('summa') or ''), '', '',
         2, 'E: закупка по общему запросу, класс машины отсюда не следует', predmet[:500],
         'общий запрос по типу машины в ЕИС с нарезкой по окну публикации; '
         'ИНН снят с карточки закупки', 'vysokaya',
         '1-я сессия, общий запрос по типу (ЕИС)', '', dedup,
         time.strftime('%Y-%m-%d %H:%M:%S'), vid, princip))
    row = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
    if row:
        for u in (url, 'https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
                       '?searchString=' + nomer):
            raz = pb.razbor_url(u)
            if raz:
                cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,'
                            'etap,pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                            (row[0], u, raz[0], raz[1],
                             'карточка закупки' if u == url else 'поиск по реестровому номеру',
                             raz[2], '', ''))
    # контакт закупщика с той же карточки
    fio = (r.get('kontakt_fio') or '').strip()
    tel = re.sub(r'\D', '', r.get('kontakt_tel') or '')[-10:]
    mail = (r.get('kontakt_email') or '').strip()
    raz = pb.razbor_url(url)
    if raz:
        if len(tel) == 10:
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                        'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                        'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, 'telefon', tel, fio[:200], 'контактное лицо закупки', raz[1],
                         url, raz[0], raz[2], '',
                         ('карточка ЕИС №%s: %s' % (nomer, predmet))[:300],
                         '1-я сессия, контакт с карточки ЕИС (общие запросы)'))
            kt += 1
        if '@' in mail:
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                        'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                        'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, 'email', mail, fio[:200], 'контактное лицо закупки', raz[1],
                         url, raz[0], raz[2], '', ('карточка ЕИС №%s' % nomer)[:300],
                         '1-я сессия, контакт с карточки ЕИС (общие запросы)'))
            km += 1
    inny.add(inn)
    if inn not in bylo_inn:
        novye.add(inn)
    pr += 1

if pr + ot != vs:
    pri['!НЕ СОШЛОСЬ'] = vs - pr - ot
cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'ОБЩИЕ ЗАПРОСЫ ПО ТИПУ: закупки ЕИС с ИНН',
             vs, pr, ot, json.dumps(dict(pri), ensure_ascii=False)))
p.commit()
q = lambda s: cur.execute(s).fetchone()[0]
print('закупок на входе %d | принято %d | брак %d' % (vs, pr, ot))
print('  причины брака:', dict(pri))
print('предприятий в потоке: %d | ИЗ НИХ НОВЫХ ДЛЯ ПАРКА: %d' % (len(inny), len(novye)))
print('контактов с карточек: телефонов %d, почт %d' % (kt, km))
print()
print('=== БАЗА ПОСЛЕ ВЛИВАНИЯ ===')
print('  фактов %d | в парке %d | ИНН в парке %d'
      % (q('select count(*) from fakt'), q('select count(*) from fakt where v_parke=1'),
         q('select count(distinct inn) from fakt where v_parke=1')))
for r in cur.execute("""select tip, vid_fakta, count(*), count(distinct inn) from fakt
   where kto like '%общий запрос%' group by 1,2 order by 3 desc limit 12"""):
    print('    %-22s %-10s фактов %5d  ИНН %4d' % (r[0], r[1], r[2], r[3]))
p.close()
