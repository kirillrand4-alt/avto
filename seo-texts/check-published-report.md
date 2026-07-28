# Проверка публикации 759 текстов на prokompressor.ru

Проверено URL: **759** из 759 (все из `publish/manifest.csv`).
Метод: обход каждого URL с отслеживанием 301/302, затем поиск на конечной
странице трёх предложений-маркеров из `publish/plain/<slug>.html`. Для страниц,
где свой текст не найден, второй проход сопоставляет H2 страницы с индексом
всех 759 текстов (плюс бэкап `gen-orig/`) и определяет, чей текст там лежит.

## Итог

| Результат | Страниц |
|---|---|
| Свой текст на месте | **494** |
| Показывается текст родительского раздела, своего текста нет | **248** |
| 301 на страницу-дубль, у которой свой текст на месте (контент не потерян) | **10** |
| 301 на страницу, где нашего текста нет (текст потерян) | **4** |
| Лежит текст страницы из другого раздела | **3** |

Итого требуют вмешательства: **255** страниц (дубли-редиректы не считаем — там контент на месте).

## 1. Текст родительского раздела вместо своего — 248 страниц

Страница отвечает 200, canonical свой, H1 совпадает с ожидаемым — но текстовый
блок принадлежит родительскому разделу. Визуально текст на странице есть,
поэтому глазами проблема не видна. Свой текст на такие страницы не встал.

Затронуто родительских разделов: 17.

<details><summary><b>po-tipu__vintovye__elektricheskie_1</b> — его текст показывается на 112 дочерних страницах</summary>

