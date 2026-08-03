## svod_polnyy.py

**Назначение.** Формирование развернутой единой сводки по предприятиям с объединением данных из базовой сводки, мастер-базы, контактов и надзорных мероприятий. Используется для получения полного профиля компании с фиксацией источника по каждому полю.

**Роль в системе.** Сборка витрины.

**Входы.**
* `SVOD-po-predpriyatiyam.csv` (25 136 строк)
* `master-base.sqlite` (3 753 103 строк)
* `SPISOK-OBZVONA.csv` (385 строк)
* `rtn-peresechenie.csv` (25 строк)
* `telefony-vodokanaly.csv` (78 строк)
* `telefony-vozdushnye.csv` (164 строк)
* `tp-lyudi-dlya-obzvona.csv` (файла нет на диске)
* `vodokanaly.csv` (файла нет на диске)

**Выходы.**
* `SVOD-POLNYY-po-predpriyatiyam.csv` (25 136 строк)

**Провайдер.** Не вызывает.

**Раннер.** Не вызывает.

**Запуск.** `python3 svod_polnyy.py`

**По одному ИНН или списку.** Нет. В текущем коде аргументы командной строки не обрабатываются. Чтобы модуль мог работать по выбранным ИНН, необходимо добавить парсинг ключей командной строки и фильтрацию данных по переданному ИНН или списку ИНН перед сборкой.

**Зависимости.**
* Зависит от файлов-источников: `SVOD-po-predpriyatiyam.csv`, `master-base.sqlite`, `SPISOK-OBZVONA.csv`, `rtn-peresechenie.csv`, `telefony-vodokanaly.csv`, `telefony-vozdushnye.csv`, `tp-lyudi-dlya-obzvona.csv` и `vodokanaly.csv`.
* От него зависят модули и сервисы, читающие итоговый файл `SVOD-POLNYY-po-predpriyatiyam.csv`.
