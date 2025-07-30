#git push -u origin master
<<<<<<< HEAD
# -*- coding: utf-8 -*-
=======

>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
<<<<<<< HEAD
import datetime
import inspect
# import pyautogui as pg
import sys
# from datetime import datetime,date
=======
import datetime  
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
start = time.time()

def stock_an():
    i=57427
    k=0
    # url = 'https://finance.naver.com/research/company_read.naver?nid='i+'&page=1'
    # html = urlopen(url) 
    # src= BeautifulSoup(html.read(), "html.parser")
    stock_an=pd.DataFrame()
    url1 = 'https://finance.naver.com/research/company_list.naver'
<<<<<<< HEAD
    html1 = urlopen(url1).read()
    html1 = html1.decode('euc-kr') 
    src1= BeautifulSoup(html1, "html.parser"    )
=======
    html1 = urlopen(url1) 
    src1= BeautifulSoup(html1.read(), "html.parser")
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    stock_item=src1.find_all(class_="stock_item")
    date=src1.find_all(class_="date")

    # src3=src2[2]
    # print(src2)
    m=0
    for k in range(len(stock_item)) :
<<<<<<< HEAD
        stock_an.loc[k,['일자']]=date[k*2].text #[k*2+1]
=======
        stock_an.loc[k,['일자']]=date[k*2+1].text
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
        stock_an.loc[k,['종목']]=stock_item[k].text
    for i in range(len(src1.find_all("tr"))):
            
        # print(src1.find_all("tr")[5].find_all("td")[1])
        if i==5 or i==6 or i==7 or i==13 or i==14 or i==15 or i==21 or i==22 or i==23 or i==29 or i==30 or i==31 or i==37 or i==38 or i==39 or i>44  :
            
            pass
        else:
            path=src1.find_all("tr")[i+2].find_all("td")[1]
            print(path)
<<<<<<< HEAD
            print(stock_an.loc[m,['종목']])
=======
            
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
<<<<<<< HEAD

                stock_an.loc[m,['내용']]=research
                
                m=m+1
                
            else:#str(src2.find_all(class_="source"))[19:26]=="한국기업데이터"  or str(src2.find_all(class_="source"))[19:26]=="IBK투자증권" or str(src2.find_all(class_="source"))[19:26]=="케이프투자증권"
=======
                # print(research)        
                # research=str(src2.find_all("p")[3].find_all("br")[n].text)
                # print(stock_item[k].text,research)
                stock_an.loc[m,['내용']]=research
                m=m+1
                
            elif str(src2.find_all(class_="source"))[19:26]=="한국기업데이터"  or str(src2.find_all(class_="source"))[19:26]=="IBK투자증권" or str(src2.find_all(class_="source"))[19:26]=="케이프투자증권":
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
                for n in range(strno2):
                    if n==0:
                        research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
                    else:
                        research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
                stock_an.loc[m,['내용']]=research
                m=m+1
            
