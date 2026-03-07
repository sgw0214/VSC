#git push -u origin master

from os import kill
from sched import scheduler
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
<<<<<<< HEAD
from email.mime.text import MIMEText   
print("서귀완")
=======
from email.mime.text import MIMEText

>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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

    url3 = 'https://finance.naver.com//marketindex/exchangeDailyQuote.naver?marketindexCd=FX_USDKRW'
    html3 = urlopen(url3) 
    src3= BeautifulSoup(html3.read(), "html.parser")
    date_USD=src3.find_all(class_="date")
    USD=src3.find_all(class_="num")

    date1=src1.find_all(class_="date")
    date2=src2.find_all(class_="date")
    date=date1+date2
    
    WTI1=src1.find_all(class_="num")
    WTI2=src2.find_all(class_="num")
    WTI=WTI1+WTI2
    # print(WTI[1])
    for k in range(len(date)):
        
        if date_USD[0].text.strip()== date[0].text.strip():
            # print(str(WTI[k*2+1])[str(WTI[k*2+1]).find("alt=")+5:str(WTI[k*2+1]).find("alt=")+7])
            if str(WTI[k*2+1])[str(WTI[k*2+1]).find("alt=")+5:str(WTI[k*2+1]).find("alt=")+7]=="하락":
                Summary.loc[k+1,['일자']]=date[k].text.strip()
                Summary.loc[k+1,['WTI']]=WTI[k*3].text.strip()+'/-'+WTI[k*3+2].text.strip()
            else:
                Summary.loc[k+1,['일자']]=date[k].text.strip()
                Summary.loc[k+1,['WTI']]=WTI[k*3].text.strip()+'/'+WTI[k*3+2].text.strip()
            
        else:
            # print(str(WTI[k*2+1])[str(WTI[k*2+1]).find("alt=")+5:str(WTI[k*2+1]).find("alt=")+7])
            if str(WTI[k*2+1])[str(WTI[k*3+2]).find("alt=")+5:str(WTI[k*2+1]).find("alt=")+7]=="하락":
                Summary.loc[0,['일자']]=date_USD[0].text.strip()
                Summary.loc[k+1,['일자']]=date[k].text.strip()
                Summary.loc[k+1,['WTI']]=WTI[k*3].text.strip()+'/-'+WTI[k*3+2].text.strip()
            else:
                Summary.loc[0,['일자']]=date_USD[0].text.strip()
                Summary.loc[k+1,['일자']]=date[k].text.strip()
                Summary.loc[k+1,['WTI']]=WTI[k*3].text.strip()+'/'+WTI[k*3+2].text.strip()
            
    

    ######    환율(USD)    ####
    
    for k in range(len(date)) :
        for m in range(len(date_USD)) :
            if date_USD[m].text.strip() == list(Summary.loc[k,['일자']])[0]:
                # print(str(USD[m*2+1])[str(USD[m*2+1]).find("alt=")+4:str(USD[m*2+1]).find("alt=")+8])
                if str(USD[m*2+1])[str(USD[m*2+1]).find("alt=")+5:str(USD[m*2+1]).find("alt=")+7]=="하락":
                    Summary.loc[k,['환율(USD)']]=USD[m*2].text+'/-'+USD[m*2+1].text.strip()
                else:
                    Summary.loc[k,['환율(USD)']]=USD[m*2].text+'/'+USD[m*2+1].text.strip()

            else:
                pass
    

    ######    미국채(10year)    ####
    url1 = 'https://kr.investing.com/rates-bonds/u.s.-10-year-bond-yield-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    date_US_INTER10Y_list=src2.find_all(class_="first left bold noWrap")
    US_INTER10Y=src2.find_all("tbody")[0]
    for k in range(len(date)) :
        for m in range(len(date_US_INTER10Y_list)):
            date_US_INTER10Y=date_US_INTER10Y_list[m].text[0:4]+"."+date_US_INTER10Y_list[m].text[6:8]+"."+date_US_INTER10Y_list[m].text[10:12]
            # print(date_US_INTER10Y)
            # print(US_INTER10Y.find_all("tr")[m].find_all("td")[1].text)
            if date_US_INTER10Y == list(Summary.loc[k,['일자']])[0]:
                Summary.loc[k,['미국채(10year)']]=US_INTER10Y.find_all("tr")[m].find_all("td")[1].text+'/'+US_INTER10Y.find_all("tr")[m].find_all("td")[5].text
                
            else:
                pass
    ######    다우    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=DJI@DJI&fdtc=0'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_DJI=src1.find_all(class_="tb_td")
    DJI=src1.find_all(class_="tb_td2")
    DJI_delta=src1.find_all(class_="tb_td3")
    DJI_UPDW=src1.find_all('tr')
    # print(DJI_UPDW[3])
    for k in range(len(date)) :
        for m in range(len(date_DJI)) :
            if date_DJI[m].text.strip() == list(Summary.loc[k,['일자']])[0]:
                # print(str(DJI_UPDW[m+3])[str(DJI_UPDW[m+3]).find("=")+2:str(DJI_UPDW[m+3]).find("=")+10])
                if str(DJI_UPDW[m+3])[str(DJI_UPDW[m+3]).find("=")+2:str(DJI_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k,['다우']]=DJI[m].text+'/-'+DJI_delta[m].text.strip()
                else:
                    Summary.loc[k,['다우']]=DJI[m].text+'/'+DJI_delta[m].text.strip()

            else:
                pass

    ######    나스닥    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=NAS@IXIC'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_NAS=src1.find_all(class_="tb_td")
    NAS=src1.find_all(class_="tb_td2")
    NAS_delta=src1.find_all(class_="tb_td3")
    NAS_UPDW=src1.find_all('tr')
    # print(NAS_UPDW[3])
    for k in range(len(date)) :
        for m in range(len(date_NAS)) :
            if date_NAS[m].text.strip() == list(Summary.loc[k,['일자']])[0]:
                # print(str(NAS_UPDW[m+3])[str(NAS_UPDW[m+3]).find("=")+2:str(NAS_UPDW[m+3]).find("=")+10])
                if str(NAS_UPDW[m+3])[str(NAS_UPDW[m+3]).find("=")+2:str(NAS_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k,['나스닥']]=NAS[m].text+'/-'+NAS_delta[m].text.strip()
                else:
                    Summary.loc[k,['나스닥']]=NAS[m].text+'/'+NAS_delta[m].text.strip()

            else:
                pass

    ######    SNP    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=SPI@SPX'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_SNP=src1.find_all(class_="tb_td")
    SNP=src1.find_all(class_="tb_td2")
    SNP_delta=src1.find_all(class_="tb_td3")
    SNP_UPDW=src1.find_all('tr')
    # print(SNP_UPDW[3])
    for k in range(len(date)) :
        for m in range(len(date_SNP)) :
            if date_SNP[m].text.strip() == list(Summary.loc[k,['일자']])[0]:
                # print(str(SNP_UPDW[m+3])[str(SNP_UPDW[m+3]).find("=")+2:str(SNP_UPDW[m+3]).find("=")+10])
                if str(SNP_UPDW[m+3])[str(SNP_UPDW[m+3]).find("=")+2:str(SNP_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k,['S&P']]=SNP[m].text+'/-'+SNP_delta[m].text.strip()
                else:
                    Summary.loc[k,['S&P']]=SNP[m].text+'/'+SNP_delta[m].text.strip()

            else:
                pass

    ######    PDM    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=NAS@SOX'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_PDM=src1.find_all(class_="tb_td")
    PDM=src1.find_all(class_="tb_td2")
    PDM_delta=src1.find_all(class_="tb_td3")
    PDM_UPDW=src1.find_all('tr')
    # print(PDM_UPDW[3])
    for k in range(len(date)) :
        for m in range(len(date_PDM)) :
            if date_PDM[m].text.strip() == list(Summary.loc[k,['일자']])[0]:
                # print(str(PDM_UPDW[m+3])[str(PDM_UPDW[m+3]).find("=")+2:str(PDM_UPDW[m+3]).find("=")+10])
                if str(PDM_UPDW[m+3])[str(PDM_UPDW[m+3]).find("=")+2:str(PDM_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k,['PDM']]=PDM[m].text+'/-'+PDM_delta[m].text.strip()
                else:
                    Summary.loc[k,['PDM']]=PDM[m].text+'/'+PDM_delta[m].text.strip()

            else:
                pass



    
    print(Summary)
    Summary_html=Summary.to_html(index=False, justify='center')
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(Summary_html,'html')
    msg['Subject'] = '주요시장지표'
    s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "sgw0214@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@naver.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "choice@lgdisplay.com", msg.as_string())
    s.quit()
    return Summary
    
        


Summary().to_csv("E:\VSC\CODE\Summary.csv")
print(time.time()-start)