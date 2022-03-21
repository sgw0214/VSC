#git push -u origin master

from pandas.core.frame import DataFrame
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
from io import BytesIO
import requests as rq
from io import BytesIO
import numpy as np
from datetime import datetime,date
from datetime import timedelta
import os

start = time.time() 
print(start)               

path = 'E:/VSC/CODE/Stock/'
def data(date):
    gen_otp_url = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'
    gen_otp_data = {
    'mktId': 'STK',
    'trdDd': date,
    'money': '1',
    'csvxls_isNo': 'false',
    'name': 'fileDown',
    'url': 'dbms/MDC/STAT/standard/MDCSTAT01501'
    }
    headers = {'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader'}
    otp = rq.post(gen_otp_url, gen_otp_data, headers=headers).text
    # print(otp)
    
    down_url = 'http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd'
    down_sector_KS  = rq.post(down_url, {'code':otp}, headers=headers)
    sector_KS = pd.read_csv(BytesIO(down_sector_KS.content), encoding='EUC-KR')
    
    sector_KS['일자'] = str(date)
    file_name = 'basic_'+ str(date) + '.xlsx'
    
    ##### 시장구분, 업종명 추가 ####
    gen_otp_url1 = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'
    gen_otp_data1 = {
    'mktId': 'STK',
    'trdDd': date,
    'money': '1',
    'csvxls_isNo': 'false',
    'name': 'fileDown',
    'url': 'dbms/MDC/STAT/standard/MDCSTAT03901'
    }
    headers = {'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader'}
    otp1 = rq.post(gen_otp_url1, gen_otp_data1, headers=headers).text
    down_url1 = 'http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd'
    down_sector_KS1  = rq.post(down_url1, {'code':otp1}, headers=headers)
    sector_KS1 = pd.read_csv(BytesIO(down_sector_KS1.content), encoding='EUC-KR')
    sector_KS1=sector_KS1[["시장구분","업종명"]]
    ##### 시장구분, 업종명 추가 ####
    sector_KS=pd.concat([sector_KS,sector_KS1],axis=1)
    
    sector_KS.to_excel(path+file_name, index=False, index_label=None)
    print('KRX crawling completed :', date)

def Total_Stack(): 
    for year in range(2020, 2023):
        for month in range(1, 13):
            for day in range(1, 32):
                tdate = year * 10000 + month * 100 + day * 1
                try:
                    file_size = os.path.getsize(path + 'basic_' + str(tdate) + '.xlsx') 
                    print('File Size:', file_size, 'bytes',"date",tdate) 
                    if file_size<7000 and  int(datetime.strftime(datetime.today() ,'%Y%m%d'))>=tdate :
                        data(tdate)
                    else: 
                        print("Pass")
                        pass 
                    
                except:
                    data(tdate)

def add_stock():
    df = pd.read_excel(path + 'Total.xlsx')
    print(df.size)
    if df.size==0:
        max_date="20200101"
        yesterday = pd.read_excel(path + 'basic_' + max_date + '.xlsx')
        df = pd.concat([df, yesterday], sort=False)
        for year in range(2020, 2023):
            for month in range(1, 13):
                for day in range(1, 32):
                    tdate = year * 10000 + month * 100 + day * 1
                    print(max_date,tdate,int(datetime.strftime(datetime.today() ,'%Y%m%d')))
                    if int(datetime.strftime(datetime.today() ,'%Y%m%d')) >= tdate :
                        yesterday = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
                        df = pd.concat([df, yesterday], sort=False)
                        print("concatenate completed :", tdate,"Last Date:",np.array(df["일자"])[-1])
                    else: pass

    else:
        max_date=np.array(df["일자"])[-1]
        for year in range(2020, 2023):
            for month in range(1, 13):
                for day in range(1, 32):
                    tdate = year * 10000 + month * 100 + day * 1
                    print(max_date,tdate,int(datetime.strftime(datetime.today() ,'%Y%m%d')))
                    if max_date<tdate and int(datetime.strftime(datetime.today() ,'%Y%m%d')) >= tdate :
                        yesterday = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
                        df = pd.concat([df, yesterday], sort=False)
                        print("concatenate completed :", tdate,"Last Date:",np.array(df["일자"])[-1])
                    else: pass
                    
    WIP = df.drop_duplicates()
    # WIP = WIP[WIP["종가"]== None].dropna(axis=0)
    WIP.to_excel(path + 'Total.xlsx', index=False, index_label=None)

