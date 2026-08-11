# -*- coding: utf-8 -*-
"""Мерит, есть ли на снимке-доказательстве хоть что-нибудь. Считает точки, а не файлы.

Владелец открыл `NOMER-7718560636-9022000976.png` и написал: «пустой скриншот». Так и есть —
белый лист 1600x1100, 7 676 байт, ноль не-белых точек. А в базе против этой строки стояло
**доказано=1**.

Причина ровно та же, что и в пяти поломках записи 141: прибор задавал вопрос, на который ему
удобно ответить. Съёмщик спрашивал «файл записался?» и «нашёлся ли номер в тексте страницы» —
оба ответа «да». Он НЕ спрашивал «на картинке что-нибудь нарисовано?». Текст в DOM был, а
кадр вышел белым (страница уводила себя редиректом уже после наших правок стилей — все 12
пустых весят байт в байт одинаково, то есть содержимое кадра одно и то же — пустота).

Мерка здесь — доля не-белых точек по всему кадру, считанная из самого PNG: разжать IDAT,
развернуть построчные фильтры, сравнить каждую точку с белым. Pillow на сервере нет, поэтому
разбор написан руками. Порог `ПУСТО` — меньше 0.1% чернил; на деле разрыв огромный:
у пустых 0.0000%, у следующего по бедности кадра 1.3% — промежутка нет вовсе.

Результат кладётся на дроп ФАЙЛОМ (durability, урок 2026-07-25): stdout раннера обрезан по
хвосту, а 99 строк в него не влезают, и по обрезанному числу нельзя ничего пересчитать.

Запуск на сервере: python C:\\sender\\_ops\\park_1s_snimok_chernila.py
"""
import json
import os
import struct
import zlib

KAT = r'C:\seostat\app\static\centro\dokaz'
DROP = r'C:\seostat\drop\drop-storage'
VYHOD = 'PARK-SNIMKI-CHERNILA.json'
PUSTO = 0.001  # доля не-белых точек, ниже которой кадр считается пустым


def raspakovat(put):
    """PNG -> (ширина, высота, каналов, сырые строки со снятыми фильтрами) без Pillow."""
    d = open(put, 'rb').read()
    if d[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('не PNG')
    i, w, h, bit, cvet, idat = 8, 0, 0, 0, 0, []
    while i + 8 <= len(d):
        dlina = struct.unpack('>I', d[i:i + 4])[0]
        tip = d[i + 4:i + 8]
        if tip == b'IHDR':
            w, h, bit, cvet = struct.unpack('>IIBB', d[i + 8:i + 18])
        elif tip == b'IDAT':
            idat.append(d[i + 8:i + 8 + dlina])
        elif tip == b'IEND':
            break
        i += 12 + dlina
    if bit != 8 or cvet not in (2, 6):
        raise ValueError('глубина %d, цвет %d — не разбираю' % (bit, cvet))
    return w, h, (3 if cvet == 2 else 4), zlib.decompress(b''.join(idat))


def dolya_chernil(put):
    """Доля точек, отличных от белого. 0.0 — чистый белый лист."""
    w, h, kan, syro = raspakovat(put)
    shag = w * kan
    prev = bytearray(shag)
    ne_belyh = 0
    p = 0
    for _ in range(h):
        f = syro[p]
        p += 1
        stroka = bytearray(syro[p:p + shag])
        p += shag
        if f == 1:
            for x in range(kan, shag):
                stroka[x] = (stroka[x] + stroka[x - kan]) & 255
        elif f == 2:
            for x in range(shag):
                stroka[x] = (stroka[x] + prev[x]) & 255
        elif f == 3:
            for x in range(shag):
                a = stroka[x - kan] if x >= kan else 0
                stroka[x] = (stroka[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(shag):
                a = stroka[x - kan] if x >= kan else 0
                b = prev[x]
                c = prev[x - kan] if x >= kan else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                stroka[x] = (stroka[x] + pr) & 255
        for x in range(0, shag, kan):
            if stroka[x] < 245 or stroka[x + 1] < 245 or stroka[x + 2] < 245:
                ne_belyh += 1
        prev = stroka
    return ne_belyh / float(w * h), w, h


if __name__ == '__main__':
    itog = []
    for f in sorted(os.listdir(KAT)):
        if not (f.startswith('NOMER-') and f.endswith('.png')):
            continue
        put = os.path.join(KAT, f)
        zapis = {'imya': f, 'bayt': os.path.getsize(put)}
        chasti = f[:-4].split('-')
        if len(chasti) == 3:
            zapis['inn'], zapis['nomer'] = chasti[1], chasti[2]
        try:
            d, w, h = dolya_chernil(put)
            zapis.update({'chernila': round(d, 6), 'shirina': w, 'vysota': h,
                          'pustoy': 1 if d < PUSTO else 0})
        except Exception as e:  # noqa: BLE001
            zapis.update({'chernila': None, 'pustoy': 1, 'oshibka': repr(e)[:80]})
        itog.append(zapis)

    os.makedirs(DROP, exist_ok=True)
    put_v = os.path.join(DROP, VYHOD)
    with open(put_v, 'w', encoding='utf-8') as f:
        json.dump(itog, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    pustyh = sum(z['pustoy'] for z in itog)
    print('снимков %d | ПУСТЫХ %d | с содержимым %d' % (len(itog), pustyh, len(itog) - pustyh))
    bednye = sorted((z for z in itog if not z['pustoy']), key=lambda z: z['chernila'])[:3]
    print('самые бедные из непустых: %s'
          % ', '.join('%.2f%%' % (z['chernila'] * 100) for z in bednye))
    print('положено на дроп: %s (%d байт)' % (VYHOD, os.path.getsize(put_v)))
