# -*- coding: utf-8 -*-
"""Чистка фактов: оставить только ВОЗДУШНОЕ компрессорное оборудование (сжатый воздух и то,
что на нём работает: воздуходувки, ВРУ, азотные и кислородные станции, осушители, воздушные ресиверы).
Каждой карточке ставится vozduh: 1 - воздушное КО, 0 - мусор, NULL - неясно, и vozduh_pochemu - причина.
Мусор: холодильные и аммиачные машины, коксовые и природные газы, углекислота, автотехника, медтехника,
покупка газов в баллонах, ЭПБ на некомпрессорное оборудование.
Разбор идёт дважды: по обычному тексту и по склеенному без пробелов - в снимках парка слова
разорваны («поршнев ого компрессор а»). argv: [POKAZAT] - показать разбор, в базу не писать."""
import os, re, sys, sqlite3, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
POKAZAT = 'POKAZAT' in sys.argv

# --- бесспорные признаки сжатого воздуха (проверяются и по склеенному тексту, поэтому \w* вместо пробелов)
VOZDUH = re.compile(r'''
 воздушн\w*\s*компрессор | компрессор\w*\s*воздушн | винтов\w*\s*компрессор | поршнев\w*\s*компрессор
 | компрессор\w*\s*(?:винтов|поршнев|роторн|спиральн|центробежн|высокого\s*давлени)
 | компрессорн\w*\s*(?:станци|установк|цех|отделени|агрегат|блок|оборудован|хозяйств)
 | станци\w*\s*сжатого\s*воздуха | сжат\w*\s*воздух | пневмосет | пневмолини | пневмосистем | пневмотранспорт | пневмоинструмент
 | воздуходувк | турбовоздуходувк | нагнетател\w*\s*воздух | воздухосборник | ресивер\w*\s*воздушн
 | осушител\w*\s*(?:сжатого\s*)?воздух | воздухоразделительн | \bВРУ\b
 | генератор\w*\s*(?:азота|кислорода) | азотн\w*\s*(?:станци|генератор|установк) | кислородн\w*\s*(?:станци|генератор|установк)
 | производств\w*\s*(?:и\s*наполнени\w*\s*)?кислород | машинист\w*\s*компрессор | компрессорн\w*\s*масл | масло\s*компрессорн
 | компрессор\w*\s*высокого\s*давления | дыхательн\w*\s*аппарат
 | \bЗИФ\b | \bПКС[-\s]?\d | Atlas\s*Copco | Атлас\s*Копко | Kraftmann | Ремеза | Remeza | Comprag | Ceccato
 | Chicago\s*Pneumatic | Ingersoll | Fusheng | Kaeser | Boge | Airpol | ДЭН[-\s]?\d | Эрствак | CROSSAIR
''', re.I | re.X)

# --- марки воздушных машин
MARKI_VOZDUH = re.compile(r'\b(?:3С2СНП|2СНП|С2СНП|7ВП|305ВП|202ВП|2ВМ|4ВМ|4ВУ|ВУ-?\d|С-?415|К-?250|К-?500|К-?1500'
                          r'|ЦК-?\d|\d{1,2}ВЦ-?\d|ВЦ-?\d{2,3}|ВК-?\d|ВВ-?\d|ЭПКУ|НВ-?10|ВШ-?\d|ВП-?\d{1,2}[/-]|ТВ-?\d{2,3}|ТГ-?\d{2,3})', re.I)

# --- бесспорно не воздух
MUSOR = re.compile(r'''
 холодильн | фреон | хладаген | аммиачн | \bАХУ\b | Tecumseh | Copeland | Bitzer | Danfoss | Sabroe | MYCOM | Grasso
 | кондиционер | сплит-систем | холодильник | морозильн | \bларь\b | пароконвектомат | \bШХС\b | кофеварк | мясорубк
 | ресивер\w*\s*(?:линейн|дренажн|защитн|циркуляционн) | \d[,.]?\d?\s*Р[ВД]\b | маслоотделител | конденсатор\w*\s*испарительн
 | нагнетател\w*\s*(?:коксов|доменн|природн|попутн) | коксов\w*\s*газ | \bН[-\s]?700 | конденсатоотводчик | маслобак
 | томограф | анализатор\w*\s*гематолог | стоматолог | стерилизатор | больниц | поликлин | медицинск | \bМИ\b
 | автомобил | автобус | \bЗИЛ\b | \bГАЗ-\d | \bПАЗ\b | КАМАЗ | трактор | комбайн | тормозн | шиномонтаж | подкачк\w*\s*шин
 | газов\w*\s*компрессор | компрессор\w*\s*газов | газопровод | газораспределени | газопотреблени | \bГРП\b | газгольдер
 | углекислот | двуокис\w*\s*углерода | \bСО2\b | \bCO2\b
 | поставк\w*\s*(?:технических\s*)?газов | азот\s*жидк | кислород\s*газообразн\w*\s*техническ | баллон
 | пожарн\w*\s*сигнализац | оценк\w*\s*рыночной\s*стоимости | транспортировани\w*\s*опасных\s*веществ
 | тротил | нитроэфир | цетаноповышающ | пылесос | тентов | телятник | пасек | \bмёда\b
 | вентиляц\w*\s*и\s*кондиционир | тепловая\s*сет | паров\w*\s*(?:котёл|котел) | \bЦВН\b
 | газификатор | криогенн\w*\s*газификатор | турбокомпрессор\w*\s*на\s*Д-?\d | \bД-?24[05]\b | \bЯМЗ\b | дизельн\w*\s*двигател
''', re.I | re.X)

