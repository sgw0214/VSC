#git push -u origin master
<<<<<<< HEAD
import sys
=======

>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
<<<<<<< HEAD
from io import StringIO
=======
from io import BytesIO
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
import numpy as np
from datetime import datetime,date
from datetime import timedelta
import os
<<<<<<< HEAD
import sys
import pypdfium2
from pypdf import PdfReader
import fitz 
from spire.pdf.common import *
from spire.pdf import *
import json
from pandas.io.json import json_normalize
import re
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)


start = time.time() 
print("start")  
print(start)               
#http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101
path = 'E:/VSC/CODE/Stock/'
def data(date):
    #전종목시세
    gen_otp_url = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd' 
=======

start = time.time() 
print(start)               

path = 'E:/VSC/CODE/Stock/'
def data(date):
    gen_otp_url = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    gen_otp_data = {
    'mktId': 'STK',
    'trdDd': date,
    'money': '1',
    'csvxls_isNo': 'false',
    'name': 'fileDown',
<<<<<<< HEAD
    'url': 'dbms/MDC/STAT/standard/MDCSTAT01501' #MDCSTAT0391
    }     
    headers = {'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101', "User-Agent" : "Mozilla/5.0"} 
    otp = rq.post(gen_otp_url, gen_otp_data, headers=headers).text
    # print(otp)
    down_url = 'http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd' 
    down_sector_KS  = rq.post(down_url, {'code':otp}, headers=headers)
    sector_KS = pd.read_csv(BytesIO(down_sector_KS.content), encoding='EUC-KR')
    sector_KS['일자'] = str(date)
    
    
       
    
    file_name = 'basic_'+ str(date) + '.xlsx'    
=======
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
    
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    sector_KS.to_excel(path+file_name, index=False, index_label=None)
    print('KRX crawling completed :', date)

def Total_Stack(): 
<<<<<<< HEAD
    for year in range(2024, 2025):
        for month in range(8, 13):
=======
    for year in range(2020, 2023):
        for month in range(1, 13):
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
            for day in range(1, 32):
                tdate = year * 10000 + month * 100 + day * 1
                try:
                    file_size = os.path.getsize(path + 'basic_' + str(tdate) + '.xlsx') 
<<<<<<< HEAD
                    print('File Size:', file_size, 'bytes',"date1 >=date2",int(datetime.strftime(datetime.today() ,'%Y%m%d')),tdate) 
                    if file_size<70000 and  int(datetime.strftime(datetime.today() ,'%Y%m%d'))>=tdate :
=======
                    print('File Size:', file_size, 'bytes',"date",tdate) 
                    if file_size<7000 and  int(datetime.strftime(datetime.today() ,'%Y%m%d'))>=tdate :
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
                        data(tdate)
                    else: 
                        print("Pass")
                        pass 
                    
                except:
                    data(tdate)
<<<<<<< HEAD
 