<<<<<<< HEAD
            # elif str(src2.find_all(class_="source"))[19:25]=="나이스디앤비" or str(src2.find_all(class_="source"))[19:25]=="하나금융투자" or str(src2.find_all(class_="source"))[19:25]=="이베스트증권" or str(src2.find_all(class_="source"))[19:25]=="이베스트증권" or str(src2.find_all(class_="source"))[19:25]=="하이투자증권" or str(src2.find_all(class_="source"))[19:25]=="미래에셋증권":
            #     for n in range(strno2):
            #         if n==0:
            #             research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
            #         else:
            #             research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
            #     stock_an.loc[m,['내용']]=research
            #     m=m+1
            # elif str(src2.find_all(class_="source"))[19:27]=="NICE평가정보":
            #     for n in range(strno2):
            #         if n==0:
            #             research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
            #         else:
            #             research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
            #     stock_an.loc[m,['내용']]=research
            #     m=m+1
            # elif str(src2.find_all(class_="source"))[19:23]=="교보증권" or str(src2.find_all(class_="source"))[19:23]=="유안타증" or str(src2.find_all(class_="source"))[19:23]=="한화투자":
            #     for n in range(strno2):
            #         if n==0:
            #             research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
            #         else:
            #             research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
            #     stock_an.loc[m,['내용']]=research
            #     m=m+1
            # elif str(src2.find_all(class_="source"))[19:23]=="하나증권" or str(src2.find_all(class_="source"))[19:23]=="대신증권"  :
            #     for n in range(strno2):
            #         if n==0:
            #             research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
            #         else:
            #             research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
            #     stock_an.loc[m,['내용']]=research
            #     m=m+1

            # else:

            #     for n in range(strno1):
            #         if n==0:
            #             print(str(src2.find_all(class_="source"))[19:23])
            #             print(src2.find_all("p"))
            #             research=str(src2.find_all("p")[7].text)[:50]
            #         else:
            #             research=research+str(src2.find_all("p")[7].text)[50*n:50*(n+1)]

            #     stock_an.loc[m,['내용']]=research
            #     m=m+1
    stock_an_html=stock_an.to_html(index=False, justify='center')
    total=stock_an_html
    mailing(total)
    # s = smtplib.SMTP('smtp.gmail.com', 587)
    # s.starttls()
    # s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    # msg = MIMEText(stock_an_html,'html')
    # msg['Subject'] = '종목분석'+"_"+datetime.datetime.strftime(datetime.datetime.today() ,'%Y%m%d')
    # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
    # s.sendmail("sgw0214@lgdisplay.com", "sgw0214@lgdisplay.com", msg.as_string())
    # s.sendmail("jwseo@pocons.co.kr", "jwseo@pocons.co.kr", msg.as_string())
    # s.quit()
    print("종목분석완료")
    
=======
            elif str(src2.find_all(class_="source"))[19:25]=="나이스디앤비" or str(src2.find_all(class_="source"))[19:25]=="하나금융투자" or str(src2.find_all(class_="source"))[19:25]=="이베스트증권" or str(src2.find_all(class_="source"))[19:25]=="이베스트증권" or str(src2.find_all(class_="source"))[19:25]=="하이투자증권" or str(src2.find_all(class_="source"))[19:25]=="미래에셋증권":
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
    s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "sgw0214@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@naver.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "choice@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "jwseo@pocons.co.kr", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "poqc@pocons.co.kr", msg.as_string())
    s.quit()
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
<<<<<<< HEAD
        economy_an.loc[k,['일자']]=date[k*2].text
=======
        economy_an.loc[k,['일자']]=date[k*2+1].text
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
<<<<<<< HEAD
    total=economy_an_html
    mailing(total)
    print("경제분석완료")
    
=======
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(economy_an_html,'html')
    msg['Subject'] = '경제분석'
    s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "sgw0214@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@naver.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "choice@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "jwseo@pocons.co.kr", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "poqc@pocons.co.kr", msg.as_string())
    s.quit()
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    return economy_an 

def headline_in():
    
    k=0
    headline_in=pd.DataFrame()
    url1 = 'https://finance.naver.com/research/market_info_list.naver'
<<<<<<< HEAD
    html1 = urlopen(url1)           
    # html2 = html2.content.decode('utf-8','replace') 
=======
    html1 = urlopen(url1) 
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    src1= BeautifulSoup(html1.read(), "html.parser")
    stock_item=src1.find_all(style="padding-left:10px")
    date=src1.find_all(class_="date")
    # print(range(1,len(stock_item)+1),stock_item)
    m=0
<<<<<<< HEAD
    no=0
    for k in range(len(stock_item)):
        headline_in.loc[k,['일자']]=date[k*2].text
        headline_in.loc[k,['제목']]=stock_item[k].text
    
