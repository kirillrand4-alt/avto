## svod_tri_sostoyaniya.py

**Назначение.** Скрипт объединяет данные о промышленном оборудовании предприятий по трем состояниям: уже установлено и отработало срок (по данным ЭПБ), находится в процессе закупки (проведенные торги) и планируется к закупке (планы закупок по 223-ФЗ). Из текстов вытаскиваются марки машин с валидацией по шаблонам.

**Роль в системе.** Сборка витрины.

**Входы.**
* OTSEV-inn-neodnoznachno.csv: 506 строк
* SVOD-po-predpriyatiyam.csv: 25136 строк
* epb-centro-ochishchennyy.csv: 7751 строк
* epb-centro-vse.csv: 7751 строк
* epb-problemnye.csv: 308 строк
* epb-processy.csv: 7736 строк
* epb-uzly.csv: 2496 строк
* epb-vozdushnye.csv: 2308 строк
* etpgpb-loty-centro.csv: 906 строк
* etpgpb-zakazchiki-inn.csv: 17499 строк
* fabrikant-centro.csv: 2821 строк
* hh-rabotodateli-inn.csv: 422 строк
* istochnik-fsa-centro-deklaranty.csv: 335 строк
* istochnik-nzl-referencii-kompressory.csv: 2141 строк
* istochnik-portal-postavshchikov-kompressory.csv: 47 строк
* kazankompressormash-zakazchiki.csv: 133 строк
* plany-zakupki-chistye.csv: 7458 строк
* portal-postavshchikov-centro.csv: 5681 строк
* poteryannye-inn.csv: 764 строк
* roseltorg-centro.csv: 1834 строк
* rts-tender-centro.csv: 448 строк
* sber-organizatory-inn.csv: 4410 строк
* sber-organizatory-polnye.csv: 4410 строк

**Выходы.**
* SVOD-tri-sostoyaniya.csv: 88579 строк

**Провайдер.** Не вызывает.

**Раннер.** Не вызывает.

**Запуск.**
* `python3 svod_tri_sostoyaniya.py --kontrol` (запуск проверки правил распознавания марок на эталонном наборе)
* `python3 svod_tri_sostoyaniya.py` (сборка итоговой сводки)

**По одному ИНН или списку.** Нет. В коде не предусмотрена фильтрация по отдельному ИНН или списку ИНН. Скрипт всегда считывает и обрабатывает полные CSV-файлы. Для работы по выбранным ИНН необходимо добавить новый аргумент командной строки (например, `--inn`) и фильтрацию строк по ИНН в функциях чтения данных.

**Зависимости.**
* Зависит от файлов с выгрузками реестров ЭПБ, электронных торговых площадок, планов закупок и справочников компаний.
* От этого файла зависит сформированный итоговый файл `SVOD-tri-sostoyaniya.csv`.