- `vintovye__elektricheskie_1__160-to-160` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/160-to-160/
- `vintovye__elektricheskie_1__18.5-to-18.5` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/18.5-to-18.5/
- `vintovye__elektricheskie_1__185-to-185` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/185-to-185/
- `vintovye__elektricheskie_1__200-to-200` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/200-to-200/
- `vintovye__elektricheskie_1__2000-to-2000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/2000-to-2000/
- `vintovye__elektricheskie_1__20000-to-20000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/20000-to-20000/
- `vintovye__elektricheskie_1__22-to-22` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/22-to-22/
- `vintovye__elektricheskie_1__220-230` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/220-230/
- `vintovye__elektricheskie_1__220-to-220` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/220-to-220/
- `vintovye__elektricheskie_1__225-to-225` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/225-to-225/
- `vintovye__elektricheskie_1__23000-to-23000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/23000-to-23000/
- `vintovye__elektricheskie_1__250-to-250` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/250-to-250/
- `vintovye__elektricheskie_1__25000-to-25000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/25000-to-25000/
- `vintovye__elektricheskie_1__30-to-30` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/30-to-30/
- `vintovye__elektricheskie_1__3000-to-3000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/3000-to-3000/
- `vintovye__elektricheskie_1__30000-to-30000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/30000-to-30000/
- `vintovye__elektricheskie_1__315-to-315` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/315-to-315/
- `vintovye__elektricheskie_1__3500-to-3500` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/3500-to-3500/
- `vintovye__elektricheskie_1__355-to-355` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/355-to-355/
- `vintovye__elektricheskie_1__37-to-37` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/37-to-37/
- `vintovye__elektricheskie_1__380-380-660-400` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/380-380-660-400/
- `vintovye__elektricheskie_1__400-to-400` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/400-to-400/
- `vintovye__elektricheskie_1__45-to-45` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/45-to-45/
- `vintovye__elektricheskie_1__450-to-450` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/450-to-450/
- `vintovye__elektricheskie_1__45000-to-45000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/45000-to-45000/
- `vintovye__elektricheskie_1__5.5-to-5.5` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/5.5-to-5.5/
- `vintovye__elektricheskie_1__50-to-55` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/50-to-55/
- `vintovye__elektricheskie_1__500-to-500` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/500-to-500/
- `vintovye__elektricheskie_1__5000-to-5000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/5000-to-5000/
- `vintovye__elektricheskie_1__50000-to-50000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/50000-to-50000/
- `vintovye__elektricheskie_1__55-to-55` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/55-to-55/
- `vintovye__elektricheskie_1__600-to-600` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/600-to-600/
- `vintovye__elektricheskie_1__6000-to-6000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/6000-to-6000/
- `vintovye__elektricheskie_1__7-to-7` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/7-to-7/
- `vintovye__elektricheskie_1__7.5-to-7.5` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/7.5-to-7.5/
- `vintovye__elektricheskie_1__700-to-700` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/700-to-700/
- `vintovye__elektricheskie_1__7000-to-7000` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/7000-to-7000/
- `vintovye__elektricheskie_1__75-to-75` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/75-to-75/
- `vintovye__elektricheskie_1__800-to-800` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/800-to-800/
- `vintovye__elektricheskie_1__90-to-90` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/90-to-90/
- `vintovye__elektricheskie_1__abac` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/abac/
- `vintovye__elektricheskie_1__airman` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/airman/
- `vintovye__elektricheskie_1__airpol` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/airpol/
- `vintovye__elektricheskie_1__almig` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/almig/
- `vintovye__elektricheskie_1__ariacom` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/ariacom/
- `vintovye__elektricheskie_1__atmos` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/atmos/
- `vintovye__elektricheskie_1__atom` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/atom/
- `vintovye__elektricheskie_1__belarus` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/belarus/
- `vintovye__elektricheskie_1__berg` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/berg/
- `vintovye__elektricheskie_1__bez-osushitelya-na-resivere` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/bez-osushitelya-na-resivere/
- `vintovye__elektricheskie_1__bez-osushitelya-na-resivere-bez-chastotnogo-preobrazovatelya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/bez-osushitelya-na-resivere-bez-chastotnogo-preobrazovatelya/
- `vintovye__elektricheskie_1__bez-resivera` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/bez-resivera/
- `vintovye__elektricheskie_1__bezhetsk` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/bezhetsk/
- `vintovye__elektricheskie_1__bezmaslyanyy` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/bezmaslyanyy/
- `vintovye__elektricheskie_1__chekhiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/chekhiya/
- `vintovye__elektricheskie_1__comaro` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/comaro/
- `vintovye__elektricheskie_1__comprag` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/comprag/
- `vintovye__elektricheskie_1__cross-air` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/cross-air/
- `vintovye__elektricheskie_1__dalgakiran` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/dalgakiran/
- `vintovye__elektricheskie_1__dali` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/dali/
- `vintovye__elektricheskie_1__das` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/das/
- `vintovye__elektricheskie_1__ekomak` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/ekomak/
- `vintovye__elektricheskie_1__enger` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/enger/
- `vintovye__elektricheskie_1__et-compressors` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/et-compressors/
- `vintovye__elektricheskie_1__fiac` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/fiac/
- `vintovye__elektricheskie_1__fini` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/fini/
- `vintovye__elektricheskie_1__fubag` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/fubag/
- `vintovye__elektricheskie_1__germaniya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/germaniya/
- `vintovye__elektricheskie_1__germaniya-rossiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/germaniya-rossiya/
- `vintovye__elektricheskie_1__hansmann` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/hansmann/
- `vintovye__elektricheskie_1__ingro` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/ingro/
- `vintovye__elektricheskie_1__ironmac` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/ironmac/
- `vintovye__elektricheskie_1__italiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/italiya/
- `vintovye__elektricheskie_1__italiya-kitay` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/italiya-kitay/
- `vintovye__elektricheskie_1__kitay` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kitay/
- `vintovye__elektricheskie_1__kompressory-10-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-10-bar/
- `vintovye__elektricheskie_1__kompressory-1000-l-min` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-1000-l-min/
- `vintovye__elektricheskie_1__kompressory-12-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-12-bar/
- `vintovye__elektricheskie_1__kompressory-13-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-13-bar/
- `vintovye__elektricheskie_1__kompressory-15-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-15-bar/
- `vintovye__elektricheskie_1__kompressory-16-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-16-bar/
- `vintovye__elektricheskie_1__kompressory-20-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-20-bar/
- `vintovye__elektricheskie_1__kompressory-25-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-25-bar/
- `vintovye__elektricheskie_1__kompressory-30-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-30-bar/
- `vintovye__elektricheskie_1__kompressory-5-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-5-bar/
- `vintovye__elektricheskie_1__kompressory-6-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-6-bar/
- `vintovye__elektricheskie_1__kompressory-7-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-7-bar/
- `vintovye__elektricheskie_1__kompressory-8-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-8-bar/
- `vintovye__elektricheskie_1__kompressory-900-l-min` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kompressory-900-l-min/
- `vintovye__elektricheskie_1__kraftmachine` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kraftmachine/
- `vintovye__elektricheskie_1__kraftmann` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/kraftmann/
- `vintovye__elektricheskie_1__lupamat` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/lupamat/
- `vintovye__elektricheskie_1__magnus` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/magnus/
- `vintovye__elektricheskie_1__mark` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/mark/
- `vintovye__elektricheskie_1__master-blast-` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/master-blast-/
- `vintovye__elektricheskie_1__na-resivere` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/na-resivere/
- `vintovye__elektricheskie_1__ozen` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/ozen/
- `vintovye__elektricheskie_1__polsha` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/polsha/
- `vintovye__elektricheskie_1__pryamoy` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/pryamoy/
- `vintovye__elektricheskie_1__remennyy` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/remennyy/
- `vintovye__elektricheskie_1__remeza` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/remeza/
- `vintovye__elektricheskie_1__rkz` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/rkz/
- `vintovye__elektricheskie_1__rossiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/rossiya/
- `vintovye__elektricheskie_1__s-chastotnym-preobrazovatelem` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/s-chastotnym-preobrazovatelem/
- `vintovye__elektricheskie_1__s-osushitelem` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/s-osushitelem/
- `vintovye__elektricheskie_1__s-osushitelem-na-resivere` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/s-osushitelem-na-resivere/
- `vintovye__elektricheskie_1__turtsiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/turtsiya/
- `vintovye__elektricheskie_1__turtsiya-belgiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/turtsiya-belgiya/
- `vintovye__elektricheskie_1__ultratech` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/ultratech/
- `vintovye__elektricheskie_1__yaponiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/yaponiya/
- `vintovye__elektricheskie_1__zega` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/zega/
- `vintovye__elektricheskie_1__zif` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/zif/

</details>

<details><summary><b>vozdushnye-kompressory__po-tipu__vintovye</b> — его текст показывается на 71 дочерних страницах</summary>

- `po-tipu__vintovye__abac` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/abac/
- `po-tipu__vintovye__airbox` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/airbox/
- `po-tipu__vintovye__airman` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/airman/
- `po-tipu__vintovye__airpol` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/airpol/
- `po-tipu__vintovye__almig` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/almig/
- `po-tipu__vintovye__ariacom` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/ariacom/
- `po-tipu__vintovye__atlas-copco` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/atlas-copco/
- `po-tipu__vintovye__atmos` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/atmos/
- `po-tipu__vintovye__atom` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/atom/
- `po-tipu__vintovye__aztec` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/aztec/
- `po-tipu__vintovye__berg` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/berg/
- `po-tipu__vintovye__bezhetsk` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/bezhetsk/
- `po-tipu__vintovye__comaro` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/comaro/
- `po-tipu__vintovye__comprag` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/comprag/
- `po-tipu__vintovye__cross-air` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/cross-air/
- `po-tipu__vintovye__dalgakiran` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dalgakiran/
- `po-tipu__vintovye__dali` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dali/
- `po-tipu__vintovye__das` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/das/
- `po-tipu__vintovye__ekomak` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/ekomak/
- `po-tipu__vintovye__enger` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/enger/
- `po-tipu__vintovye__et-compressors` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/et-compressors/
- `po-tipu__vintovye__fiac` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/fiac/
- `po-tipu__vintovye__fini` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/fini/
- `po-tipu__vintovye__fubag` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/fubag/
- `po-tipu__vintovye__germaniya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/germaniya/
- `po-tipu__vintovye__germaniya-rossiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/germaniya-rossiya/
- `po-tipu__vintovye__hansmann` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/hansmann/
- `po-tipu__vintovye__ingro` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/ingro/
- `po-tipu__vintovye__ironmac` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/ironmac/
- `po-tipu__vintovye__italiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/italiya/
- `po-tipu__vintovye__italiya-kitay` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/italiya-kitay/
- `po-tipu__vintovye__kitay` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kitay/
- `po-tipu__vintovye__kompressory-10-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-10-bar/
- `po-tipu__vintovye__kompressory-12-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-12-bar/
- `po-tipu__vintovye__kompressory-13-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-13-bar/
- `po-tipu__vintovye__kompressory-15-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-15-bar/
- `po-tipu__vintovye__kompressory-16-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-16-bar/
- `po-tipu__vintovye__kompressory-20-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-20-bar/
- `po-tipu__vintovye__kompressory-25-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-25-bar/
- `po-tipu__vintovye__kompressory-30-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-30-bar/
- `po-tipu__vintovye__kompressory-40-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-40-bar/
- `po-tipu__vintovye__kompressory-5-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-5-bar/
- `po-tipu__vintovye__kompressory-6-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-6-bar/
- `po-tipu__vintovye__kompressory-7-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-7-bar/
- `po-tipu__vintovye__kompressory-8-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-8-bar/
- `po-tipu__vintovye__kompressory-900-l-min` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kompressory-900-l-min/
- `po-tipu__vintovye__kraftmachine` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kraftmachine/
- `po-tipu__vintovye__kraftmann` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/kraftmann/
- `po-tipu__vintovye__lupamat` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/lupamat/
- `po-tipu__vintovye__magnus` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/magnus/
- `po-tipu__vintovye__mark` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/mark/
- `po-tipu__vintovye__master-blast-` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/master-blast-/
- `po-tipu__vintovye__minskiy-motornyy-zavod` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/minskiy-motornyy-zavod/
- `po-tipu__vintovye__na-resivere` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/na-resivere/
- `po-tipu__vintovye__na-resivere-s-osushitelem` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/na-resivere-s-osushitelem/
- `po-tipu__vintovye__ozen` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/ozen/
- `po-tipu__vintovye__polsha` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/polsha/
- `po-tipu__vintovye__pryamoy` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/pryamoy/
- `po-tipu__vintovye__remennyy` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/remennyy/
- `po-tipu__vintovye__remeza` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/remeza/
- `po-tipu__vintovye__rkz` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/rkz/
- `po-tipu__vintovye__rossiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/rossiya/
- `po-tipu__vintovye__s-chastotnym-preobrazovatelem` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/s-chastotnym-preobrazovatelem/
- `po-tipu__vintovye__s-osushitelem` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/s-osushitelem/
- `po-tipu__vintovye__shvetsiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/shvetsiya/
- `po-tipu__vintovye__turtsiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/turtsiya/
- `po-tipu__vintovye__turtsiya-belgiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/turtsiya-belgiya/
- `po-tipu__vintovye__ultratech` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/ultratech/
- `po-tipu__vintovye__yaponiya` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/yaponiya/
- `po-tipu__vintovye__zega` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/zega/
- `po-tipu__vintovye__zif` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/zif/

</details>

<details><summary><b>catalog__osushiteli__adsorbtsionnye</b> — его текст показывается на 22 дочерних страницах</summary>

- `osushiteli__adsorbtsionnye__almig_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/almig_osush/
- `osushiteli__adsorbtsionnye__ariacom_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/ariacom_osush/
- `osushiteli__adsorbtsionnye__atlas_copco_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/atlas_copco_osush/
- `osushiteli__adsorbtsionnye__atmos_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/atmos_osush/
- `osushiteli__adsorbtsionnye__ats` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/ats/
- `osushiteli__adsorbtsionnye__berg_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/berg_osush/
- `osushiteli__adsorbtsionnye__comaro_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/comaro_osush/
- `osushiteli__adsorbtsionnye__comprag_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/comprag_osush/
- `osushiteli__adsorbtsionnye__dalgakiran_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/dalgakiran_osush/
- `osushiteli__adsorbtsionnye__dali_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/dali_osush/
- `osushiteli__adsorbtsionnye__das_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/das_osush/
- `osushiteli__adsorbtsionnye__ekomak_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/ekomak_osush/
- `osushiteli__adsorbtsionnye__et_compressors_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/et_compressors_osush/
- `osushiteli__adsorbtsionnye__evrazkompressor` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/evrazkompressor/
- `osushiteli__adsorbtsionnye__kraftmachine_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/kraftmachine_osush/
- `osushiteli__adsorbtsionnye__kraftmann_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/kraftmann_osush/
- `osushiteli__adsorbtsionnye__ozen_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/ozen_osush/
- `osushiteli__adsorbtsionnye__pneumatech_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/pneumatech_osush/
- `osushiteli__adsorbtsionnye__remeza_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/remeza_osush/
- `osushiteli__adsorbtsionnye__rkz` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/rkz/
- `osushiteli__adsorbtsionnye__xeleron` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/xeleron/
- `osushiteli__adsorbtsionnye__zif_osush` — https://prokompressor.ru/catalog/osushiteli/adsorbtsionnye/zif_osush/

