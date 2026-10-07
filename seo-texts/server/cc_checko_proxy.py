# -*- coding: utf-8 -*-
r"""Доп. ОКВЭД и выручка с checko.ru через прокси владельца (07.10: «для чеко прокси есть»).

Прокси и ссылки ротации — C:\sender\server\checko-proxies.json (только на сервере, не в git).
Причина прежних 429 — заголовки запроса (не браузерные), а не IP: с браузерными заголовками
checko отдаёт страницы. Бережно: каждый прокси — не чаще раза в 3 с, на 429 — ротация IP по
ссылке владельца и пауза. Неподключающийся прокси выпадает после первой проверки.

Вход: C:\sender\server\cc-fns.json (ОГРН из DaData; кому нужны доп. ОКВЭД/доход).
Выход (fsync, резюм по ИНН): C:\sender\server\cc-checko-proxy.jsonl -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import socks
import sockshandler

DIR = r'C:\sender\server'
ВЫХОД = os.path.join(DIR, 'cc-checko-proxy.jsonl')
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
     'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
     'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8', 'Upgrade-Insecure-Requests': '1', 'Sec-Fetch-Dest': 'document',
     'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1'}
ЕДИНИЦЫ = {'трлн': 1e12, 'млрд': 1e9, 'млн': 1e6, 'тыс': 1e3}
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


class Прокси:
    def __init__(self, п):
        u = urllib.parse.urlsplit(п['proxy'])
        self.ротация = п['rotate']
        self.op = urllib.request.build_opener(
            sockshandler.SocksiPyHandler(socks.SOCKS5, u.hostname, u.port, True, u.username, u.password))
        self.лок = threading.Lock()
        self.последний = 0.0

    def get(self, url):
        for попытка in range(4):
            with self.лок:
                пауза = 3.0 - (time.time() - self.последний)
                if пауза > 0:
                    time.sleep(пауза)
                self.последний = time.time()
                try:
                    r = self.op.open(urllib.request.Request(url, headers=H), timeout=40)
                    return r.status, r.read().decode('utf-8', 'replace')
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        try:
                            urllib.request.urlopen(self.ротация, timeout=40).read()
                        except Exception:  # noqa: BLE001
                            pass
                        time.sleep(25)
                        continue
                    return e.code, ''
                except Exception as e:  # noqa: BLE001
                    ошибка = repr(e)[:80]
                    time.sleep(5)
        return 'ошибка', ''


def текст(html):
    html = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).replace('&nbsp;', ' ')


def окведы(т):
    м = re.search(r'Основной вид деятельности|Виды деятельности', т)
    if м:
        т = т[м.start():]
    коды = []
    for к in re.findall(r'(?<![\d.])\d{2}\.\d{1,2}(?:\.\d{1,2})?(?![\d.])', т):
        if к not in коды:
            коды.append(к)
    return коды


def выручка(т):
    м = re.search(r'Выручка\s*=?\s*(?:выросла|снизилась|не изменилась)?\s*(?:до|на уровне)?\s*'
                  r'(\d[\d \u00a0]*(?:[.,]\d+)?)\s*(трлн|млрд|млн|тыс)?\.?\s*руб', т)
    if not м:
        return None, ''
    число = float(м.group(1).replace(' ', '').replace('\u00a0', '').replace(',', '.'))
    г = re.search(r'(?:за|в)\s+(20\d\d)\s+год', т[max(0, м.start() - 400):м.start() + 400])
    return int(число * ЕДИНИЦЫ.get(м.group(2) or '', 1)), (г.group(1) if г else '')


def main():
    прокси = [Прокси(п) for п in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
    живые = []
    for п in прокси:
        код, _ = п.get('https://checko.ru/')
        if код == 200:
            живые.append(п)
    фнс = json.load(io.open(os.path.join(DIR, 'cc-fns.json'), encoding='utf-8'))
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('итог') == 'ok':
                    сделано.add(з['inn'])
            except ValueError:
                pass
    задачи = []
    for инн, ф in фнс.items():
        if инн in сделано or not ф.get('огрн'):
            continue
        нужен_оквэд = len(ф.get('оквэд_все') or []) <= 1
        нужен_доход = not ф.get('доход')
        if нужен_оквэд or нужен_доход:
            задачи.append((инн, ф['огрн'], нужен_оквэд, нужен_доход))
    print('прокси живых', len(живые), 'из', len(прокси), '| задач', len(задачи), flush=True)
    if not живые:
        return

    def одна(k_задача):
        k, (инн, огрн, нужен_оквэд, нужен_доход) = k_задача
        п = живые[k % len(живые)]
        з = {'inn': инн, 'ogrn': огрн}
        if len(огрн) == 15:  # ИП: другой адрес, отчётности (выручки) у ИП на checko нет
            код, html = п.get('https://checko.ru/entrepreneur/%s' % огрн)
            з['activity'] = код
            if код == 200:
                з['оквэд_все'] = окведы(текст(html))
            з['итог'] = 'ok' if код == 200 else 'ошибка'
            записать(з)
            return
        if нужен_оквэд:
            код, html = п.get('https://checko.ru/company/%s/activity' % огрн)
            з['activity'] = код
            if код == 200:
                з['оквэд_все'] = окведы(текст(html))
        if нужен_доход:
            код, html = п.get('https://checko.ru/company/%s' % огрн)
            з['company'] = код
            if код == 200:
                з['выручка'], з['выручка_год'] = выручка(текст(html))
        з['итог'] = 'ok' if (з.get('activity') in (200, None) and з.get('company') in (200, None)) else 'ошибка'
        записать(з)

    t0 = time.time()
    with ThreadPoolExecutor(len(живые)) as ex:
        for k, _ in enumerate(ex.map(одна, enumerate(задачи))):
            if (k + 1) % 50 == 0:
                print('готово %d/%d за %d мин' % (k + 1, len(задачи), (time.time() - t0) / 60), flush=True)
    shutil.copyfile(ВЫХОД, r'C:\seostat\drop\drop-storage\cc-checko-proxy.jsonl')
    print('готово', flush=True)


if __name__ == '__main__':
    main()
