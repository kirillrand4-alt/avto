# -*- coding: utf-8 -*-
r"""Сторож: держит конвейер живым, пока владельца нет за компьютером.

Владелец 16.08: «а я через пару часов прихожу и всё стоит». Так и было: процессы
доходят до конца своей порции и завершаются, а перезапускать их некому — я в
диалоге, а не на сервере. Сторож решает это на стороне сервера.

Что проверяет и чинит:
  * мост Зенки (zenno_most.py --demon) — умер, поднимаем;
  * поиск сайтов (poisk_saytov.py --vse) — умер, а цели остались, поднимаем;
  * сбор фактов (site_facts.py) — умер, а страницы в кэше не разобраны, поднимаем;
  * очередь Зенки короче порога — дописываем переобходом.

Ставится в планировщик Windows на каждые десять минут:
    schtasks /create /tn Storozh /tr "python storozh.py" /sc minute /mo 10 /f
"""
import json
import os
import subprocess
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
PY311 = r'C:\Program Files\Python311\python.exe'
ZENNO = r'C:\seostat\drop\zenno'
LOG = r'C:\sender\storozh.jsonl'
ФЛАГИ = 0x08 | 0x200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _живые():
    out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         'Select-Object -ExpandProperty CommandLine'],
        capture_output=True, text=True, timeout=120).stdout
    return [s.strip() for s in out.splitlines() if s.strip()]


def _крутится(живые, *куски):
    return any(all(k in s for k in куски) for s in живые)


def _поднять(имя, аргументы, лог, среда=None):
    f = open(лог, 'a', encoding='utf-8')
    f.write('\n=== сторож поднял %s %s ===\n' % (имя, time.strftime('%Y-%m-%d %H:%M:%S')))
    f.flush()
    p = subprocess.Popen([PY311, os.path.join(DIR, имя)] + аргументы,
                         stdout=f, stderr=subprocess.STDOUT, cwd=DIR, creationflags=ФЛАГИ,
                         env=dict(os.environ, **(среда or {})))
    return p.pid


def _длина_очереди():
    p = os.path.join(ZENNO, 'ochered.txt')
    if not os.path.exists(p):
        return 0
    with open(p, encoding='utf-8', errors='replace') as f:
        return sum(1 for s in f if s.strip())


def _цели_поиска_остались():
    try:
        sys.path.insert(0, DIR)
        import poisk_saytov as PS
        цели, _порог, _всего = PS.цели(1)
        return bool(цели)
    except Exception:  # noqa: BLE001
        return False


def _факты_недоразобраны():
    """Есть ли работа для сбора фактов.

    Считаем ДВА долга сразу: пустые карточки (страниц не было или провайдер упал)
    и карточки прошлых версий промпта — их 4778 на 16.08, и без второго слагаемого
    сторож считал бы конвейер простаивающим при полной очереди работы.
    """
    try:
        import sqlite3
        c = sqlite3.connect(r'C:\sender\enrich.db')
        n = c.execute("select count(*) from site_facts where coalesce(facts_json,'')='' "
                      'and coalesce(popytok,0) < 3').fetchone()[0]
        try:
            n += c.execute("select count(*) from site_facts where coalesce(facts_json,'')<>'' "
                           'and coalesce(format,0) < 2').fetchone()[0]
        except Exception:  # noqa: BLE001
            pass                       # колонки ещё нет — считаем только пустые
        c.close()
        return n > 0
    except Exception:  # noqa: BLE001
        return False



def _sekrety_iz_fayla() -> dict:
    """Ключи из runner-secrets.env: сторож работает от SYSTEM и окружения
    пользовательской сессии не видит.

    Ровно на этом 17.08 сгорел поиск сайтов: процесс поднялся без
    XMLRIVER_KEY, запросов не слал, но каждой компании записал отказ. Провайдер
    молча ведёт себя так же — без PROVIDER_API_KEY цикл фактов будет крутиться
    вхолостую и помечать карточки разобранными.
    """
    из = {}
    for п in (os.path.join(DIR, 'runner-secrets.env'),
              r'C:\sender\server\runner-secrets.env',
              r'C:\seostat\drop\runner-secrets.env'):
        if not os.path.exists(п):
            continue
        try:
            for стр in open(п, encoding='utf-8-sig', errors='replace'):
                стр = стр.strip()
                if not стр or стр.startswith('#') or '=' not in стр:
                    continue
                к, з = стр.split('=', 1)
                к, з = к.strip(), з.strip()
                if з and (к.startswith('PROVIDER') or к.startswith('XMLRIVER')):
                    из.setdefault(к, з)
        except Exception:  # noqa: BLE001
            pass
    return из