</details>

<details><summary><b>prokompressor.ru__catalog__resivery</b> — его текст показывается на 12 дочерних страницах</summary>

- `catalog__resivery__airpol_resiver` — https://prokompressor.ru/catalog/resivery/airpol_resiver/
- `catalog__resivery__ariacom_resiver` — https://prokompressor.ru/catalog/resivery/ariacom_resiver/
- `catalog__resivery__bezhetsk_resiver` — https://prokompressor.ru/catalog/resivery/bezhetsk_resiver/
- `catalog__resivery__comprag_resiver` — https://prokompressor.ru/catalog/resivery/comprag_resiver/
- `catalog__resivery__dalgakiran_resiver` — https://prokompressor.ru/catalog/resivery/dalgakiran_resiver/
- `catalog__resivery__dnt` — https://prokompressor.ru/catalog/resivery/dnt/
- `catalog__resivery__ekomak_resiver` — https://prokompressor.ru/catalog/resivery/ekomak_resiver/
- `catalog__resivery__enger` — https://prokompressor.ru/catalog/resivery/enger/
- `catalog__resivery__fiac_resiver` — https://prokompressor.ru/catalog/resivery/fiac_resiver/
- `catalog__resivery__pneumatech_resiver` — https://prokompressor.ru/catalog/resivery/pneumatech_resiver/
- `catalog__resivery__remeza_resiver` — https://prokompressor.ru/catalog/resivery/remeza_resiver/
- `catalog__resivery__rkz-airrus` — https://prokompressor.ru/catalog/resivery/rkz-airrus/

