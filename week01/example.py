# 간단한 파이썬 예제
name = "Python"
numbers = [1, 2, 3, 4, 5]

def square(x):
    return x * x

for n in numbers:
    print(f"{name}에서 {n}의 제곱은 {square(n)}입니다.")

print("프로그램 종료")