# Где статьи стоят на самом деле (проверка 10 сентября 2026)

Проверено 553 адреса: разделы из карт сайтов и со страниц каталога плюс перебор
по названиям, которыми пользуются соседние сайты (azotnye-stantsii, mks,
modulnaya-kislorodnaya-stantsiya и так далее). Каждая найденная страница
сверялась с текстом статьи по трём и более фрагментам, версия определялась по
разметке. Полная таблица по каждой статье - в `GDE-STOYAT.csv`.

## Сводка

| Сайт | новая версия | предыдущая версия | исходник из архива | текстом, вёрстка срезана | в коде есть, но не отрисована | не размещена |
|---|---|---|---|---|---|---|
| abac-kompressor.ru | 4 | 3 | 3 | 0 | 0 | 0 |
| ac-kompressor.ru | 1 | 6 | 0 | 0 | 0 | 5 |
| berg-kompressor.ru | 3 | 0 | 0 | 0 | 0 | 7 |
| crossair-compressor.ru | 0 | 1 | 0 | 0 | 5 | 3 |
| dali-kompressor.ru | 0 | 2 | 0 | 4 | 0 | 2 |
| ekomak-kompressor.com | 0 | 1 | 0 | 0 | 0 | 8 |
| enger-air.ru | 0 | 0 | 0 | 0 | 0 | 6 |
| fini-compressor.com | 0 | 0 | 0 | 0 | 0 | 7 |
| ironmac-compressor.com | 6 | 0 | 0 | 0 | 0 | 3 |
| kraftmann-kompressor.com | 0 | 0 | 0 | 0 | 0 | 11 |
| remeza-kompressor.ru | 5 | 0 | 0 | 0 | 0 | 6 |
| zif-kompressor.ru | 6 | 0 | 0 | 0 | 0 | 2 |

## Что значат состояния

- **новая версия** - файл из последней поставки: загрузчик формы внутри статьи, кнопка открывает попап;
- **предыдущая версия** - моя вёрстка, но кнопка рассчитана на кнопку сайта. Работает там, где такая кнопка есть; лучше перевставить;
- **исходник из архива** - вставлен файл из архива, а не сконвертированный: призывы легли обычными абзацами;
- **текстом, вёрстка срезана** - шаблон раздела выводит описание через strip_tags (все четыре случая на dali, разбор в PROVERKA-ZHIVYH.md);
- **в коде есть, но не отрисована** - текст лежит в исходном коде страницы, но посетителю не показывается (все пять случаев на crossair);
- **не размещена** - статьи на сайте нет.

## Что нужно перевставить

**abac-kompressor.ru**
- `azotnaya-stanciya-modulnaya.html` -> https://abac-kompressor.ru/catalog/modulnye-azotnye-stantsii/  (исходник из архива)
- `azotnaya-stanciya.html` -> https://abac-kompressor.ru/catalog/azotnye-stantsii/  (предыдущая версия)
- `kislorodnaya-stanciya-modulnaya.html` -> https://abac-kompressor.ru/catalog/modulnye-kislorodnye-stantsii/  (исходник из архива)
- `kislorodnaya-stanciya.html` -> https://abac-kompressor.ru/catalog/kislorodnye-stantsii/  (исходник из архива)
- `kompressornaya-stanciya.html` -> https://abac-kompressor.ru/catalog/kompressornaya-stantsiya/  (предыдущая версия)
- `mks.html` -> https://abac-kompressor.ru/catalog/modulnye-kompressornye-stantsii/  (предыдущая версия)

**ac-kompressor.ru**
- `azotnaya-stanciya-modulnaya.html` -> https://ac-kompressor.ru/catalog/modulnye-azotnye-stantsii/  (предыдущая версия)
- `azotnaya-stanciya.html` -> https://ac-kompressor.ru/catalog/azotnye-stantsii/  (предыдущая версия)
- `kislorodnaya-stanciya.html` -> https://ac-kompressor.ru/catalog/kislorodnaya-stanciya/  (предыдущая версия)
- `kompressornaya-stanciya.html` -> https://ac-kompressor.ru/catalog/kompressornye-stantsii/  (предыдущая версия)
- `kompressornye-stantsii.html` -> https://ac-kompressor.ru/catalog/kompressornye-stantsii/  (предыдущая версия)
- `mks.html` -> https://ac-kompressor.ru/catalog/mks/  (предыдущая версия)

**crossair-compressor.ru**
- `kompressornaya-stanciya.html` -> https://crossair-compressor.ru/catalog/kompressornye-stantsii/  (предыдущая версия)

**dali-kompressor.ru**
- `kislorodnaya-stanciya-modulnaya.html` -> https://dali-kompressor.ru/catalog/modulnaya-kislorodnaya-stantsiya/  (предыдущая версия)
- `kompressornaya-stanciya.html` -> https://dali-kompressor.ru/catalog/kompressornye-stantsii/  (предыдущая версия)

**ekomak-kompressor.com**
- `kompressornaya-stanciya.html` -> https://ekomak-kompressor.com/catalog/kompressornye-stantsii/  (предыдущая версия)

## Не размещены

- **ac-kompressor.ru** (5): dizelnye-kompressory, kislorodnaya-stanciya-modulnaya, osushiteli, porshnevye-kompressory, spiralnye-kompressory
- **berg-kompressor.ru** (7): azotnaya-stanciya-modulnaya, filtry-magistralnye, kislorodnaya-stanciya-modulnaya, mks, osushiteli, tsiklonnye-separatory, vintovye-kompressory
- **crossair-compressor.ru** (3): dizelnye-kompressory, osushiteli, vintovye-kompressory
- **dali-kompressor.ru** (2): osushiteli, vintovye-kompressory
- **ekomak-kompressor.com** (8): azotnaya-stanciya-modulnaya, azotnaya-stanciya, kislorodnaya-stanciya-modulnaya, kislorodnaya-stanciya, mks, osushiteli, spiralnye-kompressory, vintovye-kompressory
- **enger-air.ru** (6): azotnaya-stanciya-modulnaya, generatory-azota, generatory-kisloroda, kislorodnaya-stanciya-modulnaya, kompressornaya-stanciya, mks
- **fini-compressor.com** (7): azotnaya-stanciya-modulnaya, azotnaya-stanciya, kislorodnaya-stanciya-modulnaya, kislorodnaya-stanciya, kompressornaya-stanciya, mks, vintovye-kompressory
- **ironmac-compressor.com** (3): filtry-magistralnye, osushiteli, vintovye-kompressory
- **kraftmann-kompressor.com** (11): azotnaya-stanciya-modulnaya, azotnaya-stanciya, dozhimnye-kompressory, filtry-magistralnye, kislorodnaya-stanciya-modulnaya, kislorodnaya-stanciya, kompressornaya-stanciya, mks, osushiteli, tsiklonnye-separatory, vintovye-kompressory
- **remeza-kompressor.ru** (6): filtry-magistralnye, mks, osushiteli, resivery, tsiklonnye-separatory, vintovye-kompressory
- **zif-kompressor.ru** (2): osushiteli, vintovye-kompressory
