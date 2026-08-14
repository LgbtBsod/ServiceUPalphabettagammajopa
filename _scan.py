import os
total = 0
out = []
for r, d, fs in os.walk('.'):
    if '__pycache__' in r:
        continue
    for f in fs:
        if f.endswith('.py') and f != '_scan.py':
            p = os.path.join(r, f)
            try:
                with open(p, encoding='utf-8') as fh:
                    n = sum(1 for _ in fh)
                total += n
                out.append((n, p))
            except Exception as e:
                out.append((-1, p + ' ' + str(e)))
for n, p in sorted(out, reverse=True):
    print(f'{n:6d}  {p}')
print('TOTAL', total)
