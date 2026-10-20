# -*- coding: utf-8 -*-
# 20.10, владелец: «давай сначала из ФНС, потом чеко» — выручка (доход 2025, открытые данные ФНС revexp.zip на сервере) для
# юрлиц из деклараций ФСА (вход — дроп fsa-fns-vhod.json, список ИНН). Без моделей. Выход: fsa-fns-dohod.jsonl (fsync) + дроп.
import io, json, os, shutil, time, zipfile
import xml.etree.ElementTree as ET
ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХ = r'C:\sender\server\fsa-fns-dohod.jsonl'
t0 = time.time()
инн = set(json.load(io.open(os.path.join(ДРОП, 'fsa-fns-vhod.json'), encoding='utf-8')))
д = {}
z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
for zi in z.infolist():
    with z.open(zi) as fh:
        for ev, el in ET.iterparse(fh, events=('end',)):
            if not el.tag.endswith('Документ'):
                continue
            i = v = None
            for ch in el:
                if 'СведНП' in ch.tag:
                    i = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                elif 'ДохРасх' in ch.tag:
                    v = ch.get('СумДоход')
            if i in инн and v:
                try:
                    д[i] = float(v)
                except ValueError:
                    pass
            el.clear()
with io.open(ВЫХ, 'w', encoding='utf-8') as f:
    for i, v in д.items():
        f.write(json.dumps({'инн': i, 'доход_2025': v}, ensure_ascii=False) + '\n')
    f.flush()
    os.fsync(f.fileno())
shutil.copyfile(ВЫХ, os.path.join(ДРОП, 'fsa-fns-dohod.jsonl'))
print('===ИТОГ===', json.dumps({'запрошено': len(инн), 'найдено': len(д)}), 'за %.1f мин' % ((time.time() - t0) / 60))
