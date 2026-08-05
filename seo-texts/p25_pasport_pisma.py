# -*- coding: utf-8 -*-
"""ПАСПОРТ ПИСЬМА: превратить цель владельца в число. Замер, ничего не меняет.

ЦЕЛЬ СЛОВАМИ (владелец, 05.08):

> начиная от сбора новостей, заканчивая отправкой письма я мог быть ГАРАНТИРОВАННО
> уверен, что письмо будет адресное, персонифицированное в т.ч. под новость,
> сайт/почта правильно и полноценно отобраны, а письмо получит именно наиболее
> релевантный человек.

КЛЮЧЕВОЕ СЛОВО — «ГАРАНТИРОВАННО». Это не средний процент по базе. Средние числа
(«80 % писем хорошие») гарантии не дают: владелец держит в руках ОДНО письмо, и ему
нужно знать про НЕГО. Значит мера должна быть не средней, а построчной: у каждого
письма есть паспорт, и в нём пять граф. Письмо уходит, когда все пять доказаны.

ПЯТЬ ГРАФ, каждая — проверяемый факт, а не мнение:

  1. ПОВОД. Новость настоящая, свежая, капексная И ПРО ЭТУ КОМПАНИЮ.
     Доказательство: ссылка-первоисточник открывается, название компании названо в
     её тексте, дата известна. (стадия A — 3-я сессия)
  2. ЮРЛИЦО. Сайт принадлежит ИМЕННО ЭТОМУ ИНН, а человек работает в ЭТОМ юрлице,
     а не «в группе». (стадия B — 2-я сессия)
  3. АДРЕС ВЕРНЫЙ. Почта принадлежит компании (домен сходится), живая (MX),
     не платформенная и не noreply. (стадия B)
  4. АДРЕС ПОЛНЫЙ. Собран не первый попавшийся, а ВСЕ найденные, и выбор сделан из
     нескольких. Одна-единственная почта — это не «отобрано», это «что нашлось».
  5. ЧЕЛОВЕК. Роль названа, она наиболее релевантная из доступных, сторона наша
     (не кадры, не пресса, не их сервис). (стадия C — 1-я сессия)

  плюс 6. ПЕРСОНИФИКАЦИЯ ПОД НОВОСТЬ — проверяется на готовом тексте письма:
     в тексте есть конкретика ИЗ ЭТОЙ новости, а не общая фраза.

ТРИ ИСХОДА У КАЖДОЙ ГРАФЫ, и «не доказано» это НЕ «плохо»:
  * ДОКАЗАНО — есть чем подтвердить, источник назван;
  * НЕ ДОКАЗАНО — проверить нечем: письмо не бракуется, а ждёт добора;
  * ОПРОВЕРГНУТО — прямое противоречие: адрес кадровый, человек с другого завода.

Правило владельца «разделять, а не отсеивать» здесь работает буквально: письмо с
жёлтой графой не выбрасывается, оно просто не уходит без добора.

ИМЕНА КОЛОНОК НЕ УГАДЫВАЮТСЯ — печатается pragma table_info. И источник кода тоже:
после сегодняшнего урока прибор печатает, ПО КАКОМУ файлу и базе он считал.
"""
import collections
import json
import os
import re
import sqlite3

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'

FREEMAIL = ('mail.ru', 'bk.ru', 'inbox.ru', 'list.ru', 'yandex.ru', 'ya.ru',
            'gmail.com', 'rambler.ru', 'internet.ru', 'icloud.com', 'outlook.com')
AGREGATOR = re.compile(r'checko|rusprofile|list-org|zachestnyi|sbis\.ru|audit-it|'
                       r'2gis|yell\.ru|orgpage|spark-interfax', re.I)
NE_NASH = re.compile(r'кадр|персонал|подбор|ваканс|пресс|юрис|бухгалт|реклам|маркет|сми',
                     re.I)


def dom(x):
    d = str(x or '').strip().lower()
    d = re.sub(r'^https?://', '', d).split('/')[0]
    return re.sub(r'^www\.', '', d)


def kol(cx, t):
    try:
        return [r[1] for r in cx.execute('pragma table_info(%s)' % t)]
    except Exception:  # noqa: BLE001
        return []