=======
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
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    for i in range(len(src1.find_all("tr"))):
            
        # print(src1.find_all("tr")[5].find_all("td")[1])
        if i==5 or i==6 or i==7 or i==13 or i==14 or i==15 or i==21 or i==22 or i==23 or i==29 or i==30 or i==31 or i==37 or i==38 or i==39 or i>44  :
            
            pass
        else:
            path=src1.find_all("tr")[i+2].find_all("td")[0]
            path=str(path) 
            path1=path[path.find("href=")+6:path.find("""1">""")+1]
<<<<<<< HEAD
            url2 = "https://finance.naver.com/research/"+path1 
            html2 = urlopen(url2)
            src2= BeautifulSoup(html2.read(), "html.parser")
            print(src2.find_all("p")[2].text)
            print(src2.find_all("p"))
            print(str(src2.find_all("p")).count("<p"))
            if no==18:
                print("요기")
            if str(src2.find_all("p")).count("<p")==5 :
                
                strno=math.ceil(len(str(src2.find_all("p")[3].text))/50)
                for n in range(strno):
                    if n==0:
                        research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]
                    else:
                        research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+2)]
                print(research) 
                no=no+1    
            elif  str(src2.find_all("p")).count("<p")==6: 

                headline_in.loc[i,['제목']]=str(src2.find_all("p")[3].text)
                strno=math.ceil(len(str(src2.find_all("p")[4].text))/50)
  
                for n in range(strno):
                    if n==0:
                        research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]
                    else:
                        research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+2)]            
                print(research)
                no=no+1
            elif str(src2.find_all("p")).count("<p")==7: 

                headline_in.loc[i,['제목']]=str(src2.find_all("p")[3].text)
                strno=math.ceil(len(str(src2.find_all("p")[5].text))/50)
  
                for n in range(strno):
                    if n==0:
                        research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]
                    else:
                        research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+2)]            
                print(research)
                no=no+1
            elif str(src2.find_all("p")).count("<p")==8 :
                
                strno=str(src2.find_all("p")[3].text) + str(src2.find_all("p")[4].text) + str(src2.find_all("p")[5].text) + str(src2.find_all("p")[6].text) 
                strno=math.ceil(len(strno)/50)
 
                for n in range(strno):
                    if n==0:
                        research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]
                    else:
                        research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+1)]            
                print(research)
                no=no+1
            elif str(src2.find_all("p")).count("<p")>=9 :

                for no_merge in range(str(src2.find_all("p")).count("<p")-4):
                    if no_merge==0:
                        strno=str(src2.find_all("p")[no_merge+3].text)     
                    else:
                        strno=strno+str(src2.find_all("p")[no_merge+3].text) 
                
                strno=math.ceil(len(strno)/50)
 
                for n in range(strno):
                    if n==0:
                        research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]
                    else:
                        research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+1)]            
                print(research)
                no=no+1
            else: print("-") 
=======

            url2 = "https://finance.naver.com/research/"+path1 
            
            html2 = urlopen(url2)
            src2= BeautifulSoup(html2.read(), "html.parser")
            strno=math.ceil(len(str(src2.find_all("p")[8].text))/50)
            strno1=math.ceil(len(str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text))/50)
                                 
            # if str(src2.find_all("p")[2].text)!= "":
            #     for n in range(strno):
            #         if n==0:
            #             research=str(src2.find_all("p")[7].text)[:50].strip()
            #         else:
            #             research=research+str(src2.find_all("p")[7].text)[50*n:50*(n+1)].strip()

            #     headline_in.loc[m,['내용']]=research
            #     m=m+1
                
            # else:
            #     for n in range(strno1):
            #         if n==0:
            #             research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]
            #         else:
            #             research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+1)]
                
            #     headline_in.loc[m,['내용']]=research
            #     m=m+1
            for n in range(strno1):
                if n==0:
                    research=str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[:50]

                else:
                    research=research+str(src2.find_all(style="width:555px;height:100% clear:both; text-align: justify; overflow-x: auto;padding: 20px 0pt 30px;font-size:9pt;line-height:160%; color:#000000;")[0].text).strip()[50*n:50*(n+1)]
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b

            headline_in.loc[m,['내용']]=research
            # print(research)
            m=m+1

    headline_in_html=headline_in.to_html(index=False, justify='center')
