# -*- coding: utf-8 -*-
# 19.10, владелец: «посмотри чеко… добавь прокси мобильные… и закинь в 10 потоков». Вместо недельного DaData (лимит 10 тыс./сут)
# — карточки checko.ru по ИНН (поиск ?query=<ИНН> сразу ведёт на карточку) через прокси владельца (checko-proxies.json, темп и
# ротация — cc_checko_proxy). Что берём: статус, основной ОКВЭД, выручка и год, руководитель, юр. адрес/регион, телефоны с
# карточки (tel:), счётчики «Госзакупки»/«Проверки», ссылка на карточку (источник). Очередь: изготовители ФСА после отсева
# (не «нет»), кого нет в fsa-meyer-dadata.jsonl; сначала с почтой, потом с телефоном, затем остальные.
# Durable: fsa-meyer-checko.jsonl (fsync, резюм по ИНН) + дроп. Лог: fsa_checko2_*.log.
import io, json, os, re, shutil, sys, threading, time
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'fsa-meyer-checko.jsonl')
ПОТОКОВ = int(os.environ.get('CHECKO_POTOKOV', '10'))
if __name__ == '__main__' and '--vnutri' not in sys.argv:
    import subprocess
    лог = os.path.join(DIR, 'fsa_checko2_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'fsa_meyer_checko.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                             close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    time.sleep(90)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import cc_checko_proxy as CP  # noqa: E402
CP.ВЫХОД = ВЫХ
_лок = threading.Lock()
СТАТУС = re.compile(r'(Действующ\w+ (?:компания|организация|предприятие|ИП)|в процессе ликвидации|ликвидирован\w*|'
                    r'прекратил\w* деятельность|банкротств\w*|в процессе реорганизации|недействующ\w*)', re.I)
РУК = re.compile(r'(Генеральный директор|Директор|Президент|Управляющий|Управляющая компания|Председатель\w*|'
                 r'Руководитель|Исполнительный директор)\s+([А-ЯЁ][а-яё-]+ [А-ЯЁ][а-яё-]+(?: [А-ЯЁ][а-яё-]+)?)')
АДРЕС = re.compile(r'(\d{6}), ([^,]{3,60}?(?:область|край|Республика|автономный округ|г\. Москва|г\. Санкт-Петербург|'
                   r'г\. Севастополь|Кузбасс)[^,]{0,25})')


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def читать(путь):
    if not os.path.exists(путь):
        return []
    out = []
    for s in io.open(путь, encoding='utf-8', errors='replace'):
        try:
            out.append(json.loads(s))
        except ValueError:
            pass
    return out


def разобрать(html):
    т = CP.текст(html)
    з = {}
    м = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    з['ссылка'] = м.group(1) if м else ''
    м = СТАТУС.search(т)
    з['статус'] = м.group(1) if м else ''
    ок = CP.окведы(т)
    з['оквэд'] = ок[0] if ок else ''
    з['оквэд_все'] = ок[:40]  # основной + дополнительные (блок «Виды деятельности» карточки)
    з['выручка'], з['выручка_год'] = CP.выручка(т)
    м = РУК.search(т)
    з['руководитель'] = (м.group(2) if м else '')
    з['должность'] = (м.group(1) if м else '')
    м = АДРЕС.search(т)
    з['регион'] = м.group(2).strip() if м else ''
    з['телефоны'] = sorted(set(re.findall(r'href="tel:(\+?\d{10,12})"', html)))[:6]
    for метка, ключ in (('Госзакупки', 'госзакупки'), ('Проверки и КНМ', 'проверки')):
        м = re.search(re.escape(метка) + r'\s+(\d+)', т)
        з[ключ] = int(м.group(1)) if м else 0
    return з


def main():
    t0 = time.time()
    отсев = {}
    for y in читать(os.path.join(DIR, 'fsa-meyer-otsev.jsonl')):
        if y.get('инн'):
            отсев[y['инн']] = y.get('ответ')
    уже = {y['инн'] for y in читать(os.path.join(DIR, 'fsa-meyer-dadata.jsonl')) if y.get('инн') and y.get('статус')}
    уже |= {y['inn'] for y in читать(ВЫХ) if y.get('inn') and y.get('итог') == 'ok' and 'оквэд_все' in y}
    конт = {y['инн']: y for y in читать(os.path.join(DIR, 'fsa-meyer-kontakty2.jsonl')) if y.get('инн')}
    изг = [z for z in читать(os.path.join(DIR, 'fsa-meyer-izg.jsonl')) if z.get('инн') and отсев.get(z['инн']) != 'нет'
           and z['инн'] not in уже]

    def приоритет(z):
        к = конт.get(z['инн']) or {}
        почта = bool(к.get('почты') or z.get('почты'))
        тел = bool(к.get('телефоны') or z.get('телефоны'))
        return (0 if почта else 1 if тел else 2, len(z['инн']) != 10, -(z.get('деклараций') or 0))
    изг.sort(key=приоритет)
    очередь = [z['инн'] for z in изг]
    прокси = [CP.Прокси(x) for x in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
    # 19.10: замер — медленные/рвущие ответ прокси (16 с, IncompleteRead) держали потоки: 37 карточек в минуту на 10 потоках.
    # Берём только быстрые (ответ до 5 с), и у каждого потока СВОЙ прокси (раньше потоки сталкивались на одном и ждали паузу 3 с)
    живые = []
    for x in прокси:
        t_ = time.time()
        if x.get('https://checko.ru/')[0] == 200 and time.time() - t_ < 5:
            живые.append(x)
    п('прокси живых', len(живые), 'из', len(прокси), '| к проходу', len(очередь), '| уже есть (DaData/checko)', len(уже),
      '| с почтой', sum(1 for z in изг if приоритет(z)[0] == 0))
    if not живые:
        return
    всего = len(очередь)
    n = [0]

    def поток(k):
        while True:
            with _лок:
                if not очередь:
                    return
                инн = очередь.pop(0)
            px = живые[k % len(живые)]
            код, html = px.get('https://checko.ru/search?query=%s' % инн)
            з = {'inn': инн, 'код': код}
            if код == 200 and html:
                try:
                    з.update(разобрать(html))
                except Exception as e:  # noqa: BLE001
                    з['ошибка_разбора'] = repr(e)[:80]
                карточка = re.search(r'/(company|entrepreneur)/', з.get('ссылка') or '')
                з['итог'] = 'ok' if карточка else 'не найдена'
            else:
                з['итог'] = 'ошибка'
            CP.записать(з)
            with _лок:
                n[0] += 1
                if n[0] % 500 == 0:
                    п('пройдено', n[0], 'из', всего, '| %.0f в мин' % (n[0] / max(1, (time.time() - t0) / 60)))

    тт = [threading.Thread(target=поток, args=(k,)) for k in range(min(ПОТОКОВ, len(живые)))]
    for т in тт:
        т.start()
    for т in тт:
        т.join()
    shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
    все = {y['inn']: y for y in читать(ВЫХ)}
    п('===ИТОГ===', json.dumps({'всего': len(все), 'ok': sum(1 for y in все.values() if y.get('итог') == 'ok'),
                                'действующих': sum(1 for y in все.values() if 'ействующ' in (y.get('статус') or '')),
                                'с выручкой': sum(1 for y in все.values() if y.get('выручка'))}, ensure_ascii=False),
      'за %.1f ч' % ((time.time() - t0) / 3600))


if __name__ == '__main__':
    main()
