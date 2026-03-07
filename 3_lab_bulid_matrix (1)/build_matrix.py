import numpy as np
from numpy.lib.shape_base import column_stack
import pandas as pd


def get_rating_matrix(filename, dtype=np.float32):
    df=pd.read_csv("E:/VSC/CODE/3_lab_bulid_matrix (1)/" + filename,index_col="source")

    df=df.groupby(['source','target'])['rating'].mean()
    df1=df.unstack().fillna(0)
    print(df,df1)
    
    return df

'''''
두 번째 함수는 얼마나 빈번하게 제품을 구매했는지를 표현하는 
Frequent Matrix를 만드는 것 입니다. Frequent Matrix는 사용자가 
특정 제품을 구매한 횟수를 기록하는 Matrix이다. 저희가 제공하는 csv파일은 
1000i.csv라는 파일로 아래처럼 구성되어 있습니다.
본 함수에서는 기존 함수와 달리 Rating column이 없습니다. 대신 source와 target의 
조합이 한 개 이상으로 중복될 수 있고, 이것이 Frequent로 처리해야 합니다. 즉 Rating이 
명시적으로 있는게 아니라 데이터를 통해 Frequent를 찾아내는 것이 목적입니다. Matrix 형태로 
바꾸는 규칙은 다음과 같습니다.

source는 row, target은 column의 기준이 된다.
source와 target의 정렬된 값을 활용하여 index를 설정한다. 즉 위 Table에서는 1은 row의 0번째 index로 설정된다.
Source와 Target이 출현한 정보는 Frequent로 Matrix에서 각 Element 값에 할당되어야 한다.
생성되는 Matrix Ndarray로 나타내며, dtype은 np.float32
dict, collection 모듈 등 파이썬의 Built-in Module은 사용할 수 있으나, for 문은 사용할 수 없다.
생성하는 함수의 Template은 아래와 같으며, 입력값은 처리하는 csv 파일의 이름만 넣을 수 있다.
'''''


def get_frequent_matrix(filename, dtype=np.float32):
    df=pd.read_csv("E:/VSC/CODE/3_lab_bulid_matrix (1)/"+filename)
    df1=df.groupby(['source','target']).count()
    print(df1)
    return df

# get_rating_matrix("movie_rating.csv")
# get_frequent_matrix("1000i.csv")

df=pd.read_csv("E:/VSC/CODE/3_lab_bulid_matrix (1)/AirPassengers.csv")
temp=df["Month"].map(lambda x : x.split("-"))
temp_date=np.array(temp.values.tolist()) 
df["Year"]=temp_date[:,0]
df["month"]=temp_date[:,1]

df1=pd.DataFrame()
year_p=df.groupby(["Year"])["#Passengers"].sum()
mon_p=df.groupby(["month"])["#Passengers"].sum()
mon_delta=mon_p-mon_p.shift()
mon_rate=mon_p/mon_p.shift()*100
df1["Month"]=mon_p
df1["Delta"]=mon_delta
df1["Rate"]=mon_rate

pas_stack=df["#Passengers"].sum()

df.max()

print(df.max(),df.min())
# df["Year"]=temp[[0,[1]]]



