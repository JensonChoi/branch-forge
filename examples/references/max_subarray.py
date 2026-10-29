a=list(map(int,input().split()))
b=list(map(int,input().split()))
best=cur=b[0]
for x in b[1:]:
 cur=max(x,cur+x);best=max(best,cur)
print(best)
