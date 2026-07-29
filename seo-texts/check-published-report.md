# Проверка публикации 759 текстов на prokompressor.ru

Проверено URL: **759** из 759 (все из `publish/manifest.csv`).
Метод: обход каждого URL с отслеживанием 301/302, затем поиск на конечной
странице трёх предложений-маркеров из `publish/plain/<slug>.html`. Для страниц,
где свой текст не найден, второй проход сопоставляет H2 страницы с индексом
всех 759 текстов (плюс бэкап `gen-orig/`) и определяет, чей текст там лежит.

## Итог

| Результат | Страниц |
|---|---|
| Свой текст на месте | **745** |
| 301 на страницу-дубль, у которой свой текст на месте (контент не потерян) | **10** |
| 301 на страницу, где нашего текста нет (текст потерян) | **4** |

Итого требуют вмешательства: **4** страниц (дубли-редиректы не считаем — там контент на месте).

## 2. URL-дубли: 301 на страницу со своим текстом — 10 шт.

Для этих URL текст был сгенерирован зря: URL 301-редиректит на другую страницу,
которая есть в манифесте и на которой её собственный текст стоит корректно.
Контент не потерян, действий не требуется — только вычесть из плана регенерации.

| Исходный URL (301) | Ведёт на | Слаг цели |
|---|---|---|
| `bezmaslyanye_1__porshnevye__atlas-copco` | https://prokompressor.ru/catalog/vozdushnye-kompressory/atlas-copco/ | `catalog__vozdushnye-kompressory__atlas-copco` |
| `bezmaslyanye_1__porshnevye__ekomak` | https://prokompressor.ru/catalog/vozdushnye-kompressory/ekomak/ | `catalog__vozdushnye-kompressory__ekomak` |
| `bezmaslyanye_1__porshnevye__fiac` | https://prokompressor.ru/catalog/vozdushnye-kompressory/fiac/ | `catalog__vozdushnye-kompressory__fiac` |
| `bezmaslyanye_1__porshnevye__remeza` | https://prokompressor.ru/catalog/vozdushnye-kompressory/remeza/ | `catalog__vozdushnye-kompressory__remeza` |
| `vozdushnye-kompressory__po-obemu-resivera__250-l` | https://prokompressor.ru/catalog/vozdushnye-kompressory/kompressory-s-resiverom-250-l/ | `catalog__vozdushnye-kompressory__kompressory-s-resiverom-250-l` |
| `vozdushnye-kompressory__po-obemu-resivera__400-l` | https://prokompressor.ru/catalog/vozdushnye-kompressory/kompressory-s-resiverom-400-l/ | `catalog__vozdushnye-kompressory__kompressory-s-resiverom-400-l` |
| `vozdushnye-kompressory__po-obemu-resivera__450-l` | https://prokompressor.ru/catalog/vozdushnye-kompressory/kompressory-s-resiverom-450-l/ | `catalog__vozdushnye-kompressory__kompressory-s-resiverom-450-l` |
| `vozdushnye-kompressory__po-obemu-resivera__500-l` | https://prokompressor.ru/catalog/vozdushnye-kompressory/kompressory-s-resiverom-500-l/ | `catalog__vozdushnye-kompressory__kompressory-s-resiverom-500-l` |
| `vozdushnye-kompressory__po-tipu-smazki__bezmaslyanye_1` | https://prokompressor.ru/catalog/vozdushnye-kompressory/kompressory-bezmaslyanye/ | `catalog__vozdushnye-kompressory__kompressory-bezmaslyanye` |
| `vozdushnye-kompressory__po-tipu-smazki__maslyanye` | https://prokompressor.ru/catalog/vozdushnye-kompressory/kompressory-maslyanye/ | `catalog__vozdushnye-kompressory__kompressory-maslyanye` |

## 3. Редирект с потерей текста — 4 шт.

Исходный URL схлопнут 301-м на страницу, где нашего текста нет вообще.
Текст, написанный под этот URL, нигде не опубликован.

### `catalog__vozdushnye-kompressory__po-obemu-resivera`
- было: https://prokompressor.ru/catalog/vozdushnye-kompressory/po-obemu-resivera/
- стало: https://prokompressor.ru/catalog/vozdushnye-kompressory/ (в манифесте отсутствует)
- H1 на конечной странице: Воздушные компрессоры
- H1 ожидался: Воздушные компрессоры

### `catalog__vozdushnye-kompressory__po-tipu-privoda`
- было: https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu-privoda/
- стало: https://prokompressor.ru/catalog/vozdushnye-kompressory/ (в манифесте отсутствует)
- H1 на конечной странице: Воздушные компрессоры
- H1 ожидался: Воздушные компрессоры

### `catalog__vozdushnye-kompressory__po-tipu-smazki`
- было: https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu-smazki/
- стало: https://prokompressor.ru/catalog/vozdushnye-kompressory/ (в манифесте отсутствует)
- H1 на конечной странице: Воздушные компрессоры
- H1 ожидался: Воздушные компрессоры

### `po-tipu-smazki__bezmaslyanye_1__porshnevye`
- было: https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu-smazki/bezmaslyanye_1/porshnevye/
- стало: https://prokompressor.ru/catalog/vozdushnye-kompressory/ (в манифесте отсутствует)
- H1 на конечной странице: Воздушные компрессоры
- H1 ожидался: Поршневые безмасляные компрессоры

