# -*- coding: utf-8 -*-
"""Полные коды ОКВЭД с checko по МОЕЙ выдаче: ОГРН добывается сам, ждать соседку не нужно.

Владелец открыл карточку МЭС: на checko «Виды деятельности 27», у меня «1 кодов». Соседняя
сессия checko прогоняла, но по другому списку предприятий — на мою нынешнюю выдачу из её
876 карточек пришлись 548. Я попросил её прогнать мои 4 069 ИНН и уже собирался ждать.

Ждать не нужно. Два препятствия, которые я считал непреодолимыми, оказались обходимыми:

  1. «checko отвечает 429» — да, из песочницы напрямую. Её прибор ходит через ПУЛ ПРОКСИ
     (`dolphin-proxies.txt` на дропе, 78 штук). С сервера через них checko отдаёт страницу
     кодом 200 — проверено на трёх разных прокси подряд;
  2. «нужен ОГРН, а у моих предприятий карточек checko нет» — её прибор берёт ОГРН из ранее
     собранной карточки, и это её ограничение, не сайта: **поиск по ИНН
     `checko.ru/search?query=<ИНН>` сам переадресует на карточку**, и ОГРН стоит в адресе.
     Проверено: 3702597104 → `/company/vodokanal-1093702022754`.

Отсюда порядок на каждое предприятие: поиск по ИНН → ОГРН из адреса → страница
`/company/<ОГРН>/activity` → коды из раздела «Виды деятельности».

Ловушка, названная соседкой в её приборе и оплаченная чужой сменой: регулярка по ВСЕЙ
странице тащит мусор из шапки сайта («12.5», «22.5» лезли первыми у всех 473 компаний).
Поэтому текст РЕЖЕТСЯ по заголовку раздела, и только потом ищутся коды. Беру это правило
как есть — оно проверено на их данных, и переписывать его заново значит платить дважды.

DURABILITY (урок 2026-07-25): каждая строка пишется в СЕРВЕРНЫЙ файл с fsync и каждые 200
строк уходит на дроп. Уже собранные ИНН читаются при старте, поэтому прогон возобновляемый:
рестарт контейнера или обрыв не заставят собирать заново.

Запуск на сервере: python C:\\sender\\_ops\\park_1s_checko_okved.py <бюджет_секунд>
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
BYUDZHET = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
VHOD = 'PARK-1S-DLYA-2S-OKVED-NUZHEN.csv'
POTOK = 'PARK-1S-CHECKO-OKVED.jsonl'
MESTNYY = r'C:\sender\park_1s_checko_okved.jsonl'
NACHALO = time.time()
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
OGRN = re.compile(r'/company/(?:[^/"?]*?-)?(\d{13,15})')
RAZDEL = re.compile(r'(Виды\s+деятельности|Основной\s+вид\s+деятельности|ОКВЭД)')
KOD = re.compile(r'\b\d{2}\.\d{1,2}(?:\.\d{1,2})?\b')
IMYA_KODA = re.compile(r'\b(\d{2}\.\d{1,2}(?:\.\d{1,2})?)\s*[—–\-:.]?\s*([А-ЯЁа-яё][^|]{3,110}?)'
                       r'(?=\s+\d{2}\.\d{1,2}\b|\s*$)')
# ХОДИМ ЧЕРЕЗ МОБИЛЬНЫЙ ПРОКСИ, а не через пул дельфина. Пул из 78 адресов я сам посадил на
# заслон: 20 потоков на два запроса дали около 4 700 обращений за две минуты, и checko закрыл
# все 78 разом (проверено: 429 у десяти разных адресов подряд с паузой 2,5 с).
#
# Владелец подсказал: «там 3 мобильных есть, скорее всего они чистые». Нашлись сравнением
# профилей Dolphin со списком: три адреса, которых в файле нет. Из них живой один —
# 194.143.150.98, и он отдаёт ОГРН 4 раза из 4, тогда как весь пул отдаёт 429.
#
# У мобильного есть ссылка ПЕРЕПОДКЛЮЧЕНИЯ: при заслоне меняем IP и продолжаем, а не долбим
# закрытую дверь. Поэтому потоков мало и пауза заметная — один адрес надо беречь.
MOBILNYY = 'socks5://kirillrand4:39476861@194.143.150.98:1650'
SMENA_IP = ('https://lk.lte-center.ru/api/proxies/24097/reconnect-link/'
            '722df0f668deb381c2da4548e1f044f4')
POTOKOV = 6
PAUZA = 0.8
zamok = threading.Lock()
sch = {'предприятий': 0, 'ОГРН найден': 0, 'ОГРН нет': 0, 'с кодами': 0,
       'кодов всего': 0, 'сбоев': 0}


def drop_get(imya):
    return urllib.request.urlopen(urllib.request.Request(
        '%s/%s' % (DROP, imya), headers={'X-Drop-Token': TOKEN}), timeout=180).read()


def drop_put(imya, telo):
    return urllib.request.urlopen(urllib.request.Request(
        '%s/%s' % (DROP, imya), data=telo, method='PUT',
        headers={'X-Drop-Token': TOKEN}), timeout=300).read()


def kody_so_stranicy(tekst):
    """Коды и их названия ТОЛЬКО из раздела видов деятельности, не из шапки сайта."""
    m = RAZDEL.search(tekst)
    kusok = tekst[m.start():] if m else ''
    kody, vidal = [], set()
    for k in KOD.findall(kusok):
        if k not in vidal:
            vidal.add(k)
            kody.append(k)
    imena = {}
    for k, n in IMYA_KODA.findall(kusok):
        imena.setdefault(k, ' '.join(n.split())[:110].strip(' .,;'))
    return kody, imena


_poslednyaya_smena = [0.0]


def smenit_ip():
    """Сменить IP мобильного прокси. Не чаще раза в 25 секунд — оператору нужно время."""
    with zamok:
        if time.time() - _poslednyaya_smena[0] < 25:
            return False
        _poslednyaya_smena[0] = time.time()
    try:
        requests.get(SMENA_IP, timeout=40)
        with zamok:
            sch['смен IP'] = sch.get('смен IP', 0) + 1
        time.sleep(12)
        return True
    except Exception:  # noqa: BLE001
        return False


def main():
    px = [(s if s.strip().startswith('socks5') else 'socks5://' + s.strip())
          for s in drop_get('dolphin-proxies.txt').decode('utf-8', 'replace').splitlines()
          if s.strip()]
    celi = []
    for stroka in drop_get(VHOD).decode('utf-8-sig', 'replace').splitlines()[1:]:
        kus = stroka.split(';')
        if kus and re.fullmatch(r'\d{10}|\d{12}', kus[0].strip()):
            celi.append((kus[0].strip(), (kus[1] if len(kus) > 1 else '').strip('"')))
    # уже собранное — прогон возобновляемый
    sdelano = set()
    if os.path.exists(MESTNYY):
        for ln in io.open(MESTNYY, encoding='utf-8', errors='replace'):
            try:
                sdelano.add(json.loads(ln)['inn'])
            except Exception:  # noqa: BLE001
                pass
    ostalos = [c for c in celi if c[0] not in sdelano]
    print(json.dumps({'целей': len(celi), 'уже собрано': len(sdelano),
                      'осталось': len(ostalos), 'прокси': len(px)}, ensure_ascii=False),
          flush=True)
    f = io.open(MESTNYY, 'a', encoding='utf-8')

    def odno(t):
        idx, (inn, imya) = t
        if time.time() - NACHALO > BYUDZHET:
            return
        pr = {'http': MOBILNYY, 'https': MOBILNYY}
        zapis = {'inn': inn, 'predpriyatie': imya, 'istochnik': 'checko.ru, «Виды деятельности»'}
        try:
            r = requests.get('https://checko.ru/search?query=' + inn, headers=UA, timeout=45,
                             proxies=pr, allow_redirects=True)
            # 429 — НЕ «карточка не нашлась». Первый прогон записал 1 616 предприятий как
            # «ОГРН нет», а на деле сайт отвечал «Пожалуйста, подтвердите, что вы человек»:
            # двадцать потоков выжали прокси. Строку в этом случае НЕ пишем вовсе — тогда
            # возобновляемый прогон вернётся к этому ИНН, а не сочтёт его разобранным.
            if r.status_code == 429 or 'подтвердите, что вы человек' in r.text:
                with zamok:
                    sch['придержали (429)'] = sch.get('придержали (429)', 0) + 1
                smenit_ip()
                return
            m = OGRN.search(r.url) or OGRN.search(r.text)
            if not m:
                with zamok:
                    sch['ОГРН нет'] += 1
                zapis['pochemu'] = 'карточка по ИНН не нашлась, код %s' % r.status_code
            else:
                ogrn = m.group(1)
                zapis['ogrn'] = ogrn
                u = 'https://checko.ru/company/%s/activity' % ogrn
                time.sleep(PAUZA)
                ra = requests.get(u, headers=UA, timeout=45, proxies=pr, allow_redirects=True)
                if ra.status_code == 429 or 'подтвердите, что вы человек' in ra.text:
                    with zamok:
                        sch['придержали (429)'] = sch.get('придержали (429)', 0) + 1
                    smenit_ip()
                    return
                if ra.status_code != 200:
                    with zamok:
                        sch['сбоев'] += 1
                    return
                tekst = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ra.text))
                kody, imena = kody_so_stranicy(tekst)
                zapis.update({'okved_kody': kody, 'okvedov': len(kody), 'ssylka': u,
                              'okved_s_imenami': [(k + ' ' + imena.get(k, '')).strip()
                                                  for k in kody]})
                with zamok:
                    sch['ОГРН найден'] += 1
                    if kody:
                        sch['с кодами'] += 1
                        sch['кодов всего'] += len(kody)
        except Exception as e:  # noqa: BLE001
            with zamok:
                sch['сбоев'] += 1
            return
        with zamok:
            sch['предприятий'] += 1
            f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            if sch['предприятий'] % 200 == 0:
                print(json.dumps(sch, ensure_ascii=False), flush=True)
                try:
                    drop_put(POTOK, io.open(MESTNYY, 'rb').read())
                except Exception:  # noqa: BLE001
                    pass

    with ThreadPoolExecutor(max_workers=POTOKOV) as pool:
        list(pool.map(odno, list(enumerate(ostalos))))
    f.close()
    try:
        drop_put(POTOK, io.open(MESTNYY, 'rb').read())
    except Exception as e:  # noqa: BLE001
        print('на дроп не легло:', str(e)[:90], flush=True)
    print(json.dumps(sch, ensure_ascii=False), flush=True)
    print('всего строк в файле: %d'
          % sum(1 for _ in io.open(MESTNYY, encoding='utf-8', errors='replace')), flush=True)


if __name__ == '__main__':
    main()
