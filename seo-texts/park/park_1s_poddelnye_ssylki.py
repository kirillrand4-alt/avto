# -*- coding: utf-8 -*-
"""Ссылка, которая никогда ничего не докажет: чужой идентификатор в адресе поиска ЕИС.

Нашлось через пункт 7 регламента (пять случайных ссылок с сервера): две из пяти вели на
поисковую страницу ЕИС, где машины нет. Сплошной счёт дал 705 фактов, у которых ДРУГИХ
ссылок нет вовсе. Все 705 пришли из одного источника — `atlas_copco.db/tenders`, — и адрес
у них устроен так:

    https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=tek_908858

`tek_908858` — внутренний идентификатор ТЭК-ТОРГА, подставленный в поиск ЕИС. Сборщик склеил
номер одной площадки с адресом другой. Ссылка ведёт на живой домен, отдаёт http 200 — и не
докажет ничего никогда, потому что ЕИС такого номера не знает. **Это хуже пустой ссылки:
пустую видно сразу, а эта выглядит доказательством и проходит любую проверку «открывается ли».**

Проверил с сервера браузером (из песочницы ТЭК-Торг отвечает 307 на самого себя — защита):

    форма                          результат на 5 идентификаторах
    /procedures/<номер>            http 404
    /procedures/view/<номер>       http 404
    /procedures?searchText=<номер> http 200, номера на странице нет
    /procedures?name=<номер>       http 200, НОМЕР И МАШИНА НАЙДЕНЫ — 5 из 5
    контроль 999999999             не найден ни одной формой — прибор умеет говорить «нет»

Значит рабочая форма есть, и её же назвала 3-я сессия для своего сбора. Но чинится не всё:

    tek_<цифры> — настоящий номер ТЭК-Торга ........ 26 фактов, чинятся
    голое число 5–8 знаков ......................... 559 фактов, на ТЭК-Торге НЕ находятся
                                                     (проба 5 штук: 0 из 5)
    прочее (слова) ................................. остальные

Голые числа — идентификаторы неизвестного происхождения; сборщик их тоже подставил в чужой
адрес. Форма ТЭК-Торга их не открывает, поэтому чинить нечем: нужен исходный канал, а он в
`atlas_copco.db` не записан.

Что делаю:
  1. Для `tek_<цифры>` ДОБАВЛЯЮ настоящую ссылку `tektorg.ru/procedures?name=<номер>`.
     Старую не трогаю — пусть видно, откуда взялось.
  2. Все подделанные помечаю `fakt_ssylka.negodnaya=1` с причиной. **Не удаляю** — правило
     владельца «искать ссылки, не удалять», и по описанию факта их ещё можно найти заново.
  3. Считаю доказанность заново, уже без негодных ссылок: пусть цифра будет честной.

Запуск: python3 park_1s_poddelnye_ssylki.py [--pisat]
"""
import os, re, sqlite3, sys, time
from urllib.parse import urlparse, parse_qs

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
TEKTORG = 'https://www.tektorg.ru/procedures?name=%s'


def chuzhoy_identifikator(url):
    """-> номер ТЭК-Торга, если он подставлен в адрес поиска ЕИС; иначе ''."""
    if 'extendedsearch' not in url and '/search/results' not in url:
        return ''
    ss = (parse_qs(urlparse(url).query).get('searchString') or [''])[0]
    m = re.fullmatch(r'tek_(\d+)', ss)
    return m.group(1) if m else ''


def poddelnaya(url):
    """-> причина негодности или '' — ссылка на поиск с идентификатором вместо запроса."""
    if 'extendedsearch' not in url and '/search/results' not in url:
        return ''
    ss = (parse_qs(urlparse(url).query).get('searchString') or [''])[0]
    if re.fullmatch(r'tek_\S+', ss):
        return 'идентификатор ТЭК-Торга в адресе поиска ЕИС'
    if re.fullmatch(r'\d{1,9}', ss):
        return 'короткий идентификатор неизвестной площадки в адресе поиска ЕИС'
    return ''


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=120)
c = p.cursor()
if PISAT and 'negodnaya' not in [r[1] for r in c.execute('pragma table_info(fakt_ssylka)')]:
    c.execute('alter table fakt_ssylka add column negodnaya text')

rows = c.execute("select id, fakt_id, url from fakt_ssylka where url like 'http%'").fetchall()
pometit, dobavit = [], []
for sid, fid, url in rows:
    prichina = poddelnaya(url)
    if not prichina:
        continue
    pometit.append((sid, prichina))
    nomer = chuzhoy_identifikator(url)
    if nomer:
        dobavit.append((fid, TEKTORG % nomer))

print('ссылок всего ................................. %d' % len(rows))
print('подделанных (чужой номер в адресе поиска) .... %d' % len(pometit))
print('  из них чинятся адресом ТЭК-Торга ........... %d' % len(dobavit))
print('  остальные — идентификатор неизвестной площадки %d' % (len(pometit) - len(dobavit)))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.close()
    raise SystemExit

for i in range(0, len(pometit), 500):
    for sid, prichina in pometit[i:i + 500]:
        c.execute('update fakt_ssylka set negodnaya=? where id=?', (prichina, sid))
est = {(r[0], r[1]) for r in c.execute("select fakt_id, url from fakt_ssylka")}
novyh = 0
for fid, url in dobavit:
    if (fid, url) in est:
        continue
    c.execute("""insert into fakt_ssylka(fakt_id, url, domen, istochnik, etap, data_nablyudeniya)
                 values (?,?,?,?,?,?)""",
              (fid, url, 'tektorg.ru', 'починка подделанной ссылки: номер ТЭК-Торга',
               'дозор', time.strftime('%Y-%m-%d')))
    novyh += 1
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ССЫЛКИ: чужой идентификатор в адресе поиска ЕИС',
           len(rows), novyh, len(pometit),
           'форма tektorg.ru/procedures?name= проверена с сервера: 5 из 5, контроль чист'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
V = "f.v_parke=1 and coalesce(f.v_obzvone,0)=0 and coalesce(f.posrednik,0)=0"
print()
print('помечено негодными ........................... %d' % len(pometit))
print('добавлено настоящих ссылок ТЭК-Торга ......... %d' % novyh)
print()
print('ЧЕСТНЫЙ СЧЁТ, негодные ссылки не в счёт:')
print('  фактов выдачи со ссылкой ................... %d'
      % q(f"""select count(distinct f.id) from fakt f join fakt_ssylka s on s.fakt_id=f.id
              where {V} and s.url like 'http%' and s.negodnaya is null"""))
print('  фактов, у которых ВСЕ ссылки негодные ...... %d'
      % q(f"""select count(*) from (select f.id from fakt f join fakt_ssylka s on s.fakt_id=f.id
               where {V} and s.url like 'http%' group by f.id
               having sum(case when s.negodnaya is null then 1 else 0 end)=0)"""))
print('  предприятий, где все ссылки негодные ....... %d'
      % q(f"""select count(*) from (select f.inn from fakt f join fakt_ssylka s on s.fakt_id=f.id
               where {V} and s.url like 'http%' group by f.inn
               having sum(case when s.negodnaya is null then 1 else 0 end)=0)"""))
p.close()
