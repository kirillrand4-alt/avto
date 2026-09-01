# -*- coding: utf-8 -*-
"""Анализ ассортимента Битрикса: какие ещё группы (посадочные страницы фильтра)
можно сделать в разделе «Воздушные компрессоры».

Вход:  products.jsonl.gz — плоская выгрузка Битрикса (один товар = одна строка),
       собирается из bitrix-export-full.tar.gz скриптом extract_products.py.
Порог: группа считается пригодной, если в неё попадает > 10 товаров.
"""
import gzip, json, re, sys, os
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
SRC  = sys.argv[1] if len(sys.argv) > 1 else 'products.jsonl.gz'
MIN  = 11          # «больше чем 10 товаров»

# ---------------------------------------------------------------- нормализация
def num(v):
    v = v.replace(',', '.').strip()
    if not re.fullmatch(r'\d+(\.\d+)?', v):
        return None
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)

def ip(v):
    m = re.fullmatch(r'IP\s*(\d{2})', v.strip(), re.I)
    return 'IP' + m.group(1) if m else None

def yesno(v):
    v = v.strip().lower()
    return {'да': 'да', 'есть': 'да', 'нет': 'нет'}.get(v)

def noise(v):
    v = v.strip().replace('±2', '').replace('.', ',')
    return num(v.replace(',', '.'))

def plain(v):
    return v.strip()

# фасет: (человекочитаемое имя, колонки, нормализатор)
FACETS = {
    'brand':      ('Бренд / производитель',        ['IP_PROP22553'], plain),
    'country':    ('Страна происхождения',         ['IP_PROP22671'], plain),
    'ctype':      ('Тип компрессора',              ['IP_PROP22580'], plain),
    'lube':       ('Тип смазки',                   ['IP_PROP22583'], plain),
    'drive':      ('Тип привода',                  ['IP_PROP22601'], plain),
    'power':      ('Мощность, кВт',                ['IP_PROP22562'], num),
    'press':      ('Рабочее давление, бар',        ['IP_PROP22573'], num),
    'perf':       ('Производительность, л/мин',    ['IP_PROP22571'], num),
    'recv':       ('Объём ресивера, л',            ['IP_PROP22564'], num),
    'volt':       ('Напряжение питания, В',        ['IP_PROP22563'], plain),
    'mobile':     ('Передвижной',                  ['IP_PROP22566'], yesno),
    'temp':       ('Температурный режим',          ['IP_PROP22812'], plain),
    'ipclass':    ('Степень защиты двигателя',     ['IP_PROP22959', 'IP_PROP22674'], ip),
    'motor':      ('Тип двигателя',                ['IP_PROP23040'], plain),
    'tgroup':     ('Товарная группа (1С)',         ['IP_PROP22602'], plain),
    'cooling':    ('Тип охлаждения',               ['IP_PROP22669'], lambda v: {'воздушный':'воздушное'}.get(v.strip().lower(), v.strip().lower())),
    'warranty':   ('Гарантия',                     ['IP_PROP22672'], lambda v: v.strip() if re.match(r'^[123] (год|года)$', v.strip()) else None),
    'series':     ('Серия',                        ['IP_PROP22576', 'IP_PROP22575'], lambda v: re.sub(r'^Серия\s+', '', v.strip())),
    'block':      ('Винтовой блок',                ['IP_PROP22670'], lambda v: {'BAOSI':'Baosi','HANBELL':'Hanbell','HANBELL AB':'Hanbell AB','HANBELL ABD':'Hanbell ABD','HANBELL AC':'Hanbell AC','HANBELL AA':'Hanbell AA','GHH RAND':'GHH Rand','JIUYI':'Jiuyi','ROTORCOMP':'RotorComp'}.get(re.split(r'\s*[/(]', v.strip())[0].strip().upper(), re.split(r'\s*[/(]', v.strip())[0].strip())),
    'engine':     ('Производитель ДВС',            ['IP_PROP22569'], lambda v: v.strip().title().replace('Сummins', 'Cummins')),
    'noise':      ('Уровень шума, дБ',             ['IP_PROP22668'], noise),
    'quiet':      ('Малошумное исполнение',        ['IP_PROP22681'], yesno),
    'dewpt':      ('Точка росы, °C',               ['IP_PROP22585'], plain),
    'recvflag':   ('Ресивер в комплекте',          ['IP_PROP22574'], yesno),
    'dryflag':    ('Осушитель в комплекте',        ['IP_PROP22565'], yesno),
    'vsdflag':    ('Частотный преобразователь',    ['IP_PROP22586'], yesno),
    'purpose':    ('Назначение',                   ['_purpose'], plain),
}

PURPOSE = {'Для цеха', 'Для выдува ПЭТ', 'Для фотосепараторов', 'Для медицины',
           'Для буровых установок', 'Для лазерной резки', 'Для плазменной резки'}

# --- что уже есть на сайте: фасеты фильтра + 567 сгенерированных посадочных ---
HAVE = {
 'power':   {'5.5','7','7.5','11','15','18.5','22','30','37','45','50','55','75','90','100',
             '110','132','160','185','200','220','225','250','315','355','400','500'},
 'press':   {'5','6','7','8','10','12','13','15','16','20','25','30','40','200','300'},
 'perf':    {'500','600','700','800','900','1000','1500','2000','3000','3500','5000','6000',
             '7000','10000','12000','15000','20000','23000','25000','30000','45000','50000'},
 'recv':    {'200','250','400','450','500','900','1000'},
 'volt':    {'380','220'},
 'lube':    {'масляный','безмасляный'},
 'drive':   {'прямой','ременный'},
 'ctype':   {'винтовой','спиральный','винтовой двухступенчатый','дизельный','винтовой безмасляный'},
 'purpose': {'Для выдува ПЭТ','Для цеха'},
 'recvflag':{'да','нет'}, 'dryflag':{'да','нет'}, 'vsdflag':{'да','нет'},
 'country': 'ALL',   # все 16 стран уже в фильтре
 'brand':   'ALL',   # 62 бренд-страницы уже есть
}

# ------------------------------------------------------------------- загрузка
def load(src=SRC):
    out = []
    for line in gzip.open(src, 'rt', encoding='utf-8'):
        r = json.loads(line)
        g = lambda k: (lambda v: '|'.join(v) if isinstance(v, list) else (v or ''))(r.get(k))
        if 'Воздушные компрессоры' not in g('IC_GROUP0'):
            continue
        if r.get('IE_ACTIVE') != 'Y' or r.get('IP_PROP22590') == 'Нет':
            continue
        r['_purpose'] = [v for v in g('IC_GROUP2').split('|') if v in PURPOSE]
        out.append(r)
    return out

def facet_values(rec, key):
    name, cols, fn = FACETS[key]
    vals = set()
    for c in cols:
        v = rec.get(c)
        if v is None:
            continue
        for x in (v if isinstance(v, list) else [v]):
            n = fn(x)
            if n:
                vals.add(n)
    return vals

def index(data):
    """key -> value -> set(product ids)"""
    idx = defaultdict(lambda: defaultdict(set))
    for i, r in enumerate(data):
        for k in FACETS:
            for v in facet_values(r, k):
                idx[k][v].add(i)
    return idx

if __name__ == '__main__':
    data = load()
    idx = index(data)
    print(f'товаров в разделе «Воздушные компрессоры»: {len(data)}\n')
    print(f'{"фасет":<34} {"значений":>9} {">10 тов.":>9}')
    for k, (name, _, _) in FACETS.items():
        vs = idx[k]
        print(f'{name:<34} {len(vs):>9} {sum(1 for s in vs.values() if len(s) >= MIN):>9}')
