import pandas as pd
import numpy as np
import mysql.connector


df=pd.DataFrame()
for i in range(10):
    print(i)
    print("귀완")
    if i==0:
        df=pd.read_excel('E:\\VSC\\CODE\\Stock\\'+ str(2015+i) +'.xlsx')
    else:
        df=pd.concat([df,pd.read_excel('E:\\VSC\\CODE\\Stock\\'+str(2015+i) +'.xlsx')])
    print(df.shape)
    
    breakpoint()
    
df=df.drop()