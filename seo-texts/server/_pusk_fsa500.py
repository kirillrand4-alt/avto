# -*- coding: utf-8 -*-
# 20.10, владелец: «глубокий поиск ЛПР по уникальным — только тем, кому подходит Meyer, от 500 млн выручки». Набор fsa500:
# изготовители ФСА с классом Meyer (fsa_klass3, Sol), выручка от 500 млн, которых раньше не находил поиск Meyer-7/КЦ-1
# (FSA-MEYER-VSE, колонка «Уникальная»). Агенты kc_agent_glubokiy на Sol, цель — ЛПР Meyer (KC_CEL=meyer).
# Вход: дроп fsa500-spisok.json + fsa500-glubokiy-vhod.json. Выход (fsync, резюм): C:\sender\server\fsa500-glubokiy.jsonl -> дроп.
import json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'pusk_fsa500_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_pusk_fsa500.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(90)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-700:]},
                     ensure_ascii=False))
    sys.exit(0)
shutil.copyfile(os.path.join(ДРОП, 'fsa500-spisok.json'), os.path.join(DIR, 'fsa500-spisok.json'))
env = dict(os.environ, KC_NABOR='fsa500', KC_CEL='meyer', PROVIDER_MODEL='gpt-6-sol', KC_AGENT_POTOKOV='30',
           KC_XML_KANALOV='4',
           # 20.10, владелец: «запускай, пополню позже» — на 55 ₽ идём до остатка 5 ₽; после пополнения перезапуск продолжит
           # (сделанные пропускаются, «вслепую и пусто» переделываются)
           KC_AGENT_XML_MIN=os.environ.get('FSA500_XML_MIN', '5'), KC_MODEL_PARALLEL='30', PYTHONIOENCODING='utf-8')
t0 = time.time()
print(time.strftime('%d.%m %H:%M:%S'), 'старт агентов fsa500', flush=True)
# свой лог агентам (вывод агентов виден в итоге запуска; 20.10 первый пуск молча встал на балансе xmlriver < 60 ₽)
алог = os.path.join(DIR, 'fsa500_agenty_%s.log' % time.strftime('%d%m-%H%M'))
with open(алог, 'wb') as ф:
    r = subprocess.run([sys.executable, '-u', os.path.join(DIR, 'kc_agent_glubokiy.py')], cwd=DIR, env=env,
                       stdin=subprocess.DEVNULL, stdout=ф, stderr=subprocess.STDOUT)
print(open(алог, encoding='utf-8', errors='replace').read()[-800:], flush=True)
print(time.strftime('%d.%m %H:%M:%S'), 'агенты: код', r.returncode, 'за %.1f ч' % ((time.time() - t0) / 3600), flush=True)
