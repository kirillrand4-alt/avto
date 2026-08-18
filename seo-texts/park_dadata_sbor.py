# -*- coding: utf-8 -*-
"""Руководитель, адрес, статус и основной ОКВЭД по всем ИНН парка — задачей `dadata`.

ЗАЧЕМ ИМЕННО ЭТО. На 2 146 предприятий с доказанной машиной у меня было 42 имени. DaData
отдаёт ФИО руководителя с должностью из ЕГРЮЛ по каждому ИНН — это не технический ЛПР, но
это ИМЯ из официального реестра, и оно есть у всех. Плюс статус: ликвидированные отсеиваются
до звонка, а не после.

ДВЕ ПОПРАВКИ, ОПЛАЧЕННЫЕ ЗДЕСЬ ЖЕ, чтобы не платить второй раз:
  1) ключ задачи — `companies`, а не `inns`. С `inns` ответ приходит ПУСТЫМ и выглядит как
     «инструмент не работает»: results [], count 0, ошибки нет. Тихий ноль.
  2) `407 Proxy`, который я поймал раньше, приходил НЕ от dadata, а изнутри
     `enrich_contacts`: там она вызывается через глобальный опенер. Отдельная задача
     `dadata` ходит мимо него и отвечает за 0,6 c. Это то, о чём предупреждала 1-я сессия.

Пачками по 200: ответ раннера идёт одним куском, а его хвост обрезается.
"""
import csv
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
VHOD = os.path.join(L, 'PARK-CELI-CHECKO-2S.csv')
POTOK = os.path.join(L, 'PARK-DADATA-2S.jsonl')
PACHKA = int(os.environ.get('PACHKA', '200'))


def main():
    celi = [r['inn'] for r in csv.DictReader(io.open(VHOD, encoding='utf-8-sig'), delimiter=';')
            if r.get('inn')]
    gotovo = set()
    if os.path.exists(POTOK):
        for l in io.open(POTOK, encoding='utf-8'):
            try:
                gotovo.add(json.loads(l)['inn'])
            except Exception:  # noqa: BLE001
                pass
    celi = [i for i in celi if i not in gotovo]
    print('к обходу %d (уже сделано %d)' % (len(celi), len(gotovo)), flush=True)
    f = io.open(POTOK, 'a', encoding='utf-8')
    sch = {'спрошено': 0, 'найдено': 0, 'с руководителем': 0, 'ликвидировано': 0}
    for i in range(0, len(celi), PACHKA):
        kus = celi[i:i + PACHKA]
        r = R.submit('dadata', {'companies': [{'inn': x} for x in kus]}, timeout=600)
        for z in ((r.get('data') or {}).get('results') or []):
            sch['спрошено'] += 1
            if z.get('full_name'):
                sch['найдено'] += 1
            if z.get('mgmt_name'):
                sch['с руководителем'] += 1
            if (z.get('status') or '') not in ('ACTIVE', ''):
                sch['ликвидировано'] += 1
            z['istochnik'] = 'DaData findById/party (ЕГРЮЛ)'
            z['ssylka'] = 'https://egrul.nalog.ru/index.html?query=' + str(z.get('inn') or '')
            f.write(json.dumps(z, ensure_ascii=False) + '\n')
        f.flush()
        print('  %d/%d: %s' % (min(i + PACHKA, len(celi)), len(celi), sch), flush=True)
        time.sleep(1)
    f.close()
    print('ГОТОВО:', sch, '→', POTOK)


if __name__ == '__main__':
    main()
