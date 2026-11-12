# -*- coding: utf-8 -*-
r"""Добор контактов ca источниками разборщика news-скана (enrich_contacts), которые в обходе ca были урезаны
(12.11, владелец: «1,2 включай; дельфина уже нет, в окружении токен от ВК — 2 штуки разных»).

Кого (по последней записи журнала после допрохода, ca-kontakty.jsonl):
  A. выручка от 120 млн, сайт открылся, а контакта ЛПР нет:
     * поиск страниц сотрудников и руководства на домене (xmlriver, site:домен) -> разметка блоков (people_from_html:
       ФИО + должность + телефон/почта в одной карточке; karty_kontaktov: почта + раздел);
     * справочники (find_directory_contacts) — общие почты и телефоны;
     * группа ВКонтакте (find_vk_group_contacts: API ВК напрямую, сервисный и пользовательский токены из секретов
       сервера, без Dolphin) — блок «Контакты» группы: должность + телефон/почта + ФИО;
  B. сайт так и не открылся (и простым запросом, и нашим браузером): обход разборщиком с запасным путём
     прокси + решатель капчи (CapMonster) + браузер; плюс справочники и ВК.
Контакт берётся, только если есть телефон или почта (владелец: «ФИО без почты и телефона бесполезно»).
Страницы вакансий и резюме не открываются (kc_sbor_dop.ВАКАНСИИ).
Выход (fsync, резюм по ИНН): ca\ca-ec-dobor.jsonl — полная выгрузка берёт его отдельным источником. В журнал
ca-kontakty.jsonl не пишет (там идут шаги допрохода). Ждёт, пока допроход закончит доразметку.
"""
import collections, io, json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')

