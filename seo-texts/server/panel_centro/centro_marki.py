# -*- coding: utf-8 -*-
"""Разбор марки компрессора в характеристики — для карточки продавца.

Владелец просит «отдельные карточки с описанием характеристик компрессоров
конкретно для этой компании». Характеристик в базе нет, есть обозначения
машин — а советские и российские обозначения компрессоров сами несут
производительность и давление, если знать семейство.

ГЛАВНАЯ ОСТОРОЖНОСТЬ, из-за которой этот файл устроен так. В поле «марка»
лежат не только компрессоры: замер по базе показал сотни строк вида
«Л-35/11-600» (установка риформинга), «АВТ-6» (атмосферно-вакуумная
трубчатка), «ГАЦ-61-6М2», «ТЭЦ-10». Если разбирать всё подряд по числам после
дефиса, получится карточка с уверенными характеристиками несуществующего
компрессора — а выдуманная характеристика опаснее пустого места: продавец
приедет с ней к главному инженеру.

Поэтому разбираются ТОЛЬКО известные семейства, и каждая цифра подписана тем,
чем она является в этом семействе. Всё остальное честно возвращает пусто.

Числа — из обозначения, а не из паспорта машины: обозначение говорит о
номинале серии, реальная машина может быть модернизирована. Это написано и в
карточке, чтобы продавец не выдавал номинал за замер.
"""
from __future__ import annotations

import re

# Семейства. Порядок важен: сначала узкие, потом общие.
_СЕМЕЙСТВА = (
    # 43ВЦ-160/9, 32ВЦ-100/9 — центробежные воздушные, Q м³/мин, p кгс/см²
    (re.compile(r'^\s*(\d{1,3})\s*ВЦ\s*[-–]?\s*(\d{2,4})\s*[/\\]\s*(\d{1,2})',
                re.I),
     lambda m: ('центробежный воздушный компрессор',
                f'{m.group(2)} м³/мин', f'{m.group(3)} кгс/см²',
                f'серия {m.group(1)}ВЦ')),
    # ЦК-135/8, ЦК 115/9
    (re.compile(r'^\s*ЦК\s*[-–]?\s*(\d{2,4})\s*[/\\]\s*(\d{1,2})', re.I),
     lambda m: ('центробежный компрессор',
                f'{m.group(1)} м³/мин', f'{m.group(2)} кгс/см²', 'серия ЦК')),
    # К-250-61-1, К-500-61-1, К354-101-1 — центробежные (турбокомпрессоры)
    (re.compile(r'^\s*К\s*[-–]?\s*(\d{3,4})\s*[-–]\s*(\d{2,3})\s*[-–]?\s*(\d?)',
                re.I),
     lambda m: ('центробежный компрессор (турбокомпрессор)',
                f'{m.group(1)} м³/мин', 'по серии, уточнить у заказчика',
                f'серия К-{m.group(1)}-{m.group(2)}')),
    # ТВ-300-1,6 / ТВ 80-1,6 — турбовоздуходувки, p в атмосферах
    (re.compile(r'^\s*ТВ\s*[-–]?\s*(\d{2,4})\s*[-–]\s*(\d+(?:[.,]\d+)?)', re.I),
     lambda m: ('турбовоздуходувка (центробежная)',
                f'{m.group(1)} м³/мин',
                f'{m.group(2).replace(",", ".")} кгс/см²', 'серия ТВ')),
    # 4ВМ10-63/9, 2ВМ4-24/9 — поршневые оппозитные
    (re.compile(r'^\s*(\d?)\s*ВМ\s*(\d{1,2})\s*[-–]\s*(\d{1,4})\s*[/\\]\s*'
                r'(\d{1,3})', re.I),
     lambda m: ('поршневой оппозитный компрессор',
                f'{m.group(3)} м³/мин', f'{m.group(4)} кгс/см²',
                f'база {m.group(2)} тс')),
    # 4М10-40/70, 2М10-25/35 — поршневые
    (re.compile(r'^\s*(\d?)\s*М\s*(\d{1,2})\s*[-–]\s*(\d{1,4})\s*[/\\]\s*'
                r'(\d{1,3})', re.I),
     lambda m: ('поршневой компрессор',
                f'{m.group(3)} м³/мин', f'{m.group(4)} кгс/см²',
                f'база {m.group(2)} тс')),
    # 205ГП 30/8 — поршневой газовый
    (re.compile(r'^\s*(\d{2,3})\s*ГП\s*[-–]?\s*(\d{1,4})\s*[/\\]\s*(\d{1,3})',
                re.I),
     lambda m: ('поршневой компрессор (газовый ряд)',
                f'{m.group(2)} м³/мин', f'{m.group(3)} кгс/см²',
                f'серия {m.group(1)}ГП')),
    # импортные винтовые: GA 90, GA250, ESD 441, BS 480, FX20, GM 130L
    (re.compile(r'^\s*(GA|GM|ESD|BS|FX|SK|ASD|DSD|CSD|BSD|ZR|ZT|ZH)\s*'
                r'[-–]?\s*(\d{1,3})', re.I),
     lambda m: ('винтовой компрессор (импортный)',
                'по паспорту серии', 'по паспорту серии',
                f'{m.group(1).upper()} {m.group(2)}')),
)

