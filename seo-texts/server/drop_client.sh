#!/bin/bash
# Клиент обменника parsercompressor.online/drop для сессий Claude Code.
# Токен и URL берутся из окружения: DROP_TOKEN, DROP_URL (задать в env-настройках окружения).
# Использование: drop_client.sh list | up <file> | down <name> [dst] | del <name>
#
# ПОЧЕМУ ТУТ ЕСТЬ ПРОВЕРКА ОТВЕТА, А НЕ ПРОСТО curl -s.
# 10.08.2026: `up PARK-SROK-EPB-2S.jsonl` завершился МОЛЧА, без единого знака на выходе, —
# и файл на дроп не попал. Разбор: curl вернул код 92 (обрыв потока HTTP/2), но `-s`
# проглотил ошибку, а вызывающий скрипт написал «выложено». Это тот же класс дефекта, что
# мы ловим в данных: молчание выглядит как успех. Цена была бы та же — файл, который все
# считают лежащим на дропе, а его там нет.
#
# Теперь: `up` печатает ответ сервера, при неудаче ПОВТОРЯЕТ и выходит с ненулевым кодом,
# если так и не подтвердилось. Подтверждением считается `"ok":true` в ответе, а не код
# возврата curl: сервер может ответить 200 и телом с ошибкой.
#
# И КОРЕНЬ, а не только заслон. Повтор показал, что сбой не разовый: две попытки подряд
# упали с той же ошибкой. Замер в лоб — три выгрузки одного файла на HTTP/2 и три на
# HTTP/1.1: HTTP/2 прошёл 1 раз из 3, HTTP/1.1 — 3 из 3. Поэтому `-T` идёт с `--http1.1`,
# а повтор остаётся вторым рубежом. Заслон без починки корня — это привычка к сбою.
U="${DROP_URL:-https://parsercompressor.online/drop}"
[ -z "$DROP_TOKEN" ] && { echo "нет DROP_TOKEN в окружении"; exit 1; }

vylozhit() {
  local put="$1" imya popytka otvet kod
  imya="$(basename "$put")"
  [ -f "$put" ] || { echo "ФАЙЛА НЕТ: $put" >&2; return 2; }
  for popytka in 1 2 3 4; do
    otvet="$(curl -sS --http1.1 --max-time 300 -H "X-Drop-Token: $DROP_TOKEN" -T "$put" "$U/$imya" 2>&1)"
    kod=$?
    case "$otvet" in
      *'"ok":true'*) echo "$otvet"; return 0 ;;
    esac
    echo "попытка $popytka не подтвердилась (curl $kod): ${otvet:0:200}" >&2
    sleep $((popytka * 2))
  done
  echo "НЕ ВЫЛОЖЕН: $imya — сервер ни разу не подтвердил приём" >&2
  return 1
}

case "$1" in
  list) curl -sS -H "X-Drop-Token: $DROP_TOKEN" "$U/list" | python3 -m json.tool ;;
  up)   vylozhit "$2" ;;
  down) curl -sS -f -H "X-Drop-Token: $DROP_TOKEN" "$U/$2" -o "${3:-$2}" \
          && echo "скачан: ${3:-$2}" \
          || { echo "НЕ СКАЧАН: $2" >&2; exit 1; } ;;
  del)  curl -sS -H "X-Drop-Token: $DROP_TOKEN" -X DELETE "$U/$2" ;;
  *)    echo "usage: $0 list | up <file> | down <name> [dst] | del <name>" ;;
esac
