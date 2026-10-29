from collections import deque
n,m=map(int,input().split())
g=[[] for _ in range(n)]
for _ in range(m):
 u,v=map(int,input().split());g[u-1].append(v-1);g[v-1].append(u-1)
d=[-1]*n;d[0]=0;q=deque([0])
while q:
 u=q.popleft()
 for v in g[u]:
  if d[v]<0:d[v]=d[u]+1;q.append(v)
print(d[-1])
