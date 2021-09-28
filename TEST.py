#git push -u origin master

from os import kill
from sched import scheduler
from pandas.core.frame import DataFrame
import requests
from urllib.request import urlopen
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
import schedule
import time
import smtplib
from email.mime.text import MIMEText



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
            path=str(path) 
            path1=path[path.find("""=""")+2:path.find("""">""")]
            # print(k,i,path1)
            url2 = "https://finance.naver.com/research/"+path1
            html2 = urlopen(url2)
            src2= BeautifulSoup(html2.read(), "html.parser")
            strno=math.ceil(len(str(src2.find_all("p")[3].text))/50)
            strno1=math.ceil(len(str(src2.find_all("p")[2].text))/50)
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
            else:
                for n in range(strno1):
                    if n==0:
                        research=str(src2.find_all("p")[2].text)[:50]
                        
                    else:
                        research=research+str(src2.find_all("p")[2].text)[50*n:50*(n+1)]
                # research=str(src2.find_all("p")[2].text)
                # print(stock_item[k].text,research)
                stock_an.loc[m,['내용']]=research
                m=m+1
    stock_an_html=stock_an.to_html(index=False, justify='center')
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
    msg = MIMEText(stock_an_html,'html')
    msg['Subject'] = '제목 : 메일 보내기 테스트입니다.'
    s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
    s.quit()
    return stock_an
        

# stock_an()
stock_an().to_csv("E:\VSC\CODE\stock_an.csv")
print(time.time()-start)


schedule.every().day.at("07:32").do(stock_an) 

while True: 
    schedule.run_pending() 
    time.sleep(1)




