# -*- coding: utf-8 -*-
"""Приём выгрузки checko от 2-й сессии: выручка и контакты с доказательством.

Что пришло (`PARK-CHECKO-2S.jsonl`, 886 строк): карточка checko на предприятие, выручка
текстом («15,7 млн», «5,9 млрд»), телефоны, почты, сайт. У каждой записи два адреса —
карточка и страница контактов; они и становятся ссылками-доказательствами.

Три вещи делаются осознанно, а не по инерции:

1. **Выручка разбирается из текста в рубли** с записью года. «5,9 млрд» -> 5 900 000 000.
   Если разбор не удался — не пишем НИЧЕГО: неверное число хуже отсутствующего.
2. **Контакты дилеров не берём.** У 92 предприятий парка есть факт «продаёт (дилер)» —
   это конкуренты, их контакты в базу обзвона не нужны. Отсев по своей базе, а не по
   доверию к чужому флагу.
3. **checko — агрегатор, а не первоисточник** (`pervoistochnik=0`): телефон с карточки
   агрегатора слабее телефона с сайта самого предприятия, и в своде это учитывается.

Запуск: python3 park_vlit_checko_2s.py [файл.jsonl]
"""
import collections, json, os, re, sqlite3, sys, importlib.util

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

FAYL = os.path.join(D, sys.argv[1] if len(sys.argv) > 1 else 'PARK-CHECKO-2S.jsonl')
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()

park = {r[0] for r in cur.execute('select inn from predpriyatie')}
dilery = {r[0] for r in cur.execute("select distinct inn from fakt where sostoyanie like '%прода%'")}
est_vyr = {r[0] for r in cur.execute('select inn from finansy where vyruchka is not null')}

MNOZH = {'тыс': 1e3, 'млн': 1e6, 'млрд': 1e9, 'трлн': 1e12}
_VYR = re.compile(r'^\s*([\d\s ]+(?:[.,]\d+)?)\s*(тыс|млн|млрд|трлн)?\.?\s*(?:руб\w*|₽)?\s*$', re.I)


def v_rubli(s):
    """«15,7 млн» -> 15700000.0 ; непонятное -> None (лучше пусто, чем наугад)."""
    s = (s or '').strip().replace('\xa0', ' ')
    if not s:
        return None
    m = _VYR.match(s)
    if not m:
        return None
    chislo = m.group(1).replace(' ', '').replace(' ', '').replace(',', '.')
    try:
        v = float(chislo)
    except ValueError:
        return None
    return v * MNOZH.get((m.group(2) or '').lower(), 1)


def cifry10(s):
    c = re.sub(r'\D', '', s or '')
    if len(c) >= 11 and c[0] in '78':
        c = c[1:]
    return c[-10:] if len(c) >= 10 else ''


pri = collections.Counter()
vs = fin = tel = mail = 0
inny_fin = set()
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    try:
        x = json.loads(ln)
    except Exception:
        pri['строка не разобралась'] += 1
        continue
    vs += 1
    inn = str(x.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        pri['ИНН не разобран'] += 1
        continue
    if inn not in park:
        pri['предприятия нет в парке'] += 1
        continue
    kart = (x.get('ssylka_kartochka') or x.get('kartochka') or '').strip()
    kont = (x.get('ssylka_kontakty') or kart).strip()

    # ---- выручка -----------------------------------------------------------
    v = v_rubli(x.get('vyruchka'))
    if v and v > 0:
        god = str(x.get('vyruchka_god') or '').strip()
        otkuda = 'checko (2-я сессия)%s' % ((', ' + god) if god else '')
        if inn in est_vyr:
            pri['выручка уже была — не перезаписываю'] += 1
        else:
            cur.execute("insert or ignore into finansy(inn, vyruchka, vyruchka_otkuda, ts)"
                        " values (?,?,?,datetime('now'))", (inn, v, otkuda))
            cur.execute("update finansy set vyruchka=?, vyruchka_otkuda=?"
                        " where inn=? and vyruchka is null", (v, otkuda, inn))
            fin += 1
            inny_fin.add(inn)
    elif str(x.get('vyruchka') or '').strip():
        pri['выручка не разобралась: ' + str(x.get('vyruchka'))[:18]] += 1

    # ---- контакты ----------------------------------------------------------
    if inn in dilery:
        pri['дилер — контакты не берём'] += 1
        continue
    raz = pb.razbor_url(kont) or pb.razbor_url(kart)
    if not raz:
        pri['ссылка checko не разбирается'] += 1
        continue
    for t in (x.get('telefony') or []):
        c = cifry10(t)
        if not c:
            continue
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto)'
                    ' values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'telefon', c, '', '', 'checko (АГРЕГАТОР)', kont, raz[0], 0, '',
                     'карточка checko: телефон организации', '2-я сессия, выгрузка checko'))
        tel += 1
    for a in (x.get('pochty') or []):
        a = (a or '').strip().strip('.,;')
        if '@' not in a:
            continue
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto)'
                    ' values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'email', a, '', '', 'checko (АГРЕГАТОР)', kont, raz[0], 0, '',
                     'карточка checko: почта организации', '2-я сессия, выгрузка checko'))
        mail += 1

p.commit()
print('строк на входе %d' % vs)
print('  выручка записана ... %d предприятиям' % fin)
print('  телефонов .......... %d' % tel)
print('  почт ............... %d' % mail)
print('  пропуски:', dict(pri.most_common(8)))
q = lambda s: cur.execute(s).fetchone()[0]
print('\n=== ПОСЛЕ ВЛИВАНИЯ (запросом к базе) ===')
print('  выручка в finansy .. %d' % q('select count(*) from finansy where vyruchka is not null'))
print('  из них по парку .... %d' % q("""select count(*) from finansy f
        join predpriyatie e on e.inn=f.inn where f.vyruchka is not null"""))
print('  наблюдений контакта  %d' % q('select count(*) from contact_source'))
p.close()
