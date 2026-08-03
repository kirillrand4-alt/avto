## obratnyy_audit.py

**Назначение.** Автоматически проверяет актуальность собранных данных в системе: сопоставляет время изменения файлов данных с кодом их генерации, находит заброшенные инструменты сбора и рассчитывает показатели отсева.

**Роль в системе.** Проверка.

**Входы.** 
- HARAKTERISTIKI-mashin-po-predpriyatiyam.csv (885 строк)
- OCHERED-centrobezhnye.csv (744 строк)
- PROVERKA-otseva.md (95 строк)
- SREDA-po-markam.csv (2013 строк)
- SVOD-POLNYY-po-predpriyatiyam.csv (25136 строк)
- SVOD-tri-sostoyaniya.csv (88579 строк)
- SVODNAYA-centrobezhnye.csv (6582 строк)
- VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv (3732 строк)
- centro/eis/skany-lica.csv (84 строк)
- centro/lica-s-sajtov-otsev.csv (1032 строк)
- centro/lica-s-sajtov.csv (385 строк)
- centro/poteryannye-inn.csv (764 строк)
- istochnik-erknm-nashi-347.csv (163 строк)
- istochnik-nzl-referencii-kompressory.csv (2141 строк)
- lica-s-sajtov.csv (385 строк)
- poteryannye-inn.csv (764 строк)
- BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv (файла нет на диске)
- NOVOSTI-dokazatelstva.csv (файла нет на диске)
- OBHOD-kontakty-3s.csv (файла нет на диске)
- OTSEV-tip-mashiny.csv (файла нет на диске)
- TEHLPR-VSE-s-provenansom.csv (файла нет на диске)
- sajty_OCHERED_centrobezhnye_csv.jsonl (файла нет на диске)
- skany-lica.csv (файла нет на диске)
- tp-spisok.csv (файла нет на диске)

**Выходы.** В коде не видно (результаты аудита выводятся в консоль, выходные файлы не формируются).

**Провайдер.** Не вызывает.

**Раннер.** Не вызывает.

**Запуск.** `python3 obratnyy_audit.py`

**По одному ИНН или списку.** Нет. Модуль анализирует файловую систему целиком. Аргументы командной строки не предусмотрены. Чтобы запустить аудит по конкретному ИНН, потребуется добавить прием параметров в CLI и реализацию фильтрации записей внутри проверяемых файлов.

**Зависимости.** Зависит от файлов данных, создаваемых другими модулями системы (включая `SVOD-POLNYY-po-predpriyatiyam.csv`, `centro/eis/skany-lica.csv`, `sajty_OCHERED_centrobezhnye_csv.jsonl`). Ни один модуль от данного файла не зависит.
