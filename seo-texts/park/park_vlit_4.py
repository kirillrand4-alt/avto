# -*- coding: utf-8 -*-
"""Приём поставок соседей от 17:40–19:20:
  PARK-FAKTY-2S-SVOD.csv            31 492  свод ЭПБ 2-й после починки заслона (+5 016)
  park_ingest_3c.jsonl               4 351  закупки ЭТП ГПБ от 3-й
  PARK-EIS-OKPD2-3S.jsonl                4  ось ОКПД2, которую я передал 3-й
  PARK-KONTAKTY-2S-S-ROLYU.csv       3 057  контакты 2-й с ролью
  PARK-KONTAKTY-3S-CHESTNO.jsonl     7 140  контакты 3-й с честной меткой доказательства
  PARK-OBRATNYY-1S-PROVERENO-3S      114  |  обратный поиск по моим 909 инженерам,
  PARK-OBRATNYY-PROVERENO-3S         123  |  проверенный 3-й

Правило смены: ни одна ветка отбраковки не делает continue без записи ПРИЧИНЫ,
и в конце сходится «принято + брак = сумма причин». Молчаливая потеря 3 151 почты
и 838 строк за эту смену случилась ровно из-за отсутствия этой проверки.
"""
import sqlite3, json, re, os, csv, time, importlib.util

csv.field_size_limit(10 ** 7)
D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
INN = re.compile(r'^\d{10}$|^\d{12}$')
_PKS = re.compile(r'(?i)\bXATS|\bXAS\b|XAHS|\bPDS\b|\bDCA-|\bDCW-|ЗИФ-?ПВ|ПКСД|'
                  r'передвижн|на\s+шасси|на\s+прицеп|дизельн\w+\s+компрессорн|гар№|г/н\s*\d')
_MKS = re.compile(r'(?i)модульн|блочно-модульн|блок-контейнер|контейнерн\w+\s+исполнен|БМКС|'
                  r'компрессорн\w+\s+(станци\w+\s+)?под\s+ключ|компрессорн\w+\s+в\s+модуле')


def tochnyy_tip(yarlyk, tekst):
    y = (yarlyk or '').strip()
    if 'МКС' in y or 'передвиж' in y.lower():
        t = tekst or ''
        if _MKS.search(t): return 'МКС'
        if _PKS.search(t): return 'ПКС'
        return 'ПКС'
    if y in ('', 'неясно'):
        t = tekst or ''
        if _MKS.search(t): return 'МКС'
        if _PKS.search(t): return 'ПКС'
    return y


def ssyl(s):
    return [u.strip().rstrip(']') for u in re.split(r'\s*\|\s*', s or '')
            if u.strip().startswith('http')]


class Schet:
    """Счётчик, который сам ловит расхождение «принято + брак != причины»."""
    def __init__(self, chto):
        self.chto = chto; self.vs = 0; self.pr = 0; self.ot = 0; self.pri = {}

    def brak(self, prichina):
        self.ot += 1; self.pri[prichina] = self.pri.get(prichina, 0) + 1

    def zapisat(self):
        summa = sum(self.pri.values())
        if summa != self.ot:
            self.pri['!РАСХОЖДЕНИЕ причин и брака'] = self.ot - summa
        if self.pr + self.ot != self.vs:
            self.pri['!НЕ СОШЛОСЬ принято+брак vs всего'] = self.vs - self.pr - self.ot
        cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
                    (time.strftime('%Y-%m-%d %H:%M:%S'), self.chto, self.vs, self.pr, self.ot,
                     json.dumps(self.pri, ensure_ascii=False)))
        print('  %-46s всего=%-6s принято=%-6s брак=%-5s %s'
              % (self.chto[:46], self.vs, self.pr, self.ot, self.pri))
        p.commit()


