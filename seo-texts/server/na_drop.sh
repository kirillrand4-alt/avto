#!/bin/bash
# Выложить ценное на дроп. Файлы сессии иногда слетают (указание владельца
# 30.07), а дроп живёт на сервере и доступен обеим сессиям — значит документы
# и рабочие скрипты должны лежать ТАМ, а не только в песочнице.
#
# Репозиторий тоже durable, но дроп нужен по другой причине: из него берёт
# файлы параллельная сессия и оттуда же их читает раннер.
#
# ВНИМАНИЕ: имена переменных ТОЛЬКО ЛАТИНИЦЕЙ. bash не принимает
# кириллические идентификаторы и падает строкой «not a valid
# identifier» — на этом за один вечер обожглись дважды, и оба раза
# скрипт умирал молча, оставляя пустой файл вывода.
#
# Запуск: bash na_drop.sh
cd "$(dirname "$0")"
FILES="
СВЕРКА-2-ДЛЯ-СОСЕДА.md
СВЕРКА-С-СОСЕДОМ-30-07.md
ЧТО-НА-ДРОПЕ-ОТ-МЕНЯ.md
КАК-ЭТО-РАБОТАЕТ.md
ПЕРЕДАЧА-2026-07-30.md
ЧТО-МОЖЕМ-СОБРАТЬ.md
ПЕРЕДАЧА-СЕССИИ.md
ENRICH-ROADMAP.md
ЛИНЗЫ-РАЗБОР.txt
ГДЕ-ИСКАТЬ-КОНТАКТЫ.md
ocr_lib.py
ops/rtn_znaniya.py
ops/people_sources.py
ops/linzy_review.py
ops/clients_223.py
ops/tp_lica_import.py
ops/plany_import.py
ops/phones_from_obzvon.py
ops/vygruzka_dlya_soseda.py
ops/tehlpr_bez_telefona.py
ops/celi_bez_tehlpr.py
ops/lpr_serp.py
ops/utverzhdayu_ocr.py
ops/tender_platforms.py
ops/dept_directory.py
"
for f in $FILES; do
  [ -f "$f" ] || { printf '%-30s НЕТ ФАЙЛА\n' "$(basename "$f")"; continue; }
  printf '%-30s ' "$(basename "$f")"
  bash drop_client.sh up "$f" 2>/dev/null | python3 -c "
import json,sys
try:
    print('ok', json.load(sys.stdin).get('bytes'), 'байт')
except Exception:
    print('ОШИБКА ЗАЛИВКИ')
"
done
