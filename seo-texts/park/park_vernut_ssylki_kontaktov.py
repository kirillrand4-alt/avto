# -*- coding: utf-8 -*-
"""Возврат ссылок 2 688 наблюдениям контакта — из исходной базы, а не поиском заново.

Очередь сторожа: «2 688 наблюдений контакта без URL — искать ссылки, не удалять».
Смотрю, откуда они: поле `kto` у всех говорит `atlas_copco.db/kontakty_svod` — то есть это
та же исходная база, из которой сегодня уже возвращались потерянные ссылки ФАКТОВ. У неё
в `kontakty_svod` 8 911 строк с `source_url`, начинающимся на http.

Значит адрес не «не существует», а ПОТЕРЯЛСЯ при вливании — второй раз тот же дефект.

Сопоставляю по паре «ИНН + само значение контакта» (номер, приведённый к десяти цифрам,
или почта в нижнем регистре): совпадение по значению — это тот же контакт, а не похожий.
"""
import os, re, sqlite3, importlib.util

D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
a = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'atlas_copco.db'), uri=True)


def cifry10(s):
    d = re.sub(r'\D', '', s or '')
    if len(d) >= 11 and d[0] in '78':
        d = d[1:]
    return d[-10:] if len(d) >= 10 else ''


def klyuch(inn, znach):
    z = (znach or '').strip().lower()
    return (str(inn), cifry10(z) or z)


ist = {}
for inn, phone, email, url in a.execute(
        "select inn, phone, email, source_url from kontakty_svod"):
    if not url or not str(url).startswith('http') or 'ссылки нет' in str(url):
        continue
    for z in (phone, email):
        if z:
            ist.setdefault(klyuch(inn, z), url.strip())
print('в исходнике пар «контакт -> адрес»:', len(ist))

bez = c.execute("""select id, inn, znachenie from contact_source
                   where coalesce(source_url,'') not like 'http%'""").fetchall()
nash = 0
ne = 0
dubl = 0
for cid, inn, zn in bez:
    u = ist.get(klyuch(inn, zn))
    if not u:
        ne += 1
        continue
    raz = pb.razbor_url(u)
    if not raz:
        ne += 1
        continue
    # У части строк такой контакт С ЭТИМ АДРЕСОМ уже лежит отдельной записью — тогда
    # безадресная строка просто дубль, и её надо убрать, а не переименовывать: иначе
    # UNIQUE(инн, вид, значение, адрес, человек) не даст записать, и доказательство
    # осталось бы «потерянным» при живом адресе рядом.
    est = c.execute("select 1 from contact_source where inn=? and vid=(select vid from "
                    "contact_source where id=?) and znachenie=(select znachenie from "
                    "contact_source where id=?) and source_url=?",
                    (inn, cid, cid, u)).fetchone()
    if est:
        c.execute("delete from contact_source where id=?", (cid,))
        dubl += 1
        continue
    c.execute("update contact_source set source_url=?, domen=?, istochnik=?, pervoistochnik=? "
              "where id=?", (u, raz[0], raz[1], raz[2], cid))
    nash += 1
p.commit()
print('наблюдений было без ссылки: %d' % len(bez))
print('  адрес возвращён .......... %d' % nash)
print('  убрано как дубль ......... %d  (адрес уже был у такой же записи)' % dubl)
print('  адреса нет и в исходнике . %d' % ne)
q = lambda s: c.execute(s).fetchone()[0]
print('\nосталось без ссылки: %d' % q(
    "select count(*) from contact_source where coalesce(source_url,'') not like 'http%'"))
p.close()
