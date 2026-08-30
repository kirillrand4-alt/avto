# -*- coding: utf-8 -*-
r"""Перелить находки со страниц в enrich.db — через гейт атрибуции.

Владелец 29.08: «точно ли мы полезные, а не невидимые почты собираем?» Замер на
13 316 найденных адресов показал, что вопрос по адресу: сама вытяжка чистая (92%
адресов сняты со страниц собственного сайта компании), а вот атрибуция — нет.
Мусор двух видов, и оба видны числом:

  * ПОДВАЛ ПОРТАЛА: один домен у десятков ИНН. tatar.ru — 357 адресов у 105
    компаний, bashkortostan.ru — 139 у 62, 02.rospotrebnadzor.ru — 132 у 56,
    minzdrav.gov.ru — 50 у 50. Это больницы, у которых в подвале сайта висят
    контакты министерства и надзора. Туда же beget.com — 97 адресов у 33
    компаний, подпись хостера «сайт на Бегете»;
  * СПИСОК ФИЛИАЛОВ: один домен, одна компания, сотни адресов. hidro.ru — 369
    адресов у ИНН с сайтом казань.гидро.рф, pharmgarant.ru — 111, ferost.ru —
    75. Выкачана страница «наши филиалы» целиком.

Гейт стоит ЗДЕСЬ, а не в разборе: правило может оказаться неверным, и тогда
достаточно перелить заново из накопителя. Ошибись мы в разборе — перечитывать
136 ГБ. Отсеянное не удаляется, а помечается причиной: смотреть и решать.

В enrich.db пишем через EnrichDB.add_email/add_phone — это единственная воронка,
за которой стоят все накопленные правила (починка кривых адресов, роль по ящику,
общий номер не бывает личным). Свои SQL-вставки мимо неё эти правила потеряют.

Базу не караулим силой: ждём свободного окна, как slit_kopilki.py, — сверки
приговоров и лидов держат enrich.db по четверти часа.

    python slit_nahodki.py --posmotret     что накопилось и что пройдёт гейт
    python slit_nahodki.py --delat         перелить (ждёт окна до 15 минут)
    python slit_nahodki.py --delat --skolko 40 --predel 5000
"""
import collections
import json
import os
import re
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault('NO_BROWSER', '1')

НАХОДКИ = os.environ.get('RAZBOR_DB', r'D:\razbor-nahodki.db')
ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЖУРНАЛ = os.environ.get('SLIV_LOG', r'D:\sliv-nahodok.jsonl')

БЕСПЛАТНЫЕ = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'rambler.ru',
              'bk.ru', 'list.ru', 'inbox.ru', 'internet.ru', 'mail.com',
              'outlook.com', 'icloud.com', 'yahoo.com', 'narod.ru', 'nm.ru',
              'hotmail.com', 'yandex.com'}
# НЕ ЗАПИРАТЬ БАЗУ НАДОЛГО. add_email коммитит каждую строку, и слив шестидесяти
# тысяч подряд превращается в час непрерывной записи. За enrich.db стоит очередь:
# мост Зенки не может разобрать gotovo, пока база занята, а Зенка при этом качает
# двенадцать тысяч страниц в час. Поэтому льём порциями с передышкой, и один
# прогон ограничен: сторож поднимет следующий через десять минут.
ПАЧКА = 200
ПЕРЕДЫШКА = 2.0       # секунд между порциями — окно для моста и сверок
ЗА_ПРОГОН = 8000      # строк за один прогон, если предел не задан явно
# НЕ ВСЯКИЕ ОДИННАДЦАТЬ ЦИФР — ТЕЛЕФОН. Со страниц с реквизитами экстрактор
# приносит куски БИК, КПП и ОГРН: «044525225», «110101001». Нормализация
# приписывает к ним семёрку, и в базу лезет 7044525225. Замер 29.08 нашёл 5 044
# таких среди прошедших гейт. Отличаются они надёжно: в России после кода страны
# идёт код 3xx/4xx (города), 8xx (бесплатные) или 9xx (мобильные). Кодов,
# начинающихся с 0, 1, 2, 5, 6, 7, не существует — это и есть признак реквизита.
ТЕЛЕФОН_ВЕРНЫЙ = re.compile(r'^7[3489]\d{9}$')
ПОРТАЛ_ИНН = 5        # домен у стольких ИНН и более — подвал портала
ФИЛИАЛОВ = 10         # столько адресов одного чужого домена у одной компании
# ПОЧЕМУ НЕ НОВАЯ МЕТКА ИСТОЧНИКА. Соблазн пометить находки своим словом
# («zenno-стр») ломает всё, что читает базу: канонический запрос «почта с сайта»
# отбирает source in ('own-site','zenno') или like 'сайт:%', панель и выгрузки
# идут по нему же, и новая метка сделала бы 61 тысячу адресов невидимыми. Гейт
# выше пропускает только адреса со страниц СОБСТВЕННОГО сайта компании — это
# ровно то, что означает own-site. Происхождение при этом не теряется: у каждой
# записи стоит source_url на конкретную страницу, а полный след с контекстом и
# причиной отсева остаётся в накопителе на D:.
# У существующих строк source не переписывается (ON CONFLICT его не трогает) —
# реестровая почта останется реестровой, ей лишь проставится source_url.
ИСТОЧНИК = 'own-site'
ТЕЛ_ОБЩИЙ_ИНН = 5     # номер у стольких ИНН и более — коммутатор портала


