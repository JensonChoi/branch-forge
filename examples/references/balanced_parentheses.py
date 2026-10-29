s=input()
b=0
ok=True
for c in s:
 b+=1 if c=="(" else -1
 if b<0:ok=False
print("YES" if ok and b==0 else "NO")
