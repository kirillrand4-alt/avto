# -*- coding: utf-8 -*-
r"""Опись распакованного архива «01. НАШИ ПРОЕКТЫ - КЦ» (C:\seostat\kc-proekty) для соседней сессии (08.10):
CSV (путь, папка верхнего уровня, имя, расширение, размер, дата изменения) + сводка по папкам и расширениям.
Выход: C:\sender\server\kc-proekty-opis.csv и kc-proekty-opis-svodka.json (+ дроп)."""
import collections, csv, io, json, os, shutil, time
КОРЕНЬ = r'C:\seostat\kc-proekty\01. НАШИ ПРОЕКТЫ - КЦ'
ДРОП = r'C:\seostat\drop\drop-storage'
п_csv = r'C:\sender\server\kc-proekty-opis.csv'
п_св = r'C:\sender\server\kc-proekty-opis-svodka.json'
папки, расш, всего, байт = collections.Counter(), collections.Counter(), 0, 0
байт_папки = collections.Counter()
with io.open(п_csv, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['Путь (от корня архива)', 'Папка верхнего уровня', 'Имя файла', 'Расширение', 'Размер, байт', 'Изменён'])
    for d, _, ff in os.walk(КОРЕНЬ):
        for имя in ff:
            if имя.lower() == 'thumbs.db':
                continue
            п = os.path.join(d, имя)
            отн = os.path.relpath(п, КОРЕНЬ)
            верх = отн.split(os.sep)[0] if os.sep in отн else '(корень)'
            try:
                st = os.stat(п)
            except OSError:
                continue
            р = os.path.splitext(имя)[1].lower() or '(нет)'
            w.writerow([отн, верх, имя, р, st.st_size, time.strftime('%Y-%m-%d', time.localtime(st.st_mtime))])
            папки[верх] += 1
            байт_папки[верх] += st.st_size
            расш[р] += 1
            всего += 1
            байт += st.st_size
    f.flush(); os.fsync(f.fileno())
св = {'корень': КОРЕНЬ, 'файлов': всего, 'ГБ': round(байт / 1e9, 2),
      'папки_верхнего_уровня': {k: {'файлов': v, 'ГБ': round(байт_папки[k] / 1e9, 2)} for k, v in папки.most_common()},
      'расширения': dict(расш.most_common(40))}
with io.open(п_св, 'w', encoding='utf-8') as f:
    json.dump(св, f, ensure_ascii=False, indent=1); f.flush(); os.fsync(f.fileno())
for п in (п_csv, п_св):
    shutil.copyfile(п, os.path.join(ДРОП, os.path.basename(п)))
print('===ИТОГ===')
print(json.dumps({k: св[k] for k in ('файлов', 'ГБ')}, ensure_ascii=False), json.dumps(dict(list(св['папки_верхнего_уровня'].items())[:15]), ensure_ascii=False)[:2500])
print(json.dumps(dict(list(св['расширения'].items())[:15]), ensure_ascii=False))
