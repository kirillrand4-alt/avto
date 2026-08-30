# -*- coding: utf-8 -*-
r"""Кандидаты в сайты: подтвердить доказанные, дообойти нетронутые, повторить упавшие.

Владелец 30.08 по трём пунктам разбора группы «только cand_site» (мейер, 8 618):
  1) повысить кандидата до сайта там, где принадлежность доказана;
  2) нетронутых — в очередь обхода;
  3) по «не открылся» сделать второй заход.

ЧТО СЧИТАЕТСЯ ДОКАЗАТЕЛЬСТВОМ. Только улика со страницы этого же домена:
  * ИНН предприятия найден на странице его кандидата — самый сильный признак;
  * наш сбор снял с этого домена адрес, который лёг компании в карточку.
Мнение поисковика доказательством не считается: кандидат и берётся из выдачи.
Компании с вердиктом `mismatch` («провайдер прочитал страницу: сайт чужой») не
повышаем никогда, даже если улика есть, — вердикт весомее совпадения домена.

ОБРАТИМОСТЬ. Каждое повышение пишется в журнал на сервере до записи в базу:
ИНН, домен, чем доказано. Откатить — вернуть cand_site и очистить site по журналу.

    python kandidaty_sajtov.py                 посчитать, ничего не трогая
    python kandidaty_sajtov.py --delat         выполнить все три пункта
    python kandidaty_sajtov.py --delat --vsya-baza   не только мейер
"""
import json
import os
import re
import sqlite3
import sys
import time

ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
НАХОДКИ = os.environ.get('RAZBOR_DB', r'D:\razbor-nahodki.db')
ZENNO = os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ЖУРНАЛ = r'C:\sender\server\kandidaty-sajtov.jsonl'


def _журнал(записи):
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        for з in записи:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _домен(строка):
    d = re.sub(r'^https?://', '', str(строка or '').strip().lower()).split('/')[0]
    return d[4:] if d.startswith('www.') else d


def _родня(a, b):
    return bool(a) and bool(b) and (a == b or a.endswith('.' + b))


def разбор(вся_база=False):
    где = '' if вся_база else " and coalesce(division,'') like '%meyer%'"
    E = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True,
                        timeout=120)
    канд, чужие = {}, set()
    for i, c, v in E.execute(
            "select inn, cand_site, coalesce(verified,'') from companies "
            "where coalesce(site,'')='' and coalesce(cand_site,'')<>''" + где):
        i = str(i)
        d = _домен(c)
        if not d:
            continue
        канд[i] = d
        if v == 'mismatch':
            чужие.add(i)
    # улика первая: адрес снят с этого же домена
    адресом = set()
    for i, u in E.execute("select inn, coalesce(source_url,'') from emails "
                          "where coalesce(source_url,'')<>''"):
        i = str(i)
        if i in канд and _родня(_домен(u), канд[i]):
            адресом.add(i)
    E.close()
    # улика вторая: ИНН найден на странице этого же домена
    инном = set()
    try:
        N = sqlite3.connect('file:%s?mode=ro' % НАХОДКИ.replace('\\', '/'),
                            uri=True, timeout=120)
        for i, urls in N.execute('select inn, coalesce(adresa_url,\'[]\') '
                                 'from inn_na_stranicah where s_innom>0'):
            i = str(i)
            if i not in канд:
                continue
            try:
                спис = json.loads(urls)
            except Exception:  # noqa: BLE001
                спис = []
            if any(_родня(_домен(u), канд[i]) for u in спис):
                инном.add(i)
        N.close()
    except sqlite3.Error:
        pass
    доказано = (адресом | инном) - чужие
    # нетронутые и упавшие
    def множество(файл, поле=0):
        s = set()
        try:
            with open(os.path.join(ZENNO, файл), encoding='utf-8',
                      errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        s.add(line.split(';')[поле].strip())
        except OSError:
            pass
        return s
    очередь = множество('ochered.txt')
    не_открылись = множество('ne_otkrylis.txt')
    try:
        кэш = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}
    except OSError:
        кэш = set()
    нетронутые = {i for i in канд
                  if i not in кэш and i not in очередь and i not in доказано}
    упавшие = {i for i in канд
               if i in не_открылись and i not in кэш and i not in очередь}
    return {'кандидатов': канд, 'чужие': чужие, 'адресом': адресом,
            'инном': инном, 'доказано': доказано, 'нетронутые': нетронутые,
            'упавшие': упавшие, 'в_очереди': очередь}


