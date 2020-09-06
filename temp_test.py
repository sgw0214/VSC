# git push -u origin master

import pymysql
import requests
from urllib.request import urlopen
import logging
from bs4 import BeautifulSoup
import pandas as pd
from urllib.error import HTTPError
import time
from sqlalchemy import create_engine
import MySQLdb
import numpy as np
import urllib


#from pip._internal import req

def stock_info(stock_code, try_cnt):
    try:
        url="http://asp1.krx.co.kr/servlet/krx.asp.XMLSiseEng?code={}".format(stock_code)
        req=urlopen(url)
        result=req.read()
        xmlsoup=BeautifulSoup(result, "lxml-xml")
        stock = xmlsoup.find("TBL_StockInfo")
        stock_df=pd.DataFrame(stock.attrs, index=[0])
        stock_df=stock_df.applymap(lambda x: x.replace(",",""))

        stock_test=xmlsoup.find("DailyStock")
        stock_test=pd.DataFrame(stock_test.attrs, index=[0])
        stock_test=stock_test.applymap(lambda x: x.replace(",",""))
        stock_df.insert(0,'Code',stock_code)
        stock_df.insert(0,'day_Date',stock_test['day_Date'])
        #print(stock_df)

        return stock_df
    except HTTPError as e:  
        logging.warning(e)
        if try_cnt>=3:
            return None
        else:
            stock_info(stock_code,try_cnt=+1)

def stock_tday(stockItem,try_cnt,mpNum):
    try:
        url = 'http://finance.naver.com/item/sise_day.nhn?code='+stockItem
        html = urlopen(url) 
        source = BeautifulSoup(html.read(), "html.parser")
        k=0
        srvalue=list(range(mpNum*10))
        maxPage=source.find_all("table",align="center")
        mp = maxPage[0].find_all("td",class_="pgRR")
        #mpNum = int(mp[0].a.get('href')[-3:])
        #mpNum = 2
        #print('mpNum :',mpNum)                                
        for page in range(mpNum+1):
            #print ('page:',str(page) )
            url = 'http://finance.naver.com/item/sise_day.nhn?code='+ stockItem +'&page='+ str(page)
            html = urlopen(url)
            source = BeautifulSoup(html.read(), "html.parser")
            srlists=source.find_all("tr")
            isCheckNone = None
               
            if((page % 1) == 0):
                time.sleep(1.50)
            #print(len(srlists)-1)
            for i in range(len(srlists)-1): 
                if(srlists[i].span != isCheckNone):
                    srlists[i].td.text
                    #srvalue=srlists[i].find_all("td",align="center")[0].text, srlists[i].find_all("td",class_="num")[0].text
                    
                    srvalue[k]=srlists[i].find_all("td",class_="num")[0].text
                    k=k+1
                    #print(srvalue)
                    
        return srvalue
    except HTTPError as e:  
        logging.warning(e)
        if try_cnt>=3:
            return None
        else:
            stock_tday(stockItem,try_cnt=+1)

def stock_yday(stockItem,try_cnt,mpNum):
    try:
        url = 'http://finance.naver.com/item/sise_day.nhn?code='+stockItem
        html = urlopen(url) 
        source = BeautifulSoup(html.read(), "html.parser")
        k=0
        srvalue=list(range(mpNum*10+1))
        maxPage=source.find_all("table",align="center")
        mp = maxPage[0].find_all("td",class_="pgRR")
        #mpNum = int(mp[0].a.get('href')[-3:])
        #mpNum = 2
                             
        for page in range(mpNum+2):
            url = 'http://finance.naver.com/item/sise_day.nhn?code='+ stockItem +'&page='+ str(page)
            html = urlopen(url)
            source = BeautifulSoup(html.read(), "html.parser")
            srlists=source.find_all("tr")
            isCheckNone = None
   
            if((page % 1) == 0):
                time.sleep(1.50)

            for i in range(len(srlists)-1): 

                if(srlists[i].span != isCheckNone):
                    try:
                        srlists[i].td.text
                       
                        srvalue[k]=srlists[i].find_all("td",class_="num")[0].text
                        k=k+1
                    except IndexError as e:  
                        #logging.warning(e)
                        break
        del srvalue[0]
        return srvalue
    except HTTPError as e:  
        #logging.warning(e)
        if try_cnt>=3:
            return None
        else:
            stock_yday(stockItem,try_cnt=+1)

