import duckdb,json,time
con=duckdb.connect();con.execute("LOAD httpfs;SET threads=8;")
m=[x for x in json.load(open('meta_CC-MAIN-2026-39.json')) if x[1]]
Z={'ru':('ru,','ru-'),'by':('by,','by-'),'su':('su,','su-'),'rf':('xn--p1ai,','xn--p1ai-')}
con.execute("""create table cand as select d from 'zone_domains.parquet' where p_elev or d_elev or p_seed or d_seed or p_exp or d_exp or p_nuts or d_nuts or p_berr or d_berr or p_food or d_food""")
parts=[]
for z,(lo,hi) in Z.items():
    for f in [x[0] for x in m if x[1]<hi and x[2]>=lo]:
        t=time.time()
        con.execute(f"""insert into roots select url_host_registered_domain d, url, url_host_name h, warc_filename, warc_record_offset, warc_record_length
          from read_parquet('{f}') where url_surtkey>='{lo}' and url_surtkey<'{hi}' and fetch_status=200 and url_path in ('/','') and url_query is null""") if parts else \
        con.execute(f"""create table roots as select url_host_registered_domain d, url, url_host_name h, warc_filename, warc_record_offset, warc_record_length
          from read_parquet('{f}') where url_surtkey>='{lo}' and url_surtkey<'{hi}' and fetch_status=200 and url_path in ('/','') and url_query is null""")
        parts.append(f);print(z,f'{time.time()-t:.0f}s',flush=True)
# одна главная на домен: предпочесть хост = домен или www.домен
con.execute("""copy (select * from (select r.*, row_number() over (partition by r.d order by (h=r.d or h='www.'||r.d) desc, length(url)) rn
   from roots r join cand using(d)) where rn=1) to 'roots_cand.parquet' (format parquet)""")
print(con.execute("select count(*) from cand").fetchone(), con.execute("select count(*) from 'roots_cand.parquet'").fetchone())
print('done')