def _журнал(запись):
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(запись, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _свободна(секунд=3):
    try:
        c = sqlite3.connect(ENRICH, timeout=секунд)
        c.execute('PRAGMA busy_timeout=%d' % (секунд * 1000))
        c.execute('BEGIN IMMEDIATE')
        c.execute('ROLLBACK')
        c.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _накопитель():
    """Соединение с накопителем + колонки учёта слива.

    Без отметки «эта строка уже перелита» каждый следующий круг заново гонял бы
    гейт по всем 60+ тысячам находок и заново писал их в enrich.db. Отметки три:
    0 — не смотрели, 1 — легло в базу, 2 — отсеяно гейтом (с причиной). Правило
    поменяется — одним UPDATE вернём двойки в нули и пересмотрим.
    """
    c = sqlite3.connect(НАХОДКИ, timeout=60)
    c.execute('PRAGMA journal_mode=WAL')
    for таблица in ('nahodki_pochta', 'nahodki_telefon'):
        for колонка, тип in (('slito', 'int default 0'), ('prichina', 'text')):
            try:
                c.execute('alter table %s add column %s %s' % (таблица, колонка, тип))
            except sqlite3.OperationalError:
                pass          # колонка уже есть — штатный случай
    c.commit()
    return c


def _домен(строка):
    d = re.sub(r'^https?://', '', (строка or '').strip().lower()).split('/')[0]
    return d[4:] if d.startswith('www.') else d


def _родня(a, b):
    return bool(a) and bool(b) and (a == b or a.endswith('.' + b) or b.endswith('.' + a))


def _сайты():
    """Домен сайта каждой компании и отдельно те, чей сайт признан ЧУЖИМ.

    verified='mismatch' ставит провайдер, ПРОЧИТАВ страницу: «сайт принадлежит
    не этой компании». Конвейер по такому вердикту сам блокирует контакты
    (enrich_contacts: blocked = verified == 'mismatch'), а мой гейт про вердикт
    не знал и брал страницы этого домена как свои — 2 659 адресов и 11 517
    телефонов пришли так по всей базе. Теперь знает.

    'спорно' НЕ отсекаем: там выгрузка закрепляет домен за этим же ИНН, и
    конвейер контакты сохраняет — спор идёт о сайте, а не о принадлежности.
    'provider' — это ПОДТВЕРЖДЕНИЕ (провайдер-судья ручается за сайт), а не
    подозрение.
    """
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True,
                        timeout=60)
    д, чужие = {}, set()
    for i, s, cs, v in c.execute(
            "select inn, coalesce(site,''), coalesce(cand_site,''), "
            "coalesce(verified,'') from companies"):
        x = _домен(s or cs)
        if x:
            д[str(i)] = x
        if v == 'mismatch':
            чужие.add(str(i))
    c.close()
    return д, чужие


