import sys, pandas as pd
p = sys.argv[1]
x = pd.ExcelFile(p)
print('листы:', x.sheet_names)
for sh in x.sheet_names:
    df = x.parse(sh)
    print('\n=== лист %r: %d строк × %d колонок' % (sh, len(df), len(df.columns)))
    for c in df.columns:
        s = df[c]
        nn = s.notna() & (s.astype(str).str.strip() != '')
        vals = s[nn].astype(str)
        u = vals.nunique()
        ex = vals.value_counts().head(6 if u <= 30 else 3)
        exs = '; '.join('%s (%d)' % (k[:60], v) for k, v in ex.items())
        print('  %-40s заполнено %4d, разных %4d | %s' % (str(c)[:40], nn.sum(), u, exs[:260]))
