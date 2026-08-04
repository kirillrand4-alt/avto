# -*- coding: utf-8 -*-
"""Вернуть привязку тем, у кого «чужое предприятие» — то же самое, названное иначе.

ЧТО СЛУЧИЛОСЬ. Я сняла привязку у 449 человек по правилу «если рядом с именем названо
предприятие — оно и есть, а не наше». Правило верное: оно нашло инженера РУСАЛа, записанного
как человек Сегежского ЦБК. Но 1-я сессия проверила все 449 сравнением ЯДЕР имени и показала,
что у 52 строк «его предприятие» и «наше предприятие» — ОДНО И ТО ЖЕ:

    АО «НИЖНЕКАМСКТЕХУГЛЕРОД»  vs  «Нижнекамск-техуглерод»
    АО «СНХЗ»                  vs  «СНХЗ»
    ПАО «ЯТЭК»                 vs  «ЯТЭК»

Это не опечатки, а обычная жизнь текста: смена ОПФ, дефис, аббревиатура вместо полного имени.
Человек на месте, привязка была верной, а моя правка приписала ему чужого работодателя.

ПОЧЕМУ ЭТО ХУЖЕ, ЧЕМ ПРОСТО ОШИБКА НА 52 СТРОКАХ. Снятая привязка выглядит как проверенный
факт: в должности стоит «работает в «X», не у нас». Продавец такому верит и человека не
набирает. То есть ошибка не шумит, а молча вычёркивает 52 живых контакта — ровно тех, кого мы
и ищем. Класс тот же, что у правила про номер: сильное правило, применённое без сверки, бьёт
по своим.

ЧТО ДЕЛАЕТ МОДУЛЬ. Ищет в базах записи с моей меткой `[ПРИВЯЗКА СНЯТА: ...]`, сверяет ядро
нашего имени с ядром названного и там, где ядра совпадают, метку СНИМАЕТ и пишет вместо неё
«проверено: то же предприятие, названное иначе». Ничего не удаляет: и снятие, и возврат
остаются видимой историей строки.

ЯДРО ИМЕНИ: убираются ОПФ (ООО, АО, ПАО, ЗАО, ФГУП, филиал…), кавычки, дефисы и пробелы,
остаётся слитная основа в нижнем регистре. Совпадением считается равенство ядер ИЛИ вхождение
одного в другое при длине не меньше пяти знаков — короткие вхождения («БСК» в «БЭСК» не
входит, а вот «СК» вошло бы куда угодно) дают ложные склейки.

Запуск:
    python3 privyazka_sverka_yadrom.py            # посчитать по файлу и по базе
    python3 privyazka_sverka_yadrom.py --primenit # вернуть привязку в базах
"""
import base64
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

csv.field_size_limit(10 ** 7)

from yadro_imeni import to_zhe  # noqa: E402