# Total_Stack()
add_stock()

print(time.time()-start)

################################## 이전code##########################################
# def data(date):
#     gen_otp_url = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'
#     gen_otp_data = {
#     'mktId': 'STK',
#     'trdDd': date,
#     'money': '1',
#     'csvxls_isNo': 'false',
#     'name': 'fileDown',
#     'url': 'dbms/MDC/STAT/standard/MDCSTAT03901'
#     }
#     headers = {'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader'}
#     otp = rq.post(gen_otp_url, gen_otp_data, headers=headers).text
#     # print(otp)
    
#     down_url = 'http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd'
#     down_sector_KS  = rq.post(down_url, {'code':otp}, headers=headers)
#     sector_KS = pd.read_csv(BytesIO(down_sector_KS.content), encoding='EUC-KR')
    
#     sector_KS['일자'] = str(date)
#     file_name = 'basic_'+ str(date) + '.xlsx'
#     sector_KS.to_excel(path+file_name, index=False, index_label=None)
#     print('KRX crawling completed :', date)

# def Total_Stack(): 
#     for year in range(2022, 2023):
#         for month in range(1, 13):
#             for day in range(1, 32):
#                 tdate = year * 10000 + month * 100 + day * 1
#                 try:
#                     file_size = os.path.getsize(path + 'basic_' + str(tdate) + '.xlsx') 
#                     print('File Size:', file_size, 'bytes',"date",tdate) 
#                     if file_size<7000 and  int(datetime.strftime(datetime.today() ,'%Y%m%d'))>=tdate :
#                         data(tdate)
#                     else: 
#                         print("Pass")
#                         pass 
                    
#                 except:
#                     data(tdate)
    
#     # for year in range(2022, 2023):
#     #     for month in range(1, 13):
#     #         for day in range(1, 32):
#     #             tdate = year * 10000 + month * 100 + day * 1
#     #             if tdate <= 20221231:
#     #                 data(tdate)

#     # WIP = pd.read_excel(path + 'basic_20210101.xlsx')
    
#     # for year in range(2022, 2023):
#     #     for month in range(1, 13):
#     #         for day in range(1, 32):
#     #             tdate = year * 10000 + month * 100 + day * 1
#     #             if tdate <= 20220110:
#     #                 yesterday = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
#     #                 print(str(datetime.strftime(datetime.today() ,'%Y%m%d')),str(tdate))

#     #                 if datetime.strftime(datetime.today() ,'%Y%m%d') == str(tdate):
#     #                     break
#     #                 else:
#     #                     WIP = pd.concat([WIP, yesterday], sort=False)
#     #                     print("concatenate completed :", tdate)
#     # WIP = WIP.drop_duplicates()
#     # WIP.to_excel(path+'Total.xlsx', index=False, index_label=None)

# Total_Stack()

# def add_stock():
#     df = pd.read_excel(path + 'Total_modify_ver1.xlsx')
#     max_date=np.array(df["일자"])[-1]
#     print(max_date)
#     for year in range(2021, 2023):
#         for month in range(1, 13):
#             for day in range(1, 32):
#                 tdate = year * 10000 + month * 100 + day * 1
#                 print(max_date,tdate,int(datetime.strftime(datetime.today() ,'%Y%m%d')))
#                 if max_date<tdate and int(datetime.strftime(datetime.today() ,'%Y%m%d')) >= tdate :
#                     yesterday = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
#                     df = pd.concat([df, yesterday], sort=False)
#                     print("concatenate completed :", tdate,"Last Date:",np.array(df["일자"])[-1])
#                 else: pass
                    
#     WIP = df.drop_duplicates()
#     WIP.to_excel(path + 'Total_modify_ver1.xlsx', index=False, index_label=None)




