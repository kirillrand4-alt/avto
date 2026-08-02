# -*- coding: utf-8 -*-
"""Прочитать файл из хранилища дропа НАПРЯМУЮ с диска сервера.

Понадобилось потому, что HTTP-отдача дропа падает с 400 на именах с пробелом
и кириллицей («ВСЕМ сессиям.txt»): ни одна из четырёх кодировок пути не
прошла. Файл при этом на диске есть — то есть «не скачивается» и «нет файла»
это разные вещи, и различать их надо до того, как решишь, что данных нет.

Запуск: python chitat_drop.py "<имя файла>" [сколько_байт]
"""
import os
import sys

ДРОП = r'C:\seostat\drop\drop-storage'


def main():
    имя = sys.argv[1] if len(sys.argv) > 1 else ''
    предел = int(sys.argv[2]) if len(sys.argv) > 2 else 200000
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        # не молчим: показываем похожие имена, чтобы отличить опечатку от
        # реального отсутствия
        похожие = [н for н in os.listdir(ДРОП)
                   if имя.split()[0].lower() in н.lower()] if имя else []
        print(f'НЕТ ФАЙЛА: {имя}')
        for н in похожие[:10]:
            print('  похоже на:', н)
        return
    with open(п, 'rb') as ф:
        blob = ф.read(предел)
    print(f'=== {имя}, {os.path.getsize(п)} байт ===')
    print(blob.decode('utf-8', 'replace'))


if __name__ == '__main__':
    main()