# То, что в поле «марка» встречается часто и компрессором НЕ является.
# Список набран замером по базе, а не воображением.
_НЕ_МАШИНА = re.compile(
    r'^\s*(?:Л[-\s]?\d+[/-]|АВТ[-\s]?\d|ГАЦ[-\s]?\d|ТЭЦ[-\s]?\d|ЛСИ[-\s]?\d|'
    r'ХВ[-\s]?\d|ЭЛОУ|ГФУ|КТ[-\s]?\d+/|цех\b|установк\w*|печь|котёл|котел)',
    re.I)


# ═══════════════════════════════════════════════════════════════════════════
# ПАСПОРТНАЯ ТАБЛИЦА. Собрана поиском по сайтам производителей с
# адверсариальной проверкой: каждую находку второй агент открывал заново и
# сверял со ВТОРЫМ независимым источником; не подтверждённое выброшено.
#
# Она здесь не «для полноты», а потому что РАЗБОР ПО ОБОЗНАЧЕНИЮ ВРАЛ.
# Сверка 25 марок дала 5 настоящих расхождений, и все в одну сторону —
# я выдавал номер серии за производительность:
#     ТВ-42-1,4  → на деле 60 м³/мин, а не 42
#     ТВ-50-1,6  → 60, а не 50
#     ТВ-80-1,6  → 100, а не 80   (подтверждено ГОСТ 5.2050-73)
#     ТВ-175-1,6 → 167, а не 175
#     К-350-62-1 → 230-275, а не 350
# У семейства ТВ первое число вообще не производительность.
#
# И второе, ради разговора с главным инженером: давление в обозначении —
# АБСОЛЮТНОЕ. «ТВ-300-1,6» это 1,6 абс, избыточных всего 0,6. «43ВЦ-160/9» —
# 9 абс = 8 избыточных. Сказать инженеру «машина на 9 атмосфер» значит
# назвать чужое число: он услышит избыточные.
#
# У каждой строки — ССЫЛКА НА ПЕРЕПРОВЕРКУ. Характеристика без ссылки для
# продавца бесполезна: проверить он её не может, а поедет с ней к инженеру.
# ═══════════════════════════════════════════════════════════════════════════
ПАСПОРТ = {
    "К-250-61-1": {
        "tip": "центробежный, одноцилиндровый, одновальный, шестиступенчатый",
        "proizvoditel": "ПАО/АО «Дальэнергомаш» (Хабаровск)",
        "podacha": "255 м³/мин",
        "davlenie": "9.0 кгс/см² абс",
        "davlenie_izb": "8 кгс/см² изб",
        "moshchnost": "1000–1445 кВт потребляемая (Дальэнергомаш); двигатель СТД-16",
        "sreda": "воздух атмосферный",
        "url": "https://compressor-service.ru/compressors/kompressor-k-250-61-125.html",
        "nadezhnost": "справочник"
    },
    "К-250-61-5": {
        "tip": "центробежный, стационарный автоматизированный, однокорпусный",
        "proizvoditel": "ООО «НП «Энергомаш» (изготовитель по каталогу); базовая маши",
        "podacha": "250 м³/мин",
        "davlenie": "8.0 кгс/см² абс",
        "davlenie_izb": "7 кгс/см² изб",
        "moshchnost": "1000–1445 кВт по сводной таблице (в детальной таблице того ж",
        "sreda": "воздух атмосферный",
        "url": "https://vozdushnyi-kompressor.ru/files/energomash-katalog-oborudovaniya.pdf",
        "nadezhnost": "каталог дилера"
    },
    "К-350-62-1": {
        "tip": "центробежный, однокорпусный, одновальный, шестиступенчатый, ",
        "proizvoditel": "ПАО/АО «Дальэнергомаш» (Хабаровск)",
        "podacha": "275 м³/мин",
        "davlenie": "7.35 кгс/см² абс",
        "davlenie_izb": "6.35 кгс/см² изб",
        "moshchnost": "1600–2000 кВт потребляемая; двигатель 2500 кВт, 6000/10000 В",
        "sreda": "воздух атмосферный (силовой воздух)",
        "url": "https://kompress.ru/kompressory/oao-dalenergomash/k250-61-1-2-5.html",
        "nadezhnost": "каталог дилера"
    },
    "К-400-51-2": {
        "tip": "центробежный, газовый, компрессор в одноцилиндровом исполнен",
        "proizvoditel": "Невский завод (на странице записан как ЗАО «Невские завод»)",
        "podacha": "400 м³/мин",
        "davlenie": "5.0 кгс/см² абс",
        "davlenie_izb": "4 кгс/см² изб",
        "moshchnost": "1500 кВт потребляемая на муфте; двигатель 2АЗМП-2000/6000-У4",
        "sreda": "ГАЗ, а не воздух: контактный газ дегидри",
        "url": "https://compressor-service.ru/compressors/kompressor-k400-51-2.html",
        "nadezhnost": "справочник"
    },
    "К-500-61-1": {
        "tip": "центробежный, одноцилиндровый, одновальный, шестиступенчатый",
        "proizvoditel": "ПАО/АО «Дальэнергомаш» (указан на странице)",
        "podacha": "525 м³/мин",
        "davlenie": "9.0 кгс/см² абс",
        "davlenie_izb": "8 кгс/см² изб",
        "moshchnost": "2400–3000 кВт потребляемая (номинал 3000); привод СТД-3150-2",
        "sreda": "воздух промышленного назначения",
        "url": "https://compressor-service.ru/compressors/kompressory-k-500-61-15.html",
        "nadezhnost": "справочник"
    },
    "К-1500-62-2": {
        "tip": "центробежный, компрессор в одноцилиндровом исполнении, шести",
        "proizvoditel": "Невский завод (на странице записан как ЗАО «Невские завод»)",
        "podacha": "1590 м³/мин",
        "davlenie": "7.5 кгс/см² абс",
        "davlenie_izb": "6.5 кгс/см² изб",
        "moshchnost": "7400 кВт потребляемая на муфте; двигатель СТД-10000-2У4 (в Е",
        "sreda": "воздух (первичный воздух в кислородные б",
        "url": "https://compressor-service.ru/compressors/kompressor-k-1500.html",
        "nadezhnost": "справочник"
    },
    "ТВ-42-1,4-О1.У3": {
        "tip": "центробежная многоступенчатая турбовоздуходувка (турбокомпре",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ, ТУ 3643",
        "podacha": "60 м³/мин",
        "davlenie": "1.4 кгс/см² абс",
        "davlenie_izb": "0.4 кгс/см² изб",
        "moshchnost": "55 кВт (электродвигатель); подтверждено vodprom.ru — 55 кВт",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ТВ-50-1,6-О1.У3": {
        "tip": "центробежная многоступенчатая турбовоздуходувка (турбокомпре",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ, ТУ 3643",
        "podacha": "60 м³/мин",
        "davlenie": "1.6 кгс/см² абс",
        "davlenie_izb": "0.6 кгс/см² изб",
        "moshchnost": "110 кВт (электродвигатель, по БРМЗ). Потребляемая мощность 8",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ТВ-80-1,4-О1.У3": {
        "tip": "центробежная многоступенчатая турбовоздуходувка (турбокомпре",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ, ТУ 3643",
        "podacha": "100 м³/мин",
        "davlenie": "1.42 кгс/см² абс",
        "davlenie_izb": "0.42 кгс/см² изб",
        "moshchnost": "110 кВт (электродвигатель); подтверждено tduzhm.ru — «Двигат",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ТВ-80-1,6-О1.У3": {
        "tip": "центробежная многоступенчатая турбовоздуходувка (турбокомпре",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ, ТУ 3643",
        "podacha": "100 м³/мин",
        "davlenie": "1.63 кгс/см² абс",
        "davlenie_izb": "0.63 кгс/см² изб",
        "moshchnost": "160 кВт (электродвигатель) — совпадает во всех трёх источник",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ТВ-175-1,6-О1.У3": {
        "tip": "центробежная многоступенчатая турбовоздуходувка (турбокомпре",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ, ТУ 3643",
        "podacha": "167 м³/мин",
        "davlenie": "1.63 кгс/см² абс",
        "davlenie_izb": "0.63 кгс/см² изб",
        "moshchnost": "250 кВт (электродвигатель); подтверждено vodprom.ru (250 кВт",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ТВ-200-1,4-О1.У3": {
        "tip": "центробежная многоступенчатая турбовоздуходувка (турбокомпре",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ, ТУ 3643",
        "podacha": "200 м³/мин",
        "davlenie": "1.4 кгс/см² абс",
        "davlenie_izb": "0.4 кгс/см² изб",
        "moshchnost": "200 кВт (электродвигатель); подтверждено vodprom.ru — 200 кВ",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ТВ-300-1,6-О2.У1": {
        "tip": "центробежная многоступенчатая турбовоздуходувка (турбокомпре",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ, ТУ 3643",
        "podacha": "300 м³/мин",
        "davlenie": "1.6 кгс/см² абс",
        "davlenie_izb": "0.6 кгс/см² изб",
        "moshchnost": "400 кВт (электродвигатель, по БРМЗ). Потребляемая 337 кВт по",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ТВ-500-1,08-В1.У2": {
        "tip": "центробежная ОДНОСТУПЕНЧАТАЯ турбовоздуходувка (турбокомпрес",
        "proizvoditel": "ОАО «Брянский ремонтно-механический завод», цех ЦКМ. Тот же ",
        "podacha": "500 м³/мин",
        "davlenie": "1.08 кгс/см² абс",
        "davlenie_izb": "0.08 кгс/см² изб",
        "moshchnost": "132 кВт (электродвигатель). Подтверждено вторым источником p",
        "sreda": "воздух",
        "url": "http://www.brmzavod.ru/production_ckm.html",
        "nadezhnost": "сайт производителя"
    },
    "ЦК-135/8": {
        "tip": "центробежный, двухкорпусный шестиступенчатый, с внешним охла",
        "proizvoditel": "Казанский компрессорный завод (Казанькомпрессормаш). Атрибуц",
        "podacha": "135 м³/мин",
        "davlenie": "7.8 кгс/см² абс",
        "davlenie_izb": "6.8 кгс/см² изб",
        "moshchnost": "870 кВт потребляемая; электродвигатель 4АЗМ-1000 / СТД-1000,",
        "sreda": "воздух (подача воздуха в блоки разделени",
        "url": "https://en-mach.ru/turbo/",
        "nadezhnost": "каталог дилера"
    },
    "32ВЦ-100/9": {
        "tip": "мультипликаторный центробежный (МЦК), моноблок со встроенным",
        "proizvoditel": "Казанькомпрессормаш; страница АО «Компрессормашремсервис»",
        "podacha": "100 м³/мин",
        "davlenie": "9 кгс/см² абс",
        "davlenie_izb": "8 кгс/см² изб",
        "moshchnost": "630 кВт; электродвигатель 4АРМ-630/1000УХЛ4 / СТД-630-2РУХЛ4",
        "sreda": "воздух (сжатие атмосферного воздуха)",
        "url": "https://compressor-service.ru/compressors/kompressor-32vc-1009.html",
        "nadezhnost": "каталог дилера"
    },
    "43ВЦ-160/9": {
        "tip": "мультипликаторный центробежный (МЦК), моноблок со встроенным",
        "proizvoditel": "Казанькомпрессормаш; страница АО «Компрессормашремсервис»",
        "podacha": "160 м³/мин",
        "davlenie": "9 кгс/см² абс",
        "davlenie_izb": "8 кгс/см² изб",
        "moshchnost": "потребляемая 928 кВт, мощность привода 1000 кВт; электродвиг",
        "sreda": "воздух (температура начальная 293 К / 20",
        "url": "https://compressor-service.ru/compressors/kompressor-43vc-1609.html",
        "nadezhnost": "каталог дилера"
    },
    "2ВМ10-63/9": {
        "tip": "поршневой оппозитный, 2 ряда, база М10, 2 ступени (та же маш",
        "proizvoditel": "ОАО «Пензкомпрессормаш» (по атрибуции дилерского каталога); ",
        "podacha": "63 м³/мин",
        "davlenie": "",
        "davlenie_izb": "",
        "moshchnost": "400 кВт (электродвигатель); «Потребляемая мощность (при стан",
        "sreda": "воздух",
        "url": "https://www.kompress.ru/vru/14-kompressory/index.php",
        "nadezhnost": "каталог дилера"
    },
    "4ВМ10-120/9": {
        "tip": "поршневой оппозитный, 4 ряда, база М10 (второй источник)",
        "proizvoditel": "ОАО «Пензкомпрессормаш»",
        "podacha": "124.5 м³/мин",
        "davlenie": "9 кгс/см² абс",
        "davlenie_izb": "8 кгс/см² изб",
        "moshchnost": "800 кВт — совпадает с заводом",
        "sreda": "воздух",
        "url": "http://compressed-air.ru/kompressor-4vm10-120/9-opisanie-i-tehnicheskie-harakteristiki.html",
        "nadezhnost": "каталог дилера"
    },
    "2ВМ4-24/9": {
        "tip": "поршневой оппозитный (крейцкопфный), двухступенчатый, стацио",
        "proizvoditel": "ООО «Краснодарский компрессорный завод» (kkzav.ru); ту же ма",
        "podacha": "12 м³/мин",
        "davlenie": "",
        "davlenie_izb": "",
        "moshchnost": "электродвигатель А2К 85/24-8/16 УХЛ4, 160/75 кВт, 380 В; час",
        "sreda": "воздух",
        "url": "https://kkzav.ru/porshnevye-kompressory/vozduh/kompressor-2vm4-24-9",
        "nadezhnost": "сайт производителя"
    },
    "2ГМ4-24/9": {
        "tip": "газовый поршневой оппозитный (крейцкопфный), 2 ряда, база М4",
        "proizvoditel": "ООО «Краснодарский компрессорный завод»; ту же марку выпуска",
        "podacha": "12 м³/мин",
        "davlenie": "",
        "davlenie_izb": "",
        "moshchnost": "мощность на валу компрессора 122 / 60 кВт; электродвигатель ",
        "sreda": "газ (на карточке в графе «Сжимаемый газ»",
        "url": "https://kkzav.ru/porshnevye-kompressory/gazy/kompressor-2gm4-24-9",
        "nadezhnost": "сайт производителя"
    },
    "2ГМ4-1,3/12-250 (ДОЖИМАЮЩИЙ — вынесен отдельной машиной; в исходном списке был неверно приписан к таблице газовых компрессоров со всасыванием из атмосферы)": {
        "tip": "газовый поршневой дожимной (бустерный), база М4 — работает с",
        "proizvoditel": "ООО «Краснодарский компрессорный завод»",
        "podacha": "1.3 м³/мин",
        "davlenie": "",
        "davlenie_izb": "",
        "moshchnost": "126 кВт",
        "sreda": "газ: различные технические газы (азот, в",
        "url": "https://kkzav.ru/porshnevye-kompressory/dozhimaiuschie/kompressor-2gm4-1-3-12-250-dozhimnoj",
        "nadezhnost": "сайт производителя"
    },
    "305ГП-20/35": {
        "tip": "газовый поршневой на угловой базе 5П, 3 ряда. ОГОВОРКА: «трё",
        "proizvoditel": "ООО «Краснодарский компрессорный завод»; ту же марку продают",
        "podacha": "20 м³/мин",
        "davlenie": "",
        "davlenie_izb": "",
        "moshchnost": "180 кВт. Проверка физикой: изотермическая работа 20 м3/мин с",
        "sreda": "газ (разнообразные газы, в т.ч. взрывооп",
        "url": "https://kkzav.ru/porshnevye-kompressory/gazy/kompressor-305gp-20-35",
        "nadezhnost": "сайт производителя"
    },
    "305ГП-30/8 (существующая марка, предложенная вместо запрошенной «205ГП 30/8» — газовое исполнение)": {
        "tip": "газовый поршневой на угловой базе 5П, 3 ряда",
        "proizvoditel": "ООО «Краснодарский компрессорный завод»",
        "podacha": "30 м³/мин",
        "davlenie": "0.9 МПа",
        "davlenie_izb": "",
        "moshchnost": "154 кВт (только по сводной таблице газовых компрессоров ККЗ;",
        "sreda": "газ: различные технические газы (азот, в",
        "url": "https://kkzav.ru/porshnevye-kompressory/gazy/kompressor-305gp-30-8",
        "nadezhnost": "сайт производителя"
    },
    "205ВП-30/8 (существующая марка, предложенная вместо запрошенной «205ГП 30/8» — воздушное исполнение, 2 ряда на базе 5П)": {
        "tip": "поршневой воздушный на угловой базе 5П, 2 ряда",
        "proizvoditel": "ООО «Краснодарский компрессорный завод»",
        "podacha": "30 м³/мин",
        "davlenie": "8 кгс/см² абс",
        "davlenie_izb": "7 кгс/см² изб",
        "moshchnost": "не указана ни на карточке, ни в сводной таблице завода (клет",
        "sreda": "воздух",
        "url": "https://kkzav.ru/porshnevye-kompressory/vozduh/kompressor-205vp-30-8",
        "nadezhnost": "сайт производителя"
    },
    "205ГП-40/3 (единственная марка серии 205ГП в каталоге завода — для понимания, что такое серия 205ГП)": {
        "tip": "газовый поршневой на угловой базе 5П, 2 ряда",
        "proizvoditel": "ООО «Краснодарский компрессорный завод»",
        "podacha": "40 м³/мин",
        "davlenie": "",
        "davlenie_izb": "",
        "moshchnost": "160 кВт. Проверка физикой: изотермическая работа 40 м3/мин с",
        "sreda": "газ (разнообразные газы)",
        "url": "https://kkzav.ru/porshnevye-kompressory/gazy/kompressor-205gp-40-3",
        "nadezhnost": "сайт производителя"
    },
    "Atlas Copco GA 90+ (50 Гц, маслозаполненный, фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "Atlas Copco",
        "podacha": "20.2 м³/мин",
        "davlenie": "10 бар изб",
        "davlenie_izb": "",
        "moshchnost": "90 кВт (125 л.с.)",
        "sreda": "воздух",
        "url": "https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/oil-free-air/documents/ga-90--160-&-ga-110-160-vsd/2935067803%20GA90_GA110-160_GA110-160%20VSD_EN_LR.pdf",
        "nadezhnost": "сайт производителя"
    },
    "Atlas Copco GA 250 (50 Гц, маслозаполненный, фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "Atlas Copco",
        "podacha": "49.9 м³/мин",
        "davlenie": "14 бар изб",
        "davlenie_izb": "",
        "moshchnost": "250 кВт",
        "sreda": "воздух",
        "url": "https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/oil-free-air/documents/ga-160--135-(vsd)/2935062612%20GA160+%20-315%20(VSD)%20EN_LR.pdf",
        "nadezhnost": "сайт производителя"
    },
    "Atlas Copco GA 22 (50 Гц, маслозаполненный, фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "Atlas Copco",
        "podacha": "65,6 л/с",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "22 кВт (30 л.с.)",
        "sreda": "воздух",
        "url": "https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/industrial-air/documents/leaflets/compressors/ga11-30/ga-15-30-(2023)/GA15-30-Brendola-datasheet-EN-2935081941.pdf",
        "nadezhnost": "сайт производителя"
    },
    "Atlas Copco ZR 160 (безмасляный, водяное охлаждение, FF)": {
        "tip": "винтовой безмасляный двухступенчатый",
        "proizvoditel": "Atlas Copco",
        "podacha": "26.0 м³/мин",
        "davlenie": "10 бар изб",
        "davlenie_izb": "",
        "moshchnost": "160 кВт",
        "sreda": "воздух (безмасляный, класс 0)",
        "url": "https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/oil-free-air/documents/ZRZT-110-160-(VSD)-FF.pdf",
        "nadezhnost": "сайт производителя"
    },
    "Kaeser ESD 441 (снят с производства, заменён на ESD 442)": {
        "tip": "винтовой",
        "proizvoditel": "Kaeser Kompressoren",
        "podacha": "42 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "250 кВт",
        "sreda": "воздух",
        "url": "https://www.pea.ru/docs/equipment/compressors/kkr/vkk/svkk/",
        "nadezhnost": "каталог дилера"
    },
    "Kaeser ESD 442 (текущая модель, замена ESD 441, фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "Kaeser Kompressoren",
        "podacha": "42.20 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "250 кВт",
        "sreda": "воздух",
        "url": "https://mavaindustrial.com/image/catalog/pdf/035a88095172c6947860fc48de8698bd-manualkaeser-esd.pdf",
        "nadezhnost": "каталог дилера"
    },
    "Kaeser BSD 72 (фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "Kaeser Kompressoren",
        "podacha": "7.00 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "37 кВт",
        "sreda": "воздух",
        "url": "https://www.focusindustrial.com.au/wp-content/uploads/2025/01/kae_bsd_2009_de.pdf",
        "nadezhnost": "каталог дилера"
    },
    "Kaeser ASD 40 (европейское исполнение, 22 кВт)": {
        "tip": "винтовой",
        "proizvoditel": "Kaeser Kompressoren",
        "podacha": "3.92 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "22 кВт",
        "sreda": "воздух",
        "url": "https://mk-druckluft.de/files/mk-druckluft/pdf/blaetterkataloge/docs/kaeser_schraubenkompressoren.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L45 (фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "8.00 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "45 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L55 (фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "10.69 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "55 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L75 (фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "13.74 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "75 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L90 (фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "17.45 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "90 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L110 (фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "20.77 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "110 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L132 (фикс. скорость)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "22.87 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "132 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L90RS (частотное регулирование)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "17.74 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "90 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L110RS (частотное регулирование)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "20.82 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "110 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "CompAir L132RS (частотное регулирование)": {
        "tip": "винтовой",
        "proizvoditel": "CompAir (Gardner Denver)",
        "podacha": "22.84 м³/мин",
        "davlenie": "13 бар изб",
        "davlenie_izb": "",
        "moshchnost": "132 кВт",
        "sreda": "воздух",
        "url": "https://airenergyuk.com/wp-content/uploads/CompAir-L30-L132-Brochure.pdf",
        "nadezhnost": "каталог дилера"
    },
    "Ingersoll Rand R90i (50 Гц, Standard)": {
        "tip": "винтовой",
        "proizvoditel": "Ingersoll Rand",
        "podacha": "16.71 м³/мин",
        "davlenie": "14 бар изб",
        "davlenie_izb": "",
        "moshchnost": "90 кВт (125 л.с.)",
        "sreda": "воздух",
        "url": "http://ingersollrand.jp/pdf/air/air_catalog_08.pdf",
        "nadezhnost": "сайт производителя"
    },
    "Ingersoll Rand R110i (50 Гц, Standard)": {
        "tip": "винтовой",
        "proizvoditel": "Ingersoll Rand",
        "podacha": "20.76 м³/мин",
        "davlenie": "14 бар изб",
        "davlenie_izb": "",
        "moshchnost": "110 кВт (150 л.с.)",
        "sreda": "воздух",
        "url": "http://ingersollrand.jp/pdf/air/air_catalog_08.pdf",
        "nadezhnost": "сайт производителя"
    },
    "Ingersoll Rand R132i (50 Гц, Standard)": {
        "tip": "винтовой",
        "proizvoditel": "Ingersoll Rand",
        "podacha": "25.20 м³/мин",
        "davlenie": "14 бар изб",
        "davlenie_izb": "",
        "moshchnost": "132 кВт (175 л.с.)",
        "sreda": "воздух",
        "url": "http://ingersollrand.jp/pdf/air/air_catalog_08.pdf",
        "nadezhnost": "сайт производителя"
    },
    "Ingersoll Rand R160i (50 Гц, Standard)": {
        "tip": "винтовой",
        "proizvoditel": "Ingersoll Rand",
        "podacha": "29.45 м³/мин",
        "davlenie": "14 бар изб",
        "davlenie_izb": "",
        "moshchnost": "160 кВт (200 л.с.)",
        "sreda": "воздух",
        "url": "http://ingersollrand.jp/pdf/air/air_catalog_08.pdf",
        "nadezhnost": "сайт производителя"
    }
}