<<<<<<< HEAD
    total=headline_in_html
    mailing(total)
    print("시황정보완료")
    
=======
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(headline_in_html,'html')
    msg['Subject'] = '시황정보'
    s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "sgw0214@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@naver.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "choice@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "jwseo@pocons.co.kr", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "poqc@pocons.co.kr", msg.as_string())    
    s.quit()
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    return headline_in


def Summary():
    k=0
    Summary=pd.DataFrame()
<<<<<<< HEAD
    Summary1=pd.DataFrame()
=======
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
<<<<<<< HEAD
    print(date)
    for k in range(20):
        if k==0 : 
            Summary.loc[k,['일자']]=datetime.date.strftime(date,'%Y.%m.%d')
            Summary1.loc[k,['일자']]=datetime.date.strftime(date,'%Y.%m.%d')

        else:
            Summary.loc[k,['일자']]=datetime.date.strftime(date+pd.DateOffset(days=-k),'%Y.%m.%d')
            Summary1.loc[k,['일자']]=datetime.date.strftime(date+pd.DateOffset(days=-k),'%Y.%m.%d')
=======
    for k in range(20):
        if k==0 : 
            Summary.loc[k,['일자']]=datetime.date.strftime(date,'%Y.%m.%d')

        else:
            Summary.loc[k,['일자']]=datetime.date.strftime(date+pd.DateOffset(days=-k),'%Y.%m.%d')
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b

    m=0
    for m in range(10):
        for k in range(len(Summary['일자'])):
            # print(date_WTI[m].text.strip(),len(Summary['일자'].iloc[k]))
            if date_WTI[m].text.strip()== Summary['일자'].iloc[k]:
                Summary.loc[k,['WTI']]=WTI[m*3].text.strip()+'/'+WTI[m*3+2].text.strip()
                # print(Summary.loc[k,['WTI']])
            else:
                pass

<<<<<<< HEAD
=======


>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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

<<<<<<< HEAD
=======

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


>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
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
        
<<<<<<< HEAD
    ######    미국채(2year)    ####
    url1 = 'https://kr.investing.com/rates-bonds/u.s.-2-year-bond-yield-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    # pg.sleep(5)
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    value_US_INTER2Y_list=src2.find_all("td", dir="ltr" )                                        
    date_US_INTER2Y_list=src2.find_all("time")
    print(value_US_INTER2Y_list)
    print(date_US_INTER2Y_list)
    print(Summary1)
    for k in range(len(Summary1['일자'])):
        for m in range(len(Summary1['일자'])):
            # print(Summary1['일자'][k][0:4],len(Summary1['일자'][k][0:4]),date_US_INTER2Y_list[m+1].text[7:],len(date_US_INTER2Y_list[m+1].text[7:]))
            # print(Summary1['일자'][k][6:7],len(Summary1['일자'][k][6:7]),date_US_INTER2Y_list[m+1].text[0:1],len(date_US_INTER2Y_list[m+1].text[0:1]))
            # print(Summary1['일자'][k][8:10],len(Summary1['일자'][k][8:10]),date_US_INTER2Y_list[m+1].text[3:5],len(date_US_INTER2Y_list[m+1].text[3:5]))
            if Summary1['일자'][k][0:4]==date_US_INTER2Y_list[m+1].text[7:] and Summary1['일자'][k][6:7]==date_US_INTER2Y_list[m+1].text[0:1] and Summary1['일자'][k][8:10]==date_US_INTER2Y_list[m+1].text[3:5]:
                Summary1.loc[k,['미국채(2year)']]=value_US_INTER2Y_list[m*2].text +'/'+value_US_INTER2Y_list[(m*2+1)].text.strip()
                # print(Summary1)
            else:
                pass
        
    ######    미국채(10year)    ####
    url1 = 'https://kr.investing.com/rates-bonds/u.s.-10-year-bond-yield-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    # pg.sleep(5)
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    value_US_INTER10Y_list=src2.find_all("td", dir="ltr" )                                        
    date_US_INTER10Y_list=src2.find_all("time")
    for k in range(len(Summary1['일자'])):
        for m in range(len(Summary1['일자'])):
            # print(Summary1['일자'][k][0:4],len(Summary1['일자'][k][0:4]),date_US_INTER10Y_list[m+1].text[7:],len(date_US_INTER10Y_list[m+1].text[7:]))
            # print(Summary1['일자'][k][6:7],len(Summary1['일자'][k][6:7]),date_US_INTER10Y_list[m+1].text[0:1],len(date_US_INTER10Y_list[m+1].text[0:1]))
            # print(Summary1['일자'][k][8:10],len(Summary1['일자'][k][8:10]),date_US_INTER10Y_list[m+1].text[3:5],len(date_US_INTER10Y_list[m+1].text[3:5]))
            if Summary1['일자'][k][0:4]==date_US_INTER10Y_list[m+1].text[7:] and Summary1['일자'][k][6:7]==date_US_INTER10Y_list[m+1].text[0:1] and Summary1['일자'][k][8:10]==date_US_INTER10Y_list[m+1].text[3:5]:
                Summary1.loc[k,['미국채(10year)']]=value_US_INTER10Y_list[m*2].text +'/'+value_US_INTER10Y_list[(m*2+1)].text.strip()
                # print(Summary1)
            else:
                pass
             
