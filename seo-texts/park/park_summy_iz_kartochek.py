# -*- coding: utf-8 -*-
"""Сумма закупки из карточек ЕИС -> признак A ранга машины.

Правило владельца: выше в выдаче тот, у кого машина ДОРОЖЕ. Ранг стоит по лестнице
A (сумма из документа) -> B (кВт и м3/мин по марке) -> C (класс по серии) -> D+ (срок ЭПБ
истёк) -> D (класс опасности) -> E (известен только тип). Замер показал перекос:

    ранг 2 (E, «известен только тип») ... 50 482 факта парка из 65 303  (77%)
    признак A стоял всего у ................ 397 фактов

А между тем сумма лежит прямо на карточке, которую мы уже сняли: «Начальная цена
1 658 675,00 ₽». Проверено на 1 200 карточках общих запросов — **сумма есть у 1 162
(97%)**. Заново ходить в ЕИС не нужно, текст карточки сохранён.

Оговорка честная: это цена ВСЕЙ закупки, в неё может входить не только машина. Как
признак масштаба она годится (ремонт по 50 тысяч и станция за 40 миллионов — разные
разговоры), поэтому пишем её в поле `summa` и помечаем в chem_rang, чем именно ранг взят.
"""
import sqlite3, json, os, re, glob, collections

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()
_CENA = re.compile(r'([\d][\d\s ]{2,15}[,.]\d{2})\s*(?:руб|₽|Российский рубль)')


def chislo(s):
    return float(re.sub(r'[^\d,.]', '', s).replace(' ', '').replace(',', '.'))


def rang_po_summe(v):
    return 10 if v >= 5e7 else 9 if v >= 2e7 else 8 if v >= 5e6 else 7 if v >= 1e6 \
        else 6 if v >= 3e5 else 5 if v >= 1e5 else 4


# номер закупки -> сумма, из всех снятых карточек
summy = {}
for f in glob.glob(os.path.join(D, 'park_*_inn.jsonl')):
    for ln in open(f, encoding='utf-8', errors='replace'):
        if not ln.strip():
            continue
        try:
            x = json.loads(ln)
        except Exception:
            continue
        nom = (x.get('nomer') or '').strip()
        t = re.sub(r'\s+', ' ', x.get('tekst') or '')
        m = _CENA.search(t)
        if nom and m:
            try:
                summy[nom] = chislo(m.group(1))
            except Exception:
                pass
print('карточек с суммой:', len(summy))

# Индекс «номер закупки -> факты» строим ОДНИМ проходом по таблице.
# Первая версия делала `dedup like '%|номер'` на каждый из 9 302 номеров — это 700 млн
# сравнений и полное сканирование таблицы каждый раз; прогон висел без единой записи.
po_nomeru = collections.defaultdict(list)
for fid, ded, bylo, chem in cur.execute(
        "select id, coalesce(dedup,''), rang_mashiny, chem_rang from fakt"):
    if '|' in ded:
        po_nomeru[ded.rsplit('|', 1)[-1]].append((fid, bylo, chem))
print('номеров закупок в базе:', len(po_nomeru))

n = povysheno = 0
raspr = collections.Counter()
for nom, v in summy.items():
    rg = rang_po_summe(v)
    for fid, bylo, chem in po_nomeru.get(nom, ()):
        n += 1
        chem_novyy = (chem or '')
        metka = 'A: сумма закупки %s руб' % ('{:,.0f}'.format(v).replace(',', ' '))
        if 'A: сумма' not in chem_novyy:
            chem_novyy = (chem_novyy + ' | ' + metka).strip(' |')
        cur.execute('update fakt set summa=?, chem_rang=?, rang_mashiny=? where id=?',
                    ('%.2f' % v, chem_novyy, max(rg, bylo or 0), fid))
        if rg > (bylo or 0):
            povysheno += 1
        raspr[rg] += 1
p.commit()
print('фактов затронуто: %d | ранг повышен у %d' % (n, povysheno))
print('распределение нового ранга:', dict(sorted(raspr.items())))
q = lambda s: cur.execute(s).fetchone()[0]
print('\nфактов парка с признаком A:', q("select count(*) from fakt where chem_rang like '%A: сумма%'"))
print('ранг 2 (только тип) осталось:', q("select count(*) from fakt where v_parke=1 and rang_mashiny=2"))
p.close()
