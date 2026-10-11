# -*- coding: utf-8 -*-
r"""Паспорт сайта для компаний набора (владелец 09.10: «проверь, как определялся паспорт компании — будет ли он хоть как-то
похоже определяться?»). Тот же механизм, что у старой базы: site_facts.sobrat — карточка по страницам из кэша
(<ИНН>.json.gz кладёт обход kc_kontakty), модель FACTS_MODEL (по умолчанию gpt-5.6-luna), новости — FACTS_NEWS_MODEL;
запись в enrich.db, таблица site_facts (сервер, переживает рестарт). Сверка фактов со страницами — pasport_sverka.py,
годность к письму — godnost.py: работают по той же таблице.
Для Excel карточки набора выгружаются в <набор>-pasport.jsonl (-> дроп).
"""
import io
import json
import os
import shutil
import sqlite3
import sys

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import site_facts as SF  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-pasport.jsonl')


def транспорт_кусками():
    """11.10: паспорт в 24 потока — 877 обрывов «[WinError 10054]» за 45 мин, 9–19 паспортов/мин, а журнал шлюза видит
    почти все дошедшие вызовы успешными (Luna 5.6: 208 ok / 6 ош за 15 мин). Диагноз уже записан в verify_company
    (_provider_call_stdlib, инцидент 24.07): маршрут сервера до шлюза душит большие POST-тела одним куском, проходит
    gzip + chunked мелкими кусками с паузами. Обход и аудит ходят так и обрывов не видят; паспорт шлёт ~100 КБ страниц
    через gen_provider одним куском. Подмена ТОЛЬКО в этом процессе: httpx.stream/httpx.post внутри gen_provider ->
    тот же запрос (заголовки, тело, модель, рассуждение, лимит ответа — как были) сжатым телом кусками по 1200 байт,
    соединение с перебором адресов шлюза (verify_company._HTTPSPerebor, если импортируется)."""
    import contextlib
    import gzip
    import http.client
    import time
    import urllib.parse
    import httpx
    import gen_provider as GP
    try:
        import verify_company as VC
        соединение = VC._HTTPSPerebor
    except Exception:  # noqa: BLE001
        соединение = http.client.HTTPSConnection

    class Ответ:
        def __init__(self, rs):
            self._rs, self.status_code, self.request, self._тело = rs, rs.status, None, None

        def read(self):
            if self._тело is None:
                self._тело = self._rs.read()
            return self._тело

        @property
        def text(self):
            return self.read().decode('utf-8', 'replace')

        def json(self):
            return json.loads(self.text)

        def iter_lines(self):
            for сырая in self._rs:
                yield сырая.decode('utf-8', 'replace').rstrip('\r\n')

    def послать(url, headers, тело, timeout):
        u = urllib.parse.urlsplit(url)
        gz = gzip.compress(json.dumps(тело, ensure_ascii=False).encode('utf-8'), 6)

        def куски():
            for i in range(0, len(gz), 1200):
                yield gz[i:i + 1200]
                time.sleep(0.15)
        загл = {k: v for k, v in (headers or {}).items() if k.lower() not in ('content-length', 'content-encoding')}
        загл['content-type'] = 'application/json'
        загл['content-encoding'] = 'gzip'
        cn = соединение(u.hostname, timeout=min(float(timeout or 240), 240))
        cn.request('POST', (u.path or '/') + ('?' + u.query if u.query else ''), body=куски(), headers=загл)
        return cn, cn.getresponse()

    @contextlib.contextmanager
    def stream(method, url, headers=None, json=None, timeout=None, **_):  # noqa: A002
        cn, rs = послать(url, headers, json, timeout)
        try:
            yield Ответ(rs)
        finally:
            cn.close()

    def post(url, headers=None, json=None, timeout=None, **_):  # noqa: A002
        cn, rs = послать(url, headers, json, timeout)
        try:
            о = Ответ(rs)
            о.read()
            return о
        finally:
            cn.close()
    class Шим:  # остальное (классы исключений и пр.) — из настоящего httpx
        def __getattr__(self, имя):
            return getattr(httpx, имя)
    шим = Шим()
    шим.stream, шим.post = stream, post
    GP.httpx = шим


if os.environ.get('PASPORT_KUSKAMI', '1') == '1':
    транспорт_кусками()


def main():
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    конт = {}
    for s in io.open(os.path.join(DIR, НАБОР + '-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        з = json.loads(s)
        if з.get('итог') == 'ok' and any(ст == 'ok' for _, ст in з.get('страницы', [])):
            конт[з['inn']] = з
    список = [{'inn': i, 'name': сп[i]['имя'] or '', 'site': конт[i]['сайт']} for i in конт if i in сп]
    # 10.10: паспорт собран по прежнему сайту (чужой сайт заменён своим) — собрать заново по текущему
    import meyer_nalichie as MN
    _ro = sqlite3.connect('file:%s?mode=ro' % SF.BD.replace('\\', '/'), uri=True, timeout=60)
    был_сайт = {str(r[0]): r[1] or '' for r in _ro.execute("select inn, site from site_facts where coalesce(site,'')<>''")}
    _ro.close()
    # 11.10: паспорта, собранные в окне PASPORT_PEREDELAT='от|до' (ts site_facts), — собрать заново: сравнение на одних и
    # тех же 14 компаниях — Luna 6 даёт вдвое меньше оборудования линий, контроля качества и мощностей, чем Luna 5.6
    # (12/20, 6/12, 6/12 элементов); новые факты сливаются со старыми (site_facts._sliyanie), ничего не теряется
    окно = os.environ.get('PASPORT_PEREDELAT', '')
    переделать = set()
    if '|' in окно:
        от, до = окно.split('|', 1)
        _ro = sqlite3.connect('file:%s?mode=ro' % SF.BD.replace('\\', '/'), uri=True, timeout=60)
        переделать = {str(r[0]) for r in _ro.execute("select inn from site_facts where ts >= ? and ts < ? and "
                                                     "coalesce(facts_json,'')<>''", (от, до))}
        _ro.close()
    for x in список:
        if x['inn'] in был_сайт and MN.домен(был_сайт[x['inn']]) != MN.домен(x['site']):
            x['pererazbor'] = True
        if x['inn'] in переделать:
            x['pererazbor'] = True
    if переделать:
        print('паспорт заново (окно %s):' % окно, sum(1 for x in список if x['inn'] in переделать), flush=True)
    print('компаний с открывшимся сайтом', len(список), 'паспорт заново (сайт сменился)',
          sum(1 for x in список if x.get('pererazbor')), flush=True)
    итог = SF.sobrat(predel=len(список), spisok=список, potokov=int(os.environ.get('PASPORT_POTOKOV', '8')))
    print('сбор', json.dumps(итог, ensure_ascii=False), flush=True)
    c = sqlite3.connect(SF.BD, timeout=120)
    n = 0
    with io.open(ВЫХОД, 'w', encoding='utf-8') as f:
        for i in (x['inn'] for x in список):
            р = c.execute('select facts_json from site_facts where inn=?', (i,)).fetchone()
            if р and р[0]:
                f.write(json.dumps({'inn': i, 'паспорт': json.loads(р[0])}, ensure_ascii=False) + '\n')
                n += 1
        f.flush()
        os.fsync(f.fileno())
    c.close()
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    print('готово, паспортов', n, flush=True)


if __name__ == '__main__':
    main()
