# -*- coding: utf-8 -*-
"""Почему у контакта нет ссылки на первоисточник — по конкретной карточке и по всей базе.

ПОВОД. В карточке контакта стоит «Источник: свод личных номеров 1+3 сессий (источник не
назван); Тендер.Про  ссылки нет». То есть у номера есть ДВА источника, и ни у одного нет
адреса, по которому человек мог бы перепроверить. Для нас это не косметика: правило владельца
про провенанс — источники НАКАПЛИВАЮТСЯ, а «источник не назван» означает, что накапливать
оказалось нечего.

Смотрю три вещи и не смешиваю их:
  1. что лежит в самой строке этого контакта — source, source_url, откуда пришёл;
  2. сколько контактов в базе БЕЗ ссылки, в разрезе по источникам — чтобы понять, теряет
     ссылку один канал или все;
  3. есть ли у тех же людей ссылка в ДРУГИХ строках — тогда она не потеряна, а не сшита.
"""
import collections
import json
import re
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {}
NOMER = '79114151222'

o['строки_этого_номера'] = cx.execute("""
    select inn, coalesce(person,''), coalesce(position,''), coalesce(role,''),
           coalesce(phone,''), coalesce(source,''), coalesce(source_url,''), coalesce(is_tech,0)
    from person where replace(replace(replace(replace(coalesce(phone,''),' ',''),'-',''),
                              '(',''),')','') like ?""", ('%' + NOMER[-10:] + '%',)).fetchall()

o['контактов_всего'] = cx.execute('select count(*) from person').fetchone()[0]
o['без_ссылки'] = cx.execute(
    "select count(*) from person where coalesce(source_url,'') = ''").fetchone()[0]
o['со_ссылкой'] = o['контактов_всего'] - o['без_ссылки']
o['без_ссылки_по_источникам'] = cx.execute("""
    select coalesce(source,'(пусто)'), count(*),
           sum(case when coalesce(source_url,'')='' then 1 else 0 end)
    from person group by 1 order by 2 desc limit 14""").fetchall()

# Есть ли ссылка у того же ФИО+ИНН в другой строке — тогда она не потеряна, а не сшита.
o['людей_без_ссылки_но_ссылка_есть_рядом'] = cx.execute("""
    select count(*) from person a
    where coalesce(a.source_url,'') = ''
      and exists (select 1 from person b where b.inn = a.inn and b.person = a.person
                    and coalesce(b.source_url,'') <> '')""").fetchone()[0]
# У фактов того же предприятия ссылки есть?
o['фактов_со_ссылкой_у_этих_ИНН'] = cx.execute("""
    select count(*) from fact f where coalesce(f.source_url,'') <> ''
      and f.inn in (select inn from person where coalesce(source_url,'')='')""").fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1))
