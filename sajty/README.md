# Статьи для десяти сайтов: та же вёрстка, что у ac-kompressor.ru

54 текста из архива «дорогие плановые», переведённые из классовой вёрстки
в инлайновую. Вставлять целиком в поле «Описание» раздела. Стилей от сайта
не требуют, `stili-dlya-sayta.css` из архива класть не нужно.

## ГЛАВНОЕ ПРИ ВСТАВКЕ

У поля «Описание» раздела в Битриксе есть переключатель **текст / html**.
Он должен стоять на **html**. Если оставить «текст», Битрикс экранирует все
теги и на странице будет видна разметка - ровно это случилось с
`ac-kompressor.ru/catalog/mks/`. Это первое, что стоит проверить после
сохранения каждого раздела.

## Что где

| Сайт | Форма, которая открывается | Надпись на кнопке |
|---|---|---|
| abac-kompressor.ru | «Запросить коммерческое предложение» (7/40ef1t) | Получить КП |
| ac-kompressor.ru | «Запросить коммерческое предложение» (7/40ef1t) | Получить КП |
| berg-kompressor.ru | «Заказать обратный звонок» (164/7higok) | Оставить заявку |
| crossair-compressor.ru | «Запросить коммерческое предложение» (173/5pc41r) | Получить КП |
| dali-kompressor.ru | «Запросить коммерческое предложение» (7/40ef1t) | Получить КП |
| ekomak-kompressor.com | «Заказать обратный звонок» (8/cosa3e) | Оставить заявку |
| enger-air.ru | «Запросить коммерческое предложение» (160/lzzwog) | Получить КП |
| fini-compressor.com | «Заказать обратный звонок» (200/pkoq43) | Оставить заявку |
| ironmac-compressor.com | «Заказать обратный звонок» (193/h77r1g) | Оставить заявку |
| kraftmann-kompressor.com | «Запросить коммерческое предложение» (7/40ef1t) | Получить КП |
| remeza-kompressor.ru | «Запросить коммерческое предложение» (7/40ef1t) | Получить КП |
| zif-kompressor.ru | «Запросить коммерческое предложение» (7/40ef1t) | Получить КП |

У каждого сайта берётся его собственная форма Битрикс24. Формы «Запросить КП»
нет только у четырёх сайтов - там открывается их форма обратного звонка
(Имя, Телефон, Комментарий), и надпись на кнопке подобрана под неё.

## Как устроена кнопка

В конец статьи вставлен **загрузчик формы Битрикс24** и скрытый `span`, к
которому Битрикс24 привязывает эту форму. Кнопки в тексте нажимают этот span -
попап открывается прямо на странице, перехода никуда нет.

Форма вставляется в саму статью намеренно: на разделах без товаров у сайтов
своих форм на странице нет (проверено на kraftmann и remeza), и кнопка,
рассчитанная на чужую кнопку, увела бы посетителя на страницу контактов.

Запасные пути, если загрузчик не отработал: любая другая форма Битрикс24,
которая нашлась на странице, и только через 6 секунд - переход на страницу
заявки. Кнопка при этом остаётся обычной ссылкой, поэтому работает и с
отключённым JS.

Скрытый якорь - именно `span`, а не ссылка: клик по ссылке с адресом уводил
страницу раньше, чем успевал открыться попап. На этом я споткнулся при
проверке, поэтому отмечаю.

## Чем вёрстка отличается от ac-kompressor.ru

- **Цвета нейтральные.** У сайтов разные темы, свой акцент подрался бы с
  любой из них. Плашка призыва - серая заливка `rgba(0,0,0,.055)` и полоса
  слева цветом текста (`currentColor`), таблицы и оглавление в серых рамках.
- **Кнопка в родном классе сайта** (`btn btn-primary`, `bxr-color-button`,
  `enger-btn` и т.д.) - цвет берёт из темы. Инлайном добавлены три правила:
  не растягиваться во всю ширину, не подчёркиваться, не съезжать по вертикали.
- **Отступ якорных заголовков под липкую шапку** замерен в браузере на каждом
  сайте: berg 130 px, enger 60 px, остальные 90 px.

Всё остальное как на ac-kompressor.ru: блок «Содержание страницы» с кнопкой
справа (она держит кнопку на первом экране), плашки призыва с заголовком и
подписью, прокручиваемые таблицы, FAQ через `details/summary`, серый хвост.

## Что скрипт правит помимо вёрстки

- Надписи кнопок сведены к «Получить КП» (в исходниках были «Получить
  расчёт», «Подобрать оборудование», «Оставить заявку»).
- Оглавление собирается по всем заголовкам h2, а не по тем, что были в
  исходнике.
