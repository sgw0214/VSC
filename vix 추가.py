#git push -u origin master

from os import kill
from sched import scheduler
from numpy.lib.shape_base import kron
from pandas.core.frame import DataFrame
import requests
from urllib.request import Request,urlopen
import logging
from bs4 import BeautifulSoup
import pandas as pd
from urllib.error import HTTPError
import time
# from sqlalchemy import create_engine
import numpy as np
import urllib
from openpyxl import load_workbook
from openpyxl import Workbook
import math
import smtplib
import sched
import time
import smtplib
from email.mime.text import MIMEText
import datetime  



start = time.time()
def Summary():
    k=0
    Summary=pd.DataFrame()
    ######    WTI    ####
    url1 = 'https://finance.naver.com/marketindex/worldDailyQuote.naver?marketindexCd=OIL_CL&fdtc=2&page=1'
    html1 = urlopen(url1) 
    src1= BeautifulSoup(html1.read(), "html.parser")
    url2 = 'https://finance.naver.com/marketindex/worldDailyQuote.naver?marketindexCd=OIL_CL&fdtc=2&page=2'
    html2 = urlopen(url2) 
    src2= BeautifulSoup(html2.read(), "html.parser")

    date1=src1.find_all(class_="date")
    date2=src2.find_all(class_="date")
    date_WTI=date1+date2
    
    WTI1=src1.find_all(class_="num")
    WTI2=src2.find_all(class_="num")
    WTI=WTI1+WTI2

    date=datetime.date.today()
    for k in range(20):
        if k==0 : 
            Summary.loc[k,['일자']]=datetime.date.strftime(date,'%Y.%m.%d')

        else:
            Summary.loc[k,['일자']]=datetime.date.strftime(date+pd.DateOffset(days=-k),'%Y.%m.%d')

    m=0
    for m in range(10):
        for k in range(len(Summary['일자'])):

            if date_WTI[m].text.strip()== Summary['일자'].iloc[k]:
                Summary.loc[k,['WTI']]=WTI[m*3].text.strip()+'/'+WTI[m*3+2].text.strip()

            else:
                pass


    ######    VIX    ####
    url1 = 'https://kr.investing.com/indices/volatility-s-p-500-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    date_vix=src2.find_all(class_="first left bold noWrap")
    vix=src2.find_all("tbody")[1]

    for k in range(len(Summary['일자'])):
        for m in range(len(date_vix)):
            print("date",date_vix,date_vix[m],m)
            date_vix_list=date_vix[m].text[0:4]+"."+date_vix[m].text[6:8]+"."+date_vix[m].text[10:12]
            
            if date_vix_list == Summary['일자'].iloc[k]:
                Summary.loc[k,['VIX']]=vix.find_all("tr")[m].find_all("td")[1].text+'/'+vix.find_all("tr")[m].find_all("td")[6].text

            else:
                pass
    print(Summary)

    # ######    미국채(10year)    ####
    # url1 = 'https://kr.investing.com/rates-bonds/u.s.-10-year-bond-yield-historical-data'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    # src1=urlopen(req)
    # src2= BeautifulSoup(src1.read(), "html.parser")
    # date_US_INTER10Y_list=src2.find_all(class_="first left bold noWrap")
    # US_INTER10Y=src2.find_all("tbody")[0]

    # for k in range(len(Summary['일자'])):
    #     for m in range(len(date_US_INTER10Y_list)):
    #         date_US_INTER10Y=date_US_INTER10Y_list[m].text[0:4]+"."+date_US_INTER10Y_list[m].text[6:8]+"."+date_US_INTER10Y_list[m].text[10:12]
    #         # print(date_US_INTER10Y,Summary['일자'].iloc[k])
    #         if date_US_INTER10Y == Summary['일자'].iloc[k]:
    #             Summary.loc[k,['미국채(10year)']]=US_INTER10Y.find_all("tr")[m].find_all("td")[1].text+'/'+US_INTER10Y.find_all("tr")[m].find_all("td")[5].text

    #         else:
    #             pass


    # Summary=Summary.fillna('-')
    # print(Summary)  

    # return Summary       

Summary()
print(time.time()-start)