def разложить(предел=0, c=None):
    """Разнести ещё не перелитые находки по вердиктам гейта. Ничего не пишет.

    Считаем «портальность» домена и номера по ВСЕЙ накопленной выборке, а не по
    одной порции: домен, встреченный у пяти ИНН, распознаётся только целиком.
    """
    сайты, чужие = _сайты()
    своё = c is None
    if своё:
        c = _накопитель()
    все_дом = c.execute('select inn,email from nahodki_pochta').fetchall()
    все_тел = c.execute('select inn,phone from nahodki_telefon').fetchall()
    строки = c.execute('select inn,email,role,role_src,ctx,src,source_url,skryt,'
                       'coalesce(inn_na_str,0) '
                       'from nahodki_pochta where coalesce(slito,0)=0').fetchall()
    телефоны = c.execute('select inn,phone,source_url,coalesce(inn_na_str,0) '
                         'from nahodki_telefon where coalesce(slito,0)=0').fetchall()
    if своё:
        c.close()

    дом_инн = collections.defaultdict(set)
    дом_на_инн = collections.Counter()
    for inn, email in все_дом:
        д = email.split('@')[-1]
        дом_инн[д].add(str(inn))
        дом_на_инн[(str(inn), д)] += 1
    тел_инн = collections.defaultdict(set)
    for inn, phone in все_тел:
        тел_инн[phone].add(str(inn))

    годные, отсев, отсеяно = [], collections.Counter(), []
    for inn, email, role, role_src, ctx, src, url, skryt, инн_на_стр in строки:
        inn = str(inn)
        сайт = сайты.get(inn, '')
        дом = email.split('@')[-1]
        стр = _домен(url)
        причина, пометка, метка_источника = '', '', ИСТОЧНИК
        своя_страница = _родня(стр, сайт)
        if inn in чужие:
            причина = 'конвейер признал сайт чужим (verified=mismatch)'
        elif skryt:
            причина = 'скрытый адрес (ловушка)'
        elif not сайт and not инн_на_стр:
            причина = 'сайт компании неизвестен'
        elif not своя_страница:
            # ЧУЖАЯ СТРАНИЦА С ИНН — это карточка предприятия в справочнике, и
            # адрес на ней чаще всего его собственный (владелец 29.08: «особенно
            # если знаем инн на странице»). Берём, но честной меткой: у
            # справочниковых адресов своя репутация, конвейер их уже различает.
            if инн_на_стр:
                метка_источника = 'сайт:справочник'
                пометка = 'ИНН предприятия найден на странице'
            else:
                причина = 'страница не своего сайта'
        elif not (_родня(дом, сайт) or дом in БЕСПЛАТНЫЕ):
            if len(дом_инн[дом]) >= ПОРТАЛ_ИНН:
                причина = 'подвал портала (домен у %d+ ИНН)' % ПОРТАЛ_ИНН
            elif дом_на_инн[(inn, дом)] > ФИЛИАЛОВ:
                причина = 'список филиалов'
            else:
                # РЕДКИЙ ЧУЖОЙ ДОМЕН — берём (владелец 29.08: «если компания нам
                # подходит, то можно и взять для письма»). Это почта на домене
                # смежного юрлица, франшизы или старого сайта, а не подвал
                # портала: домен встречается меньше чем у пяти ИНН. Метку
                # ставим, чтобы продавец видел, с чем имеет дело.
                пометка = 'домен %s не совпадает с сайтом %s' % (дом, сайт)
                if инн_на_стр:
                    пометка += '; ИНН найден на странице'
        if причина:
            отсев[причина] += 1
            отсеяно.append((причина, inn, email))
            continue
        годные.append({'inn': inn, 'email': email, 'role': role or '',
                       'role_src': role_src or '', 'ctx': ctx or '',
                       'src': src or '', 'source_url': url or '',
                       'pometka': пометка, 'istochnik': метка_источника})
        if предел and len(годные) >= предел:
            break

    годные_тел, отсев_тел, отсеяно_тел = [], collections.Counter(), []
    for inn, phone, url, инн_на_стр in телефоны:
        inn = str(inn)
        сайт = сайты.get(inn, '')
        причина = ''
        if inn in чужие:
            причина = 'конвейер признал сайт чужим (verified=mismatch)'
        elif not ТЕЛЕФОН_ВЕРНЫЙ.match(re.sub(r'\D', '', phone or '')):
            причина = 'не телефон (кусок БИК/КПП/ОГРН или чужая страна)'
        elif not сайт and not инн_на_стр:
            причина = 'сайт компании неизвестен'
        elif not (_родня(_домен(url), сайт) or инн_на_стр):
            причина = 'страница не своего сайта'
        elif len(тел_инн[phone]) >= ТЕЛ_ОБЩИЙ_ИНН:
            причина = 'номер у %d+ ИНН (коммутатор портала)' % ТЕЛ_ОБЩИЙ_ИНН
        if причина:
            отсев_тел[причина] += 1
            отсеяно_тел.append((причина, inn, phone))
            continue
        годные_тел.append({'inn': inn, 'phone': phone, 'source_url': url or ''})
        if предел and len(годные_тел) >= предел:
            break
    return (годные, dict(отсев), годные_тел, dict(отсев_тел),
            отсеяно, отсеяно_тел)


