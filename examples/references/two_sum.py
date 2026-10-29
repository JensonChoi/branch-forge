n,t=map(int,input().split())
a=list(map(int,input().split()))
seen=set();ok=False
for x in a:
 if t-x in seen:ok=True
 seen.add(x)
print("YES" if ok else "NO")