def _po_pasportu(марка):
    """Точное совпадение марки с паспортной таблицей, с запасом на хвосты
    исполнения: «ТВ-300-1,6-О2.У1» и «ТВ-300-1,6» это одна машина, а вот
    «ТВ-300» без давления — уже не обязательно она, и такое не берём."""
    м = re.sub(r'\s+', ' ', (марка or '').strip()).upper().replace('Ё', 'Е')
    for ключ, з in ПАСПОРТ.items():
        к = ключ.upper().replace('Ё', 'Е')
        if м == к or м.startswith(к + '-') or м.startswith(к + ' ') or к.startswith(м + '-'):
            return dict(з, marka=ключ)
    return None


def razobrat(марка: str) -> dict | None:
    """Характеристики машины: сначала паспорт, потом обозначение."""
    м = (марка or '').strip()
    if len(м) < 2 or len(м) > 40 or _НЕ_МАШИНА.match(м):
        return None

    # ПАСПОРТ ВПЕРЕДИ ОБОЗНАЧЕНИЯ. Обратный порядок и был ошибкой: разбор
    # обозначения всегда что-то возвращает и выглядит увереннее паспорта.
    п = _po_pasportu(м)
    if п:
        return {'marka': м, 'tip': п['tip'],
                'podacha': п['podacha'],
                'davlenie': п['davlenie'] + (
                    f" (изб. {п['davlenie_izb']})" if п.get('davlenie_izb') else ''),
                'seriya': п.get('proizvoditel') or п['marka'],
                'moshchnost': п.get('moshchnost', ''),
                'sreda': п.get('sreda', ''),
                'otkuda': 'паспорт производителя',
                'ssylka': п.get('url', ''),
                'nadezhnost': п.get('nadezhnost', ''),
                'nash_profil': 'центроб' in п['tip'] or 'воздуходувк' in п['tip']}
    for правило, разбор in _СЕМЕЙСТВА:
        сов = правило.match(м)
        if сов:
            тип, подача, давление, серия = разбор(сов)
            return {'marka': м, 'tip': тип, 'podacha': подача,
                    'davlenie': давление, 'seriya': серия,
                    'moshchnost': '', 'sreda': '',
                    # честно говорим, что это ПРОЧТЕНИЕ ОБОЗНАЧЕНИЯ, а не
                    # паспорт: у ТВ и К-350 такое прочтение уже соврало
                    'otkuda': 'прочтение обозначения, паспорт не найден',
                    'ssylka': '', 'nadezhnost': '',
                    'nash_profil': 'центроб' in тип or 'воздуходувк' in тип}
    return None


def po_faktam(facts: list[dict]) -> list[dict]:
    """Уникальные разобранные машины компании, самые частые первыми."""
    счёт: dict[str, int] = {}
    разбор: dict[str, dict] = {}
    for f in facts or []:
        if f.get('rejected'):
            continue
        # Запятая — и разделитель марок, и десятичная точка в давлении.
        # Первый прогон разрезал «ТВ-300-1,6» на «ТВ-300-1» и «6», и карточка
        # показывала давление 1 вместо 1,6. Режем по запятой, только если
        # сразу за ней НЕ цифра.
        for кусок in re.split(r'[|;]|,(?!\d)', str(f.get('model') or '')):
            к = кусок.strip()
            если = razobrat(к)
            if не_пусто(если):
                ключ = если['marka'].upper()
                счёт[ключ] = счёт.get(ключ, 0) + 1
                разбор.setdefault(ключ, если)
    вывод = []
    for ключ, n in sorted(счёт.items(), key=lambda x: -x[1]):
        з = dict(разбор[ключ])
        з['vstrechaetsya'] = n
        вывод.append(з)
    return вывод


def не_пусто(x) -> bool:
    return bool(x)
