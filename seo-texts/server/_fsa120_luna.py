# -*- coding: utf-8 -*-
# 21.10, владелец: «2» — агенты глубокого поиска на GPT-6 Luna (~$0,005 на компанию) для второй волны (уникальные Meyer
# 120 млн – 1 млрд без сделок), у которых дешёвая схема сайта не дала («ИНН ни на одном кандидате», «сайт группы?», бывший
# «сайт»-справочник, не проверены). Сначала крупные. Запасная модель — gpt-5.6-luna, без ухода на Sol (KC_MODEL_POSLEDNIY='').
# xmlriver — до остатка 1 ₽. После агентов — досбор (обход + паспорт) по подтверждённым сайтам, справочники отсеиваются.
# Durable: fsa120L-glubokiy.jsonl (fsync, резюм), fsa120Lp-*.jsonl.
import io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa120_luna_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa120_luna.py'), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(45)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-700:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402

сп = json.load(io.open(os.path.join(ДРОП, 'fsa120-spisok.json'), encoding='utf-8'))['компании']
искл = set(json.load(io.open(os.path.join(ДРОП, 'fsa-isklyuchit.json'), encoding='utf-8')))
рез = V.читать(os.path.join(DIR, 'fsa120-sayt-inn.jsonl'))
уже_sol = set(V.читать(os.path.join(DIR, 'fsa1000-glubokiy.jsonl')))
нб = {i: к for i, к in сп.items() if i not in искл and i not in уже_sol and (к.get('выручка') or 0) < 1e9
      and not (рез.get(i) or {}).get('сайт')}
V.п('Luna-агенты: компаний', len(нб), '| из них бывший «сайт»-справочник',
    sum(1 for i in нб if str((рез.get(i) or {}).get('как', '')).startswith('агрегатор')))
for имя, данные in (('fsa120L-spisok.json', {'компании': нб, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}),
                    ('fsa120L-glubokiy-vhod.json', {i: {'отклонены': (рез.get(i) or {}).get('агрегатор', '')} for i in нб})):
    with open(os.path.join(ДРОП, имя), 'w', encoding='utf-8') as f:
        json.dump(данные, f, ensure_ascii=False)
shutil.copyfile(os.path.join(ДРОП, 'fsa120L-spisok.json'), os.path.join(DIR, 'fsa120L-spisok.json'))
env = dict(os.environ, KC_NABOR='fsa120L', KC_CEL='meyer', PROVIDER_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna',
           KC_MODEL_POSLEDNIY='', KC_AGENT_POTOKOV='30', KC_XML_KANALOV='4', KC_AGENT_XML_MIN='1', KC_MODEL_PARALLEL='30',
           PYTHONIOENCODING='utf-8')
t0 = time.time()
pr, лог = V.запуск('kc_agent_glubokiy.py', env, 'fsa120L_agenty')
pr.wait()
V.п('Luna-агенты: код', pr.returncode, 'за %.1f ч' % ((time.time() - t0) / 3600), '|', V.хвост(лог))
try:
    shutil.copyfile(os.path.join(DIR, 'fsa120L-glubokiy.jsonl'), os.path.join(ДРОП, 'fsa120L-glubokiy.jsonl'))
except Exception as e:  # noqa: BLE001
    V.п('копия', repr(e)[:80])
V.досбор('fsa120L')
V.п('LUNA fsa120: ГОТОВО')
