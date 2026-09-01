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

| Сайт | Статей | Кнопка «Получить КП» | Какие формы Битрикс24 есть на сайте |
|---|---|---|---|
| `abac-kompressor.ru` | 6 | ссылка на страницу заявки | только «Заказать обратный звонок» (8/cosa3e) |
| `berg-kompressor.ru` | 5 | ссылка на страницу заявки | «Заказать обратный звонок» (164), «Куда вам отправить прайс?» (166) |
| `crossair-compressor.ru` | 6 | открывает форму click/173/5pc41r | «Запросить коммерческое предложение» (173), звонок (175) |
| `dali-kompressor.ru` | 6 | открывает форму click/7/40ef1t | «Запросить КП» (7), звонок (8), прайс (33) |
| `ekomak-kompressor.com` | 5 | ссылка на страницу заявки | только звонок, и тот вставлен как inline, кнопки нет |
| `enger-air.ru` | 5 | ссылка на страницу заявки | на внутренних страницах только звонок (158); форма КП (160) стоит лишь на главной |
| `fini-compressor.com` | 6 | ссылка на страницу заявки | только «Заказать обратный звонок» (200) |
| `ironmac-compressor.com` | 5 | ссылка на страницу заявки | звонок (193), «Напишите нам сообщение» (194), прайс (196) |
| `remeza-kompressor.ru` | 4 | ссылка на страницу заявки | только «Заказать обратный звонок» (8/cosa3e) |
| `zif-kompressor.ru` | 6 | открывает форму click/7/40ef1t | «Запросить КП» (7), звонок (8), «Подбор компрессора» (9) |

Кнопка везде остаётся ссылкой на страницу заявки, поэтому работает и без JS.
На трёх сайтах, где в Битрикс24 нашлась форма «Запросить коммерческое
предложение», к статье дописан обработчик: клик открывает попап этой формы
вместо перехода на страницу. На остальных семи подходящей формы нет - есть
только «Заказать обратный звонок» или «Куда вам отправить прайс», вешать на
них кнопку «Получить КП» неправильно, поэтому там обычная ссылка. Если нужно
иначе (например, кнопка открывает обратный звонок), это одна строка в
реестре `verstka.py`.

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