def fakt_ssylki(fid, urls, predel=20):
    for u in urls[:predel]:
        raz = pb.razbor_url(u)
        if raz:
            cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                        'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                        (fid, u, raz[0], raz[1], '', raz[2], '', ''))


bylo_f = cur.execute('select count(*) from fakt').fetchone()[0]
bylo_k = cur.execute('select count(*) from contact_source').fetchone()[0]

# ---- 1. свод ЭПБ 2-й после починки заслона ----------------------------------
s = Schet('PARK-FAKTY-2S-SVOD.csv (свод 2-й, +заслон)')
with open(os.path.join(D, 'PARK-FAKTY-2S-SVOD.csv'), encoding='utf-8-sig', newline='') as fh:
    for r in csv.DictReader(fh, delimiter=';'):
        s.vs += 1
        inn = (r.get('inn') or '').strip()
        u = (r.get('ssylka') or '').strip()
        raz = pb.razbor_url(u)
        if not INN.match(inn):
            s.brak('ИНН не 10/12 цифр'); continue
        if not raz:
            s.brak('ссылка не URL'); continue
        citata = (r.get('citata') or '')
        tip = tochnyy_tip(r.get('tip'), citata)
        mm = (r.get('marka_model') or '').strip()
        zn = (r.get('zavodskoy_nomer') or '').strip()
        # ключ склейки: марка+зав.№ различают машины внутри одного предприятия,
        # без них ключом становится сама ссылка (урок «6 128 -> 1 459»)
        if mm or zn:
            dedup = '|'.join([inn, tip, '', mm, zn, (r.get('data') or '')])
        else:
            dedup = '|'.join([inn, tip, '', '', '', u])
        cur.execute(
            'insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
            'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
            'pochemu,uverennost,kto,karantin,dedup,ts) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (inn, (r.get('predpriyatie') or '')[:200], tip, 'эксплуатирует', '', mm, mm, zn,
             (r.get('sreda') or ''), '', (r.get('data') or ''), (r.get('srok_do') or ''),
             1, 'D+: срок ЭПБ %s' % (r.get('status_sroka') or ''), citata[:500],
             'ЭПБ №%s, вывод: %s, марка: %s' % (r.get('nomer_zaklucheniya'), r.get('vyvod'),
                                                r.get('chem_marka')),
             'vysokaya', 'PARK-FAKTY-2S-SVOD.csv (2-я, после заслона)', '', dedup,
             time.strftime('%Y-%m-%d %H:%M:%S')))
        row = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
        if not row:
            s.brak('вставка не дала id'); continue
        fakt_ssylki(row[0], [u])
        s.pr += 1
s.zapisat()

