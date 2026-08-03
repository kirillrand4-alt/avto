## vodokanaly_obogatit.py

**Назначение.** Модуль обогащает данные по водоканалам. Он объединяет информацию из внешних выгрузок обзвона, выкачивает страницы сайтов организаций и извлекает контакты, домены, а также список сотрудников с их должностями.

**Роль в системе.** Обогащение.

**Входы.** 
* `vodokanaly.csv` (файла нет на диске)
* `vk_iz_obzvona.json` (файла нет на диске)
* `karta_staff.json` (файла нет на диске)
* `myagkij404.json` (файла нет на диске)

**Выходы.** 
* `vodokanaly-obogashchennye.csv` (файла нет на диске)
* `vodokanaly-domeny-dobor.csv` (файла нет на диске)
* `vodokanaly-lica.csv` (файла нет на диске)
* `vk_ec_rezultaty.jsonl` (файла нет на диске)
* `vk_ec_bez_sajta.jsonl` (файла нет на диске)

**Провайдер.** Извлекает данные о людях и должностях из текстов страниц. Названия конкретных моделей в коде не видны.

**Раннер.** Вызывает задачу `fetch_url`.

**Запуск.** Поэтапный запуск с помощью ключей командной строки:
* `python3 vodokanaly_obogatit.py --slit`
* `python3 vodokanaly_obogatit.py --razdely`
* `python3 vodokanaly_obogatit.py --ec`
* `python3 vodokanaly_obogatit.py --domeny`
* `python3 vodokanaly_obogatit.py --lica`

Также поддерживаются аргументы: `--ec-bez-sajta`, `--many`, `--predel`, `--slit-ec`, `--staff`, `--threads`.

**По одному ИНН или списку.** Да, обработка списка поддерживается. Запуск по одному конкретному ИНН в аргументах не предусмотрен (в коде не видно явного ключа вроде `--inn`). Чтобы запускать по одному ИНН, нужно добавить параметр фильтрации входных данных по ИНН.

**Зависимости.** Зависит от входных файлов `vodokanaly.csv`, `vk_iz_obzvona.json`, `karta_staff.json` и `myagkij404.json`. От результатов его работы зависят итоговые файлы обогащения `vodokanaly-obogashchennye.csv`, `vodokanaly-domeny-dobor.csv`, `vodokanaly-lica.csv`, `vk_ec_rezultaty.jsonl` и `vk_ec_bez_sajta.jsonl`.