if '--vnutri' not in sys.argv:
    лог = os.path.join(ПАПКА, 'ca_dobor_ec_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(15)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)

os.chdir(DIR)
ЗАМОК = os.path.join(ПАПКА, 'ca_dobor_ec.lock')


def жив(pid):
    return bool(pid) and pid in subprocess.run(['tasklist', '/FI', 'PID eq %s' % pid], capture_output=True, text=True).stdout


try:
    _fd = os.open(ЗАМОК, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(_fd, str(os.getpid()).encode())
    os.close(_fd)
except FileExistsError:
    if жив(open(ЗАМОК).read().strip()):
        print('уже запущен')
        sys.exit(0)
    open(ЗАМОК, 'w').write(str(os.getpid()))

ВЫХОД = os.path.join(ПАПКА, 'ca-ec-dobor.jsonl')
ПРОГРЕСС = os.path.join(ПАПКА, 'ca-ec-dobor-progress.json')
ПОТОКОВ = int(os.environ.get('KC_DOBOR_POTOKOV', '6'))
ОТ = float(os.environ.get('KC_DOBOR_OT', '120e6'))
_лок = threading.Lock()


def отметка(**k):
    k['обновлено'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(ПРОГРЕСС + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)
    os.replace(ПРОГРЕСС + '.tmp', ПРОГРЕСС)
    print(json.dumps(k, ensure_ascii=False)[:300], flush=True)


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def ждать_доразметку():
    п = os.path.join(ПАПКА, 'ca-dopohod-progress.json')
    while True:
        try:
            с = json.load(open(п, encoding='utf-8'))
        except Exception:  # noqa: BLE001
            с = {}
        if 'доразметка' in (с.get('готово') or []):
            return
        отметка(этап='жду доразметку допрохода', допроход=с.get('этап', ''))
        time.sleep(600)


import enrich_contacts as EC  # noqa: E402
import kc_pochty as KP  # noqa: E402
import kc_sbor_dop as SD  # noqa: E402
import cc_obhod as CO  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

EC._SKIP_PROVIDER = True  # без модели: только сбор, роли — по подписям


def строка(ист, url, фио='', должность='', телефон='', почта='', контекст=''):
    почта = (почта or '').strip().lower()
    if почта and (not KP.ПОЧТА.fullmatch(почта) or KP.ЛОВУШКИ.search(почта)):
        почта = ''
    тел = CO.норм(телефон or '') if телефон else ''
    if not (почта or тел):
        return None
    return {'источник': ист, 'url': url or '', 'фио': (фио or '').strip()[:80], 'должность': (должность or '').strip()[:120],
            'телефон': тел, 'почта': почта, 'контекст': re.sub(r'\s+', ' ', контекст or '')[:300]}


def страницы_людей(comp, dom):
    урлы = []
    for f in (EC.find_staff_via_search, EC.find_leadership_via_search):
        try:
            for u in f(comp, dom) or []:
                if u not in урлы and not SD.ВАКАНСИИ.search(u):
                    урлы.append(u)
        except Exception:  # noqa: BLE001
            pass
    out = []
    for u in урлы[:6]:
        ст, html, _ = MN.скачать(u)
        if ст != 'ok':
            continue
        html = SD.раскрыть_cf(html)
        for ч in EC.people_from_html(html, u) or []:
            r = строка('поиск страниц сотрудников', u, ч.get('person'), ч.get('post'), ч.get('phone'), ч.get('email'))
            if r:
                out.append(r)
        for к in EC.karty_kontaktov(html, u) or []:
            r = строка('поиск страниц сотрудников (карточка)', u, '', к.get('razdel'), '', к.get('email'), к.get('kartochka'))
            if r:
                out.append(r)
    return out, урлы


def одна(к):
    inn, сайт = к['inn'], к.get('сайт') or ''
    dom = EC._domain(сайт if сайт.startswith('http') else 'http://' + сайт) if сайт else ''
    comp = {'inn': inn, 'name': к.get('имя') or '', 'site': сайт, 'okved': к.get('осн') or '',
            'region': к.get('регион') or '', 'city': к.get('город') or '', 'выручка': к.get('выручка') or 0}
    рез = {'inn': inn, 'группа': к['_группа'], 'контакты': [], 'ошибки': {}}
    if к['_группа'] == 'A' and dom:
        try:
            рез['контакты'], рез['страницы_поиска'] = страницы_людей(comp, dom)
        except Exception as e:  # noqa: BLE001
            рез['ошибки']['сотрудники'] = repr(e)[:120]
    if к['_группа'] == 'B' and сайт:
        try:
            текст, стр, _, csrc = EC.crawl_contacts(сайт, pace=(0.5, 1.5), inn=inn)
            рез['капча_обход'] = {'страниц': len(стр or []), 'текст': len(текст or '')}
            for п in KP.почты(None, текст or ''):
                r = строка('сайт (обход с решением капчи)', сайт, почта=п['почта'], контекст=п['контекст'])
                if r:
                    рез['контакты'].append(r)
            for м in list(CO.ТЕЛ.finditer(текст or ''))[:30]:
                r = строка('сайт (обход с решением капчи)', сайт, телефон=м.group(0),
                           контекст=(текст or '')[max(0, м.start() - 160):м.end() + 40])
                if r:
                    рез['контакты'].append(r)
        except Exception as e:  # noqa: BLE001
            рез['ошибки']['капча'] = repr(e)[:120]
    try:
        dc = EC.find_directory_contacts(comp)
        if dc:
            ист = 'справочник: ' + EC._domain(dc.get('dir_url') or '')
            for e in dc.get('emails') or []:
                r = строка(ист, dc.get('dir_url'), почта=e)
                if r:
                    рез['контакты'].append(r)
            for t in dc.get('phones') or []:
                r = строка(ист, dc.get('dir_url'), телефон=t)
                if r:
                    рез['контакты'].append(r)
    except Exception as e:  # noqa: BLE001
        рез['ошибки']['справочники'] = repr(e)[:120]
    try:
        vk = EC.find_vk_group_contacts(comp) or {}
        if vk.get('error'):
            рез['ошибки']['вк'] = vk['error'][:120]
        for c in vk.get('contacts') or []:
            r = строка('ВКонтакте: контакты группы', vk.get('url'), c.get('person'), c.get('desc'), c.get('phone'), c.get('email'))
            if r:
                рез['контакты'].append(r)
        for e in vk.get('emails') or []:
            r = строка('ВКонтакте: группа', vk.get('url'), почта=e)
            if r:
                рез['контакты'].append(r)
        for t in vk.get('phones') or []:
            r = строка('ВКонтакте: группа', vk.get('url'), телефон=t)
            if r:
                рез['контакты'].append(r)
    except Exception as e:  # noqa: BLE001
        рез['ошибки']['вк'] = repr(e)[:120]
    # дубли (тот же телефон/почта) — одна строка, с подписью побогаче
    лучш = {}
    for r in рез['контакты']:
        ключ = (r['телефон'], r['почта'])
        if ключ not in лучш or (bool(r['фио']) + bool(r['должность'])) > (bool(лучш[ключ]['фио']) + bool(лучш[ключ]['должность'])):
            лучш[ключ] = r
    рез['контакты'] = list(лучш.values())
    рез['итог'] = 'ok'
    записать(рез)
    return рез


def main():
    ждать_доразметку()
    сп = json.load(io.open(os.path.join(DIR, 'ca-spisok.json'), encoding='utf-8'))['компании']
    посл = {}
    for s in io.open(os.path.join(DIR, 'ca-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn') and з.get('итог') == 'ok':
            посл[з['inn']] = з
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                сделано.add(json.loads(s)['inn'])
            except (ValueError, KeyError):
                pass
    задачи = []
    for i, з in посл.items():
        if i not in сп or i in сделано or not з.get('сайт'):
            continue
        ном = [x for x in з.get('номера') or [] if x.get('чей') != 'другая']
        открылся = any(ст == 'ok' for _, ст in з.get('страницы') or [])
        лпр = any(x.get('лпр') == 'да' for x in ном)
        выр = сп[i].get('выручка') or 0
        if not открылся:
            задачи.append(dict(сп[i], inn=i, сайт=з['сайт'], _группа='B'))
        elif not лпр and выр >= ОТ:
            задачи.append(dict(сп[i], inn=i, сайт=з['сайт'], _группа='A'))
    задачи.sort(key=lambda к: -(к.get('выручка') or 0))
    сч = collections.Counter(к['_группа'] for к in задачи)
    отметка(этап='добор', задач=len(задачи), A_нет_ЛПР=сч['A'], B_не_открылся=сч['B'], сделано_раньше=len(сделано))
    итог = collections.Counter()
    n = [0]

    def шаг(к):
        try:
            р = одна(к)
        except Exception as e:  # noqa: BLE001
            записать({'inn': к['inn'], 'итог': 'сбой', 'ошибка': repr(e)[:150]})
            р = {}
        with _лок:
            n[0] += 1
            итог['с контактом'] += bool(р.get('контакты'))
            итог['с ФИО/должностью'] += any(r['фио'] or r['должность'] for r in р.get('контакты') or [])
            for r in р.get('контакты') or []:
                итог[r['источник'].split(':')[0]] += 1
            for k in (р.get('ошибки') or {}):
                итог['ошибка ' + k] += 1
            if n[0] % 20 == 0:
                отметка(этап='добор', готово=n[0], задач=len(задачи), **{k[:30]: v for k, v in итог.items()})

    with ThreadPoolExecutor(ПОТОКОВ) as ex:
        list(ex.map(шаг, задачи))
    отметка(этап='готово', готово=n[0], задач=len(задачи), **{k[:30]: v for k, v in итог.items()})


if __name__ == '__main__':
    try:
        main()
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass
