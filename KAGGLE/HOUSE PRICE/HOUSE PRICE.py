from numpy.core.numeric import NaN
import pandas as pd
import numpy as np
from pandas.core.frame import DataFrame
from pandas.core.indexes.base import Index
from scipy.stats.stats import _threshold_mgc_map
from sklearn.base import ClassifierMixin
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.metrics import roc_curve,roc_auc_score
from sklearn.model_selection import cross_val_predict
import scipy.stats as stats 
import matplotlib
import matplotlib.pyplot as plt

ncount_list=pd.DataFrame()

df1=pd.read_csv("E:/VSC/CODE/KAGGLE/HOUSE PRICE/train.csv")
df2=pd.read_csv("E:/VSC/CODE/KAGGLE/HOUSE PRICE/test.csv")

df_train=df1
df_test=df2

df_train=df_train.drop(columns=["Alley","PoolQC","Fence","MiscFeature","FireplaceQu"])


df_train["LotFrontage"]=np.where(df_train["LotFrontage"].notnull()==True,
                                  df_train["LotFrontage"],df_train["1stFlrSF"].mean()/df_train["1stFlrSF"]*df_train["LotFrontage"].mean())



df_corr=pd.DataFrame(df_train.corr())
# print(df_corr[[ "MasVnrArea","GarageYrBlt"]])


                                  
df_train["GarageYrBlt"]=np.where(df_train["GarageYrBlt"].notnull()==True,
                                  df_train["GarageYrBlt"],df_train["YearBuilt"].median()/df_train["YearBuilt"]*df_train["GarageYrBlt"].median())

print(len(df_train.columns), df_train.info())

from sklearn.preprocessing import LabelEncoder

def encoding_label(x):
    le=LabelEncoder()
    le.fit(x) 
    le_fitted=le.transform(x)
    return le_fitted

d1=df_train[["MasVnrType"]].apply(encoding_label)
print(d1)

# print(df_train[["MasVnrArea","MasVnrArea1","OverallQual"]].head(938))
# print(df_train[["GarageYrBlt","GarageYrBlt1","YearBuilt"]].head(943))


# print(round(df_train.describe(),3),df_train.iloc[:,0].count())
# print([x for x in df_train.columns if df_train[x].count()<1460 ])
# under_1460_list=[x for x in df_train.columns if df_train[x].count()<1460 ]
# print(df_train[under_1460_list])
# print(df_train[under_1460_list].describe())


# df_count=df_train.columns(df_train.iloc[df_train.columns].count()<1460)
# print(df_count)



'''''''''
SalePrice - 부동산의 판매 가격(달러)입니다. 이것은 예측하려는 대상 변수입니다.
MSSubClass : 건물 클래스
MSZoning : 일반 zoning 분류
LotFrontage : 부동산에 연결된 거리의 선형 피트
LotArea : 평방 피트 단위의 부지 크기
거리 : 도로 접근 유형
골목 : 골목 접근 방식
LotShape : 속성의 일반적인 모양
LandContour : 부동산의 평탄도
유틸리티 : 사용 가능한 유틸리티 유형
LotConfig : 로트 구성
LandSlope : 속성의 기울기
인근 지역 : Ames 시 경계 내의 물리적 위치
조건1 : 간선도로 또는 철도와 인접
조건2 : 간선도로 또는 철도와의 근접성(초가 있는 경우)
BldgType : 주거 유형
HouseStyle : 주거 스타일
OverallQual : 전체 재질과 마감 품질
OverallCond : 전체 상태 등급
연도 : 원래 건설 날짜
YearRemodAdd : 리모델링 날짜
RoofStyle : 지붕 유형
RoofMatl : 지붕 재료
외부1차 : 주택의 외부 피복
외부 2차 : 주택의 외부 덮음(하나 이상의 재료인 경우)
MasVnrType : 석조 베니어 유형
MasVnrArea : 석조 베니어판 면적(제곱피트)
ExterQual : 외장재 품질
ExterCond : 외장재의 현황
기초 : 기초의 종류
BsmtQual : 지하실 높이
BsmtCond : 지하실의 일반 상태
BsmtExposure : 파업 또는 정원 수준의 지하 벽
BsmtFinType1 : 지하실 마감 면적의 품질
BsmtFinSF1 : 1종 제곱피트 완성
BsmtFinType2 : 두 번째 완성 영역의 품질(있는 경우)
BsmtFinSF2 : 유형 2 완성 평방 피트
BsmtUnfSF : 지하실의 미완성 평방 피트
TotalBsmtSF : 지하실 면적의 총 평방 피트
난방 : 난방의 종류
HeatingQC : 난방 품질 및 상태
CentralAir : 중앙 에어컨
전기 : 전기 시스템
1stFlrSF : 1층 평방피트
2ndFlrSF : 2층 평방피트
LowQualFinSF : 저품질 마감 평방 피트(모든 층)
GrLivArea : 지상(지상) 거실 면적 평방피트
BsmtFullBath : 지하 전체 욕실
BsmtHalfBath : 지하 반 화장실
FullBath : 등급 이상의 전체 욕실
HalfBath : 등급 이상의 반욕
침실 : 지하층 이상의 침실 수
주방 : 주방 수
KitchenQual : 주방 품질
TotRmsAbvGrd : 등급 이상의 총 방(화장실 제외)
기능 : 홈 기능 등급
벽난로 : 벽난로의 수
FireplaceQu : 벽난로 품질
GarageType : 차고 위치
GarageYrBlt : 차고 건설 연도
GarageFinish : 차고 인테리어 마감
GarageCars : 차고의 차고 크기
GarageArea : 평방 피트의 차고 크기
GarageQual : 차고 품질
GarageCond : 차고 상태
PavedDrive : 포장된 차도
WoodDeckSF : 평방 피트의 목재 데크 면적
OpenPorchSF : 평방 피트의 오픈 베란다 영역
EnclosedPorch : 평방 피트의 닫힌 베란다 영역
3SsnPorch : 제곱피트의 3계절 베란다 면적
ScreenPorch : 평방 피트의 스크린 베란다 면적
PoolArea : 평방 피트의 수영장 면적
PoolQC : 수영장 품질
울타리 : 울타리 품질
MiscFeature : 다른 범주에서 다루지 않는 기타 기능
MiscVal : 기타 기능의 $값
MoSold : 월 판매
YrSold : 년도 판매
SaleType : 판매 유형
SaleCondition : 판매 조건
'''''''''