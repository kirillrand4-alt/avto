# -*- coding: utf-8 -*-
"""Помечает факты, где в поле МАРКА лежит внутризаводской позиционный номер, а не модель.

Класс передала 3-я сессия: у неё 90 из 159 коротких обозначений «К-…/…» оказались номерами
позиции по технологической схеме, а не марками. Проверил у себя — класс есть, но узкий и с
ЛОЖНОЙ ТРЕВОГОЙ на первом образце. Мой первый признак («короткая марка + рядом поз./техн.№»)
дал 107 совпадений, и среди них настоящие модели: ЦК-135/8, КТК-12,5/35, ВК9020, 305ВП16/70,
ТВ-80, ВЦ 4-75 — это реальные советские компрессоры и воздуходувки, а «поз. 2/1» стоит рядом
отдельным полем. Признак пришлось переписать.

Настоящий разделитель — не вид марки, а ЧТО описывает факт:

    брак:   «Напорный бак уплотнительного масла компрессора К-601, техн. № 701А» — марка К-601
            вытащена из имени СОСЕДНЕЙ машины, а предмет экспертизы — бак;
    брак:   «Электродвигатель ... техн. № АВО масла В-5 ГПА 32» — ГПА 32 это номер агрегата
            в цехе, то есть адрес, а не марка;
    НЕ брак: «Компрессор центробежный ЦК-135/8 (зав.№78027, техн.№ 8-3)» — марка настоящая.

Признак: в поле марки короткое «буквы-цифры» И в голове описания стоит УЗЕЛ (бак, сепаратор,
холодильник, трубопровод, электродвигатель, клапан, нагреватель) РАНЬШЕ, чем сама машина.

Замер: 78 фактов у 6 предприятий, всем проставлен ранг машины. Цена для выдачи — ноль: ни у
одного из 6 брачный факт не задаёт ранг, у каждого есть свой компрессорный факт того же
ранга. То есть врёт не место в выдаче, а надпись в карточке — менеджер прочтёт «К-601» и
будет искать такую модель в прайсе.

Не удаляю: машина у предприятия ЕСТЬ (ТОАЗ действительно эксплуатирует компрессоры К-601,
заключение ЭПБ на бак это подтверждает). Ставлю `marka_pozicionnaya=1` — карточка покажет,
что обозначение позиционное. Так же поступили с посредниками, сшитыми ИНН и общими почтами.
"""
import os, re, sqlite3, time

D = os.path.dirname(os.path.abspath(__file__))
UZEL = re.compile(r'\b(напорн\w+ бак|дренажн\w+ бак|бак|сепаратор|холодильник|пароконденсатор|'
                  r'трубопровод|электродвигател|клапан|нагревател|маслоохладител|теплообменник)', re.I)
MASH = re.compile(r'\b(компрессор|воздуходувк|нагнетател|турбокомпрессор|генератор|мкс|ресивер)', re.I)
POZ = re.compile(r'^[А-ЯЁ]{1,4}[\s-]?\d{1,4}([/-]\d{1,4})?$')
SHAPKA = re.compile(r'^(техническо\w+ устройство[,:]?\s*'
                    r'(применяемо\w+ на опасном производственном объекте)?[:,]?\s*)', re.I)


def pozicionnaya(marka, chto_naydeno):
    """True — в поле марки лежит позиция по схеме, а не модель машины."""
    m = (marka or '').strip()
    if not POZ.match(m):
        return False
    golova = SHAPKA.sub('', (chto_naydeno or '').strip()).lstrip('«"\'  ')[:70]
    u, s = UZEL.search(golova), MASH.search(golova)
    return bool(u and (not s or u.start() < s.start()))


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=120)
c = p.cursor()
if 'marka_pozicionnaya' not in [r[1] for r in c.execute('pragma table_info(fakt)')]:
    c.execute('alter table fakt add column marka_pozicionnaya integer default 0')
c.execute('update fakt set marka_pozicionnaya=0')

rows = c.execute("""select id, inn, coalesce(marka,''), coalesce(chto_naydeno,'') from fakt
                     where coalesce(marka,'')<>''""").fetchall()
pometit = [r[0] for r in rows if pozicionnaya(r[2], r[3])]
for i in range(0, len(pometit), 800):
    pack = pometit[i:i + 800]
    c.execute('update fakt set marka_pozicionnaya=1 where id in (%s)'
              % ','.join('?' * len(pack)), pack)
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'МАРКА: позиционный номер вместо модели',
           len(rows), len(pometit), len(rows) - len(pometit),
           'класс передала 3-я сессия; предмет факта — узел, марка взята из имени соседней машины'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
V = "v_parke=1 and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0"
print('фактов с маркой всего ................... %d' % len(rows))
print('  помечено позиционной маркой ........... %d' % len(pometit))
print('в выдаче: помечено %d у %d предприятий'
      % (q('select count(*) from fakt where marka_pozicionnaya=1 and ' + V),
         q('select count(distinct inn) from fakt where marka_pozicionnaya=1 and ' + V)))
print('  из них факту проставлен ранг машины ... %d'
      % q('select count(*) from fakt where marka_pozicionnaya=1 and coalesce(rang_mashiny,0)>0 and ' + V))
p.close()