- `enger-air.ru/generatory-azota` и `generatory-kisloroda`: в исходниках у
  заголовков не было якорей и не было оглавления - якоря сделаны
  транслитерацией, оглавление собрано, к блоку вопросов дописан заголовок
  «Частые вопросы» (его тоже не было).
- `fini-compressor.com/kislorodnaya-stanciya-modulnaya`: в исходнике нет ни
  одного призыва, поэтому в статье только кнопка в оглавлении. Если нужны
  плашки по тексту - скажите, добавлю.

## Куда какой файл

### abac-kompressor.ru

- `azotnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://abac-kompressor.ru/catalog/azotnaya-stanciya/
- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://abac-kompressor.ru/catalog/azotnaya-stanciya-modulnaya/
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://abac-kompressor.ru/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://abac-kompressor.ru/catalog/kislorodnaya-stanciya-modulnaya/
- `kompressornaya-stanciya.html` ✓ -> СОЗДАТЬ: https://abac-kompressor.ru/catalog/kompressornaya-stanciya/
- `mks.html` ✓ -> СОЗДАТЬ: https://abac-kompressor.ru/catalog/mks/

### berg-kompressor.ru

- `azotnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://berg-kompressor.ru/catalog/azotnaya-stanciya/
- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://berg-kompressor.ru/catalog/azotnaya-stanciya-modulnaya/
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://berg-kompressor.ru/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://berg-kompressor.ru/catalog/kislorodnaya-stanciya-modulnaya/
- `mks.html` ✓ -> СОЗДАТЬ: https://berg-kompressor.ru/catalog/mks/  адрес занят страницей berg-kompressor--kompressornaya-stanciya

### crossair-compressor.ru

- `azotnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://crossair-compressor.ru/catalog/azotnaya-stanciya/
- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://crossair-compressor.ru/catalog/azotnaya-stanciya-modulnaya/
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://crossair-compressor.ru/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://crossair-compressor.ru/catalog/kislorodnaya-stanciya-modulnaya/
- `kompressornaya-stanciya.html` ✓ -> СОЗДАТЬ: https://crossair-compressor.ru/catalog/kompressornaya-stanciya/
- `mks.html` ✓ -> СОЗДАТЬ: https://crossair-compressor.ru/catalog/mks/

### dali-kompressor.ru

- `azotnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://dali-kompressor.ru/catalog/azotnaya-stanciya/
- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://dali-kompressor.ru/catalog/azotnaya-stanciya-modulnaya/
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://dali-kompressor.ru/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://dali-kompressor.ru/catalog/kislorodnaya-stanciya-modulnaya/
- `kompressornaya-stanciya.html` ✓ -> СОЗДАТЬ: https://dali-kompressor.ru/catalog/kompressornaya-stanciya/
- `mks.html` ✓ -> СОЗДАТЬ: https://dali-kompressor.ru/catalog/mks/

### ekomak-kompressor.com

- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://ekomak-kompressor.com/catalog/azotnaya-stanciya-modulnaya/  адрес занят страницей ekomak-kompressor--azotnaya-stanciya
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://ekomak-kompressor.com/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://ekomak-kompressor.com/catalog/kislorodnaya-stanciya-modulnaya/
- `kompressornaya-stanciya.html` ✓ -> СОЗДАТЬ: https://ekomak-kompressor.com/catalog/kompressornaya-stanciya/
- `mks.html` ✓ -> СОЗДАТЬ: https://ekomak-kompressor.com/catalog/mks/

### enger-air.ru

- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://enger-air.ru/catalog/azotnaya-stanciya-modulnaya/  адрес занят страницей enger-air--azotnaya-stanciya
- `generatory-azota.html` ✓ -> СОЗДАТЬ: https://enger-air.ru/catalog/generatory-azota/  адрес занят страницей enger-air--azotnaya-stanciya
- `generatory-kisloroda.html` ✓ -> СОЗДАТЬ: https://enger-air.ru/catalog/generatory-kisloroda/  адрес занят страницей enger-air--kislorodnaya-stanciya
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://enger-air.ru/catalog/kislorodnaya-stanciya-modulnaya/  адрес занят страницей enger-air--kislorodnaya-stanciya
- `mks.html` ✓ -> СОЗДАТЬ новый раздел (адрес https://enger-air.ru/catalog/mks/ занят)  адрес занят страницей enger-air--kompressornaya-stanciya

### fini-compressor.com

- `azotnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://fini-compressor.com/catalog/azotnaya-stanciya/
- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://fini-compressor.com/catalog/azotnaya-stanciya-modulnaya/
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://fini-compressor.com/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://fini-compressor.com/catalog/kislorodnaya-stanciya-modulnaya/
- `kompressornaya-stanciya.html` ✓ -> СОЗДАТЬ: https://fini-compressor.com/catalog/kompressornaya-stanciya/
- `mks.html` ✓ -> СОЗДАТЬ: https://fini-compressor.com/catalog/mks/

### ironmac-compressor.com

- `azotnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://ironmac-compressor.com/catalog/azotnaya-stanciya/
- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://ironmac-compressor.com/catalog/azotnaya-stanciya-modulnaya/
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://ironmac-compressor.com/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://ironmac-compressor.com/catalog/kislorodnaya-stanciya-modulnaya/
- `kompressornaya-stanciya.html` ✓ -> СОЗДАТЬ: https://ironmac-compressor.com/catalog/kompressornaya-stanciya/

### remeza-kompressor.ru

- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://remeza-kompressor.ru/catalog/azotnaya-stanciya-modulnaya/  адрес занят страницей remeza-kompressor--azotnaya-stanciya
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://remeza-kompressor.ru/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://remeza-kompressor.ru/catalog/kislorodnaya-stanciya-modulnaya/
- `mks.html` ✓ -> СОЗДАТЬ: https://remeza-kompressor.ru/catalog/mks/  адрес занят страницей remeza-kompressor--kompressornaya-stanciya

### zif-kompressor.ru

- `azotnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://zif-kompressor.ru/catalog/azotnaya-stanciya/
- `azotnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://zif-kompressor.ru/catalog/azotnaya-stanciya-modulnaya/
- `kislorodnaya-stanciya.html` ✓ -> СОЗДАТЬ: https://zif-kompressor.ru/catalog/kislorodnaya-stanciya/
- `kislorodnaya-stanciya-modulnaya.html` ✓ -> СОЗДАТЬ: https://zif-kompressor.ru/catalog/kislorodnaya-stanciya-modulnaya/
- `kompressornaya-stanciya.html` ✓ -> СОЗДАТЬ: https://zif-kompressor.ru/catalog/kompressornaya-stanciya/
- `mks.html` ✓ -> СОЗДАТЬ: https://zif-kompressor.ru/catalog/mks/

## Вторая партия: тексты для существующих разделов (49 статей)

Архив «есть категория». Разделы на сайтах уже созданы, тексты в них не
размещены - проверил все 49 адресов, ни на одном ни одного фрагмента этих
статей нет. Свёрстаны тем же скриптом.

Добавился двенадцатый сайт - `kraftmann-kompressor.com` (11 статей). Форм
Битрикс24 на нём нет вообще, поэтому кнопка там обычная ссылка на
`/contacts/`. Пять статей для `ac-kompressor.ru` лежат не здесь, а в
`ac-kompressor/statyi/` - вместе с остальными его текстами и в его
оформлении (белая кнопка, синяя полоса у плашек).

**Разделы уже существующие, у части из них есть своё описание** - статья его
заменит. Точно проверено, что описание непустое, у пяти адресов: три раздела
crossair (340-530 знаков) и два ironmac (по 2,5 тысячи знаков). На остальных
сайтах шаблон не помечает блок описания классом, снаружи не посмотреть -
увидите в админке, поле будет непустым.

### Куда какой файл (вторая партия)

### abac-kompressor.ru

- `sajty/abac-kompressor.ru/filtry-magistralnye.html` -> https://abac-kompressor.ru/catalog/filtry-magistralnye-abac/  (раздел нашёлся под другим именем)
- `sajty/abac-kompressor.ru/osushiteli.html` -> https://abac-kompressor.ru/catalog/ochistka-szhatogo-vozdukha/  (раздел нашёлся под другим именем)
- `sajty/abac-kompressor.ru/tsiklonnye-separatory.html` -> https://abac-kompressor.ru/catalog/maslovlagootdeliteli-abac/  (раздел нашёлся под другим именем)
- `sajty/abac-kompressor.ru/vintovye-kompressory.html` -> https://abac-kompressor.ru/catalog/vintovye-kompressory/

### ac-kompressor.ru

- `ac-kompressor/statyi/dizelnye-kompressory.html` -> https://ac-kompressor.ru/catalog/dizelnye-kompressory-do-14-bar/  (раздел нашёлся под другим именем)
- `ac-kompressor/statyi/osushiteli.html` -> https://ac-kompressor.ru/catalog/adsorbtsionnye-osushiteli-vozdukha/  (раздел нашёлся под другим именем)
- `ac-kompressor/statyi/porshnevye-kompressory.html` -> https://ac-kompressor.ru/catalog/porshnevye-kompressory/
- `ac-kompressor/statyi/spiralnye-kompressory.html` -> https://ac-kompressor.ru/catalog/spiralnye-bezmaslyanye-kompressory/  (раздел нашёлся под другим именем)
- `ac-kompressor/statyi/vintovye-kompressory.html` -> https://ac-kompressor.ru/catalog/vintovye-kompressory/

### berg-kompressor.ru

- `sajty/berg-kompressor.ru/filtry-magistralnye.html` -> https://berg-kompressor.ru/catalog/vozdukhopodgotovka/magistralnye-filtry/  (раздел нашёлся под другим именем)
- `sajty/berg-kompressor.ru/kompressornaya-stanciya.html` -> https://berg-kompressor.ru/catalog/modulnye-kompressornye-stantsii/  (раздел нашёлся под другим именем)
- `sajty/berg-kompressor.ru/osushiteli.html` -> https://berg-kompressor.ru/catalog/osushiteli/
- `sajty/berg-kompressor.ru/tsiklonnye-separatory.html` -> https://berg-kompressor.ru/catalog/vozdukhopodgotovka/tsiklonnye-separatory/  (раздел нашёлся под другим именем)
- `sajty/berg-kompressor.ru/vintovye-kompressory.html` -> https://berg-kompressor.ru/catalog/vintovye-kompressory/

### crossair-compressor.ru

- `sajty/crossair-compressor.ru/dizelnye-kompressory.html` -> https://crossair-compressor.ru/catalog/dizelnye-kompressory/
- `sajty/crossair-compressor.ru/osushiteli.html` -> https://crossair-compressor.ru/catalog/vintovye-kompressory/na-resivere-s-osushitelem/  (раздел нашёлся под другим именем)
- `sajty/crossair-compressor.ru/vintovye-kompressory.html` -> https://crossair-compressor.ru/catalog/vintovye-kompressory/

### dali-kompressor.ru

- `sajty/dali-kompressor.ru/osushiteli.html` -> https://dali-kompressor.ru/catalog/osushiteli/
- `sajty/dali-kompressor.ru/vintovye-kompressory.html` -> https://dali-kompressor.ru/catalog/vintovye-kompressory/

### ekomak-kompressor.com

- `sajty/ekomak-kompressor.com/azotnaya-stanciya.html` -> https://ekomak-kompressor.com/catalog/generatory-azota-ppng/  (раздел нашёлся под другим именем)
- `sajty/ekomak-kompressor.com/osushiteli.html` -> https://ekomak-kompressor.com/catalog/osushiteli/
- `sajty/ekomak-kompressor.com/spiralnye-kompressory.html` -> https://ekomak-kompressor.com/catalog/bezmaslyanye/spiralnye/  (раздел нашёлся под другим именем)
- `sajty/ekomak-kompressor.com/vintovye-kompressory.html` -> https://ekomak-kompressor.com/catalog/bezmaslyanye/vintovye/  (раздел нашёлся под другим именем)

### enger-air.ru

- `sajty/enger-air.ru/kompressornaya-stanciya.html` -> https://enger-air.ru/catalog/mks/  (раздел нашёлся под другим именем)

### fini-compressor.com

- `sajty/fini-compressor.com/vintovye-kompressory.html` -> https://fini-compressor.com/catalog/vintovye-kompressory/

### ironmac-compressor.com

- `sajty/ironmac-compressor.com/filtry-magistralnye.html` -> https://ironmac-compressor.com/catalog/filtry-magistralnye/
- `sajty/ironmac-compressor.com/mks.html` -> https://ironmac-compressor.com/catalog/blochnye-stantsii/  (раздел нашёлся под другим именем)
- `sajty/ironmac-compressor.com/osushiteli.html` -> https://ironmac-compressor.com/catalog/refrizheratornye-osushiteli-vozdukha/  (раздел нашёлся под другим именем)
- `sajty/ironmac-compressor.com/vintovye-kompressory.html` -> https://ironmac-compressor.com/catalog/vintovye-kompressory/

### kraftmann-kompressor.com

- `sajty/kraftmann-kompressor.com/azotnaya-stanciya.html` -> https://kraftmann-kompressor.com/catalog/azotnaya-stanciya/
- `sajty/kraftmann-kompressor.com/azotnaya-stanciya-modulnaya.html` -> https://kraftmann-kompressor.com/catalog/azotnaya-stanciya-modulnaya/
- `sajty/kraftmann-kompressor.com/dozhimnye-kompressory.html` -> https://kraftmann-kompressor.com/catalog/dozhimnye-kompressory/
- `sajty/kraftmann-kompressor.com/filtry-magistralnye.html` -> https://kraftmann-kompressor.com/catalog/filtry-magistralnye/
- `sajty/kraftmann-kompressor.com/kislorodnaya-stanciya.html` -> https://kraftmann-kompressor.com/catalog/kislorodnaya-stanciya/
- `sajty/kraftmann-kompressor.com/kislorodnaya-stanciya-modulnaya.html` -> https://kraftmann-kompressor.com/catalog/kislorodnaya-stanciya-modulnaya/
- `sajty/kraftmann-kompressor.com/kompressornaya-stanciya.html` -> https://kraftmann-kompressor.com/catalog/kompressornaya-stanciya/
- `sajty/kraftmann-kompressor.com/mks.html` -> https://kraftmann-kompressor.com/catalog/mks/
- `sajty/kraftmann-kompressor.com/osushiteli.html` -> https://kraftmann-kompressor.com/catalog/osushiteli/
- `sajty/kraftmann-kompressor.com/tsiklonnye-separatory.html` -> https://kraftmann-kompressor.com/catalog/tsiklonnye-separatory/
- `sajty/kraftmann-kompressor.com/vintovye-kompressory.html` -> https://kraftmann-kompressor.com/catalog/vintovye-kompressory/

### remeza-kompressor.ru

- `sajty/remeza-kompressor.ru/azotnaya-stanciya.html` -> https://remeza-kompressor.ru/catalog/generatori-azota/  (раздел нашёлся под другим именем)
- `sajty/remeza-kompressor.ru/filtry-magistralnye.html` -> https://remeza-kompressor.ru/catalog/ochistka-szhatogo-vozdukha/filtry-magistralnye/  (раздел нашёлся под другим именем)
- `sajty/remeza-kompressor.ru/kompressornaya-stanciya.html` -> https://remeza-kompressor.ru/catalog/modulnye-kompressornye-stantsii/  (раздел нашёлся под другим именем)
- `sajty/remeza-kompressor.ru/osushiteli.html` -> https://remeza-kompressor.ru/catalog/ochistka-szhatogo-vozdukha/  (раздел нашёлся под другим именем)
- `sajty/remeza-kompressor.ru/resivery.html` -> https://remeza-kompressor.ru/catalog/vozdushnye-resivery/  (раздел нашёлся под другим именем)
- `sajty/remeza-kompressor.ru/tsiklonnye-separatory.html` -> https://remeza-kompressor.ru/catalog/ochistka-szhatogo-vozdukha/maslovlagootdeliteli/  (раздел нашёлся под другим именем)
- `sajty/remeza-kompressor.ru/vintovye-kompressory.html` -> https://remeza-kompressor.ru/catalog/kompressory/vintovye/  (раздел нашёлся под другим именем)

### zif-kompressor.ru

- `sajty/zif-kompressor.ru/osushiteli.html` -> https://zif-kompressor.ru/catalog/osushiteli/
- `sajty/zif-kompressor.ru/vintovye-kompressory.html` -> https://zif-kompressor.ru/catalog/vintovye-kompressory/

## Что поправлено в первой партии

- `enger-air.ru/generatory-azota.html` и `generatory-kisloroda.html`: в стиль
  заголовка «Частые вопросы» попадала незаполненная подстановка
  `scroll-margin-top:{}px`, и закрывающий тег аккордеона стоял не на месте.
  Оба файла пересобраны, если уже вставляли - вставьте заново.
- `abac-kompressor.ru/mks.html`: подписи к таблицам (`caption`) получили
  стиль, раньше шли по центру мелким.

Остальные 51 файл первой партии не изменились.

## Запуск

```
python3 verstka.py ishodniki/<домен>/*.html
```

Результат кладётся в папку домена. Реестр сайтов (класс кнопки, адрес
заявки, форма, высота шапки) - в начале `verstka.py`.

## Проверено

Chromium (Playwright), живые сайты. По одной статье на каждый из десяти
сайтов вставлено в реальную страницу `/catalog/` и проверено:

- заголовки, таблицы, FAQ и оглавление на месте, следов классовой вёрстки нет;
- ничего не выходит за контейнер, страница не тянется вбок;
- кнопка отрисована в цветах темы сайта и не растянута во всю ширину;
- на crossair, dali и zif клик открывает попап «Запросить коммерческое
  предложение», адрес страницы не меняется, прокрутка не прыгает наверх
  (кнопки этих сайтов - `<a href="#">`, поэтому в обработчике стоит возврат
  прокрутки);
- структурная проверка всех 54 файлов: число пунктов оглавления совпадает с
  числом заголовков, битых якорей нет, теги сбалансированы.
