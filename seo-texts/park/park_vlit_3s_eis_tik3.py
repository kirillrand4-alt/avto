# -*- coding: utf-8 -*-
"""Приём потока ЕИС от 3-й сессии (`PARK-EIS-TIK3-PODTV-3S.jsonl`) с ДВУМЯ своими заслонами.

Померил до вливания, а не после: из 1 259 строк ИНН есть у 823, для моего парка новых 154.
Но среди них два класса мусора, каждый портит базу по-своему:

  * НЕ НАША МАШИНА — «установка лесопожарная ранцевая (воздуходувка)», садовые бензиновые
    воздуходувки: слово наше, машина не наша (33 строки);
  * ЗАКАЗЧИК-ПОСРЕДНИК — «Агентство государственного заказа», «Комитет по регулированию
    контрактной системы»: у них свой ИНН, а машина у того, ДЛЯ КОГО закупают. Такой ИНН
    сел бы в парк вместо настоящего эксплуатанта, и продавец звонил бы в агентство (35).

Ссылок на факт две, как требует владелец: карточка закупки по реестровому номеру и
карточка организации-заказчика.
"""
import collections, importlib.util, json, os, re, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()

NE_NASHA = re.compile(r'ранцев|лесопожарн|садов|пылесос|аккумуляторн|бензинов\w*\s+воздуходувк|'
                      r'ручн\w+\s+воздуходувк|уборк\w+\s+листв', re.I)
POSREDNIK = re.compile(r'агентств|комитет по регулированию|управление по закупкам|'
                       r'центр организации закупок|дирекция закупок', re.I)
KANON = [(r'мкс|модульн\w*компрессорн', 'МКС'),
         (r'\bпкс\b|передвижн\w*компрессорн|дизельн\w*компрессорн', 'ПКС'),
         (r'\bгпа\b|газоперекачив', 'ГПА'), (r'\bвру\b|воздухораздел', 'ВРУ'),
         (r'генератор\w*кислород|кислородн\w*(станци|установк|генератор)', 'генератор кислорода'),
         (r'генератор\w*азот|азотн\w*(станци|установк|генератор)', 'генератор азота'),
         (r'турбокомпрессор|центробежн\w*компрессор', 'турбокомпрессор'),
         (r'воздуходувк|газодувк', 'воздуходувка'), (r'нагнетател', 'нагнетатель'),
         (r'осушител|влагоотделител', 'осушитель'), (r'ресивер|воздухосборник', 'ресивер'),
         (r'компрессорн\w*станци', 'компрессорная станция'), (r'компрессор', 'компрессор')]
RASHODNIK = re.compile(r'ремонт|обслуживан|запчаст|зип|фильтр|масл|сервис|поверк|диагностик', re.I)


def bp(t):
    return re.sub(r'\s+', '', (t or '').lower().replace('ё', 'е'))


def tip_iz(t):
    b = bp(t)
    for rx, imya in KANON:
        if re.search(rx, b):
            return imya
    return ''


pri = collections.Counter()
vs = prin = 0
novye = set()
for ln in open(os.path.join(D, 'PARK-EIS-TIK3-PODTV-3S.jsonl'), encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    try:
        x = json.loads(ln)
    except Exception:
        pri['строка не разобралась'] += 1
        continue
    vs += 1
    inn = (x.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        pri['ИНН не найден'] += 1
        continue
    predmet = (x.get('predmet') or '').strip()
    zakazchik = (x.get('zakazchik') or '').strip()
    if NE_NASHA.search(predmet):
        pri['НЕ НАША МАШИНА (ранцевая/садовая)'] += 1
        continue
    if POSREDNIK.search(zakazchik):
        pri['заказчик-посредник, машина не его'] += 1
        continue
    if not x.get('slovo_podtverzhdeno_tekstom'):
        pri['слово не подтверждено текстом карточки'] += 1
        continue
    tip = tip_iz(predmet)
    if not tip:
        pri['тип из предмета не определился'] += 1
        continue
    nomer = (x.get('nomer') or '').strip()
    if not nomer:
        pri['нет реестрового номера'] += 1
        continue
    url_zak = ('https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=' + nomer
               if len(nomer) == 19 else
               'https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=' + nomer)
    vid = 'расходник' if RASHODNIK.search(predmet) else 'машина'
    dedup = '%s|%s|3s-eis-tik3|%s' % (inn, tip, nomer)
    cur.execute("""insert or ignore into fakt(inn, nazvanie, tip, sostoyanie, vid_fakta,
                     chto_naydeno, sila, kto, dedup, ts, v_parke, uverennost, pochemu)
                   values (?,?,?,?,?,?,?,?,?,datetime('now'),1,'srednyaya',?)""",
                (inn, zakazchik[:200], tip, 'закупка', vid,
                 (nomer + ' ' + predmet)[:400], 2, '3-я сессия, срез ЕИС (тик 3)', dedup,
                 'закупка называет машину; заслоны: не ранцевая/садовая, заказчик не посредник'))
    fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()
    if not fid:
        pri['факт не создался'] += 1
        continue
    fid = fid[0]
    for u in (url_zak, (x.get('zakazchik_kartochka') or '').strip()):
        if not u.startswith('http'):
            continue
        raz = pb.razbor_url(u)
        if not raz:
            continue
        cur.execute("insert or ignore into fakt_ssylka(fakt_id, url, domen, istochnik,"
                    " pervoistochnik, etap) values (?,?,?,?,?,?)",
                    (fid, u, raz[0], raz[1], raz[2],
                     'карточка закупки' if 'regNumber' in u else 'карточка организации-заказчика'))
    prin += 1
    novye.add(inn)

p.commit()
print('строк на входе %d | принято %d | предприятий в потоке %d' % (vs, prin, len(novye)))
print('  отсев:', dict(pri.most_common(8)))
q = lambda s: cur.execute(s).fetchone()[0]
print('\n=== ПО БАЗЕ ===')
print('  фактов ......... %d' % q('select count(*) from fakt'))
print('  в парке ........ %d' % q('select count(*) from fakt where v_parke=1'))
print('  предприятий .... %d' % q('select count(distinct inn) from fakt where v_parke=1'))
print('  ссылок ......... %d' % q('select count(*) from fakt_ssylka'))
p.close()
