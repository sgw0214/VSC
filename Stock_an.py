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

def stock_an():
    i=57427
    k=0
    # url = 'https://finance.naver.com/research/company_read.naver?nid='i+'&page=1'
    # html = urlopen(url) 
    # src= BeautifulSoup(html.read(), "html.parser")
    stock_an=pd.DataFrame()
    url1 = 'https://finance.naver.com/research/company_list.naver'
    html1 = urlopen(url1) 
    src1= BeautifulSoup(html1.read(), "html.parser")
    stock_item=src1.find_all(class_="stock_item")
    date=src1.find_all(class_="date")

    # src3=src2[2]
    # print(src2)
    m=0
    for k in range(len(stock_item)) :
        stock_an.loc[k,['일자']]=date[k*2+1].text
        stock_an.loc[k,['종목']]=stock_item[k].text
    for i in range(len(src1.find_all("tr"))):
            
        # print(src1.find_all("tr")[5].find_all("td")[1])
        if i==5 or i==6 or i==7 or i==13 or i==14 or i==15 or i==21 or i==22 or i==23 or i==29 or i==30 or i==31 or i==37 or i==38 or i==39 or i>44  :
            
            pass
        else:
            path=src1.find_all("tr")[i+2].find_all("td")[1]
            print(path)
            
            path=str(path) 
            path1=path[path.find("""=""")+2:path.find("""">""")]
  
            # print(k,i,path1)
            url2 = "https://finance.naver.com/research/"+path1

            html2 = urlopen(url2)
            src2= BeautifulSoup(html2.read(), "html.parser")
            strno=math.ceil(len(str(src2.find_all("p")[3].text))/50)
            strno1=math.ceil(len(str(src2.find_all("p")[2].text))/50)
            strno2=math.ceil(len(str(src2.find_all("tr")[3].find_all("div")[0].text.strip()))/50)
            # print(str(src2.find_all(class_="source"))[19:25])

            if str(src2.find_all("p")[2].text)== "":
                
                for n in range(strno):
                    if n==0:
                        research=str(src2.find_all("p")[3].text)[:50]
                        
                    else:
                        research=research+str(src2.find_all("p")[3].text)[50*n:50*(n+1)]
                # print(research)        
                # research=str(src2.find_all("p")[3].find_all("br")[n].text)
                # print(stock_item[k].text,research)
                stock_an.loc[m,['내용']]=research
                m=m+1
                
            elif str(src2.find_all(class_="source"))[19:26]=="한국기업데이터"  or str(src2.find_all(class_="source"))[19:26]=="IBK투자증권" or str(src2.find_all(class_="source"))[19:26]=="케이프투자증권":
                for n in range(strno2):
                    if n==0:
                        research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
                    else:
                        research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
                stock_an.loc[m,['내용']]=research
                m=m+1
            
            elif str(src2.find_all(class_="source"))[19:25]=="나이스디앤비" or str(src2.find_all(class_="source"))[19:25]=="하나금융투자" or str(src2.find_all(class_="source"))[19:25]=="이베스트증권" or str(src2.find_all(class_="source"))[19:25]=="하이투자증권" or str(src2.find_all(class_="source"))[19:25]=="미래에셋증권":
                for n in range(strno2):
                    if n==0:
                        research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
                    else:
                        research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
                stock_an.loc[m,['내용']]=research
                m=m+1
            elif str(src2.find_all(class_="source"))[19:27]=="NICE평가정보":
                for n in range(strno2):
                    if n==0:
                        research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
                    else:
                        research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
                stock_an.loc[m,['내용']]=research
                m=m+1
            elif str(src2.find_all(class_="source"))[19:23]=="교보증권":
                for n in range(strno2):
                    if n==0:
                        research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
                    else:
                        research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
                stock_an.loc[m,['내용']]=research
                m=m+1
                

            
            else:

                for n in range(strno1):
                    if n==0:
                        research=str(src2.find_all("p")[7].text)[:50]
                        
                    else:
                        research=research+str(src2.find_all("p")[7].text)[50*n:50*(n+1)]

                # research=str(src2.find_all("p")[2].text)
                # print(stock_item[k].text,research)
                stock_an.loc[m,['내용']]=research
                m=m+1
    stock_an_html=stock_an.to_html(index=False, justify='center')
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(stock_an_html,'html')
    msg['Subject'] = '종목분석'
    # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())

    s.quit()
    return stock_an