# ---- 2. закупки ЭТП ГПБ от 3-й ----------------------------------------------
s = Schet('park_ingest_3c.jsonl (ЭТП ГПБ, 3-я)')
for ln in open(os.path.join(D, 'park_ingest_3c.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    s.vs += 1
    r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    urls = ssyl(r.get('istochniki'))
    if not INN.match(inn):
        s.brak('ИНН не 10/12 цифр'); continue
    if not urls:
        s.brak('нет ссылки'); continue
    nz = (r.get('nazvanie_zakupki') or '')
    tip = tochnyy_tip(r.get('vid'), nz)
    # sama_mashina=False => это ЗИП/сервис: машину доказывает, но силу ставим слабее
    sama = bool(r.get('sama_mashina'))
    dedup = '|'.join([inn, tip, '', '', '', (r.get('nomer_zakupki') or urls[0])])
    cur.execute(
        'insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
        'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,rang_mashiny,'
        'chto_naydeno,pochemu,uverennost,kto,karantin,dedup,ts) '
        'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (inn, (r.get('organizaciya') or '')[:200], tip,
         'покупает машину' if sama else 'эксплуатирует', '', '', '', '', '', '', '', '',
         5 if sama else 2, 'C: класс цены по серии, ветка %s' % (r.get('vetka') or ''),
         r.get('klass_ceny'), nz[:500],
         'ЭТП ГПБ №%s; сама машина: %s; как искали: %s'
         % (r.get('nomer_zakupki'), sama, (r.get('ssylka_otkuda') or '')[:120]),
         'srednyaya', 'park_ingest_3c.jsonl (3-я, ЭТП ГПБ)', '', dedup,
         time.strftime('%Y-%m-%d %H:%M:%S')))
    row = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
    if not row:
        s.brak('вставка не дала id'); continue
    fakt_ssylki(row[0], urls)
    s.pr += 1
s.zapisat()

# ---- 3. ось ОКПД2 (я её передал 3-й, вернулась заполненной) -----------------
s = Schet('PARK-EIS-OKPD2-3S.jsonl (ось ОКПД2)')
for ln in open(os.path.join(D, 'PARK-EIS-OKPD2-3S.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    s.vs += 1
    r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    urls = ssyl(r.get('istochniki'))
    if not INN.match(inn):
        s.brak('ИНН не 10/12 цифр'); continue
    if not urls:
        s.brak('нет ссылки'); continue
    pred = (r.get('predmet') or '')
    tip = tochnyy_tip(pb.tip_po_tekstu(pred) or '', pred)
    if not tip:
        s.brak('тип по тексту не определён'); continue
    dedup = '|'.join([inn, tip, '', '', '', (r.get('nomer') or urls[0])])
    cur.execute(
        'insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,napisanie,'
        'zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,chto_naydeno,'
        'pochemu,uverennost,kto,karantin,dedup,ts) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (inn, (r.get('zakazchik') or '')[:200], tip, 'неясно', '', '', '', '', '', '', '', '',
         5, 'E: ОКПД2 %s' % (r.get('okpd2') or ''), pred[:500],
         'ОКПД2 из карточки ЕИС, код %s' % (r.get('okpd2') or ''), 'srednyaya',
         'PARK-EIS-OKPD2-3S.jsonl (3-я, ОКПД2)', '', dedup,
         time.strftime('%Y-%m-%d %H:%M:%S')))
    row = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
    if not row:
        s.brak('вставка не дала id'); continue
    fakt_ssylki(row[0], urls)
    s.pr += 1
s.zapisat()

# ---- 4. контакты 2-й с ролью ------------------------------------------------
s = Schet('PARK-KONTAKTY-2S-S-ROLYU.csv (2-я, с ролью)')
with open(os.path.join(D, 'PARK-KONTAKTY-2S-S-ROLYU.csv'), encoding='utf-8-sig', newline='') as fh:
    for r in csv.DictReader(fh, delimiter=';'):
        s.vs += 1
        inn = (r.get('inn') or '').strip()
        u = (r.get('ssylka') or '').strip() or (r.get('sayt') or '').strip()
        raz = pb.razbor_url(u)
        zn = (r.get('znachenie') or '').strip()
        if not INN.match(inn):
            s.brak('ИНН не 10/12 цифр'); continue
        if not raz:
            s.brak('ссылка не URL'); continue
        if not zn:
            s.brak('пустое значение контакта'); continue
        vid = 'pochta' if '@' in zn else 'telefon'
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, vid, zn, (r.get('chelovek') or '').strip(),
                     (r.get('dolzhnost') or '').strip(), raz[1], u, raz[0], raz[2], '',
                     (r.get('citata') or '')[:300],
                     'PARK-KONTAKTY-2S-S-ROLYU.csv (2-я, роль: %s)' % (r.get('rol') or '')))
        s.pr += 1
s.zapisat()