def слить(ждать_минут=15, предел=0):
    н = _накопитель()
    (годные, отсев, годные_тел, отсев_тел,
     отсеяно, отсеяно_тел) = разложить(предел or ЗА_ПРОГОН, н)
    итог = {'через_гейт_почт': len(годные), 'отсев_почт': отсев,
            'через_гейт_телефонов': len(годные_тел), 'отсев_телефонов': отсев_тел}
    # отсеянное помечаем сразу: причина записана, второй раз гейт их не считает
    for причина, inn, email in отсеяно:
        н.execute('update nahodki_pochta set slito=2, prichina=? '
                  'where inn=? and email=?', (причина, inn, email))
    for причина, inn, phone in отсеяно_тел:
        н.execute('update nahodki_telefon set slito=2, prichina=? '
                  'where inn=? and phone=?', (причина, inn, phone))
    н.commit()
    if not (годные or годные_тел):
        итог['итог'] = 'лить нечего'
        н.close()
        return итог

    # ЖДЁМ ОКНА, НО НЕ ОТКАЗЫВАЕМСЯ ИЗ-ЗА ЕГО ОТСУТСТВИЯ (замер 29.08). Первый
    # прогон простоял 45 минут и не записал ни строки: свободного мига не
    # случилось ни разу. Немудрено — за enrich.db стоят часовые сверки (по
    # четверти часа каждая), вечный цикл фактов и краулер контактов, и «сейчас
    # никто не пишет» бывает реже, чем раз в час. При этом ждать умеет сам
    # SQLite: busy_timeout ставит нас в очередь, а не роняет. Поэтому окно —
    # приятный случай, а не условие: не дождались, льём с ожиданием в очереди,
    # порциями и с передышками, чтобы не запереть базу самим.
    t0 = time.time()
    ждали = 0
    while time.time() - t0 < ждать_минут * 60:
        if _свободна():
            break
        ждали += 1
        time.sleep(30)
    итог['ждали_проб'] = ждали
    итог['окно_дождались'] = _свободна()

    import enrich_db as ED
    db = ED.EnrichDB(ENRICH)
    # add_email коммитит каждую строку: сверка, начавшаяся посреди слива, роняет
    # запись на «database is locked». Ждём её, а не теряем строку.
    db.cx.execute('PRAGMA busy_timeout=180000')
    легло = легло_тел = сбоев = занято = 0
    сделано = 0
    for з in годные:
        try:
            db.add_email(з['inn'], з['email'], role=з['role'],
                         source=з.get('istochnik') or ИСТОЧНИК,
                         source_url=з['source_url'], pometka=з.get('pometka') or '')
            легло += 1
            н.execute('update nahodki_pochta set slito=1 where inn=? and email=?',
                      (з['inn'], з['email']))
        except sqlite3.OperationalError as e:
            занято += 1
            if 'locked' not in str(e).lower() and 'busy' not in str(e).lower():
                сбоев += 1
        except Exception:  # noqa: BLE001
            сбоев += 1
        сделано += 1
        if сделано % ПАЧКА == 0:
            н.commit()
            time.sleep(ПЕРЕДЫШКА)
    for з in годные_тел:
        try:
            db.add_phone(з['inn'], з['phone'], source=ИСТОЧНИК,
                         source_url=з['source_url'])
            легло_тел += 1
            н.execute('update nahodki_telefon set slito=1 where inn=? and phone=?',
                      (з['inn'], з['phone']))
        except sqlite3.OperationalError as e:
            занято += 1
            if 'locked' not in str(e).lower() and 'busy' not in str(e).lower():
                сбоев += 1
        except Exception:  # noqa: BLE001
            сбоев += 1
        сделано += 1
        if сделано % ПАЧКА == 0:
            н.commit()
            time.sleep(ПЕРЕДЫШКА)
    н.commit()
    н.close()
    try:
        db.cx.commit()
        db.cx.close()
    except Exception:  # noqa: BLE001
        pass
    итог.update({'легло_почт': легло, 'легло_телефонов': легло_тел,
                 'не_легло_база_занята': занято, 'сбоев': сбоев,
                 'секунд': round(time.time() - t0)})
    _журнал({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'ИТОГ': итог})
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]

    def чис(ключ, умолч):
        if ключ in a:
            try:
                return int(a[a.index(ключ) + 1])
            except Exception:  # noqa: BLE001
                pass
        return умолч

    if '--delat' not in a:
        н = _накопитель()
        годные, отсев, годные_тел, отсев_тел, _о, _от = разложить(чис('--predel', 0), н)
        легло = н.execute('select count(*) from nahodki_pochta where slito=1'
                          ).fetchone()[0]
        легло_т = н.execute('select count(*) from nahodki_telefon where slito=1'
                            ).fetchone()[0]
        н.close()
        роли = collections.Counter(з['role'] or 'без роли' for з in годные)
        print(json.dumps({'через_гейт_почт': len(годные), 'отсев_почт': отсев,
                          'роли': роли.most_common(),
                          'через_гейт_телефонов': len(годные_тел),
                          'отсев_телефонов': отсев_тел,
                          'уже_перелито_почт': легло,
                          'уже_перелито_телефонов': легло_т,
                          'база_свободна': _свободна()},
                         ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(слить(чис('--skolko', 15), чис('--predel', 0)),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
