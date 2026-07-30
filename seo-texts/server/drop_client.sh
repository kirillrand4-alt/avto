#!/bin/bash
# Клиент обменника parsercompressor.online/drop для сессий Claude Code.
# Токен и URL берутся из окружения: DROP_TOKEN, DROP_URL (задать в env-настройках окружения).
# Использование: drop_client.sh list | up <file> | down <name> [dst] | del <name>
U="${DROP_URL:-https://parsercompressor.online/drop}"
[ -z "$DROP_TOKEN" ] && { echo "нет DROP_TOKEN в окружении"; exit 1; }
# `down` проверяет КОД ОТВЕТА и пишет файл только при 200. Прежде было
# `curl -s "$U/$2" -o "${3:-$2}" && echo "скачан: …"`, и это молча портило данные: curl кладёт
# тело ответа при ЛЮБОМ коде, выходит с нулём, скрипт печатает «скачан», а в файле лежит
# 404-страница дропа. Поймано 30.07.2026 на живом `down ZHURNAL-1.md`: в файле оказался
# `<!doctype html><title>404 Not Found</title>`, и он прекрасно читался как текст. Тот же класс,
# что `down файл > файл` из предупреждения соседей, только срабатывает и при верном вызове.
# Скачивание идёт во временный файл: при сбое прежняя копия остаётся целой, а не затирается.
case "$1" in
  list) curl -s -H "X-Drop-Token: $DROP_TOKEN" "$U/list" | python3 -m json.tool ;;
  up)   curl -s -H "X-Drop-Token: $DROP_TOKEN" -T "$2" "$U/$(basename "$2")" ;;
  down) DST="${3:-$2}"; TMP="$DST.chast"
        KOD=$(curl -s -H "X-Drop-Token: $DROP_TOKEN" "$U/$2" -o "$TMP" -w '%{http_code}')
        if [ "$KOD" = "200" ]; then mv -f "$TMP" "$DST"; echo "скачан: $DST"
        else rm -f "$TMP"; echo "СБОЙ: HTTP $KOD на $2, файл не тронут" >&2; exit 1; fi ;;
  del)  curl -s -X DELETE -H "X-Drop-Token: $DROP_TOKEN" "$U/$2" ;;
  *)    echo "usage: $0 list | up <file> | down <name> [dst] | del <name>" ;;
esac
