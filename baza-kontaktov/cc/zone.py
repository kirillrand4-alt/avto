import duckdb,json,time,os
con=duckdb.connect();con.execute("LOAD httpfs;SET threads=8;")
m=[x for x in json.load(open('meta_CC-MAIN-2026-39.json')) if x[1]]
Z={'ru':('ru,','ru-'),'by':('by,','by-'),'su':('su,','su-'),'rf':('xn--p1ai,','xn--p1ai-')}
B=r'(^|[/._-])'
SEG={
 'elev': B+r'(elevat|elevator|hpp|khp|kxp|zernohran|zernosush|zerno-?sush|sushk[aiy]?-?zern|hranen\w*-?zern|priem\w*-?zern|podrabot|silos|mukomol|kombikorm|zernotok)',
 'seed': B+r'(semena|semyon|semen|semenovod|gibrid|reprodukc|protravl|kalibrov|posevn|selekc|pitomnik|sazhen|rassad|seeds?([/._-]|$))',
 'exp':  B+r'(export|eksport|grain|wheat|barley|sunflower|oilseed|pulse|chickpea|lentil|flax|psheni|yachmen|kukuruz|podsolnech|raps|nut-|chechevic|goroh|soya|zhmyh|shrot)',
 'nuts': B+r'(oreh|orekh|funduk|grecki|mindal|keshyu|kedrov|fistash|pistach|nuts?([/._-]|$)|hazelnut|walnut|almond)',
 'berr': B+r'(yagod|klubnik|zemlyanik|malin|smorodin|golubik|klyukv|brusnik|oblepih|zhimolost|berry|berries|iqf|shokov|zamorozk|dzhem|konfityur|varen)',
 'food': B+r'(molok|molochn|syr([/._-]|$)|syry|tvorog|maslo|myas|kolbas|hleb|konditer|krup|muk[ai]([/._-]|$)|sahar|sok[ia]?([/._-]|$)|konserv|makaron|pelmen|polufabrik|pishchev|myasopererab|pticefabr|krahmal|patok)',
}
CONT=r'(kontakt|contact|rekviz|requisit|about|o-kompanii|o_kompanii|company|o-nas|politik|privacy)'
for z,(lo,hi) in Z.items():
    files=[x[0] for x in m if x[1]<hi and x[2]>=lo]
    for i,f in enumerate(files):
        out=f'zone/{z}_{i}.parquet'
        if os.path.exists(out): continue
        t=time.time()
        segcols=','.join(f"bool_or(regexp_matches(p,'{rx}')) as p_{k}, bool_or(regexp_matches(d,'{rx}')) as d_{k}" for k,rx in SEG.items())
        con.execute(f"""copy (select d, count(*) n, bool_or(p in ('/','')) root, bool_or(regexp_matches(p,'{CONT}')) cont, {segcols}
           from (select url_host_registered_domain d, lower(url_path) p from read_parquet('{f}')
                 where url_surtkey>='{lo}' and url_surtkey<'{hi}' and fetch_status=200) group by d) to '{out}' (format parquet)""")
        print(z,i,len(files),f'{time.time()-t:.0f}s',flush=True)
print('done')
