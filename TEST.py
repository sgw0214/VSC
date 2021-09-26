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

GC=pd.DataFrame()
url = 'https://finance.naver.com/sise/item_gold.naver'
html = urlopen(url) 
src= BeautifulSoup(html.read(), "html.parser")
GC_TITLELIST=src.find_all(class_="tltle")
for i in range(len(GC_TITLELIST)):
    
    GC.loc[i,0]=GC_TITLELIST[i].text
    GC.loc[i,1]=i+1
    print(GC)





print(time.time()-start)