MARKI_HOLOD = re.compile(r'\b(?:П-?\d{2,3}(?:-7)?(?:-0?\d)?|АУ-?\d{2,3}|АУУ|21А\d{2,3}|NF-?\d|SAB-?\d|ФУУ|ФУБС|5ПБ|22ПБ|АГК|МКТ-?\d|ХМ-?\d|ВХ-?\d)\b', re.I)
KONTEKST_GAZ = re.compile(r'\bГНС\b|\bГНП\b|\bАГЗС\b|сжиженн|пропан|бутан|\bСУГ\b|нефтепровод|скважин', re.I)
# --- собственный воздушный узел, назван прямо: перебивает стоп-слово рядом
UZEL = re.compile(r'винтов\w*\s*компрессор|поршнев\w*\s*компрессор|воздуходувк|компрессорн\w*\s*станци|воздухоразделительн|сжат\w*\s*воздух|пневмо', re.I)
# --- ЭПБ и ОПО не про компрессор: экспертиза чужого оборудования
NE_KO = re.compile(r'насос|теплообмен|металлорежущ|грузоподъёмн|грузоподъемн|\bкран\b|трубопровод|резервуар|эстакад|дымов\w*\s*труб|здани|сооружени|склад', re.I)

def sudit(tip, marka, sreda, citata, vid):
    syr = ' '.join(x or '' for x in (tip, marka, sreda, citata))
    skl = re.sub(r'\s+', '', syr)
    def est(rx): 
        m = rx.search(syr) or rx.search(skl)
        return m
    mv, mm = est(VOZDUH), est(MUSOR)
    if mm and mv and est(UZEL): return 1, 'воздушный узел назван прямо: ' + mv.group(0)[:40]
    if mm: return 0, 'стоп-слово: ' + mm.group(0)[:40]
    if mv: return 1, 'признак: ' + mv.group(0)[:40]
    if est(KONTEKST_GAZ): return 0, 'газовое хозяйство: ' + est(KONTEKST_GAZ).group(0)[:30]
    if MARKI_HOLOD.search(syr): return 0, 'марка холодильной машины: ' + MARKI_HOLOD.search(syr).group(0)[:30]
    if MARKI_VOZDUH.search(syr): return 1, 'марка воздушной машины: ' + MARKI_VOZDUH.search(syr).group(0)[:30]
    sr = (sreda or '').strip()
    if sr == 'воздух': return 1, 'среда воздух'
    # Промышленный «компрессор» без уточнения - почти всегда воздушный: холод, газ и авто уже отсеяны
    # стоп-словами выше. Помечаем 2 - «вероятно воздушный», в выгрузке идёт с оговоркой.
    if re.search(r'компрессор', syr, re.I) or re.search(r'компрессор', skl, re.I):
        return 2, 'компрессор назван, тип не уточнён - вероятно воздушный'
    if sr in ('газ', 'аммиак', 'водород', 'кислород', 'азот'): return 0, 'среда не воздух: ' + sr
    v = vid or ''
    if v.startswith('ОПО') or v == 'ЭПБ':
        m = NE_KO.search(syr)
        if m: return 0, 'экспертиза не компрессорного оборудования: ' + m.group(0)[:30]
        return 0, 'объект/устройство без признака сжатого воздуха'
    return None, 'неясно'

c = sqlite3.connect(DB, timeout=180)
for st in ('alter table fakty add column vozduh integer', 'alter table fakty add column vozduh_pochemu text'):
    try: c.execute(st)
    except sqlite3.OperationalError: pass
rows = c.execute('select rowid, tip, marka_model, sreda, citata, vid_fakta from fakty').fetchall()
sch = collections.Counter(); prim = collections.defaultdict(list); obn = []
for rid, tip, marka, sreda, cit, vid in rows:
    v, poch = sudit(tip, marka, sreda, cit, vid)
    imya = 'воздух' if v == 1 else 'вероятно воздух' if v == 2 else 'мусор' if v == 0 else 'неясно'
    sch[imya] += 1; sch[imya + ' / ' + (vid or '?')] += 1
    if len(prim[v]) < 6: prim[v].append(f'{vid} | {tip} | ' + re.sub(r'\s+', ' ', cit or '')[:110] + '  <= ' + poch)
    obn.append((v, poch, rid))
if not POKAZAT:
    c.executemany('update fakty set vozduh=?, vozduh_pochemu=? where rowid=?', obn); c.commit()
print('всего карточек', len(rows))
for k in ('воздух', 'вероятно воздух', 'мусор', 'неясно'): print(f'  {k}: {sch[k]}')
print('--- по видам (топ)')
for k, n in sorted(((k, n) for k, n in sch.items() if ' / ' in k), key=lambda x: -x[1])[:18]: print(f'   {k}: {n}')
for v in (2, None):
    print('=== примеры', {2: 'ВЕРОЯТНО ВОЗДУХ', None: 'НЕЯСНО'}[v])
    for s in prim[v]: print('   ', s)
print('предприятий с воздушным фактом:', c.execute('select count(distinct inn) from fakty where vozduh=1').fetchone()[0])
print('предприятий с вероятным:', c.execute('select count(distinct inn) from fakty where vozduh=2').fetchone()[0],
      '| из них только вероятное:', c.execute('select count(distinct inn) from fakty where vozduh=2 and inn not in (select inn from fakty where vozduh=1)').fetchone()[0])
print('предприятий только со спорным (неясно, без воздуха):',
      c.execute('select count(distinct inn) from fakty where vozduh is null and inn not in (select inn from fakty where vozduh=1)').fetchone()[0])
c.close()
