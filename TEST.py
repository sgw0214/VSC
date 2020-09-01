# git push -u origin master

import pymysql
import requests
from urllib.request import urlopen
import logging
from bs4 import BeautifulSoup
import pandas as pd
from urllib.error import HTTPError
import time
from pip._internal import req

db = pymysql.connect(host="localhost", user="root", passwd="rnldhks0214",db='temp',charset='utf8')           
cur =db.cursor()
def get_sise(stock_code, try_cnt):
    try:
        url="http://asp1.krx.co.kr/servlet/krx.asp.XMLSiseEng?code={}".format(stock_code)
        result=req.read()
        req=urlopen(url)
        xmlsoup=BeautifulSoup(result, "lxml-xml")
        stock = xmlsoup.find("TBL_Stocklnfo")
        stock_df=pd.DataFrame(stock.attrs, index=[0])
        stock_df=stock_df.applymap(lambda x: x.replace(",",""))
        return stock_df
    except HTTPError as e:
        logging.warning(e)
        if try_cnt>=3:
            return None
        else:
            get_sise(stock_code,try_cnt=+1)
    

# 주식 시세 DB에 저장하기


stock_code=['005930','066570']

for s in stock_code:
    temp=get_sise(s,1)
    temp.to_sql(con=db,name="div_stock_sise", if_exists="append")
    time.sleep(0.5)
db.close()



'''
rows =db.fetchall()
for i in rows :
    print(i)
'''


'''
##table 추가   
sql="create table test("\
    "title varchar(100),"\
    "content text(1),"\
    "primary key(title))"
cur.execute(sql)
db.commit()


##table 삭제
sql="drop table test"
cur.execute(sql)
db.commit()


##data 조회
sql="SELECT * FROM test;"
cur.execute(sql)
result=cur.fetchall()
print(result)
'''