'''  
def yday_20_mean():
    day20 = list(range(20))

    for i in day20:
        day20[i]=int(str(yday_20[i]).replace(',',''))
    return np.mean(day20)

def tday_20_mean():
    day20 = list(range(20))

    for i in day20:
        day20[i]=int(str(tday_20[i]).replace(',',''))
    return np.mean(day20)

def tday_60_mean():
    day60 = list(range(60))

    for i in day60:
        day60[i]=int(str(tday_60[i]).replace(',',''))
    return np.mean(day60)

def yday_60_mean():
    day60 = list(range(60))

    for i in day60:
        day60[i]=int(str(yday_60[i]).replace(',',''))
    return np.mean(day60)
'''
def day_20_mean(yday_20,tday_20):
    yday20 = list(range(20))
    tday20 = list(range(20))

    for i in tday20:
        yday20[i]=int(str(yday_20[i]).replace(',',''))
        tday20[i]=int(str(tday_20[i]).replace(',',''))
    return np.mean(yday20), np.mean(tday20)

def day_60_mean(yday_60,tday_60):
    yday60 = list(range(60))
    tday60 = list(range(60))

    for i in tday60:
        yday60[i]=int(str(yday_60[i]).replace(',',''))
        tday60[i]=int(str(tday_60[i]).replace(',',''))
    return np.mean(yday60), np.mean(tday60)

import sys
import io
from tracemalloc import stop
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding = 'utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding = 'utf-8')


df = pd.read_excel('D:\VSC\CODE\상장법인목록.xls',converters={'종목코드':str})
stock_code=df.iloc[:,1]
K=0
'''
stock_code='357120'
K=0
tday_20=stock_tday(stock_code,1,2)
tday_60=stock_tday(stock_code,1,6)
yday_20=stock_yday(stock_code,1,2)
yday_60=stock_yday(stock_code,1,6)

day_20_mean=day_20_mean(yday_20,tday_20)
day_60_mean=day_60_mean(yday_60,tday_60)

print(day_20_mean,day_60_mean)

'''
for i in range(len(stock_code)):

    try:    
        
        tday_20=stock_tday(str(stock_code[i]),1,2)
        tday_60=stock_tday(str(stock_code[i]),1,6)
        yday_20=stock_yday(str(stock_code[i]),1,2)
        yday_60=stock_yday(str(stock_code[i]),1,6)

        day_20=day_20_mean(yday_20,tday_20)
        day_60=day_60_mean(yday_60,tday_60)
        #print(day_20_mean,day_60_mean)
        if day_20[1]>day_60[1]:
            
            K=K+1
            
            if day_20[0]<day_60[0]:
                print(K,stock_info(str(stock_code[i]), 1))
                
                engine = create_engine("mysql://root:rnldhks0214@localhost/temp")
                con = engine.connect()
                temp=stock_info(str(stock_code[i]),1)
                temp.to_sql(name='test',con=con,if_exists='append')
                con.close()

    except urllib.error.URLError as e:  
        logging.warning(e)




'''
stock_code='034220'
engine = create_engine("mysql://root:rnldhks0214@localhost/temp")
con = engine.connect()
temp=stock_info(stock_code,1)
print(temp)
temp.to_sql(name='test',con=con,if_exists='append')
con.close()
'''





















'''
db = pymysql.connect(host="localhost", user="root", passwd="rnldhks0214",db='temp',charset='utf8')           
cur =db.cursor()
print(cur)
print(db)
'''



'''
temp=get_sise(stock_code,1)
temp.to_sql(con=cur,name="test", if_exists="append")
#time.sleep(0.5)

#con.close()
'''