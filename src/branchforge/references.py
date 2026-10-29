"""Packaged deterministic fake-provider fixtures, not live model outputs."""

REFERENCES = {
    "max_subarray": "a=list(map(int,input().split()))\nb=list(map(int,input().split()))\nbest=cur=b[0]\nfor x in b[1:]:\n cur=max(x,cur+x);best=max(best,cur)\nprint(best)\n",
    "balanced_parentheses": 's=input()\nb=0\nok=True\nfor c in s:\n b+=1 if c=="(" else -1\n if b<0:ok=False\nprint("YES" if ok and b==0 else "NO")\n',
    "two_sum": 'n,t=map(int,input().split())\na=list(map(int,input().split()))\nseen=set();ok=False\nfor x in a:\n if t-x in seen:ok=True\n seen.add(x)\nprint("YES" if ok else "NO")\n',
    "shortest_path": "from collections import deque\nn,m=map(int,input().split())\ng=[[] for _ in range(n)]\nfor _ in range(m):\n u,v=map(int,input().split());g[u-1].append(v-1);g[v-1].append(u-1)\nd=[-1]*n;d[0]=0;q=deque([0])\nwhile q:\n u=q.popleft()\n for v in g[u]:\n  if d[v]<0:d[v]=d[u]+1;q.append(v)\nprint(d[-1])\n",
    "coin_change": "n,t=map(int,input().split())\na=list(map(int,input().split()))\nd=[0]+[t+1]*t\nfor x in range(1,t+1):\n for c in a:\n  if c<=x:d[x]=min(d[x],d[x-c]+1)\nprint(d[t] if d[t]<=t else -1)\n",
}
