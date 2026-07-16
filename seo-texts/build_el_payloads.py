# -*- coding: utf-8 -*-
"""Сборка payload-файлов для 5 пилотных электрических страниц:
CSV-срез + живые листинги (el-pilot/raw-*.json) + проекты + курированные факты брендов."""
import csv, json, re

CSV = 'elektro-pages-data.csv'
OUT = 'gen/payload-el-{slug}.json'

PAGES = {
 'enger': dict(tier='rodnoy', skeleton='ENGER-EL', count_in_title=True),
 'berg': dict(tier='druzhestvennyy', skeleton='S3', count_in_title=True),
 'dalgakiran': dict(tier='neytralnyy', skeleton='S2', count_in_title=True),
 '15-to-15': dict(tier='neytralnyy', skeleton='F-POWER', count_in_title=False),
 's-chastotnym-preobrazovatelem': dict(tier='neytralnyy', skeleton='F-EQUIP', count_in_title=False),
}

BRAND_FACTS = {
 'enger': ("Родной бренд. Более 6 000 моделей в линейке бренда (по каталогу — писать только про бренд целиком). "
  "Маркировка по винтовому блоку: BS = блок BAOSI (4 подшипника SKF), HA/HB/HC = HANBELL серий AA/AB/AC (6 подшипников SKF), "
  "HBD (двухступенчатые) = HANBELL ABD, 12 подшипников, ресурс блока более 100 000 моточасов. "
  "Суффикс VSD в названии = частотный преобразователь. Частотники INOVANCE: регулировка производительности 30–100 %, "
  "экономия электроэнергии 20–40 %. Безмасляные OFSZ — на блоке HANBELL ABD, двигатель класса IE5. "
  "В листинге есть высоковольтные модели на 6 000 В (IP55). "
  "Гарантия 2 года, на крупные машины — до 5 лет. Часть моделей в наличии на складах (отгрузка сразу), под заказ срок поставки от 45 до 90 дней. Тестовый запуск с видеозаписью перед отгрузкой. "
  "Склады: Москва, Барнаул, Новосибирск и другие города. "
  "Расшифровка маркировки BS (пример BS-7,5DTE L 8): число = мощность в кВт; B/D = привод ременной/прямой; T/F = защита двигателя IP23/IP54; R = встроенный осушитель; E = частотный преобразователь; последняя цифра = давление в барах. Суффикс «L» = серия Лайт (введена недавно, моделей мало): так отмечены самые доступные машины линейки, на технические характеристики не влияет. В тексте про Enger подавать позитивно: «доступная серия Лайт», НЕ «дешёвая»."),
 'berg': ("Дружественный бренд, «Руспром» — официальный дилер: прямые прайсы, заводская гарантия. "
  "Немецкая разработка; производитель выпускает собственные винтовые блоки, фильтры и сепараторы. "
  "Ресурс винтового блока: 40 000 часов до замены подшипников, общий срок службы более 100 000 часов. "
  "Работает почти в любом климате, не требует специальных помещений. "
  "На сайте 368 проектов поставок BERG. Ниша: малый и средний бизнес, автосервисы, пескоструйные и покрасочные участки. "
  "ВНИМАНИЕ: расшифровка суффиксов серии ВК (Р/Е/РО) в источниках расходится — в тексте суффиксы НЕ расшифровывать, "
  "если расшифровка не видна в самом названии модели (например «10 бар», «IP54» — можно)."),
 'dalgakiran': ('Суффикс -200 в названии серии F (например F 3-10-200) = исполнение на ресивере 200 литров (подтверждено владельцем 15.07); базовая F без суффикса - без ресивера.'),
 '15-to-15': None,
 's-chastotnym-preobrazovatelem': (
  "Общее правило (не привязано к бренду): частотный преобразователь регулирует обороты двигателя под фактический "
  "расход воздуха; выгоден при переменной нагрузке (смены с неравномерным потреблением, рост парка потребителей), "
  "при стабильной полной загрузке переплата окупается хуже. У Enger частотники INOVANCE, заявленная экономия "
  "электроэнергии 20–40 % при регулировании 30–100 % производительности (это заявка бренда — подавать как заявку)."),
}

rows = {}
for r in csv.reader(open(CSV), delimiter=';'):
    if r[0].startswith('http'):
        slug = r[0].rstrip('/').split('/')[-1]
        rows[slug] = r

projects = json.load(open('el-pilot/projects-electric.json'))['projects']

def pick_projects(slug):
    if slug == 'enger':
        pj = [p for p in projects if p['brand'].lower() == 'enger'][:3]
    elif slug == 'berg':
        pj = [p for p in projects if p['brand'].upper() == 'BERG'][:3]
    elif slug == 'dalgakiran':
        pj = [p for p in projects if 'dalgakiran' in p['brand'].lower()][:3]
    elif slug == '15-to-15':
        pj = [p for p in projects if p.get('power_kw') == 15][:2]
    else:
        pj = [p for p in projects if p.get('vsd')][:3]
    return [{k: p[k] for k in ('url', 'equipment', 'client', 'city')} for p in pj]

for slug, cfg in PAGES.items():
    r = rows[slug]
    raw = json.load(open(f'el-pilot/raw-{slug}.json'))
    tag = r[2]
    m = re.search(r'(\d[\d\s]*)', tag.replace(' ', ' '))
    el_count = int(m.group(1).replace(' ', '')) if m and cfg['count_in_title'] else None
    csv_min = int(r[5]) if r[5].isdigit() else None
    live_min = raw.get('min_price_verified')
    notes = list(raw.get('notes') or [])
    if csv_min and live_min and abs(csv_min - live_min) > 1:
        notes.append(f'цена в фасете ({csv_min}) устарела: реальный минимум листинга {live_min} — использован минимум листинга')
    payload = {
        'slug': slug,
        'url': r[0],
        'h1': r[3],
        'title_current': r[4],
        'tier': cfg['tier'],
        'skeleton': cfg['skeleton'],
        'el_count': el_count,
        'count_in_title': cfg['count_in_title'],
        'count_note': 'число позиций С УЧЁТОМ ИСПОЛНЕНИЙ (давление/комплектация), не уникальных моделей',
        'price_min': live_min,
        'price_max': raw.get('max_price_verified'),
        'pressure_bar': r[7],
        'other_ranges': r[8],
        'facet_ranges': raw.get('facet_ranges') or {},
        'pages_of_listing': int(r[10]) if r[10].isdigit() else None,
        'sample_models_cheap': [re.sub(r'\s*[—–-]\s*[\d\s]+(?:₽|руб\.?).*$', '', s).strip() for s in raw.get('sample_models_cheap', [])],
        'sample_models_default': [re.sub(r'\s*[—–-]\s*[\d\s]+(?:₽|руб\.?).*$', '', s).strip() for s in raw.get('sample_models_default', [])],
        'series_observed': [re.sub(r'<[^>]{1,12}>', 'N', x) for x in raw.get('series_observed', [])],  # плейсхолдеры <кВт> не должны утекать в тексты
        'brands_in_facet': raw.get('brands_in_facet', []),
        'warranty': ('гарантия 2 года, на крупные машины — до 5 лет' if slug == 'enger' else {}),
        'brand_facts': BRAND_FACTS[slug],
        'projects': pick_projects(slug),
        'data_notes': notes,
    }
    out = OUT.format(slug=slug)
    json.dump(payload, open(out, 'w'), ensure_ascii=False, indent=1)
    print(f'{out}: count={el_count} min={live_min} проектов={len(payload["projects"])} notes={len(notes)}')