</details>

<details><summary><b>catalog__osushiteli__refrizheratornye</b> — его текст показывается на 5 дочерних страницах</summary>

- `osushiteli__refrizheratornye__ats` — https://prokompressor.ru/catalog/osushiteli/refrizheratornye/ats/
- `osushiteli__refrizheratornye__enger` — https://prokompressor.ru/catalog/osushiteli/refrizheratornye/enger/
- `osushiteli__refrizheratornye__evrazkompressor` — https://prokompressor.ru/catalog/osushiteli/refrizheratornye/evrazkompressor/
- `osushiteli__refrizheratornye__rkz` — https://prokompressor.ru/catalog/osushiteli/refrizheratornye/rkz/
- `osushiteli__refrizheratornye__xeleron` — https://prokompressor.ru/catalog/osushiteli/refrizheratornye/xeleron/

</details>

<details><summary><b>catalog__podgotovka-vozdukha__separatory-tsentrobezhnye-tsiklonnye</b> — его текст показывается на 5 дочерних страницах</summary>

- `podgotovka-vozdukha__separatory-tsentrobezhnye-tsiklonnye__ats` — https://prokompressor.ru/catalog/podgotovka-vozdukha/separatory-tsentrobezhnye-tsiklonnye/ats/
- `podgotovka-vozdukha__separatory-tsentrobezhnye-tsiklonnye__enger` — https://prokompressor.ru/catalog/podgotovka-vozdukha/separatory-tsentrobezhnye-tsiklonnye/enger/
- `podgotovka-vozdukha__separatory-tsentrobezhnye-tsiklonnye__evrazkompressor` — https://prokompressor.ru/catalog/podgotovka-vozdukha/separatory-tsentrobezhnye-tsiklonnye/evrazkompressor/
- `podgotovka-vozdukha__separatory-tsentrobezhnye-tsiklonnye__rkz` — https://prokompressor.ru/catalog/podgotovka-vozdukha/separatory-tsentrobezhnye-tsiklonnye/rkz/
- `podgotovka-vozdukha__separatory-tsentrobezhnye-tsiklonnye__xeleron` — https://prokompressor.ru/catalog/podgotovka-vozdukha/separatory-tsentrobezhnye-tsiklonnye/xeleron/

