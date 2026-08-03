## novosti_dokazatelstva.py
**Назначение.** Находит в новостях и публикациях упоминания промышленного оборудования компаний, извлекая дословные цитаты, марки машин и имена упомянутых людей.
**Роль в системе.** Обогащение.
**Входы.** 
- `OCHERED-centrobezhnye.csv`: 744 строк
- `karta.json`: файла нет на диске
- `novosti_ssylki.jsonl`: файла нет на диске
**Выходы.** 
- `DOKAZATELSTVA-iz-novostey.csv`: файла нет на диске
- `OTSEV-iz-novostey.csv`: файла нет на диске
**Провайдер.** Вызывает провайдер, наименование модели в коде не видно. Модель анализирует текст статьи и извлекает доказательства наличия оборудования, дословные цитаты, марки и упомянутых людей.
**Раннер.** Вызывает задачи: `browser_probe`.
**Запуск.** 
- `python3 novosti_dokazatelstva.py --iskat` (с опциональными ключами `--predel`, `--many`, `--threads`)
- `python3 novosti_dokazatelstva.py --tyanut` (с опциональным ключом `--threads`)
- `python3 novosti_dokazatelstva.py --razobrat` (с опциональным ключом `--threads`)
**По одному ИНН или списку.** Да, модуль поддерживает обработку по списку компаний.
**Зависимости.** Зависит от входящей очереди `OCHERED-centrobezhnye.csv` и карты `karta.json`. Результаты работы передает в файлы `DOKAZATELSTVA-iz-novostey.csv`, `OTSEV-iz-novostey.csv` и `novosti_ssylki.jsonl`.