def повысить(разб):
    """cand_site -> site у доказанных. Одной транзакцией, с журналом до записи."""
    пары = [(i, разб['кандидатов'][i],
             ('инн-на-странице' if i in разб['инном'] else '') +
             ('+адрес-с-домена' if i in разб['адресом'] else ''))
            for i in sorted(разб['доказано'])]
    if not пары:
        return {'повышено': 0}
    _журнал([{'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'что': 'повышение',
              'inn': i, 'domen': d, 'чем_доказано': ч} for i, d, ч in пары])
    # ПОРЦИЯМИ И ТЕРПЕЛИВО. Одна транзакция на три тысячи строк не втискивается:
    # enrich.db занята почти непрерывно (слив, цикл фактов, краулер контактов,
    # мост). Замер 30.08: большая транзакция не прошла за восемнадцать минут, а
    # порция в двести строк проскакивает между чужими записями. Поэтому мелкими
    # кусками, с долгим сроком и без потери сделанного: каждый кусок коммитится
    # сам по себе, оборвёмся — повтор доберёт остаток.
    c = sqlite3.connect(ENRICH, timeout=60)
    c.execute('PRAGMA busy_timeout=60000')
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    легло = не_вышло = 0
    крайний = time.time() + 40 * 60
    for k in range(0, len(пары), 200):
        кусок = [(d, сейчас, i) for i, d, _ч in пары[k:k + 200]]
        вышло = False
        while time.time() < крайний:
            try:
                c.executemany("update companies set site=?, updated_at=? "
                              "where inn=? and coalesce(site,'')=''", кусок)
                c.commit()
                легло += len(кусок)
                вышло = True
                break
            except sqlite3.OperationalError as e:
                if 'locked' not in str(e).lower() and 'busy' not in str(e).lower():
                    raise
                try:
                    c.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(5)
        if not вышло:
            не_вышло += len(кусок)
    c.close()
    return {'повышено': легло, 'не_вышло': не_вышло,
            'по_инну_на_странице': len(разб['инном'] - разб['чужие']),
            'по_адресу_с_домена': len(разб['адресом'] - разб['чужие'])}


def в_очередь(разб, кого, метка):
    """Дописать компании в НАЧАЛО очереди обхода."""
    строки = ['%s;%s;oba' % (i, разб['кандидатов'][i]) for i in sorted(кого)]
    if not строки:
        return {'поставлено': 0, 'кого': метка}
    путь = os.path.join(ZENNO, 'ochered.txt')
    наши = set(кого)
    было = []
    try:
        with open(путь, encoding='utf-8', errors='replace') as f:
            for s in f:
                s = s.strip()
                if s and s.split(';')[0].strip() not in наши:
                    было.append(s)
    except OSError:
        pass
    врем = путь + '.new'
    with open(врем, 'w', encoding='utf-8') as f:
        f.write('\n'.join(строки + было) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(врем, путь)
    with open(os.path.join(ZENNO, 'otdano.txt'), 'a', encoding='utf-8') as f:
        f.write('\n'.join(sorted(наши)) + '\n')
        f.flush()
        os.fsync(f.fileno())
    _журнал([{'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'что': 'в очередь',
              'кого': метка, 'сколько': len(строки)}])
    return {'поставлено': len(строки), 'кого': метка,
            'прежних_строк_очереди': len(было)}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    разб = разбор('--vsya-baza' in a)
    итог = {'кандидатов': len(разб['кандидатов']),
            'улика_адрес_с_домена': len(разб['адресом']),
            'улика_инн_на_странице': len(разб['инном']),
            'доказано_всего': len(разб['доказано']),
            'исключены_как_чужие': len(разб['чужие']),
            'нетронутых': len(разб['нетронутые']),
            'упавших_на_повтор': len(разб['упавшие'])}
    if '--delat' in a:
        итог['повышение'] = повысить(разб)
        итог['очередь_нетронутые'] = в_очередь(разб, разб['нетронутые'],
                                               'нетронутые')
        итог['очередь_упавшие'] = в_очередь(разб, разб['упавшие'],
                                            'повтор не открывшихся')
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