def main():
    print('=== ЧЕМ СЧИТАНО (после сегодняшнего урока про устаревшие копии)')
    for p in (ENRICH, SENDER):
        print('  %s  %s' % (p, ('%d б' % os.path.getsize(p)) if os.path.exists(p)
                            else 'НЕТ'))
    if not os.path.exists(ENRICH):
        print('ИТОГ ' + json.dumps({'нет базы': ENRICH}, ensure_ascii=False))
        return
    cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    for t in ('companies', 'emails', 'signals'):
        if t in tabl:
            print('  enrich.%-10s %s' % (t, ', '.join(kol(cx, t))))

    c_kol, e_kol, s_kol = kol(cx, 'companies'), kol(cx, 'emails'), kol(cx, 'signals')

    # --- собираем всё по ИНН
    adresa = collections.defaultdict(list)
    pol_e = [x for x in ('inn', 'email', 'role', 'person', 'mx_ok', 'source',
                         'source_url', 'verified_by') if x in e_kol]
    for r in cx.execute('select %s from emails' % ','.join(pol_e)):
        z = dict(zip(pol_e, r))
        if z.get('email'):
            adresa[str(z['inn'])].append(z)

    signaly = collections.defaultdict(list)
    pol_s = [x for x in ('inn', 'what', 'event_type', 'source_url', 'hotness',
                         'suspect', 'ts') if x in s_kol]
    for r in cx.execute('select %s from signals' % ','.join(pol_s)):
        z = dict(zip(pol_s, r))
        signaly[str(z['inn'])].append(z)

    sch = collections.Counter()
    grafy = collections.Counter()
    primery = []
    pol_c = [x for x in ('inn', 'name', 'best_email', 'site', 'is_competitor',
                         'verified') if x in c_kol]
    for r in cx.execute('select %s from companies where coalesce(best_email,"")<>""'
                        % ','.join(pol_c)):
        c = dict(zip(pol_c, r))
        if str(c.get('is_competitor') or '') in ('1', 'True'):
            continue
        inn = str(c['inn'])
        be = (c.get('best_email') or '').strip().lower()
        ems = adresa.get(inn) or []
        sig = signaly.get(inn) or []
        sch['писем возможно (есть адрес)'] += 1
        pasport = {}

        # 1. ПОВОД
        zhirn = [s for s in sig if len((s.get('what') or '')) >= 60
                 and not str(s.get('suspect') or '') == '1']
        ssylka_ok = any(str(s.get('source_url') or '').startswith('http')
                        and not AGREGATOR.search(str(s.get('source_url') or ''))
                        for s in zhirn)
        pasport['1.повод'] = ('ДОКАЗАНО' if (zhirn and ssylka_ok) else
                              ('НЕ ДОКАЗАНО' if sig else 'ОПРОВЕРГНУТО: сигнала нет'))

        # 2. ЮРЛИЦО: сайт есть и не агрегатор; принадлежность человека не проверяется
        #    нигде — поэтому честно «не доказано», а не «доказано».
        sayt = dom(c.get('site'))
        pasport['2.юрлицо'] = ('НЕ ДОКАЗАНО: принадлежность человека не проверялась'
                              if sayt and not AGREGATOR.search(sayt)
                              else 'НЕ ДОКАЗАНО: сайта нет')

        # 3. АДРЕС ВЕРНЫЙ
        zap = next((e for e in ems if (e.get('email') or '').lower() == be), {})
        d_be = be.split('@')[-1]
        if NE_NASH.search(str(zap.get('role') or '')):
            pasport['3.адрес верный'] = 'ОПРОВЕРГНУТО: не наш отдел'
        elif sayt and d_be == sayt:
            pasport['3.адрес верный'] = 'ДОКАЗАНО: домен предприятия'
        elif d_be in FREEMAIL:
            pasport['3.адрес верный'] = 'НЕ ДОКАЗАНО: бесплатная почта'
        else:
            pasport['3.адрес верный'] = 'НЕ ДОКАЗАНО: домен не сверен с сайтом'

        # 4. АДРЕС ПОЛНЫЙ — выбор был ИЗ ЧЕГО делать
        pasport['4.адрес полный'] = ('ДОКАЗАНО: выбран из %d' % len(ems)
                                     if len(ems) >= 2 else
                                     'НЕ ДОКАЗАНО: адрес единственный')

        # 5. ЧЕЛОВЕК
        rol = str(zap.get('role') or '').strip()
        chel = str(zap.get('person') or '').strip()
        if NE_NASH.search(rol):
            pasport['5.человек'] = 'ОПРОВЕРГНУТО: чужой отдел'
        elif rol and rol not in ('общий', 'приёмная') and chel:
            pasport['5.человек'] = 'ДОКАЗАНО: роль и имя'
        elif rol and rol not in ('общий', 'приёмная'):
            pasport['5.человек'] = 'НЕ ДОКАЗАНО: роль есть, имени нет'
        else:
            pasport['5.человек'] = 'НЕ ДОКАЗАНО: роль общая'

        for g, v in pasport.items():
            grafy['%s -> %s' % (g, v.split(':')[0])] += 1
        zel = sum(1 for v in pasport.values() if v.startswith('ДОКАЗАНО'))
        sch['зелёных граф: %d из 5' % zel] += 1
        if zel == 5:
            sch['ПИСЬМО С ГАРАНТИЕЙ (все графы доказаны)'] += 1
            if len(primery) < 10:
                primery.append((inn, (c.get('name') or '')[:34], be, rol, chel))

    cx.close()
    print('\n=== письма, где ДОКАЗАНЫ ВСЕ ПЯТЬ ГРАФ (примеры)')
    for x in primery:
        print('   ' + ' | '.join(str(y)[:32] for y in x))
    if not primery:
        print('   НИ ОДНОГО')
    print('\n=== по графам')
    for k, v in sorted(grafy.items()):
        print('  %-52s %6d' % (k, v))
    print()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    vsego = sch.get('писем возможно (есть адрес)', 0)
    garant = sch.get('ПИСЬМО С ГАРАНТИЕЙ (все графы доказаны)', 0)
    print('ИТОГ ' + json.dumps({
        'писем возможно': vsego,
        'С ГАРАНТИЕЙ (все 5 граф доказаны)': garant,
        'доля, %': round(100.0 * garant / vsego, 2) if vsego else 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
