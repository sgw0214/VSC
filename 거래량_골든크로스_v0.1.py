#git push -u origin master
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

        return stock_df
    except HTTPError as e:  
        print(e,stock_code)
        if try_cnt>=3:
            return None
        else:
            stock_info(stock_code,try_cnt=+1)

'''
def Volume(stock_code, try_cnt):
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

        return stock_df
    except HTTPError as e:  
        print(e,stock_code)
        if try_cnt>=3:
            return None
        else:
            stock_info(stock_code,try_cnt=+1)

'''

def stock_tday(stockItem,try_cnt,mpNum):
    try:
        url = 'http://finance.naver.com/item/sise_day.nhn?code='+stockItem
        html = urlopen(url) 
        source = BeautifulSoup(html.read(), "html.parser")
        k=0
        srvalue=list(range(mpNum*10))
        maxPage=source.find_all("table",align="center")
        mp = maxPage[0].find_all("td",class_="pgRR")
                             
        for page in range(mpNum+1):

            url = 'http://finance.naver.com/item/sise_day.nhn?code='+ stockItem +'&page='+ str(page)
            html = urlopen(url)
            source = BeautifulSoup(html.read(), "html.parser")
            srlists=source.find_all("tr")
            isCheckNone = None
               
            #if((page % 1) == 0):
                #time.sleep(1.50)

            for i in range(len(srlists)-1): 
                if(srlists[i].span != isCheckNone):
                    srlists[i].td.text
                    srvalue[k]=srlists[i].find_all("td",class_="num")[0].text
                    k=k+1
                    
        return srvalue
    except HTTPError as e:  
        print(e,stockItem)
        if try_cnt>=3:
            return None
        else:
            stock_tday(stockItem,try_cnt=+1,*mpNum)
            
def stock_yday(stockItem,try_cnt,mpNum):
    try:
        url = 'http://finance.naver.com/item/sise_day.nhn?code='+stockItem
        html = urlopen(url) 
        source = BeautifulSoup(html.read(), "html.parser")
        k=0
        srvalue=list(range(mpNum*10+1))
        maxPage=source.find_all("table",align="center")
        mp = maxPage[0].find_all("td",class_="pgRR")
     
        for page in range(mpNum+2):
            url = 'http://finance.naver.com/item/sise_day.nhn?code='+ stockItem +'&page='+ str(page)
            html = urlopen(url)
            source = BeautifulSoup(html.read(), "html.parser")
            srlists=source.find_all("tr")
            isCheckNone = None
            try:
            #if((page % 1) == 0):
                #time.sleep(1.50)
                
                for i in range(len(srlists)-1): 

                    if(srlists[i].span != isCheckNone):

                            srlists[i].td.text
                            srvalue[k]=srlists[i].find_all("td",class_="num")[0].text
                            k=k+1
            except IndexError as e:  
                    None
                        
        del srvalue[0]
        return srvalue
    except HTTPError as e:  
        print(e,stockItem)
        if try_cnt>=3:
            return None
        else:
            stock_yday(stockItem,try_cnt=+1,*mpNum)

def day_20_mean(yday_20,tday_20):
    try:
        yday20 = list(range(20))
        tday20 = list(range(20))

        for i in tday20:
            if str(tday_20[i])!="" and str(yday_20[i])!="":
                #print(str(tday_20[i]),str(yday_20[i]))
                
                yday20[i]=int(str(yday_20[i]).replace(',',''))
                tday20[i]=int(str(tday_20[i]).replace(',',''))
            else: 
                print('0')

        return np.mean(yday20), np.mean(tday20)
    except ValueError as e:  
        print('Error')


def day_60_mean(yday_60,tday_60):
    try:
        yday60 = list(range(60))
        tday60 = list(range(60))

        for i in tday60:
            yday60[i]=int(str(yday_60[i]).replace(',',''))
            tday60[i]=int(str(tday_60[i]).replace(',',''))
        return np.mean(yday60), np.mean(tday60)
    except ValueError as e:  
        print('Error')

def volume_avg(stock_code, try_cnt):
    try:
        url="http://asp1.krx.co.kr/servlet/krx.asp.XMLSiseEng?code={}".format(stock_code)
        req=urlopen (url)
        result=req.read()
        xmlsoup=BeautifulSoup(result, "lxml-xml")
        stock_d=pd.DataFrame ()
        a=range(10)
        for i in a:
            stock= xmlsoup.find_all("DailyStock")
            stock_df=pd.DataFrame(stock[i].attrs,index=[i])
            stock_d=stock_d.append(stock_df)
            stock_d=stock_d.applymap(lambda x: x.replace(",",""))
            #print (stock_d)
        volume_avg=stock_d.iloc[1:9,7].astype('int64').mean()
        #print(volume_avg)|
        return volume_avg
    except HTTPError as e:
        print(e, stock_code)
        if try_cnt>=3:
            return None
        else:stock_info(stock_code, try_cnt=+1)

import sys
import io
from tracemalloc import stop


#sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding = 'utf-8')
#sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding = 'utf-8')

df = pd.read_excel('D:\VSC\CODE\상장법인목록.xls',converters={'종목코드':str})
stock_code=df.iloc[:,1]

K=0

for i in range(len(stock_code)):

    try:
        info=stock_info(str(stock_code[i]), 1)
        volume_AVG=volume_avg(str(stock_code[i]),1)
        if int(info.iloc[0,7])>int(volume_AVG*1): #거래량
            tday_20=stock_tday(str(stock_code[i]),1,2)
            tday_60=stock_tday(str(stock_code[i]),1,6)
            yday_20=stock_yday(str(stock_code[i]),1,2)
            yday_60=stock_yday(str(stock_code[i]),1,6)

            day_20=day_20_mean(yday_20,tday_20)
            day_60=day_60_mean(yday_60,tday_60)

            if day_20[1]*1.05>int(info.iloc[0,3]) or day_20[1]*0.95>int(info.iloc[0,3]): #종가-20일돌파
                if info.iloc[0,4] != "" and info.iloc[0,16] != "":   # 빈값확인 
                    if day_20[1]>=day_60[1] and day_20[0]<=day_60[0]: # 20일-60일돌파

                        print(K,'Check',str(stock_code[i]),info.iloc[0,2])
                        engine = create_engine("mysql://root:rnldhks0214@localhost/temp")
                        con = engine.connect()
                        temp=stock_info(str(stock_code[i]),1)
                        temp.to_sql(name='test',con=con,if_exists='append')
                        con.close()
                        
                        K=K+1
                    else:
                        print(K,'/Golden Cross Fail/',str(stock_code[i]),info.iloc[0,2])
                        K=K+1
                else:
                    print(K,'/None Value/',str(stock_code[i]),info.iloc[0,2])
                    K=K+1
                
            else:
                print(K,'/Under 20day Line/',str(stock_code[i]),info.iloc[0,2])
                K=K+1
        else:
            print(K,'/Under Tran.Vol/',str(stock_code[i]),info.iloc[0,2])
            K=K+1
        #break
    except AttributeError or TypeError or urllib.error.URLError as e:   # as e:  
        #print(e,stock_info(str(stock_code[i]), 1),info.iloc[0,2])
        print('Error',str(stock_code[i]))