def _sreda_faktov() -> dict:
    """Окружение цикла фактов: ключи + настройки шлюза.

    PROVIDER_FIRST_TOKEN_SEC=90, как в умолчании. Порог в 25 секунд стоял здесь
    с 20.08, когда шлюз отдавал содержимое примерно через раз и неудачный вызов
    висел на ping-кадрах сотню секунд. 28.08 владелец показал журнал шлюза: луна
    отвечает СТАБИЛЬНО, но за 17-48 секунд, и каждый запрос списывается со счёта.
    А в логе цикла в это же время стояли «стрим молчит 28с / 30с / 31с / 35с /
    38с» — все чуть выше нашего порога. То есть мы обрывали здоровые вызовы за
    секунды до ответа, платили за них и отправляли компанию на повтор: порог из
    экономии превратился в чистый убыток. Возвращаем запас.

    PROVIDER_FALLBACK_CHEAP=gpt-5.6-luna вместо claude-haiku-4-5. На молчание
    луны остаток попыток уходил на хайку, и прогон, запущенный как дешёвый,
    досчитывался по ставке в девять раз выше: $333 против $41 на весь остаток.
    Владелец 20.08: «восьмикратно не надо». Держим луну и в запасе — медленнее
    на плохих кругах, но по цене луны.
    """
    # Потоков 32, а не 16. Замер первой проверки 20.08: на 16 потоках вышло
    # 115 карточек в час — за ночь остаток в 14 457 не пройти, нужно пять
    # суток. Упирается не в процессор (зенка рядом держит 59%), а в ожидание
    # шлюза: примерно половина вызовов висит на ping-кадрах по 40 секунд, и
    # это ожидание распараллеливается почти линейно.
    среда = {'FAKTY_PACHKA': '96', 'FAKTY_POTOKOV': '32',
             'PROVIDER_FIRST_TOKEN_SEC': '90',
             'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna',
             'PROVIDER_FALLBACK_CHEAP2': 'gpt-5.6-luna'}
    среда.update(_sekrety_iz_fayla())
    return среда


