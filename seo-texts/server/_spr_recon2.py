# -*- coding: utf-8 -*-
"""Разведка 2: что уже есть от checko в базе + печать проб recon1."""
import io
import json
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
O = {}
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)

O['requisites'] = dict(zip(
    ['всего', 'src_разные', 'site_checko_непусто', 'phones_checko', 'emails_checko',
     'revenue_непусто'],
    cx.execute("""SELECT COUNT(*), COUNT(DISTINCT src),
      SUM(COALESCE(site_checko,'')!=''), SUM(COALESCE(phones_checko,'')!=''),
      SUM(COALESCE(emails_checko,'')!=''), SUM(COALESCE(revenue_rub,'') NOT IN ('','0'))
      FROM requisites""").fetchone()))
O['requisites_src'] = cx.execute(
    "SELECT src, COUNT(*) FROM requisites GROUP BY src ORDER BY 2 DESC").fetchall()[:12]
O['site_checko_примеры'] = cx.execute(
    "SELECT inn, site_checko FROM requisites WHERE COALESCE(site_checko,'')!='' LIMIT 8"
).fetchall()
O['companies.site_checko'] = cx.execute(
    "SELECT SUM(COALESCE(site_checko,'')!=''), COUNT(*) FROM companies").fetchone()
O['стадии'] = cx.execute(
    "SELECT stage, COUNT(*) FROM stage_log GROUP BY stage ORDER BY 2 DESC").fetchall()
O['companies_срез'] = dict(zip(
    ['всего', 'с_site', 'с_cand_site', 'без_обоих', 'с_выручкой',
     'без_сайта_с_выручкой', 'с_ogrn', 'без_сайта_с_ogrn'],
    cx.execute("""SELECT COUNT(*),
      SUM(COALESCE(site,'')!=''), SUM(COALESCE(cand_site,'')!=''),
      SUM(COALESCE(site,'')='' AND COALESCE(cand_site,'')=''),
      SUM(COALESCE(revenue_rub,'') NOT IN ('','0')),
      SUM(COALESCE(site,'')='' AND COALESCE(cand_site,'')='' AND COALESCE(revenue_rub,'') NOT IN ('','0')),
      SUM(COALESCE(ogrn,'')!=''),
      SUM(COALESCE(site,'')='' AND COALESCE(cand_site,'')='' AND COALESCE(ogrn,'')!='')
      FROM companies""").fetchone()))
# распределение выручки среди безсайтовых
O['безсайтовые_по_выручке'] = cx.execute("""
  SELECT SUM(CAST(revenue_rub AS REAL)>=1e10), SUM(CAST(revenue_rub AS REAL)>=1e9),
         SUM(CAST(revenue_rub AS REAL)>=1e8), SUM(CAST(revenue_rub AS REAL)>=1e7)
  FROM companies WHERE COALESCE(site,'')='' AND COALESCE(cand_site,'')=''
    AND COALESCE(revenue_rub,'') NOT IN ('','0')""").fetchone()
cx.close()

try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
    O['пробы'] = prev.get('recon1', {}).get('пробы', {})
except Exception as e:
    O['пробы'] = str(e)[:100]
print(json.dumps(O, ensure_ascii=False)[:5900])
