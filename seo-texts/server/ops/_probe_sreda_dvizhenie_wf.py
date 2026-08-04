# -*- coding: utf-8 -*-
"""Только чтение: строгое правило по СНИМКУ ДО применения (centrifugal.db.bak-*)."""
import glob, json, os, runpy, sys, time
баки = sorted(glob.glob(r'C:\seostat\data\centrifugal.db.bak-*'))
if not баки:
    print(json.dumps({'ОШИБКА': 'бэкапа нет',
                      'что_есть': os.listdir(r'C:\seostat\data')[:60]},
                     ensure_ascii=False)); sys.exit(0)
бак = баки[-1]
s = os.stat(бак)
sys.stderr.write(json.dumps({'бэкап': бак, 'байт': s.st_size,
    'mtime': time.strftime('%m-%d %H:%M:%S', time.localtime(s.st_mtime))},
    ensure_ascii=False) + '\n')
os.environ['CENTRIFUGAL_DB'] = бак
sys.path.insert(0, r'C:\sender\server\ops')
sys.argv = ['sreda_iz_citaty_wf.py'] + sys.argv[1:]
runpy.run_path(r'C:\sender\server\ops\sreda_iz_citaty_wf.py', run_name='__main__')
