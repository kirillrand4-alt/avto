# Реестр разделов каталога: итог этапа 0

Старому реестру на 788 разделов не доверяли, собрали с нуля. Ниже - что получилось
и чем это подтверждено.

## Сколько разделов на самом деле

| Показатель | Значение |
|---|---:|
| URL разделов найдено обходом | 838 |
| из них дубли-редиректы (canonical ведёт на другой адрес) | 56 |
| **канонических разделов** | **782** |

Обход замкнулся: вторая волна не нашла ни одного нового адреса.

Дубли - это старые фильтровые пути, редиректящие на новые короткие:
`/po-davleniyu/12-bar/` на `/kompressory-12-bar/`, `/po-obemu-resivera/250-l/` на
`/kompressory-s-resiverom-250-l/`, `/po-tipu-smazki/bezmaslyanye_1/` на
`/kompressory-bezmaslyanye/`. Ещё 12 адресов схлопываются прямо в корень
`/catalog/vozdushnye-kompressory/`.

## Покрытие статьями

| Состояние | Разделов |
|---|---:|
| наша статья (байлайн «Руспром») | 738 |
| чужой или старый текст | 35 |
| **статьи нет вовсе** | **9** |

Суммарно у 44 проблемных разделов **11 525 показов** в двух ПС за месяц выгрузки.

### 9 разделов без статьи

| URL | Показы | Клики |
|---|---:|---:|
| `/catalog/vozdushnye-kompressory/` | 3 047 | 15 |
| `/catalog/` | 414 | 14 |
| `/catalog/truby/` | 20 | 0 |
| `/catalog/raskhodomery-i-datchiki/difmanometry/` | 0 | 0 |
| `/catalog/vozdushnye-kompressory/po-tipu/vintovye/odnostupenchatye/` | 0 | 0 |
| `/catalog/vozdushnye-kompressory/po-tipu/vintovye/peredvizhnye/dizelnye_1/` | 0 | 0 |
| `/catalog/vozdushnye-kompressory/belarus/` | 0 | 0 |
| `/catalog/vozdushnye-kompressory/po-tipu/vozdukhoduvki/rotornye/` | 0 | 0 |
| `/catalog/vozdushnye-kompressory/po-tipu/vozdukhoduvki/vintovye_2/` | 0 | 0 |

### 35 разделов с чужим текстом - это огрызки, а не статьи

У большинства 1-4 заголовка `<h2>` против 5-6 у нормальной статьи, байлайна нет.
При этом трафик у них живой:

| URL | Показы | `<h2>` |
|---|---:|---:|
| `/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-tsekha/` | 1 594 | 3 |
| `/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-lazernoy-rezki/` | 1 194 | 3 |
| `/catalog/vozdushnye-kompressory/po-komplektatsii/s-resiverom-i-osushitelem/` | 1 130 | 3 |
| `/catalog/generatsiya-gazov/generatory-azota/` | 826 | 2 |
| `/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-peskostruya/` | 717 | 3 |
| `/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-meditsiny/` | 652 | 3 |
| `/catalog/vozdushnye-kompressory/po-tipu/tsentrobezhnye/` | 481 | 2 |
| `/catalog/mks/` | 391 | 12 |

Исключение - `/catalog/mks/` и лендинги азотных и кислородных станций: там полноценные
большие тексты, просто написанные не нашим конвейером.

## Сверка со старым реестром 788

- **61 раздел** есть сейчас, но не было в старом реестре;
- **11 разделов** были в старом, сейчас не нашлись. Проверены поштучно:
  **8 отдают 404** (разделы удалены, а статьи на них были написаны), **3 живы (200), но
  на них нет ни одной входящей ссылки** - страницы-сироты, обход до них не доходит.

Мёртвые: `.../po-tipu/vozdukhoduvki/{airpol,dalgakiran,dali,enger,remeza,sas,zega}/`
и `.../bezmaslyanye_1/porshnevye/fiac/`.
Сироты: `.../bezmaslyanye_1/porshnevye/{atlas-copco,ekomak,remeza}/`.

Плюс `/catalog/vozdushnye-kompressory/voltage/` отдаёт 404, хотя подразделы под ним живы.

## Почему экспорт Screaming Frog не годится как знаменатель

В экспорте 147 476 строк и 74 колонки, но по разделам он пустой:

- **701 из 838 разделов отдали лягушке 403**;
- все 709 ошибок 403 во всём экспорте приходятся ровно на страницы разделов
  (`vozdushnye-kompressory` 555, `podgotovka-vozdukha` 59, `osushiteli` 52,
  `zapasnye-chasti` 30, `resivery` 12), карточки товаров обошлись штатно;
- 68 разделов помечены как 404/301, но живьём все 68 отдают 200.

Проверено, что дело не в юзер-агенте: сейчас 200 получают и Screaming Frog, и Chrome,
и YandexBot, и Googlebot. Значит на том обходе сработал **троттлинг по скорости**, и
страницы разделов из выгрузки просто выпали.

**Отдельная находка для владельца:** сайт отвечает 403 на быстрый обход, причём бьёт
именно по категориям. Для повторного обхода лягушкой надо снизить число потоков и
поставить задержку, иначе выгрузка снова будет без разделов.

Экспорт при этом полезен для другого: Word Count, near-duplicates, семантическое
сходство и входящие ссылки по карточкам товаров - всё это лежит в
`audit/frog-all.csv.gz`.

## Мусор в sitemap

167 URL в `sitemap.xml` ведут на мёртвые демо-разделы шаблона Aspro
(`bizhuteriya`, `chasy`, `elektronika`, `igrushki`, `mebel`, `obuv`, `odezhda`,
`osveshchenie`, `santekhnika`, `sport`). Все отдают 404. В экспорте лягушки таких
битых адресов **5 898**.
