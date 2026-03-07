#git push -u origin master
#"set PYTHONIOENCODING=utf8 && python" #인코딩(CodeRunner)
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
    except ValueError or TypeError as e:  
        print('Error day_20_mean')

def day_sel_mean(tday_60,k): #과거20일선(예:3일전 20일선)
    try:
        #yday60 = list(range(20))
        tday20 = list(range(20))
        a=range(20)
        for i in a:
            if str(tday_60[i])!="":
                #print(str(tday_20[i]),str(yday_20[i]))
                
                #yday20[i]=int(str(yday_20[i]).replace(',',''))
                tday20[i]=int(str(tday_60[i+k]).replace(',',''))
            else: 
                print('0')
                
        return np.mean(tday20)
    except ValueError or TypeError as e:  
        print('Error day_sel_mean')

def day_past_mean(tday_60,k): #일봉값수정(예:17일선,8일선)
    try:
        #yday60 = list(range(20))
        tday20 = list(range(k))
        a=range(k)
        for i in a:
            if str(tday_60[i])!="":
                #print(str(tday_20[i]),str(yday_20[i]))
                
                #yday20[i]=int(str(yday_20[i]).replace(',',''))
                tday20[i]=int(str(tday_60[i]).replace(',',''))
            else: 
                print('0')
                
        return np.mean(tday20)
    except ValueError or TypeError as e:  
        print('Error day_past_mean')

def day_selpast_mean(tday_60,k,m): #일봉값수정(예:2일전17일선,8일선)
    try:
        #yday60 = list(range(20))
        tday20 = list(range(m))
        a=range(m)
        for i in a:
            if str(tday_60[i])!="":
                #print(str(tday_20[i]),str(yday_20[i]))
                
                #yday20[i]=int(str(yday_20[i]).replace(',',''))
                tday20[i]=int(str(tday_60[i+k]).replace(',',''))
            else: 
                print('0')
                
        return np.mean(tday20)
    except ValueError or TypeError as e:  
        print('Error day_selpast_mean')


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
        else:
            stock_info(stock_code, try_cnt=+1)

def stock_summary(stockItem):
    url = 'http://finance.naver.com/item/coinfo.nhn?code='+ stockItem +'&target=finsum_more'
    html = urlopen(url) 
    source = BeautifulSoup(html.read(), "html.parser")
    srlists=source.find_all("p")[0:2]
    srlists=str(srlists).replace('<p>','')
    srlists=str(srlists).replace('</p>','')
    srlists=str(srlists).replace(',','')
    return srlists

def stock_finance(stockItem):
    try:
        url1 = 'https://comp.fnguide.com/SVO2/asp/SVD_Finance.asp?pGB=1&gicode=A'+ stockItem +'&cID=&MenuYn=Y&ReportGB=D&NewMenuID=103&stkGb=701'
        session=requests.Session()
        r=session.get(url1)
        r.encoding='utf-8'
        r.text
        df=pd.read_html(r.text)[1]
        return df
    except ValueError as e:
        return 0
  

import sys
import io
from tracemalloc import stop

df = pd.read_excel('D:\VSC\CODE\상장법인목록.xls',converters={'종목코드':str})
stock_code=df.iloc[:,1]

