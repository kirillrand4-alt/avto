#!/usr/bin/env bash
# Выгрузка всего ценного на дроп одной командой.
#
# Зачем. Файлы сессии слетают, а репозиторий соседней сессии и раннеру не виден: они берут
# файлы с дропа. Поэтому ценное уезжает туда, а не только в git.
#
# ВНИМАНИЕ, ловушка, на которой соседняя сессия потеряла круг работы: **имя переменной в bash
# нельзя писать кириллицей.** Оболочка отвечает «not a valid identifier» и умирает молча,
# оставляя пустой файл вывода — снаружи это выглядит как «прогон ничего не дал». Все
# идентификаторы здесь латиницей; кириллица только в строках и комментариях.
#
# Использование:
#   bash na_drop.sh            # выгрузить всё из списка
#   bash na_drop.sh --list     # только показать, что лежит на дропе сейчас
set -u

BAZA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KLIENT="$BAZA/server/drop_client.sh"
LENS="$BAZA/engineers-lens"

if [ "${1:-}" = "--list" ]; then
    bash "$KLIENT" list
    exit 0
fi

# Что считается ценным. Три группы: итоговые документы, боевые данные, скрипты-инструменты.
# Не кладём сюда промежуточные выгрузки и логи — на дропе и так лежат тяжёлые исходники.
FAJLY=(
    # итоговые документы
    "$LENS/METOD.md"
    "$LENS/PEREDACHA-2026-07-30.md"
    "$LENS/PROVERKA-LINZAMI-2026-07-30.md"
    "$LENS/SPOSOBY-POISKA.md"
    "$LENS/IDEI-NEPROVERENNYE.md"
    "$LENS/SVERKA-s-massovym-obogashcheniem.md"
    "$LENS/HANDOFF.md"
    # боевые данные: люди и телефоны
    "$LENS/SPISOK-OBZVONA.csv"
    "$LENS/centro/tenderpro/tp-lica.csv"
    "$LENS/centro/tenderpro/tp-kartochki.csv"
    "$LENS/centro/tenderpro/tp-spisok.csv"
    "$LENS/centro/tenderpro/tp-inn.csv"
    "$LENS/centro/telefony-vozdushnye.csv"
    "$LENS/centro/telefony-vodokanaly.csv"
    # боевые данные: предприятия и оборудование
    "$LENS/centro/epb-vozdushnye.csv"
    "$LENS/centro/novye-dlya-obzvona.csv"
    "$LENS/centro/dop/vodokanaly.csv"
    "$LENS/centro/PERESECHENIE-sber-epb.csv"
    "$LENS/centro/plany-zakupki.csv"
    # выгрузки площадок
    "$LENS/centro/portal-postavshchikov-centro.csv"
    "$LENS/centro/fabrikant-centro.csv"
    "$LENS/centro/roseltorg-centro.csv"
    "$LENS/centro/rts-tender-centro.csv"
    "$LENS/centro/sber-organizatory-inn.csv"
    # инструменты
    "$BAZA/tenderpro_harvest.py"
    "$BAZA/tenderpro_lica.py"
    "$BAZA/lens_dyry.py"
    "$BAZA/mpb_harvest.py"
    "$BAZA/mpb_models.py"
    "$BAZA/mpb_delta.py"
    "$BAZA/dadata_inn.py"
    "$BAZA/svesti_obzvon.py"
    "$BAZA/erknm_harvest.py"
    "$BAZA/na_drop.sh"
)

OK=0
NET=0
SBOJ=0
for f in "${FAJLY[@]}"; do
    if [ ! -f "$f" ]; then
        echo "нет файла: ${f#"$BAZA"/}"
        NET=$((NET + 1))
        continue
    fi
    # Правило В8 в собственном инструменте: молчаливый ноль не различает «пусто в мире» и
    # «сломано у тебя». Поэтому проверяем код возврата, а не наличие вывода.
    if bash "$KLIENT" up "$f" > /dev/null 2>&1; then
        echo "уехало: ${f#"$BAZA"/} ($(wc -c < "$f") байт)"
        OK=$((OK + 1))
    else
        echo "СБОЙ ЗАГРУЗКИ: ${f#"$BAZA"/}"
        SBOJ=$((SBOJ + 1))
    fi
done

echo "----"
echo "уехало $OK, нет на диске $NET, сбоев загрузки $SBOJ из ${#FAJLY[@]}"
[ "$SBOJ" -gt 0 ] && exit 1
exit 0