</details>

<details><summary><b>vozdushnye-kompressory__po-naznacheniyu__dlya-vyduva-pet</b> — его текст показывается на 4 дочерних страницах</summary>

- `po-naznacheniyu__dlya-vyduva-pet__16-bar-1` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-vyduva-pet/16-bar-1/
- `po-naznacheniyu__dlya-vyduva-pet__30-bar-1` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-vyduva-pet/30-bar-1/
- `po-naznacheniyu__dlya-vyduva-pet__40-bar-1` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-vyduva-pet/40-bar-1/
- `po-naznacheniyu__dlya-vyduva-pet__vd-vyshe-40-bar` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-vyduva-pet/vd-vyshe-40-bar/

</details>

<details><summary><b>catalog__podgotovka-vozdukha__filtry-magistralnye</b> — его текст показывается на 4 дочерних страницах</summary>

- `podgotovka-vozdukha__filtry-magistralnye__ats` — https://prokompressor.ru/catalog/podgotovka-vozdukha/filtry-magistralnye/ats/
- `podgotovka-vozdukha__filtry-magistralnye__enger` — https://prokompressor.ru/catalog/podgotovka-vozdukha/filtry-magistralnye/enger/
- `podgotovka-vozdukha__filtry-magistralnye__rkz` — https://prokompressor.ru/catalog/podgotovka-vozdukha/filtry-magistralnye/rkz/
- `podgotovka-vozdukha__filtry-magistralnye__xeleron` — https://prokompressor.ru/catalog/podgotovka-vozdukha/filtry-magistralnye/xeleron/