K=0
'''
from datetime import date, timedelta
 
today = date.today()
y20d = date.today() - timedelta(1)
'''
for i in range(len(stock_code)):
    try:
        info=stock_info(str(stock_code[i]), 1)
        tday_60=stock_tday(str(stock_code[i]),1,6)
        if tday_60[59]!=59: #60일선없으면제외
            tday_20=stock_tday(str(stock_code[i]),1,2)
            yday_20=stock_yday(str(stock_code[i]),1,2)
            yday_60=stock_yday(str(stock_code[i]),1,6)

            day_past_3_17=day_selpast_mean(tday_60,3,17)
            day_past_2_17=day_selpast_mean(tday_60,2,17)
            day_past_1_17=day_selpast_mean(tday_60,1,17)

            #day_20=day_20_mean(yday_20,tday_20)
            day_60=day_60_mean(yday_60,tday_60)

            if day_past_1_17<day_60[1]*1.05 and day_past_1_17>day_60[1]*0.95: #60일선과 17일선 근접
 
                if day_past_2_17<day_past_1_17 and day_past_2_17<day_past_3_17: #17일선 상승방향 전환
                    print(day_past_3_17,day_past_2_17,day_past_1_17 )
                    fin=stock_finance(str(stock_code[i]))
                    if fin.iloc[5,4]>10 : #영업이익 10억이상
                        if ((int(info.iloc[0,3])-int(info.iloc[0,6]))/int(info.iloc[0,6]))<0.05: #급등종목제한

                            print(K,'Check',str(stock_code[i]),info.iloc[0,2])
                            #print(stock_summary(str(stock_code[i])))
                            engine = create_engine("mysql://root:rnldhks0214@localhost/temp")
                            con = engine.connect()
                            temp=info#.insert(0,'Description',stock_summary(str(stock_code[i])))
                            
                            #temp=stock_summary(str(stock_code[i]))
                            temp.to_sql(name='test1',con=con,if_exists='append')
                            con.close()
                            K=K+1     
                        else:
                            print(K,'/Today Jump/',str(stock_code[i]),info.iloc[0,2])
                            K=K+1   
                    else:
                        print(K,'/Operating profit X/',str(stock_code[i]),info.iloc[0,2])
                        K=K+1 
                else:
                    print(K,'/20day Up Turn X/',str(stock_code[i]),info.iloc[0,2])
                    K=K+1
            else:
                print(K,'/20day range(60day) X/',str(stock_code[i]),info.iloc[0,2])
                K=K+1
        else:
            print(K,'/New Stock/',str(stock_code[i]),info.iloc[0,2])
            K=K+1
    except AttributeError or TypeError or urllib.error.URLError as e:   # as e:  
        #print(e,stock_info(str(stock_code[i]), 1),info.iloc[0,2])
        print(e,'Error',str(stock_code[i]))

'''
from datetime import date, timedelta
 
today = date.today()
y20d = date.today() - timedelta(1)
'''
'''
for i in range(len(stock_code)):
    try:
        info=stock_info(str(stock_code[i]), 1)
        tday_60=stock_tday(str(stock_code[i]),1,6)
        if tday_60[59]!=59:
            tday_20=stock_tday(str(stock_code[i]),1,2)
            yday_20=stock_yday(str(stock_code[i]),1,2)
            yday_60=stock_yday(str(stock_code[i]),1,6)

            day_20=day_20_mean(yday_20,tday_20)
            day_60=day_60_mean(yday_60,tday_60)

            if day_20[1]<day_60[1]*1.05 and day_20[1]>day_60[1]*0.95:
                day_sel_10=day_sel_mean(tday_60,10)
                day_sel_3=day_sel_mean(tday_60,3)

                if day_20[0]<day_20[1] and day_20[0]<day_sel_3 :
                    print(day_20[0],day_20[1],day_sel_3)
                    fin=stock_finance(str(stock_code[i]))
                    if fin.iloc[5,4]>10 :  
                        if ((int(info.iloc[0,3])-int(info.iloc[0,6]))/int(info.iloc[0,6]))<0.05:

                            print(K,'Check',str(stock_code[i]),info.iloc[0,2])
                            #print(stock_summary(str(stock_code[i])))
                            engine = create_engine("mysql://root:rnldhks0214@localhost/temp")
                            con = engine.connect()
                            temp=info#.insert(0,'Description',stock_summary(str(stock_code[i])))
                            
                            #temp=stock_summary(str(stock_code[i]))
                            temp.to_sql(name='test1',con=con,if_exists='append')
                            con.close()
                            K=K+1     
                        else:
                            print(K,'/Today Jump/',str(stock_code[i]),info.iloc[0,2])
                            K=K+1   
                    else:
                        print(K,'/Operating profit X/',str(stock_code[i]),info.iloc[0,2])
                        K=K+1 
                else:
                    print(K,'/20day Up Turn X/',str(stock_code[i]),info.iloc[0,2])
                    K=K+1
            else:
                print(K,'/20day range(60day) X/',str(stock_code[i]),info.iloc[0,2])
                K=K+1
        else:
            print(K,'/New Stock/',str(stock_code[i]),info.iloc[0,2])
            K=K+1
    except AttributeError or TypeError or urllib.error.URLError as e:   # as e:  
        #print(e,stock_info(str(stock_code[i]), 1),info.iloc[0,2])
        print(e,'Error',str(stock_code[i]))
        '''