=======
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
    ######    VIX(S&P500)    ####
    url1 = 'https://kr.investing.com/indices/volatility-s-p-500-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
<<<<<<< HEAD
    value_US_vix_list=src2.find_all("td", dir="ltr" )                                        
    date_US_vix_list=src2.find_all("time")
    for k in range(len(Summary1['일자'])):
        for m in range(len(Summary1['일자'])):
            # print(Summary1['일자'][k][0:4],len(Summary1['일자'][k][0:4]),date_US_vix_list[m+1].text[7:],len(date_US_vix_list[m+1].text[7:]))
            # print(Summary1['일자'][k][6:7],len(Summary1['일자'][k][6:7]),date_US_vix_list[m+1].text[0:1],len(date_US_vix_list[m+1].text[0:1]))
            # print(Summary1['일자'][k][8:10],len(Summary1['일자'][k][8:10]),date_US_vix_list[m+1].text[3:5],len(date_US_vix_list[m+1].text[3:5]))
            if Summary1['일자'][k][0:4]==date_US_vix_list[m+1].text[7:] and Summary1['일자'][k][6:7]==date_US_vix_list[m+1].text[0:1] and Summary1['일자'][k][8:10]==date_US_vix_list[m+1].text[3:5]:
                Summary1.loc[k,['VIX(S&P)']]=value_US_vix_list[m*2].text +'/'+value_US_vix_list[(m*2+1)].text.strip()
                # print(Summary1)
=======
    date_vix=src2.find_all(class_="first left bold noWrap")
    vix=src2.find_all("tbody")[1]

    for k in range(len(Summary['일자'])):
        for m in range(len(date_vix)):
            # print("date",date_vix,date_vix[m],m)
            date_vix_list=date_vix[m].text[0:4]+"."+date_vix[m].text[6:8]+"."+date_vix[m].text[10:12]
            
            if date_vix_list == Summary['일자'].iloc[k]:
                Summary.loc[k,['VIX(S&P)']]=vix.find_all("tr")[m].find_all("td")[1].text+'/'+vix.find_all("tr")[m].find_all("td")[6].text

>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
            else:
                pass
            
    ######    VIX(KOSPI)    ####
    url1 = 'https://kr.investing.com/indices/kospi-volatility-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
