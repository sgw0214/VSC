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

start = time.time()

path = 'E:/VSC/CODE/Stock/'

def data(date):
    gen_otp_url = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'
    gen_otp_data = {
    'mktId': 'STK',
    'trdDd': date,
    'money': '1',
    'csvxls_isNo': 'false',
    'name': 'fileDown',
    'url': 'dbms/MDC/STAT/standard/MDCSTAT03901'
    }
    headers = {'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader'}
    otp = rq.post(gen_otp_url, gen_otp_data, headers=headers).text
    # print(otp)
    
    down_url = 'http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd'
    down_sector_KS  = rq.post(down_url, {'code':otp}, headers=headers)
    sector_KS = pd.read_csv(BytesIO(down_sector_KS.content), encoding='EUC-KR')
    
    sector_KS['일자'] = str(date)
    file_name = 'basic_'+ str(date) + '.xlsx'
    sector_KS.to_excel(path+file_name, index=False, index_label=None)
    print('KRX crawling completed :', date)

def Total_Stack():    
    for year in range(2021, 2022):
        for month in range(1, 13):
            for day in range(1, 32):
                tdate = year * 10000 + month * 100 + day * 1
                if tdate <= 20211231:
                    data(tdate)

    WIP = pd.read_excel(path + 'basic_20210101.xlsx')
    
    for year in range(2021, 2022):
        for month in range(1, 13):
            for day in range(1, 32):
                tdate = year * 10000 + month * 100 + day * 1
                if tdate <= 20211231:
                    yesterday = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
                    print(str(datetime.date.strftime(datetime.date.today() ,'%Y%m%d')),str(tdate))

                    if datetime.date.strftime(datetime.date.today() ,'%Y%m%d') == str(tdate):
                        break
                    else:
                        WIP = pd.concat([WIP, yesterday], sort=False)
                        print("concatenate completed :", tdate)
    WIP = WIP.drop_duplicates()
    WIP.to_excel(path+'Total.xlsx', index=False, index_label=None)

# Total_Stack()

def add_stock():
    df = pd.read_excel(path + 'Total_modify_ver1.xlsx')
    df.index.set_names='No'
    max_date=datetime.strptime(str(max(df['일자'])),'%Y%m%d')
    tdate=datetime.today()
    get_day=tdate-max_date
    print(get_day)
    for k in tdate-max_date:
        add_date=datetime.strftime(max_date+timedelta(days=1),'%Y%m%d')
        data(add_date)
        
        add_file = pd.read_excel(path + 'basic_' + str(add_date) + '.xlsx')
        df = pd.concat([df, add_file], sort=False)
    df.to_excel(path+'Total_modify_ver1.xlsx', index=False, index_label=None)


# wip2=len(wip['종목코드'])

add_stock()
print(time.time()-start)