</details>

<details><summary><b>vozdushnye-kompressory__po-tipu__bustery</b> — его текст показывается на 2 дочерних страницах</summary>

- `po-tipu__bustery__enger` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/bustery/enger/
- `po-tipu__bustery__rkz` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/bustery/rkz/

</details>

<details><summary><b>catalog__podgotovka-vozdukha__dookhladiteli</b> — его текст показывается на 2 дочерних страницах</summary>

- `podgotovka-vozdukha__dookhladiteli__ats` — https://prokompressor.ru/catalog/podgotovka-vozdukha/dookhladiteli/ats/
- `podgotovka-vozdukha__dookhladiteli__enger` — https://prokompressor.ru/catalog/podgotovka-vozdukha/dookhladiteli/enger/

</details>

<details><summary><b>catalog__podgotovka-vozdukha__maslovlagorazdeliteli</b> — его текст показывается на 2 дочерних страницах</summary>

- `podgotovka-vozdukha__maslovlagorazdeliteli__enger` — https://prokompressor.ru/catalog/podgotovka-vozdukha/maslovlagorazdeliteli/enger/
- `podgotovka-vozdukha__maslovlagorazdeliteli__rkz` — https://prokompressor.ru/catalog/podgotovka-vozdukha/maslovlagorazdeliteli/rkz/