<<<<<<< HEAD
    value_KOR_vix_list=src2.find_all("td", dir="ltr" )                                        
    date_KOR_vix_list=src2.find_all("time")
    for k in range(len(Summary1['일자'])):
        for m in range(len(Summary1['일자'])):
            # print(Summary1['일자'][k][0:4],len(Summary1['일자'][k][0:4]),date_KOR_vix_list[m+1].text[7:],len(date_KOR_vix_list[m+1].text[7:]))
            # print(Summary1['일자'][k][6:7],len(Summary1['일자'][k][6:7]),date_KOR_vix_list[m+1].text[0:1],len(date_KOR_vix_list[m+1].text[0:1]))
            # print(Summary1['일자'][k][8:10],len(Summary1['일자'][k][8:10]),date_KOR_vix_list[m+1].text[3:5],len(date_KOR_vix_list[m+1].text[3:5]))
            if Summary1['일자'][k][0:4]==date_KOR_vix_list[m+1].text[7:] and Summary1['일자'][k][6:7]==date_KOR_vix_list[m+1].text[0:1] and Summary1['일자'][k][8:10]==date_KOR_vix_list[m+1].text[3:5]:
                Summary1.loc[k,['VIX(KOSPI)']]=value_KOR_vix_list[m*2].text +'/'+value_KOR_vix_list[(m*2+1)].text.strip()
                # print(Summary1)
            else:
                pass
            
    ######    Gold(USA)    ####
    url1 = 'https://kr.investing.com/currencies/xau-usd-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    value_USA_GOLD_list=src2.find_all("td", dir="ltr" )                                        
    date_USA_GOLD_list=src2.find_all("time")
    for k in range(len(Summary1['일자'])):
        for m in range(len(Summary1['일자'])):
            # print(Summary1['일자'][k][0:4],len(Summary1['일자'][k][0:4]),date_USA_GOLD_list[m+1].text[7:],len(date_USA_GOLD_list[m+1].text[7:]))
            # print(Summary1['일자'][k][6:7],len(Summary1['일자'][k][6:7]),date_USA_GOLD_list[m+1].text[0:1],len(date_USA_GOLD_list[m+1].text[0:1]))
            # print(Summary1['일자'][k][8:10],len(Summary1['일자'][k][8:10]),date_USA_GOLD_list[m+1].text[3:5],len(date_USA_GOLD_list[m+1].text[3:5]))
            if Summary1['일자'][k][0:4]==date_USA_GOLD_list[m+1].text[7:] and Summary1['일자'][k][6:7]==date_USA_GOLD_list[m+1].text[0:1] and Summary1['일자'][k][8:10]==date_USA_GOLD_list[m+1].text[3:5]:
                Summary1.loc[k,['GOLD(USA)']]=value_USA_GOLD_list[m*2].text +'/'+value_USA_GOLD_list[(m*2+1)].text.strip()
                # print(Summary1)
            else:
                pass
            
    ######    Silver(USA)    ####
    url1 = 'https://kr.investing.com/currencies/usd-xag-historical-data'
    req=Request(url1,headers={'User-Agent':'Mozila/5.0'})
    src1=urlopen(req)
    src2= BeautifulSoup(src1.read(), "html.parser")
    value_USA_SILVER_list=src2.find_all("td", dir="ltr" )                                        
    date_USA_SILVER_list=src2.find_all("time")
    for k in range(len(Summary1['일자'])):
        for m in range(len(Summary1['일자'])):
            # print(Summary1['일자'][k][0:4])
            # print(date_USA_SILVER_list[m+1].text[7:])
            # print(Summary1['일자'][k][0:4],len(Summary1['일자'][k][0:4]),date_USA_SILVER_list[m+1].text[7:],len(date_USA_SILVER_list[m+1].text[7:]))
            # print(Summary1['일자'][k][6:7],len(Summary1['일자'][k][6:7]),date_USA_SILVER_list[m+1].text[0:1],len(date_USA_SILVER_list[m+1].text[0:1]))
            # print(Summary1['일자'][k][8:10],len(Summary1['일자'][k][8:10]),date_USA_SILVER_list[m+1].text[3:5],len(date_USA_SILVER_list[m+1].text[3:5]))
            if Summary1['일자'][k][0:4]==date_USA_SILVER_list[m+1].text[7:] and Summary1['일자'][k][6:7]==date_USA_SILVER_list[m+1].text[0:1] and Summary1['일자'][k][8:10]==date_USA_SILVER_list[m+1].text[3:5]:
                Summary1.loc[k,['SILVER(USA)']]=value_USA_SILVER_list[m*2].text +'/'+value_USA_SILVER_list[(m*2+1)].text.strip()
                # print(Summary1)
            else:
                pass

    # Summary1.loc[:,['예비1']]="00.00000/0.00000"
    # Summary1.loc[:,['예비2']]="00.00000/0.00000"
          
    Summary=Summary.fillna('-') 
    Summary1=Summary1.fillna('-') 
    # print(Summary)
    # print(Summary1)
    Summary_html=Summary.to_html(index=False, justify='center')
    Summary1_html=Summary1.to_html(index=False, justify='center')
    total=Summary_html+Summary1_html
    
    mailing(total)
    print("주요시장지표완료")    
    
    return Summary  

