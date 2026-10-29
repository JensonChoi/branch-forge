n,t=map(int,input().split())
a=list(map(int,input().split()))
d=[0]+[t+1]*t
for x in range(1,t+1):
 for c in a:
  if c<=x:d[x]=min(d[x],d[x-c]+1)
print(d[t] if d[t]<=t else -1)