</details>

<details><summary><b>po-tipu__vintovye__dizelnye</b> — его текст показывается на 2 дочерних страницах</summary>

- `vintovye__dizelnye__enger` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dizelnye/enger/
- `vintovye__dizelnye__s-osushitelem` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dizelnye/s-osushitelem/

</details>

<details><summary><b>po-tipu-smazki__bezmaslyanye_1__spiralnye_1</b> — его текст показывается на 1 дочерних страницах</summary>

- `bezmaslyanye_1__spiralnye_1__enger` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu-smazki/bezmaslyanye_1/spiralnye_1/enger/

</details>

<details><summary><b>vozdushnye-kompressory__po-tipu__nizkogo-davleniya</b> — его текст показывается на 1 дочерних страницах</summary>

- `po-tipu__nizkogo-davleniya__enger` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/nizkogo-davleniya/enger/

</details>

<details><summary><b>catalog__podgotovka-vozdukha__kondensatootvodchiki</b> — его текст показывается на 1 дочерних страницах</summary>

- `podgotovka-vozdukha__kondensatootvodchiki__enger` — https://prokompressor.ru/catalog/podgotovka-vozdukha/kondensatootvodchiki/enger/

</details>

<details><summary><b>catalog__podgotovka-vozdukha__ugolnye-kolonny</b> — его текст показывается на 1 дочерних страницах</summary>

- `podgotovka-vozdukha__ugolnye-kolonny__enger` — https://prokompressor.ru/catalog/podgotovka-vozdukha/ugolnye-kolonny/enger/

</details>

<details><summary><b>po-tipu__vintovye__dvukhstupenchatye</b> — его текст показывается на 1 дочерних страницах</summary>

- `vintovye__dvukhstupenchatye__enger` — https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dvukhstupenchatye/enger/

</details>

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

## 4. Текст из другого раздела — 3 шт.

Самое грубое: на странице стоит текст, тематически к ней не относящийся.
Здесь и пользователь, и поиск видят нерелевантный контент.

### `catalog__zapasnye-chasti-i-raskhodniki__komplekty-dlya-to`
- URL: https://prokompressor.ru/catalog/zapasnye-chasti-i-raskhodniki/komplekty-dlya-to/
- лежит текст страницы: `adsorbtsionnye__enger_2__kholodnoy-regeneratsii`
- H2 на странице: адсорбционная осушка для глубокого удаления влаги; холодная регенерация: простота против потерь воздуха; как подбирают осушитель под систему; место в цепочке подготовки воздуха

### `catalog__zapasnye-chasti-i-raskhodniki__remkomplekty`
- URL: https://prokompressor.ru/catalog/zapasnye-chasti-i-raskhodniki/remkomplekty/
- лежит текст страницы: `catalog__vozdushnye-kompressory__enger`
- H2 на странице: линейка винтовых компрессоров enger для промышленности; технические характеристики и параметры подбора; цены и условия поставки; опыт применения и запуск оборудования

### `po-tipu-smazki__bezmaslyanye_1__vintovye_1`
- URL: https://prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu-smazki/bezmaslyanye_1/vintovye_1/
- лежит текст страницы: `vozdushnye-kompressory__po-tipu__vintovye`
- H2 на странице: конструкция винтовых компрессоров для промышленных задач; линейка брендов и технические диапазоны; когда винтовой компрессор избыточен; стоимость и условия поставки

