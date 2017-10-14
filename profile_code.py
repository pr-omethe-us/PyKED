import pstats
p = pstats.Stats('profile')
p.strip_dirs()
p.sort_stats('tottime')
print(p.print_stats(20))
