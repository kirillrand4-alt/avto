# -*- coding: utf-8 -*-
"""Две работы очереди:
1) чистка: «НЕ НАША МАШИНА» и дилеры выводятся из парка (пометкой, НЕ удалением);
2) сопоставление ФОРМ серий словаря с марками ЭПБ — сейчас класс машины стоял у 142 фактов,
   потому что серия записана «К-500-61-1», а марка «4ВМ10-100/8»: сравнение по началу строки
   не работает. Нормализуем обе стороны и сравниваем ядра."""
import sqlite3, re, os, time, collections
D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()

# ---------- 1. чистка -------------------------------------------------------
cur.execute("alter table fakt add column v_parke INTEGER default 1") if not [
    r for r in cur.execute('pragma table_info(fakt)') if r[1] == 'v_parke'] else None
cur.execute("update fakt set v_parke=1")
n1 = cur.execute("update fakt set v_parke=0 where tip='НЕ НАША МАШИНА'").rowcount
n2 = cur.execute("update fakt set v_parke=0 where sostoyanie like '%дилер%' "
                 "or sostoyanie like 'ПРОДА%' or sostoyanie='продаёт (дилер)'").rowcount
p.commit()
print('выведено из парка: НЕ НАША МАШИНА %s, дилеры %s' % (n1, n2))

# ---------- 2. нормализация обозначений -------------------------------------
def yadro(s):
    """«К-500-61-1» -> «К500611»; «4ВМ10-100/8» -> «4ВМ100100 8»... нужен разбор на части."""
    s = (s or '').upper().replace('Ё', 'Е')
    s = re.sub(r'[^A-ZА-Я0-9]+', '', s)
    return s

def formy(s):
    """варианты написания: полное ядро и ядро до первого разделителя."""
    s = (s or '').upper().strip()
    if not s: return set()
    out = {yadro(s)}
    m = re.match(r'^([A-ZА-Я0-9]+?[-\s/]?\d+)', s)
    if m: out.add(yadro(m.group(1)))
    # буквенный префикс + первое число: ЦК135, ТВ80, ГА160
    m = re.match(r'^([A-ZА-Я]{1,4})[\s\-]*(\d{1,4})', s)
    if m: out.add(yadro(m.group(1) + m.group(2)))
    return {x for x in out if len(x) >= 3}

serii = {}
for ser, pr, vid, kl in cur.execute('select seriya,princip,vid,klass_ceny from seriya'):
    for f in formy(ser):
        serii.setdefault(f, (ser, pr, vid, kl))
print('форм серий в указателе:', len(serii), 'из', cur.execute('select count(*) from seriya').fetchone()[0], 'серий')

# ---------- 3. сопоставление ------------------------------------------------
sovp = 0; po_seriyam = collections.Counter()
for fid, model, marka, chto in cur.execute(
        "select id,model,marka,chto_naydeno from fakt where v_parke=1 and rang_mashiny is null "
        "or (v_parke=1 and rang_mashiny<=2)").fetchall():
    kand = formy(model) | formy(marka)
    nashli = None
    for f in kand:
        if f in serii: nashli = serii[f]; break
    if not nashli and chto:
        # ядро из текста: буквы+цифры длиной от 4
        for tok in re.findall(r'[A-ZА-Я]{1,4}[\s\-]?\d{2,4}(?:[-/]\d+)*', (chto or '').upper()):
            f = yadro(tok)
            if f in serii: nashli = serii[f]; break
    if not nashli: continue
    ser, pr, vid, kl = nashli
    cur.execute("update fakt set rang_mashiny=?, chem_rang=chem_rang||' | C: серия '||?||' ('||?||')' "
                "where id=?", (kl, ser, pr or 'принцип не установлен', fid))
    sovp += 1; po_seriyam[ser] += 1
p.commit()
print('фактов, которым серия проставила класс машины:', sovp)
print('топ серий по попаданиям:', po_seriyam.most_common(10))

q = lambda s: cur.execute(s).fetchone()[0]
print()
print('=== ПАРК ПОСЛЕ ЧИСТКИ ===')
for t, s in (('фактов в парке', "select count(*) from fakt where v_parke=1"),
             ('ИНН в парке', "select count(distinct inn) from fakt where v_parke=1"),
             ('ИНН силы 1', "select count(distinct inn) from fakt where v_parke=1 and sila=1"),
             ('фактов с рангом', "select count(*) from fakt where v_parke=1 and rang_mashiny is not null"),
             ('выведено из парка', "select count(*) from fakt where v_parke=0")):
    print('  %-24s %s' % (t, q(s)))
print('--- ранг машины: распределение ---')
for r in cur.execute('select cast(rang_mashiny as int),count(*),count(distinct inn) from fakt '
                     'where v_parke=1 and rang_mashiny is not null group by 1 order by 1 desc'):
    print('  ранг %-3s строк=%-6s ИНН=%s' % r)
p.close()
