# -*- coding: utf-8 -*-
"""Задания для зенки по ЗАКРЫТЫМ площадкам (то, что нам недоступно с сервера: Сбер-АСТ, РТС, Фабрикант, Tender.pro, ЕРКНМ, B2B с регионом).
Пишет C:\\seostat\\drop\\zenno\\ak_zadaniya.txt в формате:
    <id>;<источник>;<url>;<что_ждать_на_странице>
Кубик кладёт HTML в ak_gotovo\\<id>.html и дописывает ak_vypolneno.txt; отказы - в ak_otkazy.txt.
Также СНИМАЕТ из ochered.txt строки, добавленные под сайты предприятий края (зенка нужна под площадки).
argv: [--snyat-sayty] [--predel N]"""
import os, sys, re, sqlite3, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
OB = os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno')
Z = os.path.join(OB, 'ak_zadaniya.txt'); OCH = os.path.join(OB, 'ochered.txt')
PREDEL = int(sys.argv[sys.argv.index('--predel') + 1]) if '--predel' in sys.argv else 400
Q = lambda s: __import__('urllib.parse', fromlist=['quote']).quote(s)
SLOVA = ['компрессор', 'компрессорная станция', 'компрессорная установка', 'винтовой компрессор', 'воздуходувка', 'ресивер',
         'осушитель сжатого воздуха', 'генератор азота', 'генератор кислорода', 'воздухоразделительная установка', 'ремонт компрессора', 'масло компрессорное']
# --- снять сайты предприятий края из очереди зенки (они не приоритет)
if '--snyat-sayty' in sys.argv and os.path.exists(OCH):
    c0 = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    nashi = {r[0] for r in c0.execute("select inn from predpriyatiya where inn like '22%'")}
    c0.close()
    stroki = open(OCH, encoding='utf-8', errors='replace').read().splitlines()
    ost = [l for l in stroki if l.split(';')[0].strip() not in nashi]
    snyato = len(stroki) - len(ost)
    open(OCH, 'w', encoding='utf-8').write('\n'.join(ost) + ('\n' if ost else ''))
    print(f'из ochered.txt снято строк края {snyato}, осталось {len(ost)}')
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
vyr = {r[0]: (r[1] or 0) for r in c.execute('select inn, max(vyruchka_rub) from finansy group by 1')}
celi = c.execute("""select inn, nazvanie, klass from predpriyatiya where inn like '22%'
                    and (klass like 'доказано%' or klass like 'косвенно%')""").fetchall()
c.close()
celi.sort(key=lambda r: -vyr.get(r[0], 0))
celi = celi[:PREDEL]
est = set()
if os.path.exists(Z):
    for l in open(Z, encoding='utf-8', errors='replace'):
        p = l.split(';')
        if p: est.add(p[0].strip())
zad = []
def dob(zid, ist, url, zhdat):
    if zid in est: return
    zad.append(f'{zid};{ist};{url};{zhdat}'); est.add(zid)
# 1. ЕРКНМ по каждому ИНН цели (проверки, в том числе оборудования)
for inn, naz, kl in celi:
    dob(f'erknm-{inn}', 'erknm', f'https://proverki.gov.ru/portal/search?inn={inn}', 'Найдено')
# 2. Сбер-АСТ по словам (223-ФЗ + 44-ФЗ), фильтр региона выставляется в интерфейсе
for i, s in enumerate(SLOVA):
    dob(f'sber-{i}', 'sberast', f'https://utp.sberbank-ast.ru/Trade/NBT/PurchaseList/1/0/0/0?searchString={Q(s)}&region=%D0%90%D0%BB%D1%82%D0%B0%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D0%BA%D1%80%D0%B0%D0%B9', 'Реестр')
    dob(f'sber44-{i}', 'sberast', f'https://www.sberbank-ast.ru/purchaseList.aspx?SearchString={Q(s)}', 'Реестр')
# 3. РТС-тендер по словам с регионом и по ИНН-КПП топ-целей
for i, s in enumerate(SLOVA):
    dob(f'rts-{i}', 'rts', f'https://www.rts-tender.ru/poisk?query={Q(s)}&region={Q("Алтайский край")}', 'найдено')
for inn, naz, kl in celi[:120]:
    dob(f'rtsinn-{inn}', 'rts', f'https://www.rts-tender.ru/poisk/organizator/{inn}/', 'организатор')
# 4. Фабрикант по словам
for i, s in enumerate(SLOVA):
    dob(f'fabr-{i}', 'fabrikant', f'https://www.fabrikant.ru/trades/procedure/search/?query={Q(s)}&region=22', 'процедур')
# 5. Tender.pro по ИНН (нужна сессия площадки)
for inn, naz, kl in celi[:120]:
    dob(f'tp-{inn}', 'tenderpro', f'https://www.tender.pro/api/companies/list?inn={inn}', 'company')
# 6. B2B-Center по словам с фильтром региона (в URL не пробрасывается, нужен клик по фильтру «Алтайский край»)
for i, s in enumerate(SLOVA):
    dob(f'b2b-{i}', 'b2b', f'https://www.b2b-center.ru/market/?searching=1&f_keyword={Q(s)}&trade=buy', 'Алтайский')
# 7. Ростехнадзор: территориальное управление (ошибка сертификата с сервера, браузер зенки пройдёт)
for i, u in enumerate(['https://zsib.gosnadzor.ru/', 'https://zsib.gosnadzor.ru/activity/industrial/', 'https://sib.gosnadzor.ru/']):
    dob(f'rtn-{i}', 'gosnadzor', u, 'Ростехнадзор')
with open(Z, 'a', encoding='utf-8') as f:
    for l in zad: f.write(l + '\n')
print(f'дописано заданий {len(zad)} | всего в {Z}: {sum(1 for _ in open(Z, encoding="utf-8", errors="replace"))}')
print('по источникам:', {k: sum(1 for l in zad if l.split(";")[1] == k) for k in ('erknm', 'sberast', 'rts', 'fabrikant', 'tenderpro', 'b2b', 'gosnadzor')})
os.makedirs(os.path.join(OB, 'ak_gotovo'), exist_ok=True)
print('папка для результатов:', os.path.join(OB, 'ak_gotovo'))