def mailing(total):
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(total,'html')
    
    if inspect.stack()[1].function=="stock_an":        
        msg['Subject'] = '종목분석'+"_"+datetime.datetime.strftime(datetime.datetime.today() ,'%Y%m%d')
        # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
        s.sendmail("sgw0214@lgdisplay.com", "sgw0214@lgdisplay.com", msg.as_string())
        s.sendmail("jwseo@pocons.co.kr", "jwseo@pocons.co.kr", msg.as_string())
        s.quit()
    elif inspect.stack()[1].function=="economy_an":
        msg['Subject'] = '경제분석'+"_"+datetime.datetime.strftime(datetime.datetime.today() ,'%Y%m%d')
        # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
        s.sendmail("sgw0214@lgdisplay.com", "sgw0214@lgdisplay.com", msg.as_string())
        s.sendmail("jwseo@pocons.co.kr", "jwseo@pocons.co.kr", msg.as_string())
        s.quit()
    elif inspect.stack()[1].function=="headline_in":
        msg['Subject'] = '시황정보'+"_"+datetime.datetime.strftime(datetime.datetime.today() ,'%Y%m%d')
        # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
        s.sendmail("sgw0214@lgdisplay.com", "sgw0214@lgdisplay.com", msg.as_string())
        s.sendmail("jwseo@pocons.co.kr", "jwseo@pocons.co.kr", msg.as_string())
        s.quit()
    elif inspect.stack()[1].function=="Summary":
        msg['Subject'] = '주요시장지표'+"_"+datetime.datetime.strftime(datetime.datetime.today() ,'%Y%m%d')
        s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
        s.sendmail("sgw0214@lgdisplay.com", "sgw0214@lgdisplay.com", msg.as_string())
        s.sendmail("jwseo@pocons.co.kr", "jwseo@pocons.co.kr", msg.as_string())
        s.quit() 
=======
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
    s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "sgw0214@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@naver.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "nuclearabc@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "choice@lgdisplay.com", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "jwseo@pocons.co.kr", msg.as_string())
    s.sendmail("sgw0214@gmail.com", "poqc@pocons.co.kr", msg.as_string())
    s.quit() 
    return Summary       
>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b


stock_an().to_csv("E:\VSC\CODE\stock_an.csv")
economy_an().to_csv("E:\VSC\CODE\economy_an.csv")
headline_in().to_csv("E:\VSC\CODE\headline_in.csv")
Summary().to_csv("E:\VSC\CODE\Summary.csv")
<<<<<<< HEAD
print(time.time()-start)
=======
print(time.time()-start)



>>>>>>> d94d1e5bc2617341817aaa91149fa23bbc08a09b
