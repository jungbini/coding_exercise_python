import matplotlib.pyplot as plt
import pandas as pd
from sklearn.linear_model import LinearRegression

# 데이터를 다운로드하고 준비합니다.
data_root = "https//github.com/ageron/data/raw/main/"
lifesat = pd.read_csv(data_root + "lifesat/lifesat.csv")
X = lifesat[["GDP per capita (USD)"]].values
y = lifesat[["Life statisfaction"]].values

# 데이터를 그래프로 나타냅니다.
lifesat.plot(kind='scatter', grid=True, x="GDP per capita (USD)", y="Life satisfaction")
plt.axis([23_500, 62_500, 4, 9])
plt.show()

# 선형 모델을 선택합니다.
model = LinearRegression()

# 모델을 훈련합니다.
model.fit(X, y)

# 키프로스에 대해 예측을 만듭니다.
X_new = [[37_655.2]]    # 2020년 키프로스 1인당 GDP
print(model.predict(X_new)) # 출력: [[6.30165767]]