#git push -u origin master

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
start = time.time()

k=0
title=pd.DataFrame(columns=["종목","Code","현재가","전일비","등락률","액면가","시가총액","상장주식수","외국인비율","거래량","PER","ROE"])
url = 'https://finance.naver.com/sise/sise_market_sum.nhn?&page=1'
html = urlopen(url) 
src= BeautifulSoup(html.read(), "html.parser")
maxpage=src.find_all("table",align="center")
maxpage = maxpage[0].find_all("td",class_="pgRR")
maxpage=str(maxpage)
maxpage=maxpage[maxpage.find("page=")+5:maxpage.find(">맨뒤")-1]
for page in range(0,int(maxpage)-1):
    
    url = 'https://finance.naver.com/sise/sise_market_sum.nhn?&page='+ str(page+1)
    html = urlopen(url) 
    src= BeautifulSoup(html.read(), "html.parser")
    titlelist=src.find_all(class_="tltle")
    classnumber=src.find_all("td",class_="number")
    spanclass=src.find_all("span")
    
    # print(titlelist)
    
    for i in range(0,50):

        # print(str(str(spanclass[i*2+61].text).strip()[0]+str(spanclass[i*2+60].text).strip()) )
        
        title.loc[k*50+i,["종목"]]=titlelist[i].text
        title.loc[k*50+i,["Code"]]=str(titlelist[i])[str(titlelist[i]).find("code=")+5:str(titlelist[i]).find(">")-1]
        title.loc[k*50+i,["현재가"]]=classnumber[i*(10)].text
        title.loc[k*50+i,["전일비"]]=str(str(spanclass[i*2+61].text).strip()[0]+str(spanclass[i*2+60].text).strip())
        title.loc[k*50+i,["등락률"]]=str(spanclass[i*2+61].text).strip()
        title.loc[k*50+i,["액면가"]]=classnumber[i*(10)+3].text
        title.loc[k*50+i,["시가총액"]]=classnumber[i*(10)+4].text
        title.loc[k*50+i,["상장주식수"]]=classnumber[i*(10)+5].text
        title.loc[k*50+i,["외국인비율"]]=classnumber[i*(10)+6].text
        title.loc[k*50+i,["거래량"]]=classnumber[i*(10)+7].text
        title.loc[k*50+i,["PER"]]=classnumber[i*(10)+8].text
        title.loc[k*50+i,["ROE"]]=classnumber[i*(10)+9].text
        
        # [str(titlelist[i]).find("code=")+5:str(titlelist[i]).find(">")-1]
        print(title)


    k=k+1
    
title.to_excel("E:\VSC\CODE\stock.xlsx",encoding='utf8')
title.to_csv("E:\VSC\CODE\stock.csv")
 

print(time.time()-start)

