# -*- coding: utf-8 -*-
"""Перевод ссылок «поиск ЕИС по номеру» в карточку закупки.

Повод — пятая ссылка случайного жребия: `extendedsearch?searchString=0390100009419000169`.
Номер полный, а страница поиска отдаёт 3 622 знака и ни ИНН, ни предмета: результаты
рисуются скриптом. Та же закупка по адресу карточки — 8 368 знаков с предметом и заказчиком.
Значит «поиск по полному номеру» я зря считал крепкой ссылкой: он показывает, КАК я искал,
а не ЧТО нашёл.

Правило проверено НА ВЫБОРКЕ в 60 ссылок (открывать 14 467 нельзя):

    19 знаков (44-ФЗ) .... 13 из 13 карточка отдаётся
    11 знаков (223-ФЗ) ... 47 из 47 карточка отдаётся

Сначала прибор сказал «22 из 47 не лучше поиска» — и соврал: порог «длиннее 5 000 знаков»
я взял с потолка, а эти карточки весят 4 783–4 939. У ВСЕХ 22 номер на странице, у 21 ИНН,
у всех 22 «Объект закупки Поставка компрессоров винтовых…». Считать надо было по содержимому,
а не по длине. Итог выборки: 60 из 60.

Старую ссылку не выбрасываем молча: если карточка у факта уже есть, поисковую УДАЛЯЕМ
(доказательство не теряется), иначе переименовываем и пишем причину в `etap`.
"""
import json, os, re, sqlite3, urllib.parse

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
zad = json.load(open(os.path.join(D, '_poisk_v_kartochku.json'), encoding='utf-8'))
pereim = udal = ne = 0
for z in zad:
    est = c.execute("select 1 from fakt_ssylka where fakt_id=? and url=?",
                    (z['fakt_id'], z['novaya'])).fetchone()
    if est:
        c.execute("delete from fakt_ssylka where rowid=? and url=?", (z['rowid'], z['staraya']))
        udal += 1 if c.rowcount else 0
    else:
        c.execute("update fakt_ssylka set url=?, etap='карточка закупки; было — поиск по "
                  "номеру, он показывает как искали, а не что нашли' where rowid=? and url=?",
                  (z['novaya'], z['rowid'], z['staraya']))
        pereim += 1 if c.rowcount else 0
    if not c.rowcount:
        ne += 1
p.commit()
print('переведено в карточки: %d | удалено как дубль: %d | не найдено: %d' % (pereim, udal, ne))
q = lambda s: c.execute(s).fetchone()[0]
print('осталось ссылок-поисков: %d' % q(r"select count(*) from fakt_ssylka where url like '%extendedsearch%'"))
print('всего ссылок: %d' % q('select count(*) from fakt_ssylka'))
p.close()