def обход():
    живые = _живые()
    сделано = {}
    # ХОЛД МОСТА (27.08). У моста флага не было, и он поднимался безусловно —
    # а он пишет в enrich.db каждый круг и на время тяжёлой записи держит замок.
    # Трижды за день я гасил его, мерил «база всё равно занята» и обвинял то
    # Зенку, то цикл паспортов: сторож поднимал мост обратно через минуту.
    # Снять холд = удалить HOLD-MOST.flag, следующий круг поднимет мост сам.
    if os.path.exists(os.path.join(DIR, 'HOLD-MOST.flag')):
        сделано['мост'] = 'HOLD-MOST.flag — не поднимаем'
    elif not _крутится(живые, 'zenno_most.py', '--demon'):
        сделано['мост'] = _поднять('zenno_most.py', ['--demon', '120'],
                                   os.path.join(ZENNO, 'demon.out'))
    # ХОЛД ПОИСКА САЙТОВ (владелец 19.08: «без использования провайдера и
    # хмлривера пока что»). poisk_saytov тратит платные запросы XMLRiver, а
    # сейчас задача другая — качать страницы по уже известным сайтам. Снять
    # холд = удалить файл HOLD-POISK.flag, сторож поднимет поиск сам.
    #
    # СПИСОК ЦЕЛЕЙ ОБЯЗАТЕЛЕН (29.08). Здесь стояло голое `--vse 500 8`, без
    # POISK_SPISOK, — то есть поиск по ВСЕЙ базе. Пока поиск жил под холдом, это
    # не стреляло. 28.08 я снял холд, чтобы прогнать мейеровский список своим
    # процессом; тот доработал и завершился, сторож увидел «поиска нет, цели
    # есть» и 103 раза поднял его заново — уже по всей базе. За ночь ушёл весь
    # баланс xmlriver (318 рублей), а мейеровский список остался недобранным.
    # Правка 1438d50 ловила случай «список задан, а файла нет» и мимо этого
    # случая проходила: список не был задан вовсе.
    #
    # Теперь: есть файл списка — поднимаем строго по нему; файла нет — НЕ
    # поднимаем вовсе и пишем это в журнал. Платный прогон по всей базе — это
    # решение владельца, а не самодеятельность сторожа.
    СПИСОК = os.environ.get('POISK_SPISOK', r'C:\sender\_tmp\poisk-meyer.txt')
    if os.path.exists(os.path.join(DIR, 'HOLD-POISK.flag')):
        pass
    elif not _крутится(живые, 'poisk_saytov.py') and _цели_поиска_остались():
        if os.path.exists(СПИСОК):
            сделано['поиск_сайтов'] = _поднять(
                'poisk_saytov.py', ['--vse', '60', '24'],
                r'C:\sender\poisk_saytov.out',
                {'POISK_SPISOK': СПИСОК, 'POISK_DOLYA': '1.0',
                 'XMLRIVER_CHANNELS': '5', 'XMLRIVER_PAUSE': '3',
                 'POISK_PAUZA': '5', 'NO_BROWSER': '1'})
        else:
            сделано['поиск_не_поднят'] = 'нет списка целей ' + СПИСОК
    # факты собирает ВЕЧНЫЙ цикл fakty_cikl.py, а не разовый вызов site_facts.py:
    # сторож раньше смотрел на имя site_facts.py и при живом цикле поднимал ещё
    # и переспрос — два процесса на одну очередь
    # ХОЛД ВЛАДЕЛЬЦА (17.08 «останови пока что обогащение карточек через
    # провайдера»): пока рядом лежит HOLD-FAKTY.flag, цикл фактов не поднимаем.
    # Снять холд = удалить флаг; следующий круг сторожа поднимет цикл сам, и
    # очередь доберётся с места остановки — она резюмируемая (format/ts/popytok).
    if os.path.exists(os.path.join(DIR, 'HOLD-FAKTY.flag')):
        pass
    elif not _крутится(живые, 'fakty_cikl.py') and _факты_недоразобраны():
        сделано['факты'] = _поднять('fakty_cikl.py', [],
                                    r'C:\sender\server\fakty_cikl.log',
                                    _sreda_faktov())
    # СЛИВ КОПИЛОК. Находки, не попавшие в занятую базу, лежат на диске и ждут
    # окна. Сами конвейеры пробуют слить их в начале своей пачки — но только
    # если база свободна ровно в этот миг, а окна редкие: 28.08 в четырёх
    # пачках подряд слив не прошёл ни разу. Сторож обходит сервер каждые десять
    # минут, и это лучшее место для регулярной попытки.
    #
    # Ждать ему нельзя — обход должен быть быстрым, — поэтому ровно одна проба:
    # свободна база, льём; занята, уходим до следующего круга.
    try:
        sys.path.insert(0, DIR)
        import slit_kopilki as SK
        было = SK.что_накопилось()
        if (было['поиск']['записей'] or было['паспорта']['записей']):
            if было['база_свободна']:
                сделано['слив_копилок'] = SK.слить(0)
            else:
                сделано['копилки_ждут'] = {
                    'поиск': было['поиск']['записей'],
                    'паспорта': было['паспорта']['записей']}
    except Exception as e:  # noqa: BLE001
        сделано['слив_сбой'] = str(e)[:120]

    длина = _длина_очереди()
    if длина < 150:
        try:
            sys.path.insert(0, DIR)
            import zenno_most as Z
            сделано['очередь_дописана'] = Z.pereobhod(500)
        except Exception as e:  # noqa: BLE001
            сделано['очередь_сбой'] = str(e)[:120]
    итог = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'очередь': длина,
            'подняли': сделано or 'ничего не требовалось'}
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(итог, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return итог


if __name__ == '__main__':
    print(json.dumps(обход(), ensure_ascii=False)[:600])
