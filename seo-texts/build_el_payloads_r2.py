# -*- coding: utf-8 -*-
"""Payload'ы раунда 2 калибровки (Fable 5 vs Sonnet 5): hansmann, rossiya, remennyy,
kompressory-10-bar, kompressory-1000-l-min. Данные: CSV-срез + el-pilot/raw-*.json +
el-pilot/projects-round2.json + курированные факты."""
import csv, json, re

CSV = 'elektro-pages-data.csv'
OUT = 'gen/payload-el-{slug}.json'

PAGES = {
 'hansmann': dict(tier='druzhestvennyy', skeleton='S4', count_in_title=True),
 'rossiya': dict(tier='neytralnyy', skeleton='F-COUNTRY', count_in_title=False),
 'remennyy': dict(tier='neytralnyy', skeleton='F-DRIVE', count_in_title=False),
 'kompressory-10-bar': dict(tier='neytralnyy', skeleton='F-PRESSURE', count_in_title=False),
 'kompressory-1000-l-min': dict(tier='neytralnyy', skeleton='F-PERF', count_in_title=False),
}

BRAND_FACTS = {
 'hansmann': ("Дружественный бренд, «Руспром» - официальный дилер: прямые прайсы, заводская гарантия. "
  "Позиционирование: немецкая инженерная мысль с адаптацией к России. Завод в Шанхае работает с 1997 года, "
  "площадь 50 000 м². Серии: RS A (базовые машины 11-160 кВт), RS E (с частотным преобразователем). "
  "Двигатели классов энергоэффективности IE2/IE3. Гарантия бренда 2 года. "
  "Про винтовые блоки писать ТОЛЬКО «европейские винтовые блоки» (конкретный производитель блоков не подтверждён). "
  "Ниша: металлообработка, деревообработка, упаковка, шиномонтаж, производство пластика, пищевые производства."),
 'rossiya': ("Фасет страны производства. Тональность: нейтрально-экспертная, БЕЗ политики. "
  "Аргументы страницы: доступность запчастей и расходников, ремонтопригодность, близость сервиса, "
  "независимость от импортной логистики. "
  "ВАЖНО: Enger в составе этой страницы НЕ числится (сайт относит его к стране производства Китай) - "
  "НЕ подавать Enger как часть страницы. Реальный состав: ЗИФ, РКЗ, Бежецк (ZEGA - см. критическую пометку ниже). "
  "Мост-блок на Enger допустим только как альтернатива из каталога с честной формулировкой: "
  "российский бренд компании «Руспром» (Барнаул) с собственными заводами в Хуэйчжоу (Китай), "
  "инженерия и сервис в России. Без принижения российских заводов страницы. " + "КРИТИЧНО (владелец, 15.07): ZEGA НЕ российский бренд - страна производства Китай; его 223 позиции висят в фасете «Россия» из-за ошибки свойства в Битриксе (будет исправляться). В тексте НЕ называть ZEGA российским заводом и НЕ строить на нём аргументацию страницы. Реальные российские производители страницы: ЗИФ, РКЗ, Бежецк - на них и опираться. Диапазон цен страницы тоже не привязывать к машинам ZEGA (дорогой хвост до 21 млн - это ZEGA)."),
 'remennyy': ("Фасет типа привода. ВАЖНО: страница продаёт именно ременные машины - не агитировать за "
  "прямой привод, честно показать нишу ременного. Факты: блок соединён с двигателем шкивами и ремнями "
  "(подтверждено карточками BERG ВК-...Р); обслуживание передачи сводится к контролю натяжения и замене "
  "ремней - дёшево и без спецоборудования; схема распространена в малых и средних мощностях. "
  "Прямой привод - альтернатива без обслуживания передачи (не «лучше», а другая ниша)."),
 'kompressory-10-bar': ("Фасет давления. Правило подбора: 10 бар выбирают, когда самому требовательному "
  "потребителю нужно больше, чем дают 8 бар, с учётом потерь давления в магистрали. "
  "Исполнения одной модели на разное давление обычно стоят одинаково, но чем выше давление, "
  "тем ниже производительность той же машины - поэтому давление берут по паспорту потребителя, не «с запасом»."),
 'kompressory-1000-l-min': ("Фасет производительности. Ориентир: ~1000 л/мин закрывает 1-2 поста "
  "пневмоинструмента или небольшой участок; типичная мощность таких машин видна из sample_models "
  "(писать только то, что подтверждается моделями листинга). Правило запаса: расход потребителей + 15-20 %."),
}

def as_model_str(x):
    """Агенты сохраняют модели то строкой, то объектом {name, price...} - нормализуем."""
    if isinstance(x, dict):
        x = x.get('name') or x.get('model') or json.dumps(x, ensure_ascii=False)
    return re.sub(r'\s*[—–-]\s*[\d\s]+(?:₽|руб\.?).*$', '', str(x)).strip()

rows = {}
for r in csv.reader(open(CSV), delimiter=';'):
    if r[0].startswith('http'):
        rows[r[0].rstrip('/').split('/')[-1]] = r

proj = json.load(open('el-pilot/projects-round2.json'))['pages']

for slug, cfg in PAGES.items():
    r = rows[slug]
    raw = json.load(open(f'el-pilot/raw-{slug}.json'))
    tag = r[2]
    m = re.search(r'(\d[\d\s]*)', tag.replace(' ', ' '))
    el_count = int(m.group(1).replace(' ', '')) if m and cfg['count_in_title'] else None
    csv_min = int(r[5]) if r[5].isdigit() else None
    live_min = raw.get('min_price_verified')
    notes = list(raw.get('notes') or [])
    if csv_min and live_min and abs(csv_min - live_min) > 1:
        notes.append(f'цена в фасете ({csv_min}) устарела: реальный минимум листинга {live_min}')
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
        'facet_ranges_warning': 'диапазоны фильтров НЕ сужены сайтом под страницу - это границы всего раздела; как диапазон ИМЕННО этой страницы их не подавать',
        'pages_of_listing': int(r[10]) if r[10].isdigit() else None,
        'sample_models_cheap': [as_model_str(s) for s in raw.get('sample_models_cheap', [])],
        'sample_models_default': [as_model_str(s) for s in raw.get('sample_models_default', [])],
        'series_observed': [re.sub(r'<[^>]{1,12}>', 'N',
                                   x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))
                            for x in raw.get('series_observed', [])],
        'brands_in_facet': raw.get('brands_in_facet', []),
        'warranty': {},
        'brand_facts': BRAND_FACTS[slug],
        'projects': [{k: p[k] for k in ('url', 'equipment', 'client', 'city')}
                     for p in proj.get(slug, []) if p.get('verified_live', True)][:3],
        'data_notes': notes,
    }
    out = OUT.format(slug=slug)
    json.dump(payload, open(out, 'w'), ensure_ascii=False, indent=1)
    print(f'{out}: count={el_count} min={live_min} проектов={len(payload["projects"])} notes={len(notes)}')