def economy_an():
    k=0
    economy_an=pd.DataFrame()
    url1 = 'https://finance.naver.com/research/economy_list.naver'
    html1 = urlopen(url1) 
    src1= BeautifulSoup(html1.read(), "html.parser")
    stock_item=src1.find_all(style="padding-left:10px")
    date=src1.find_all(class_="date")
    # print(range(1,len(stock_item)+1),stock_item)
    m=0
    for k in range(len(stock_item)) :
        economy_an.loc[k,['일자']]=date[k*2+1].text
        economy_an.loc[k,['제목']]=stock_item[k*1].text
         
    # print(economy_an)
    for i in range(len(src1.find_all("tr"))):

        # print(src1.find_all("tr")[5].find_all("td")[1])
        if i==5 or i==6 or i==7 or i==13 or i==14 or i==15 or i==21 or i==22 or i==23 or i==29 or i==30 or i==31 or i==37 or i==38 or i==39 or i>44  :
            
            pass
        else:
            path=src1.find_all("tr")[i+2].find_all("td")[0]
            path=str(path) 
            path1=path[path.find("href=")+6:path.find("""1">""")+1]
            url2 = "https://finance.naver.com/research/"+path1 
            html2 = urlopen(url2)
            src2= BeautifulSoup(html2.read(), "html.parser")
            strno=math.ceil(len(str(src2.find_all("p")[3].text))/50)
            strno1=math.ceil(len(str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text))/50)
                       
            if str(src2.find_all("p")[2].text)== "":
                for n in range(strno):
                    if n==0:
                        research=str(src2.find_all("p")[3].text)[:50]
                        
                    else:
                        research=research+str(src2.find_all("p")[3].text)[50*n:50*(n+1)]
                economy_an.loc[m,['내용']]=research
                m=m+1
                # print(economy_an)
                
            else:
                for n in range(strno1):
                    if n==0:
                        research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]
                    else:
                        research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+1)]
                
                economy_an.loc[m,['내용']]=research
                m=m+1
                # print(economy_an)
    economy_an_html=economy_an.to_html(index=False, justify='center')
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(economy_an_html,'html')
    msg['Subject'] = '경제분석'
    # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())

    s.quit()
    return economy_an 

