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



df=pd.read_csv("E:/VSC/CODE/KAGGLE/TITANIC/train.csv")
df2=pd.read_csv("E:/VSC/CODE/KAGGLE/TITANIC/test.csv")
df_ty=pd.read_csv("E:/VSC/CODE/KAGGLE/TITANIC/gender_submission.csv")
# print(df.info())

df1=df
df_t=df2

df1["Age_mod"]=df1["Age"].fillna(df1.groupby(["Pclass","Sex"])["Age"]. transform('mean'))
df1.drop(columns=["Cabin"],inplace=True)
df1.drop(columns=["Ticket"],inplace=True)
df1.drop(columns=["Age"],inplace=True)
df1.drop(columns=["Name"],inplace=True)
df1["Sex"].replace({"male":1,"female":0},inplace=True)
df1["Embarked"]=df1["Embarked"].fillna("S")
df1["Embarked"].replace({"S":1,"C":2,"Q":3},inplace=True)


df_t["Age_mod"]=df_t["Age"].fillna(df_t.groupby(["Pclass","Sex"])["Age"]. transform('mean'))
df_t.drop(columns=["Cabin"],inplace=True)
df_t.drop(columns=["Ticket"],inplace=True)
df_t.drop(columns=["Age"],inplace=True)
df_t.drop(columns=["Name"],inplace=True)
df_t["Sex"].replace({"male":1,"female":0},inplace=True)
df_t["Embarked"]=df_t["Embarked"].fillna("S")
df_t["Embarked"].replace({"S":1,"C":2,"Q":3},inplace=True)
df_t["Fare"]=df_t["Fare"].fillna(df_t["Fare"].mean())

# print(df1.describe(),df1.info())
# print(df1.corr(method='pearson'))
# print(df_t)

train_x=df1.iloc[:,2:]
train_y=df1["Survived"]
test_x=df_t.iloc[:,1:]
test_y=df_ty["Survived"]
# print(train_x,train_y,test_x,test_y)
# print(test_x.describe(),test_x.info())
model=RandomForestClassifier()
model.fit(train_x,train_y)
pred=model.predict(test_x)

print(classification_report(pred,test_y))
# model.score(pred,test_y)
y_scores=cross_val_predict(model,train_x,train_y,cv=3)
fpr,tpr,thresholds=roc_curve(train_y,y_scores)
print(fpr,tpr,thresholds)
def plot_roc_curve(fpr,tpr,label=None):
    plt.plot(fpr,tpr,linewidth=2,label=label)
    plt.plot([0,1],[0,1],'k--')
    plt.axis([0,1,0,1])
    plt.xlabel("FPR")
    plt.ylabel("TPR")
    return plt.show()
# plot_roc_curve(fpr,tpr)
print(roc_auc_score(train_y,y_scores))
Submit=DataFrame()
print(df2)
Submit["PassengerId"]=df2["PassengerId"]
Submit["Survived"]=pred

Submit.to_csv("E:/VSC/CODE/KAGGLE/TITANIC/submit.csv",index=False)







