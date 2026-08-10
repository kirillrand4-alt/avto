# -*- coding: utf-8 -*-
"""Восстановление обрезанных ссылок ЕИС по номеру ИЗ ТЕКСТА факта — идея 3-й сессии.

Она предложила: «ваши обрезанные ссылки восстановимы не из адреса, а из предмета — номер
извещения часто стоит прямо в нём». Проверил на своих данных, прежде чем строить:

    обрезанных ссылок ................................ 1 024
    у скольких полный номер (11/19/23/25 цифр) в тексте    65

То есть идея работает, но на 6 % — говорю это числом, а не «помогло». 65 ссылок из мусорных
станут карточками, остальные 959 останутся помеченными, и врать про них не будем.

Ссылку строим по длине номера: 19 знаков — извещение 44-ФЗ, 11 — закупка 223-ФЗ.
Новую строку ДОБАВЛЯЕМ, старую не трогаем: пусть видно, откуда взялось.
"""
import os, re, sqlite3, urllib.parse, importlib.util

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
NOMER = re.compile(r'\b(\d{11}|\d{19}|\d{23}|\d{25})\b')

kand = []
for fid, txt, url in c.execute("""select f.id, coalesce(f.chto_naydeno,''), s.url
      from fakt f join fakt_ssylka s on s.fakt_id=f.id
      where f.v_parke=1 and s.url like '%extendedsearch%searchString=%'"""):
    m = re.search(r'searchString=([^&#]*)', url)
    ss = urllib.parse.unquote(m.group(1)) if m else ''
    cif = re.sub(r'\D', '', ss)
    if not cif or len(cif) in (11, 19):
        continue
    mn = NOMER.search(txt)
    if mn:
        kand.append((fid, mn.group(1)))

dob = 0
for fid, nomer in kand:
    u = ('https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=' + nomer
         if len(nomer) == 19 else
         'https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=' + nomer)
    raz = pb.razbor_url(u)
    if not raz:
        continue
    c.execute("insert or ignore into fakt_ssylka(fakt_id, url, domen, istochnik,"
              " pervoistochnik, etap) values (?,?,?,?,?,?)",
              (fid, u, raz[0], raz[1], raz[2],
               'карточка закупки, номер взят из текста факта (адрес в базе был обрезан)'))
    dob += 1 if c.rowcount else 0
p.commit()
print('кандидатов с полным номером в тексте: %d | добавлено ссылок: %d' % (len(kand), dob))
q = lambda s: c.execute(s).fetchone()[0]
print('всего ссылок: %d' % q('select count(*) from fakt_ssylka'))
p.close()