def headline_in():
    
    k=0
    headline_in=pd.DataFrame()
    url1 = 'https://finance.naver.com/research/market_info_list.naver'
    html1 = urlopen(url1) 
    src1= BeautifulSoup(html1.read(), "html.parser")
    stock_item=src1.find_all(style="padding-left:10px")
    date=src1.find_all(class_="date")
    # print(range(1,len(stock_item)+1),stock_item)
    m=0
    for k in range(len(stock_item)):
        headline_in.loc[k,['일자']]=date[k*2+1].text
        headline_in.loc[k,['제목']]=stock_item[k].text
 

    # for k in range(len(stock_item)) :
    #     headline_in.loc[k,['일자']]=date[k*2+1].text

    #     if k==5 or k==6 or k==7 or k==13 or k==14 or k==15 or k==21 or k==22 or k==23 or k==29 or k==30 or k==31 or k==37 or k==38 or k==39 or k>44  :
    #         pass
    #     else:
    #         if stock_item[k].text[0]=="[":
    #             headline_in.loc[k,['제목']]=stock_item[k*2].text[0:16]

    #         else:
    #             headline_in.loc[k,['제목']]=stock_item[(k+1)*2].text
    #     print(headline_in.loc[k,['제목']])
    # print(headline_in)
    for i in range(len(src1.find_all("tr"))):
            
        # print(src1.find_all("tr")[5].find_all("td")[1])
        if i==5 or i==6 or i==7 or i==13 or i==14 or i==15 or i==21 or i==22 or i==23 or i==29 or i==30 or i==31 or i==37 or i==38 or i==39 or i>44  :
            
            pass
        else:
            path=src1.find_all("tr")[i+2].find_all("td")[0]
            path=str(path) 
            path1=path[path.find("href=")+6:path.find("""1">""")+1]

            url2 = "https://finance.naver.com/research/"+path1 
            
            html2 = urlopen(url2)
            src2= BeautifulSoup(html2.read(), "html.parser")
            strno=math.ceil(len(str(src2.find_all("p")[8].text))/50)
            strno1=math.ceil(len(str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text))/50)
            # print(strno,strno1,str(src2.find_all("p")[8].text))                     
            # if str(src2.find_all("p")[2].text)!= "":
            #     for n in range(strno):
            #         if n==0:
            #             research=str(src2.find_all("p")[8].text)[:50].strip()

            #         else:
            #             research=research+str(src2.find_all("p")[8].text)[50*n:50*(n+1)].strip()


            #     headline_in.loc[m,['내용']]=research
            #     # print(research)
            #     m=m+1
                
            # else:
            #     for n in range(strno1):
            #         if n==0:
            #             research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]

            #         else:
            #             research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+1)]

            #     headline_in.loc[m,['내용']]=research
            #     # print(research)
            #     m=m+1
            for n in range(strno1):
                if n==0:
                    research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]

                else:
                    research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+1)]

            headline_in.loc[m,['내용']]=research
            print(research)
            m=m+1
            
  

    headline_in_html=headline_in.to_html(index=False, justify='center')
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(headline_in_html,'html')
    msg['Subject'] = '시황정보'
    s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())

    s.quit()
    return headline_in


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
            # print(date_WTI[m].text.strip(),len(Summary['일자'].iloc[k]))
            if date_WTI[m].text.strip()== Summary['일자'].iloc[k]:
                Summary.loc[k,['WTI']]=WTI[m*3].text.strip()+'/'+WTI[m*3+2].text.strip()
                # print(Summary.loc[k,['WTI']])
            else:
                pass



    ######    환율(USD)    ####
    url1 = 'https://finance.naver.com//marketindex/exchangeDailyQuote.naver?marketindexCd=FX_USDKRW'
    html1 = urlopen(url1) 
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_USD=src1.find_all(class_="date")
    USD=src1.find_all(class_="num")

    m=0
    for m in range(10):
        for k in range(len(Summary['일자'])):
            if date_USD[m].text.strip()== Summary['일자'].iloc[k]:
                # print(m,k,date_USD[m].text.strip(),Summary['일자'].iloc[k],len(Summary['일자']))
                if str(USD[m*2+1])[str(USD[m*2+1]).find("alt=")+5:str(USD[m*2+1]).find("alt=")+7]=="하락":
                    Summary.loc[k,['USD']]=USD[m*2].text.strip()+'/-'+USD[m*2+1].text.strip()

                else:
                    Summary.loc[k,['USD']]=USD[m*2].text.strip()+'/'+USD[m*2+1].text.strip()


            else:
                pass


    ######    미국채(10year)    ####
    url1 = 'https://kr.investing.com/rates-bonds/u.s.-10-year-bond-yield-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    date_US_INTER10Y_list=src2.find_all(class_="first left bold noWrap")
    US_INTER10Y=src2.find_all("tbody")[0]

    for k in range(len(Summary['일자'])):
        for m in range(len(date_US_INTER10Y_list)):
            date_US_INTER10Y=date_US_INTER10Y_list[m].text[0:4]+"."+date_US_INTER10Y_list[m].text[6:8]+"."+date_US_INTER10Y_list[m].text[10:12]
            # print(date_US_INTER10Y,Summary['일자'].iloc[k])
            if date_US_INTER10Y == Summary['일자'].iloc[k]:
                Summary.loc[k,['미국채(10year)']]=US_INTER10Y.find_all("tr")[m].find_all("td")[1].text+'/'+US_INTER10Y.find_all("tr")[m].find_all("td")[5].text

            else:
                pass


    ######    다우    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=DJI@DJI'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_DJI=src1.find_all(class_="tb_td")
    DJI=src1.find_all(class_="tb_td2")
    DJI_delta=src1.find_all(class_="tb_td3")
    DJI_UPDW=src1.find_all('tr')

    m=0
    for k in range(len(Summary['일자'])):
        if m+1!=11:
            # print(date_DJI[m+1].text.strip(),Summary['일자'].iloc[k])
            if date_DJI[m+1].text.strip()== Summary['일자'].iloc[k]:
                # print('dji',str(DJI_UPDW[m+3])[str(DJI_UPDW[m+3]).find("=")+2:str(DJI_UPDW[m+3]).find("=")+10])
                if str(DJI_UPDW[m+3])[str(DJI_UPDW[m+3]).find("=")+2:str(DJI_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k-1,['다우']]=DJI[m+1].text+'/-'+DJI_delta[m+1].text.strip()
                    # print(Summary.loc[k-1,['다우']],DJI[m+1].text+'/-'+DJI_delta[m+1].text.strip())
                    m=m+1
                else:
                    Summary.loc[k-1,['다우']]=DJI[m+1].text+'/'+DJI_delta[m+1].text.strip()
                    # print(Summary.loc[k-1,['다우']],DJI[m+1].text+'/'+DJI_delta[m+1].text.strip())
                    m=m+1

            else:
                pass
        else:
            break



    ######    나스닥    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=NAS@IXIC'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_NAS=src1.find_all(class_="tb_td")
    NAS=src1.find_all(class_="tb_td2")
    NAS_delta=src1.find_all(class_="tb_td3")
    NAS_UPDW=src1.find_all('tr')


    m=0
    for k in range(len(Summary['일자'])):
        if m+1!=11:
            if date_NAS[m+1].text.strip()== Summary['일자'].iloc[k]:
                # print('nas',str(NAS_UPDW[m+3])[str(NAS_UPDW[m+3]).find("=")+2:str(NAS_UPDW[m+3]).find("=")+10])
                if str(NAS_UPDW[m+3])[str(NAS_UPDW[m+3]).find("=")+2:str(NAS_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k-1,['나스닥']]=NAS[m+1].text+'/-'+NAS_delta[m+1].text.strip()
                    m=m+1
                else:
                    Summary.loc[k-1,['나스닥']]=NAS[m+1].text+'/'+NAS_delta[m+1].text.strip()
                    m=m+1

            else:
                pass
        else:
            break
 

    ######    SNP    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=SPI@SPX'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_SNP=src1.find_all(class_="tb_td")
    SNP=src1.find_all(class_="tb_td2")
    SNP_delta=src1.find_all(class_="tb_td3")
    SNP_UPDW=src1.find_all('tr')


    m=0
    for k in range(len(Summary['일자'])):
        if m+1!=11:
            if date_SNP[m+1].text.strip()== Summary['일자'].iloc[k]:
                # print(str(SNP_UPDW[m+3])[str(SNP_UPDW[m+3]).find("=")+2:str(SNP_UPDW[m+3]).find("=")+10])
                if str(SNP_UPDW[m+3])[str(SNP_UPDW[m+3]).find("=")+2:str(SNP_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k-1,['S&P']]=SNP[m+1].text+'/-'+SNP_delta[m+1].text.strip()
                    m=m+1
                else:
                    Summary.loc[k-1,['S&P']]=SNP[m+1].text+'/'+SNP_delta[m+1].text.strip()
                    m=m+1

            else:
                pass
        else:
            break


    ######    PDM    ####
    url1 = 'https://finance.naver.com/world/sise.naver?symbol=NAS@SOX'
    # req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    html1=urlopen(url1)
    src1= BeautifulSoup(html1.read(), "html.parser")
    date_PDM=src1.find_all(class_="tb_td")
    PDM=src1.find_all(class_="tb_td2")
    PDM_delta=src1.find_all(class_="tb_td3")
    PDM_UPDW=src1.find_all('tr')
        
    m=0
    for k in range(len(Summary['일자'])):
        if m+1!=11:
            if date_PDM[m+1].text.strip()== Summary['일자'].iloc[k]:
                # print('pdm',str(PDM_UPDW[m+3])[str(PDM_UPDW[m+3]).find("=")+2:str(PDM_UPDW[m+3]).find("=")+10])
                if str(PDM_UPDW[m+3])[str(PDM_UPDW[m+3]).find("=")+2:str(PDM_UPDW[m+3]).find("=")+10]=="point_dn":
                    Summary.loc[k-1,['PDM']]=PDM[m+1].text+'/-'+PDM_delta[m+1].text.strip()
                    m=m+1
                else:
                    Summary.loc[k-1,['PDM']]=PDM[m+1].text+'/'+PDM_delta[m+1].text.strip()
                    m=m+1

            else:
                pass
        else:
            break
        
    ######    VIX(S&P500)    ####
    url1 = 'https://kr.investing.com/indices/volatility-s-p-500-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    date_vix=src2.find_all(class_="first left bold noWrap")
    vix=src2.find_all("tbody")[1]

    for k in range(len(Summary['일자'])):
        for m in range(len(date_vix)):
            # print("date",date_vix,date_vix[m],m)
            date_vix_list=date_vix[m].text[0:4]+"."+date_vix[m].text[6:8]+"."+date_vix[m].text[10:12]
            
            if date_vix_list == Summary['일자'].iloc[k]:
                Summary.loc[k,['VIX(S&P)']]=vix.find_all("tr")[m].find_all("td")[1].text+'/'+vix.find_all("tr")[m].find_all("td")[6].text

            else:
                pass
            
    ######    VIX(KOSPI)    ####
    url1 = 'https://kr.investing.com/indices/kospi-volatility-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    date_vix=src2.find_all(class_="first left bold noWrap")
    vix=src2.find_all("tbody")[0]

    for k in range(len(Summary['일자'])):
        for m in range(len(date_vix)):
            # print("date",date_vix,date_vix[m],m)
            date_vix_list=date_vix[m].text[0:4]+"."+date_vix[m].text[6:8]+"."+date_vix[m].text[10:12]
            
            if date_vix_list == Summary['일자'].iloc[k]:
                Summary.loc[k,['VIX(KOSPI)']]=vix.find_all("tr")[m].find_all("td")[1].text+'/'+vix.find_all("tr")[m].find_all("td")[6].text

            else:
                pass
            
    Summary=Summary.fillna('-') 
    # print(Summary)
    Summary_html=Summary.to_html(index=False, justify='center')
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(Summary_html,'html')
    msg['Subject'] = '주요시장지표'
    # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())

    s.quit() 
    return Summary       


# stock_an().to_csv("E:\VSC\CODE\stock_an.csv") ##종목분석
# economy_an().to_csv("E:\VSC\CODE\economy_an.csv")  ##경제분석
headline_in().to_csv("E:\VSC\CODE\headline_in.csv")  ##시황정보
# Summary().to_csv("E:\VSC\CODE\Summary.csv") ##주요시장지표
print(time.time()-start)



