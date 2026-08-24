# -*- coding: utf-8 -*-
r"""«Отдали в Bitrix» — из общей ленты в свою очередь.

Владелец 24.08 обвёл метку в ленте: «сделай чтобы переносило в свою очередь эта
метка из общей ленты». Лид, отданный в Битрикс, из работы уже вышел — дальше им
занимается отдел продаж, — и в общей ленте он только мешает считать оставшееся.
Механика ровно та же, что у «не интересно» с 11.08: лид не удаляется, из ленты
уходит, достаётся фильтром по статусу, а счётчик над лентой говорит, сколько
спрятано и где смотреть.
"""
import json
import re

d = {}
п = r'C:\sender\sender\store.py'
т = open(п, encoding='utf-8').read()
старое = """            sql.append("AND status NOT IN ('deleted', 'not_interested')")"""
новое = """            # «Отдали в Bitrix» прячем по той же причине (владелец 24.08):
            # лид ушёл в отдел продаж, в общей ленте ему делать нечего.
            sql.append("AND status NOT IN ('deleted', 'not_interested', "
                       "'in_bitrix')")"""
if новое.split('\n')[-1] in т:
    d['store'] = 'уже стояло'
elif старое in т:
    т = т.replace(старое, новое, 1)
    open(п, 'w', encoding='utf-8', newline='').write(т)
    d['store'] = 'заменено'
else:
    d['store'] = 'НЕ НАШЁЛ'
try:
    compile(т, п, 'exec')
    d['синтаксис_store'] = 'ок'
except SyntaxError as e:
    d['синтаксис_store'] = str(e)[:140]

# фронт: счётчик спрятанных «в Bitrix» рядом с «не интересно»
ф = r'C:\sender\_tmp\web-pravki\screens\Leads.tsx'
т2 = open(ф, encoding='utf-8').read()
ст2 = """  const скрытоНеинтересно = поСтатусам["not_interested"] || 0;"""
но2 = """  const скрытоНеинтересно = поСтатусам["not_interested"] || 0;
  // «Отдали в Bitrix» лента тоже прячет: лид ушёл в отдел продаж. Счётчик
  // рядом — чтобы спрятанное не выглядело пропажей (владелец 24.08).
  const скрытоBitrix = поСтатусам["in_bitrix"] || 0;"""
if 'скрытоBitrix' in т2:
    d['front_счётчик'] = 'уже стояло'
elif ст2 in т2:
    т2 = т2.replace(ст2, но2, 1)
    d['front_счётчик'] = 'вставлено'
else:
    d['front_счётчик'] = 'НЕ НАШЁЛ'

ст3 = """          {!mine && !status && скрытоНеинтересно > 0 && (
            <>
              {" · "}
              <button className="btn-link" title="показать их"
                      onClick={() => setStatus("not_interested")}>
                скрыто «не интересно»: {скрытоНеинтересно}
              </button>
            </>
          )}"""
но3 = ст3 + """
          {!mine && !status && скрытоBitrix > 0 && (
            <>
              {" · "}
              <button className="btn-link" title="показать их"
                      onClick={() => setStatus("in_bitrix")}>
                отдали в Bitrix: {скрытоBitrix}
              </button>
            </>
          )}"""
if 'отдали в Bitrix: {скрытоBitrix}' in т2:
    d['front_кнопка'] = 'уже стояло'
elif ст3 in т2:
    т2 = т2.replace(ст3, но3, 1)
    d['front_кнопка'] = 'вставлено'
else:
    d['front_кнопка'] = 'НЕ НАШЁЛ'
if 'вставлено' in (d.get('front_счётчик'), d.get('front_кнопка')):
    open(ф, 'w', encoding='utf-8', newline='').write(т2)
print(json.dumps(d, ensure_ascii=False, indent=1))
