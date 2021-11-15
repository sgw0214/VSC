from numpy.core.numeric import NaN
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression


df=pd.read_csv("E :/VSC/CODE/KAGGLE/TITANIC/train.csv")
print(df.info())

df1=df
age_avg=df1.groupby(["Survived","Sex"])["Age"].mean()
age_avg=age_avg.reset_index()
# print(age_avg)
df1["Age_mod"]=df1["Age"].fillna(df1.groupby(["Survived","Sex"])["Age"]. transform('mean'))
print(df1)
df1.drop(columns=["Cabin"],inplace=True)
print(df1)

