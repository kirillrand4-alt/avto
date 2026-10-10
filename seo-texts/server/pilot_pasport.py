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
    for x in список:
        if x['inn'] in был_сайт and MN.домен(был_сайт[x['inn']]) != MN.домен(x['site']):
            x['pererazbor'] = True
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