# ---- 5. контакты 3-й с меткой доказательства --------------------------------
s = Schet('PARK-KONTAKTY-3S-CHESTNO.jsonl (3-я, честно)')
for ln in open(os.path.join(D, 'PARK-KONTAKTY-3S-CHESTNO.jsonl'), encoding='utf-8'):
    if not ln.strip(): continue
    s.vs += 1
    r = json.loads(ln)
    inn = (r.get('inn') or '').strip()
    urls = ssyl(r.get('istochniki'))
    nomer = (r.get('nomer') or '').strip()
    if not INN.match(inn):
        s.brak('ИНН не 10/12 цифр'); continue
    if not urls:
        s.brak('нет ссылки'); continue
    if not nomer:
        s.brak('нет номера'); continue
    if (r.get('dokazatelstvo_metka') or '').startswith('ссылки нет'):
        s.brak('сама 3-я пометила: доказательства нет'); continue
    # каждая ссылка — отдельная строка провенанса: владелец требует несколько ссылок,
    # а не одну и «и др.»
    for u in urls[:12]:
        raz = pb.razbor_url(u)
        if not raz: continue
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'telefon', nomer, (r.get('imya') or '')[:200],
                     (r.get('dolzhnost') or '')[:200], raz[1], u, raz[0], raz[2], '',
                     ('%s; машина: %s; вид: %s' % ((r.get('dokazano_iz') or '')[:150],
                                                   r.get('mashina'), r.get('vid_nomera')))[:300],
                     'PARK-KONTAKTY-3S-CHESTNO.jsonl (3-я)'))
    s.pr += 1
s.zapisat()

# ---- 6. обратный поиск по моим 909 инженерам, проверенный 3-й ---------------
for fayl in ('PARK-OBRATNYY-1S-PROVERENO-3S.jsonl', 'PARK-OBRATNYY-PROVERENO-3S.jsonl'):
    s = Schet('%s (обратный ход, проверен 3-й)' % fayl[:40])
    for ln in open(os.path.join(D, fayl), encoding='utf-8'):
        if not ln.strip(): continue
        s.vs += 1
        r = json.loads(ln)
        inn = (r.get('inn') or '').strip()
        urls = ssyl(r.get('istochniki'))
        zn = (r.get('znachenie') or r.get('nomer') or '').strip()
        prin = (r.get('prinadlezhnost') or '')
        if not INN.match(inn):
            s.brak('ИНН не 10/12 цифр'); continue
        if not urls:
            s.brak('нет ссылки'); continue
        if not zn:
            s.brak('пустое значение'); continue
        if prin.startswith('совпала только фамилия') or prin.startswith('ближе к номеру'):
            s.brak('3-я доказала: номер принадлежит не нашему ФИО'); continue
        if 'утёкш' in (r.get('vid_nomera') or ''):
            s.brak('источник — сборник утёкших данных, не берём'); continue
        vid = 'pochta' if '@' in zn else 'telefon'
        for u in urls[:8]:
            raz = pb.razbor_url(u)
            if not raz: continue
            cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                        'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                        'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (inn, vid, zn, (r.get('imya') or '')[:200],
                         (r.get('dolzhnost') or '')[:200], raz[1], u, raz[0], raz[2], '',
                         ('%s | %s' % (prin, (r.get('citata') or '')))[:300],
                         '%s (обратный ход, вид: %s)' % (fayl, r.get('vid_nomera'))))
        s.pr += 1
    s.zapisat()

q = lambda sq: cur.execute(sq).fetchone()[0]
print()
print('=== ИТОГО ПОСЛЕ ВЛИВАНИЯ ===')
print('  фактов        %6d  (было %d, +%d)' % (q('select count(*) from fakt'), bylo_f,
                                               q('select count(*) from fakt') - bylo_f))
print('  ИНН с фактом  %6d' % q('select count(distinct inn) from fakt'))
print('  ссылок факта  %6d' % q('select count(*) from fakt_ssylka'))
print('  contact_source%6d  (было %d, +%d)' % (q('select count(*) from contact_source'), bylo_k,
                                               q('select count(*) from contact_source') - bylo_k))
print('  ИНН с контактом %4d' % q('select count(distinct inn) from contact_source'))
p.commit()
p.close()
