# -*- coding: utf-8 -*-
"""Записывает вторую ссылку — карточку организации ЕИС — там, где ИНН на ней СОВПАЛ.

Разрыв: машина доказана у 95 % фактов выдачи, машина вместе с ИНН — у 63 %. Извещение 44-ФЗ
печатает название заказчика, но не ИНН; ИНН на карточке организации. Адрес карточки выводится
из реестрового номера (первые 11 цифр — код организации), но код принадлежит тому, кто
РАЗМЕЩАЕТ закупку, поэтому ссылка пишется только после того, как страница открыта и ИНН на
ней совпал с ИНН факта. Разбор делает `park_1s_karta_org.py` на сервере.

Ссылка ставится ВСЕМ фактам этого предприятия, у которых её нет: карточка организации у
одного ИНН одна, и проверять её повторно для каждого факта — тратить вызовы впустую.

Этап у ссылки назван честно: «карточка организации ЕИС, ИНН сверен» — она доказывает ИНН
заказчика, но не машину; машину доказывает извещение, которое уже лежит рядом.
"""
import importlib.util, json, os, sqlite3, time

D = os.path.dirname(os.path.abspath(__file__))
razbor = json.load(open(os.path.join(D, 'PARK-1S-KARTAORG-RAZBOR.json'), encoding='utf-8'))
p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=120)
c = p.cursor()
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

sovp = [r for r in razbor if r.get('sovpal')]
napisano = 0
tronuto_inn = set()
for r in sovp:
    raz = pb.razbor_url(r['url'])
    if not raz:
        continue
    fakty = c.execute("""select f.id from fakt f
                          where f.inn=? and f.v_parke=1
                            and not exists(select 1 from fakt_ssylka s where s.fakt_id=f.id
                                            and s.url like '%epz/organization/%')""",
                      (r['inn'],)).fetchall()
    for (fid,) in fakty:
        c.execute("""insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,
                       pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)""",
                  (fid, r['url'], raz[0], raz[1], 'карточка организации ЕИС, ИНН сверен',
                   raz[2], '', 'karta_org'))
        napisano += c.rowcount
    tronuto_inn.add(r['inn'])
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ССЫЛКА НА ИНН: карточка организации ЕИС',
           len(razbor), napisano, len(razbor) - len(sovp),
           'записаны только те, где ИНН на открытой странице совпал с ИНН факта'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
V = 'f.v_parke=1 and coalesce(f.v_obzvone,0)=0 and coalesce(f.posrednik,0)=0'
MASH = ("(s.url like '%monitor-pb.ru/conclusion/%' or s.url like '%/223/purchase%' "
        "or s.url like '%notice/ea44%' or s.url like '%etpgpb.ru%' "
        "or s.url like '%tender.pro/api%' or s.url like '%mos.ru%' or s.url like '%tektorg%')")
INNS = ("(s.url like '%monitor-pb.ru/conclusion/%' or s.url like '%/223/purchase%' "
        "or s.url like '%epz/organization/%')")
print('в разборе %d | ИНН совпал у %d | предприятий затронуто %d'
      % (len(razbor), len(sovp), len(tronuto_inn)))
print('новых строк ссылок: %d' % napisano)
print('фактов выдачи, где доказаны И машина, И ИНН: %d'
      % q('select count(*) from fakt f where ' + V +
          ' and exists(select 1 from fakt_ssylka s where s.fakt_id=f.id and ' + MASH + ')'
          ' and exists(select 1 from fakt_ssylka s where s.fakt_id=f.id and ' + INNS + ')'))
print('предприятий с полной парой доказательств: %d'
      % q('select count(distinct f.inn) from fakt f where ' + V +
          ' and exists(select 1 from fakt_ssylka s where s.fakt_id=f.id and ' + MASH + ')'
          ' and exists(select 1 from fakt_ssylka s where s.fakt_id=f.id and ' + INNS + ')'))
p.close()
