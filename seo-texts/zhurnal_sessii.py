# -*- coding: utf-8 -*-
"""Журнал сессии на дропе: писать своё, следить за чужим.

Замысел владельца 30.07.2026: у всех сессий есть дроп, пусть каждая ведёт файл «что сделано,
какие выводы и ошибки», дописывает его, а чужие проверяет часто и отвечает.

Уговор по именам: `SESSIYA-1.md`, `SESSIYA-2.md`, `SESSIYA-3.md` — по номеру сессии. Первая
сессия развернула схему первой и уже следит за `SESSIYA-2/3.md`, поэтому имя взято её, а не моё
`ZHURNAL-*`: спорить об имени, когда чужая слежка уже запущена, значит остаться невидимым.

Две поправки к исходной схеме, обе по замеру, а не по вкусу:

1. **Следить по размеру нельзя.** Правка в середине файла или перезапись той же длины размера не
   меняют — изменение пройдёт молча. В листинге дропа есть `mtime`, поэтому признак изменения —
   пара `(bytes, mtime)`.
2. **Журнал только дописывается, новая запись снизу, с отметкой времени.** Если каждый
   перезаписывает файл целиком, «прочитать новое» превращается в сравнение версий. При дописывании
   новое — это просто хвост длиннее прежнего.

Заслон против потери своих же записей: перед дописыванием журнал СКАЧИВАЕТСЯ с дропа и запись
идёт в конец скачанного. Иначе две сессии, пишущие в один файл, затрут друг друга — а на дропе
последняя выгрузка выигрывает молча.

Использование:
    python3 zhurnal_sessii.py --zapis "текст записи"      # дописать и выгрузить
    python3 zhurnal_sessii.py --sled                      # следить за чужими (для Monitor)
    python3 zhurnal_sessii.py --chitat 1                  # показать чужой журнал целиком
"""
import json
import os
import subprocess
import sys
import time

BAZA = os.path.dirname(os.path.abspath(__file__))
DROP = os.path.join(BAZA, 'server', 'drop_client.sh')
MOY_NOMER = os.environ.get('ZHURNAL_NOMER', '3')
MOY = f'SESSIYA-{MOY_NOMER}.md'
# Схем имён на дропе оказалось две: первая сессия пишет `SESSIYA-1.md`, вторая — `ZHURNAL-2.md`
# со сторожем по шаблону `ZHURNAL-*.md`. Договариваться задним числом дороже, чем следить за
# обеими и держать свой журнал под обоими именами: невидимость хуже дублирования.
CHUZHIE = [f'{p}-{n}.md' for p in ('SESSIYA', 'ZHURNAL') for n in ('1', '2', '4')
           if n != MOY_NOMER]
RAB = os.environ.get('ZHURNAL_RAB', '/home/user/work/zhurnal')


def spisok():
    p = subprocess.run(['bash', DROP, 'list'], capture_output=True, text=True, timeout=120)
    try:
        return {f['name']: (f['bytes'], f['mtime']) for f in json.loads(p.stdout)}
    except Exception:  # noqa: BLE001  дроп мог ответить не-JSON; молчать нельзя, но и падать зря
        return {}


def skachat(imya, kuda):
    os.makedirs(kuda, exist_ok=True)
    # ВНИМАНИЕ: клиент пишет файл сам. Перенаправлять его вывод В ФАЙЛ нельзя — оболочка и curl
    # молча портят начало, файл потом читается, а заголовка нет (предупреждение соседней сессии).
    subprocess.run(['bash', DROP, 'down', imya], cwd=kuda, capture_output=True, timeout=300)
    p = os.path.join(kuda, imya)
    return open(p, encoding='utf-8', errors='replace').read() if os.path.exists(p) else ''


def vygruzit(put):
    p = subprocess.run(['bash', DROP, 'up', os.path.basename(put)],
                       cwd=os.path.dirname(put), capture_output=True, text=True, timeout=300)
    return '"ok":true' in p.stdout.replace(' ', '')


def zapisat(tekst):
    os.makedirs(RAB, exist_ok=True)
    bylo = skachat(MOY, RAB)
    put = os.path.join(RAB, MOY)
    metka = time.strftime('%d.%m %H:%M')
    with open(put, 'w', encoding='utf-8') as f:
        f.write((bylo.rstrip() + '\n\n' if bylo.strip() else '') + f'## {metka}\n\n{tekst}\n')
    ok = vygruzit(put)
    # Тот же текст выкладывается вторым именем: соседи следят по разным шаблонам.
    dubl = os.path.join(RAB, f'ZHURNAL-{MOY_NOMER}.md' if MOY.startswith('SESSIYA')
                        else f'SESSIYA-{MOY_NOMER}.md')
    with open(dubl, 'w', encoding='utf-8') as f:
        f.write(open(put, encoding='utf-8').read())
    ok2 = vygruzit(dubl)
    print(f'{"выгружено" if ok else "СБОЙ ВЫГРУЗКИ"}: {MOY} и {os.path.basename(dubl)}'
          f'{"" if ok2 else " (второе имя не легло)"}, стало {os.path.getsize(put)} байт')


def sled(pauza=10):
    """Печатает строку, когда чужой журнал изменился. Каждая строка — событие для наблюдателя."""
    bylo = {}
    s = spisok()
    for c in CHUZHIE:
        bylo[c] = s.get(c)
        if s.get(c):
            print(f'{c}: есть на дропе, {s[c][0]} байт', flush=True)
        else:
            print(f'{c}: пока нет на дропе', flush=True)
    while True:
        time.sleep(pauza)
        s = spisok()
        if not s:
            continue
        for c in CHUZHIE:
            if s.get(c) != bylo.get(c):
                staro = (bylo.get(c) or (0, 0))[0]
                novo = (s.get(c) or (0, 0))[0]
                print(f'ИЗМЕНИЛСЯ {c}: было {staro} байт, стало {novo}', flush=True)
                bylo[c] = s.get(c)


def main():
    if '--zapis' in sys.argv:
        zapisat(sys.argv[sys.argv.index('--zapis') + 1])
    elif '--sled' in sys.argv:
        sled(int(sys.argv[sys.argv.index('--pauza') + 1]) if '--pauza' in sys.argv else 10)
    elif '--chitat' in sys.argv:
        n = sys.argv[sys.argv.index('--chitat') + 1]
        print(skachat(f'SESSIYA-{n}.md', RAB) or f'SESSIYA-{n}.md пуст или отсутствует')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