#개별종목종합정보                   
def UNITSTOCKINFO(x):
    sd_gen_otp_url = 'http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
    sd_gen_otp_data = { 
    'bld': 'dbms/MDC/STAT/standard/MDCSTAT01901',
    'locale': 'ko_KR',
    'mktId': 'STK',
    'share': '1',
    'csvxls_isNo': 'false' }
    url='http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020203'     
    sd_headers = {'Referer': url, "User-Agent" : "Mozilla/5.0"}
    data = rq.post(sd_gen_otp_url, sd_gen_otp_data, headers=sd_headers).text
    src=json.loads(data)
    # src=pd.DataFrame(src)

    
    for i in range(len(src['OutBlock_1'])):
        
        if src['OutBlock_1'][i]['ISU_ABBRV']==x:
            y1=src['OutBlock_1'][i]['ISU_CD']
            y2=src['OutBlock_1'][i]['ISU_SRT_CD']
            print(x,y1,y2)
            break 
    
    gen_otp_url1 = 'http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd'    
    gen_otp_data1 = { 
    'locale': 'ko_KR',
    'tboxisuCd_finder_stkisu0_0': y2+'/'+x,
    'isuCd': y1,
    'isuCd2': 'KR7005930003',
    'codeNmisuCd_finder_stkisu0_0': x,
    'param1isuCd_finder_stkisu0_0': 'ALL',
    'csvxls_isNo': 'false',
    'name': 'fileDown',
    'menuId': 'MDC0201020203',
    'url': 'url',
    'pdfJsDelay': '5000',
    'pdftemplet': 'mdc_pdf' }
        
    headers1 = {'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020203', "User-Agent" : "Mozilla/5.0"}
    otp1 = rq.post(gen_otp_url1, gen_otp_data1, headers=headers1).text
    down_url1 = 'http://data.krx.co.kr/comm/fileDn/download_pdf/download.cmd' 
    down_sector_KS1  = rq.post(down_url1, {'code':otp1}, headers=headers1)
 
    # print(BytesIO(down_sector_KS1.content))
    
    # sector_KS1=pd.DataFrame(BytesIO(down_sector_KS1.content),) #
    doc = fitz.open(stream=BytesIO(down_sector_KS1.content).read())
    # print(doc)
    page = doc.load_page(0)
    text = page.get_textbox("text")
    # print(text)
    text=str(text).splitlines()
    print(text)
    print(pd.DataFrame(data=text).head(200))
    minus=172-len(text)

    data=[text[1],text[5],text[9],text[51],text[3],text[7],text[11],text[15],text[19],text[23],text[17],text[21].split("/")[0],text[21].split("/")[1],text[25],
        text[149-minus],text[150-minus],text[152-minus],text[153-minus],text[154-minus],text[155-minus],text[156-minus],
        text[157-minus],text[158-minus],text[159-minus],text[160-minus],text[161-minus],text[162-minus],
        f"{int(int(re.sub(r'[^-0-9]', '', text[164-minus]))/100000000):,}"+" 억원",
        f"{int(int(re.sub(r'[^-0-9]', '', text[165-minus]))/100000000):,}"+" 억원",
        f"{int(int(re.sub(r'[^-0-9]', '', text[166-minus]))/100000000):,}"+" 억원",
        f"{int(int(re.sub(r'[^-0-9]', '', text[167-minus]))/100000000):,}"+" 억원",
        f"{int(int(re.sub(r'[^-0-9]', '', text[168-minus]))/100000000):,}"+" 억원",
        f"{int(int(re.sub(r'[^-0-9]', '', text[169-minus]))/100000000):,}"+" 억원",
        f"{int(int(re.sub(r'[^-0-9]', '', text[170-minus]))/100000000):,}"+" 억원"]
    # elif len(text)==171:
    #     data=[text[1],text[5],text[9],text[51],text[3],text[7],text[11],text[15],text[19],text[23],text[17],text[21].split("/")[0],text[21].split("/")[1],text[25],
    #         text[148],text[149],text[151],text[152],text[153],text[154],text[155],text[156],text[157],text[158],
    #         text[159],text[160],text[161],
    #         f"{int(int(re.sub(r'[^0-9]', '', text[163]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[164]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[165]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[166]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[167]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[168]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[169]))/100000000):,}"+" 억원"]
    # elif len(text)==168:
    #     data=[text[1],text[5],text[9],text[51],text[3],text[7],text[11],text[15],text[19],text[23],text[17],text[21].split("/")[0],text[21].split("/")[1],text[25],
    #         text[148],text[149],text[151],text[152],text[153],text[154],text[155],text[156],text[157],text[158],
    #         text[159],text[160],text[161],
    #         f"{int(int(re.sub(r'[^0-9]', '', text[163]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[164]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[165]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[166]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[167]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[168]))/100000000):,}"+" 억원",
    #         f"{int(int(re.sub(r'[^0-9]', '', text[169]))/100000000):,}"+" 억원"]
        
    columns=["시가","고가","저가","종가","거래량","거래대금(원)","시가총액(백만원)","52주 최고","52주 최저","대용가","외국인비율","PER","PBR","배당수익률",
             '영문명', '표준코드', '액면가', '결산월', '상장주식수(주)', '소속부', '상장일', 
             '설립일', '업종명', '대표이사','주소', '전화번호', '홈페이지', 
             '자산총계', 
             '매출액(수익)', 
             '부채총계', 
             '영업이익', 
             '자본금', 
             '당기순이익', 
             '자본총계']
    text_df=pd.DataFrame(data=[data],columns=columns)
    print(text_df.T)
    # print(text_df)
    
    doc.close()
    return text_df

def add_stock(x):
    df = pd.read_excel(path + str(x)+'.xlsx',engine='openpyxl')
    print(df.size)
    if df.size==0:
        start_date=str(x)+"0101"
        startday = pd.read_excel(path + 'basic_' + start_date + '.xlsx')
        df = pd.concat([df, startday], sort=False)
        for year in range(x, x+1):
            for month in range(1, 13):
                for day in range(1, 32):
                    tdate = year * 10000 + month * 100 + day * 1
                    print(start_date,tdate,int(datetime.strftime(datetime.today() ,'%Y%m%d')))
                    if int(datetime.strftime(datetime.today() ,'%Y%m%d')) >= tdate :
                        startday = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
                        df = pd.concat([df, startday], sort=False)
=======

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
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
                        print("concatenate completed :", tdate,"Last Date:",np.array(df["일자"])[-1])
                    else: pass

    else:
        max_date=np.array(df["일자"])[-1]
<<<<<<< HEAD
        for year in range(x,x+1):
=======
        for year in range(2020, 2023):
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
<<<<<<< HEAD
    WIP.to_excel(path + str(x)+'.xlsx', index=False, index_label=None)




# Total_Stack()
# UNITSTOCKINFO("LG디스플레이")
# add_stock(2021)
# add_stock(2022)
# add_stock(2023)
# add_stock(2024)

# # pip install -U pypdfium2
# df=DataFrame()
# for i in range(10):
#     df1 = pd.read_excel(path + str(2015+i)+'.xlsx',engine='openpyxl')
#     df = pd.concat([df, df1], sort=False)
#     WIP = df.drop_duplicates()
#     # WIP = WIP[WIP["종가"]== None].dropna(axis=0)
#     WIP.to_excel(path + 'Total.xlsx', index=False, index_label=None)
#     print(df.size)
=======
    WIP.to_excel(path + 'Total.xlsx', index=False, index_label=None)

# Total_Stack()
add_stock()

>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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