SCRIPT = r'''
# -*- coding: utf-8 -*-
import csv, json, os, re, sqlite3, sys
sys.path.insert(0, r'C:\sender\_ops')
import _3s_privyazka_yadro as Y

csv.field_size_limit(10 ** 7)
PRIMENIT = 'PRIMENIT' in sys.argv
METKA = re.compile(r'\s*\[ПРИВЯЗКА СНЯТА: в источнике назван «([^»]+)»\]')
METKA_POST = re.compile(r'\s*\[работает в «([^»]+)», не у нас\]')

# ИМЯ НАШЕГО ПРЕДПРИЯТИЯ БЕРЁТСЯ ИЗ ФАЙЛА РЕШЕНИЯ, А НЕ ИЗ БАЗЫ. Первый прогон сверял с
# `company` и вернул ноль: у таблицы вообще нет колонки с именем (ни `name`, ни `title`, ни
# `company_name`). Ноль выглядел как «ошибок не было» — а на деле сравнивать было не с чем.
# В файле 449 оба имени записаны в момент решения, и это и есть честный источник сверки.
FAJL = r'C:\sender\_ops\3s_VAZHNOE-3s-CHUZHAYA-PRIVYAZKA-449.csv'
# ПАРА ИЩЕТСЯ ПО ИНН + ФАМИЛИИ, А НЕ ПО ПОЛНОМУ ИМЕНИ. Первый прогон не нашёл в файле 43
# строки с моей же меткой: у меня в базе «Амелин С.А.», а в файле «Амелин Сергей
# Александрович» — один человек, разные строки. Правило 1-й сессии, дословно: сшивать по
# ИНН и ПЕРВОМУ слову имени, отчество и инициалы не сравнивать (они пишутся то полностью,
# то буквой, то в родительном падеже). Их же оговорка соблюдена: по фамилии сшиваем только
# ВНУТРИ одного ИНН — по всей базе фамилия не ключ, Ивановых сотни.
def fam(ch):
    ch = re.sub(r'[^А-Яа-яЁёA-Za-z\s.-]', ' ', str(ch or '')).strip()
    ch = ch.split()
    return ch[0].lower().replace('ё', 'е').strip('.-') if ch else ''


imena_po_pare, po_familii, odnofamiltsy = {}, {}, set()
if os.path.exists(FAJL):
    for r in csv.DictReader(open(FAJL, encoding='utf-8-sig'), delimiter=';'):
        inn = (r.get('nash_inn') or '').strip()
        fio = (r.get('fio') or '').strip()
        para = ((r.get('nashe_predpriyatie') or '').strip(),
                (r.get('ego_predpriyatie') or '').strip())
        imena_po_pare[(inn, fio)] = para
        kf = (inn, fam(fio))
        if kf in po_familii and po_familii[kf] != para:
            # ДВЕ РАЗНЫЕ ЗАПИСИ С ОДНОЙ ФАМИЛИЕЙ У ОДНОГО ИНН — не сшиваем вовсе. Молча
            # выбрать одну хуже, чем оставить обе неразобранными.
            odnofamiltsy.add(kf)
        po_familii[kf] = para
else:
    print('ФАЙЛА 449 НЕТ на сервере — сверять не с чем, ничего не меняю')

itog = {'пар_в_файле': len(imena_po_pare)}
for baza, tabl, pole_post in (
        (r'C:\seostat\data\centrifugal.db', 'person', 'position'),
        (r'C:\sender\enrich.db', 'people', 'post')):
    if not os.path.exists(baza):
        itog[baza] = 'базы нет'
        continue
    cx = sqlite3.connect(baza)
    # ИМЯ ПРЕДПРИЯТИЯ В ПАНЕЛИ — `predpriyatie`, ответ 1-й сессии. Я искал `name`, `title`,
    # `company_name` и получил пустоту, которая читалась как «ошибок нет». Схема панели вся
    # на латинской транслитерации русских слов: `sayt`, `pochta`, `telefony_iz_bazy`.
    # Теперь основной источник сверки — сама база, а файл решения только запасной: 40 строк
    # с моей меткой в файле 449 отсутствуют вовсе, и без колонки их было не проверить.
    imena = {}
    try:
        kol = [r[1] for r in cx.execute('pragma table_info(company)')]
        pi = next((k for k in ('predpriyatie', 'company_name', 'name', 'title') if k in kol), '')
        if pi:
            imena = dict(cx.execute('select inn, coalesce("%s", \'\') from company' % pi))
        else:
            print('в %s у company нет колонки с именем; поля: %s' % (tabl, ','.join(kol[:12])))
    except Exception as e:
        print('company в %s: %s' % (tabl, type(e).__name__))
    vozvrat, ostavit, bez_pary = [], 0, 0
    for rid, inn, person, post, src in cx.execute(
            "select rowid, coalesce(inn,''), coalesce(person,''), coalesce(%s,''), "
            "coalesce(source,'') from %s" % (pole_post, tabl)):
        m = METKA.search(src)
        if not m:
            continue
        ego = m.group(1)
        nashe = imena.get(inn, '')
        if not nashe:
            para = imena_po_pare.get((inn, person.strip()))
            if not para:
                kf = (inn, fam(person))
                para = None if kf in odnofamiltsy else po_familii.get(kf)
            if not para:
                bez_pary += 1
                continue
            nashe = para[0]
        odno, pochemu = Y.to_zhe(nashe, ego)
        if not odno:
            ostavit += 1
            continue
        vozvrat.append((METKA_POST.sub('', post),
                        METKA.sub(' [привязка проверена по ядру имени: «%s» и «%s» — одно '
                                  'предприятие, названное иначе]' % (nashe[:60], ego[:60]),
                                  src)[:2000], rid, inn, person, pochemu))
    itog[tabl] = {'помечено_снятыми': len(vozvrat) + ostavit + bez_pary,
                  'вернуть_привязку': len(vozvrat), 'оставить_снятой': ostavit,
                  'пары_нет_в_файле': bez_pary,
                  'примеры': [{'inn': v[3], 'chelovek': v[4], 'pochemu': v[5]}
                              for v in vozvrat[:8]]}
    if PRIMENIT and vozvrat:
        cx.executemany('update %s set %s = ?, source = ? where rowid = ?' % (tabl, pole_post),
                       [(v[0], v[1], v[2]) for v in vozvrat])
        cx.commit()
        itog[tabl]['применено'] = True
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
'''


def po_faylu():
    """Пересчёт по выложенному файлу — не веря соседям на слово и не прося пересчитать."""
    put = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'VAZHNOE-3s-CHUZHAYA-PRIVYAZKA-449.csv')
    if not os.path.exists(put):
        put = ('/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/'
               'scratchpad/VAZHNOE-3s-CHUZHAYA-PRIVYAZKA-449.csv')
    if not os.path.exists(put):
        print('файла 449 нет под рукой — пропускаю сверку по файлу', file=sys.stderr)
        return
    rows = list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'))
    odno = [r for r in rows if to_zhe(r.get('nashe_predpriyatie'), r.get('ego_predpriyatie'))[0]]
    print(f'по файлу: строк {len(rows)}, то же предприятие {len(odno)}, '
          f'действительно чужих {len(rows) - len(odno)}')
    for r in odno[:8]:
        print(f'  {r["nashe_predpriyatie"][:38]:<38} vs {r["ego_predpriyatie"][:30]:<30} '
              f'{r["fio"][:22]}')


def main():
    po_faylu()
    tut = os.path.dirname(os.path.abspath(__file__))
    fajly = [{'dest': r'C:\sender\_ops\_3s_privyazka_yadro.py',
              'b64': base64.b64encode(
                  open(os.path.join(tut, 'yadro_imeni.py'), encoding='utf-8')
                  .read().encode()).decode()},
             {'dest': r'C:\sender\_ops\3s_privyazka_vozvrat.py',
              'b64': base64.b64encode(SCRIPT.encode()).decode()}]
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': r'C:\sender\_ops\3s_privyazka_vozvrat.py',
                  'argv': ['PRIMENIT'] if '--primenit' in sys.argv else [], 'timeout': 900},
                 timeout=1200)
    d = r.get('data') or {}
    hvost = d.get('stdout_tail') or ''
    for s in hvost.splitlines():
        if s.strip().startswith('ИТОГ '):
            print(json.dumps(json.loads(s.strip()[5:]), ensure_ascii=False, indent=1))
            return
    print('строки ИТОГ нет:', hvost[-800:], (d.get('stderr_tail') or '')[-800:], file=sys.stderr)


if __name__ == '__main__':
    main()
