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
# import pyautogui as pg
import sys
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from datetime import datetime

#-*-coding:utf-8-*-

# # url = "https://m.land.naver.com/search/result/{}".format(keyword)
url = "https://fin.land.naver.com/complexes/100702?tradeTypes=A1&pyeongTypeNumbers=3,4&sortingType=%EB%82%AE%EC%9D%80%EA%B0%80%EA%B2%A9%EC%88%9C&tab=article"   
# res = requests.get(url)
# res.raise_for_status()
html = urlopen(url).read()
html = html.decode('utf-8') 
src= BeautifulSoup(html, "html.parser")
# # https://fin.land.naver.com/complexes/100702?tradeTypes=A1&pyeongTypeNumbers=3,4&sortingType=%EB%82%AE%EC%9D%80%EA%B0%80%EA%B2%A9%EC%88%9C&tab=article   
# # print(src)
# src1=src.find_all("span")[38:]
# # src2=src.find_all("href")
# print(src1)

chrome_options = Options()
chrome_options.add_experimental_option("detach", True)

# 불필요한 에러 메시지 없애기
chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
chrome_options.add_argument("--headless") 
# 브라우저 생성
browser = webdriver.Chrome(options=chrome_options)
browser.get("https://fin.land.naver.com/complexes/100702?tradeTypes=A1&pyeongTypeNumbers=3,4&sortingType=%EB%82%AE%EC%9D%80%EA%B0%80%EA%B2%A9%EC%88%9C&tab=article"  )

df=DataFrame()
xpath='//*[@id="article-list"]/ul/li[1]'
list = browser.find_elements(By.XPATH, xpath)
list_count=len(src.find_all(lambda tag: tag.name == "li" and tag.get("class") and any("ComplexArticleItem_item__L5o7k" in class_name for class_name in tag.get("class"))))
j=1    
for i in range(1,list_count+1):
  
    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/span/span[1]'
    # gubun=browser.find_element(By.XPATH, xpath).text[3]
    try:
        browser.find_element(By.XPATH, xpath).text
        # print(browser.find_element(By.XPATH, xpath).text[:3])
        if browser.find_element(By.XPATH, xpath).text[:3]=="중개사":
            
            button = browser.find_element(By.XPATH, '//*[@id="article-list"]/ul/li['+str(i)+']/div/button')  
            button.click()
            parent_element=button.find_element(By.XPATH, '//*[@id="article-list"]/ul/li['+str(i)+']/ul')

            child_elements = parent_element.find_elements(By.TAG_NAME, 'li')
            # print(len(child_elements))
            list_count1=int(len(child_elements)/2)
            # print(list_count1)
            try:
                for k in range(1,list_count1+1):
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/span[1]'
                    title = browser.find_element(By.XPATH, xpath).text
                    df.loc[j,"동"]=title
                    
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/ul/li[2]'
                    pyeng = browser.find_element(By.XPATH, xpath).text
                    df.loc[j,"평구분"]=pyeng[-2:-1]
                    
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/ul/li[3]'
                    floor = browser.find_element(By.XPATH, xpath).text
                    df.loc[j,"층"]=floor
                    
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/ul/li[4]'
                    quarter = browser.find_element(By.XPATH, xpath).text
                    df.loc[j,"방향"]=quarter  
                    
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/ul/li['+str(k)+']/div/div/ul[2]/li[1]'
                    s_name1 = browser.find_element(By.XPATH, xpath).text
                    df.loc[j,"부동산명"]=s_name1
                    # print(s_name) 
                    
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/ul/li['+str(k)+']/div/div/p/span'
                    desc1 = browser.find_element(By.XPATH, xpath).text
                    df.loc[j,"내용"]=desc1
                    # print(desc)           
                                                    
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/ul/li['+str(k)+']/div/div/ul[1]/li[2]' 
                    update_day1 = browser.find_element(By.XPATH, xpath).text
                    df.loc[j,"확인날짜"]=update_day1[5:]
                    # print(update_day1)
                                                    
                    xpath='//*[@id="article-list"]/ul/li['+str(i)+']/ul/li['+str(k)+']/div/div/span'
                    value1 = browser.find_element(By.XPATH, xpath).text
                    value1=value1.replace("변동", "")
                    value1=value1.replace("하락내역 보기", "")
                    df.loc[j,"호가"]=value1[3:]
                    # print(value1)
                    
                    j=j+1 
                    
            except NoSuchElementException:
                pass
          
    except NoSuchElementException:
        # print("na")
 
        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/span[1]'
        title = browser.find_element(By.XPATH, xpath).text
        df.loc[j,"동"]=title
        
        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/ul/li[2]'
        pyeng = browser.find_element(By.XPATH, xpath).text
        df.loc[j,"평구분"]=pyeng[-2:-1]
        
        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/ul/li[3]'
        floor = browser.find_element(By.XPATH, xpath).text
        df.loc[j,"층"]=floor
        
        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/ul/li[4]'
        quarter = browser.find_element(By.XPATH, xpath).text
        df.loc[j,"방향"]=quarter  
        
        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/ul[2]/li[1]'
        s_name = browser.find_element(By.XPATH, xpath).text
        df.loc[j,"부동산명"]=s_name 

        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/p/span'
        desc = browser.find_element(By.XPATH, xpath).text
        df.loc[j,"내용"]=desc 

        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/ul[1]/li[2]'
        update_day = browser.find_element(By.XPATH, xpath).text
        df.loc[j,"확인날짜"]=update_day[5:]

        xpath='//*[@id="article-list"]/ul/li['+str(i)+']/div/div/div/span[2]'
        value = browser.find_element(By.XPATH, xpath).text
        value=value.replace("변동", "")
        value=value.replace("하락내역 보기", "")
        df.loc[j,"호가"]=value[3:22]

        j=j+1
df=df.dropna()
print(df)
df = df.drop_duplicates(keep='last') 

def convert_price(value):
    # 쉼표와 공백 제거
    value = value.replace(",", "").replace(" ", "")
    # "억"과 "천"을 기준으로 숫자 변환
    if "억" in value and "천" in value:
        parts = value.split("억")
        main = float(parts[0]) if parts[0] else 0  # 억 단위
        sub = float(parts[1].replace("천", ""))  if parts[1] else ".00"  # 천 단위
        return float(main + "."+sub)
    elif "억" in value:
        return float(value.replace("억", ".00"))
    
    return float(value)

# 컬럼 값 변환
df["호가"] = df["호가"].apply(convert_price)


df.to_excel('제니스매물_조회일.xlsx', index=False)
# df.to_excel('제니스매물1.xlsx', index=False)
df_origin = pd.read_excel("E:\VSC\CODE\제니스매물.xlsx")
df_origin1=pd.DataFrame(columns=["동","평구분", "층", "방향","부동산명","내용","확인날짜","호가"])
cnt_col=len(df_origin.columns)
# df = pd.read_excel("E:\VSC\CODE\제니스매물1.xlsx")
k=0
today = datetime.now()
formatted_date = today.strftime("%y%m%d")  # "년월일" 형식 (241219)
for m in range(len(df_origin)): #len(df_origin) - 1, insert_position, -1
    print("m:" , m,"k:",k) 
    # m=m+k
    
    for n in range(len(df)):
        print("m:" , m,"/",len(df_origin)-1, ",n:",n,"/",len(df)-1 , ",k:",k)  
        if m==33:
            print("")  
        if n==len(df):
            break
        print("df_origin:",df_origin.iloc[m,0:8].to_numpy())
        print("df:",df.iloc[n,0:8].to_numpy())  
                
        if df_origin.iloc[m,0:8].tolist()==df.iloc[n,0:8].tolist():
            print("완전동일",m,n)
            print("확인:",df_origin.iloc[m,0:8].to_numpy())
            df = df.drop(df.index[n])
            df = df.reset_index(drop=True)
            print(n,"df행삭제")
            reset="true"

        
    for n in range(len(df)):
        print("m:" , m,"/",len(df_origin)-1, ",n:",n,"/",len(df)-1 , ",k:",k)  
        if reset=="true" or n==len(df):
            break        
        
        print("df_origin:",df_origin.iloc[m,0:8].to_numpy())
        print("df:",df.iloc[n,0:8].to_numpy())  
        
        if df_origin.iloc[m,0:6].tolist()==df.iloc[n,0:6].tolist():
            print("호가 또는 확인날짜 다름",m,n)
            
            if df_origin.loc[m,"확인날짜"]==df.iloc[n,6]: #호가 다름
                print("호가다름",m,n)
                if len(df_origin.iloc[m,:])==len(df_origin.columns):
                    df_origin.loc[m,"이전호가변동"]=df_origin.loc[m,"호가"]+"("+df_origin.loc[m,"확인날짜"]+")"
                elif len(df_origin.iloc[m,])<len(df_origin.columns):  
                    df_origin.iloc[m,len(df_origin.iloc[m,:])+1]=df_origin.loc[m,"호가"]+"("+df_origin.loc[m,"확인날짜"]+")"
                df_origin.loc[m,"호가"]=df.iloc[n,7] 
                print("확인:",df_origin.iloc[m,0:8].to_numpy())
                df = df.drop(df.index[n])
                df = df.reset_index(drop=True)
                print(n,"df행삭제")
                reset=="true1"
                # break
            elif df_origin.loc[m,"호가"]==df.iloc[n,7]: #확인날짜 다름
                print("확인날짜 다름",m,n)
                df_origin.loc[m,"확인날짜"]=df.iloc[n,6]
                print("확인:",df_origin.iloc[m,0:8].to_numpy())
                df = df.drop(df.index[n])
                df = df.reset_index(drop=True)
                print(n,"df행삭제")
                reset=="true1"
                # break
            else: #둘다 다름            
                print("호가와 확인날짜 다름",m,n)
                if len(df_origin.iloc[m,:])==len(df_origin.columns):
                    df_origin.loc[m,"이전호가변동"]=df_origin.loc[m,"호가"]+"("+df_origin.loc[m,"확인날짜"]+")"
                elif len(df_origin.iloc[m,])<len(df_origin.columns):  
                    df_origin.iloc[m,len(df_origin.iloc[m,:])+1]=df_origin.loc[m,"호가"]+"("+df_origin.loc[m,"확인날짜"]+")"
                df_origin.loc[m,"확인날짜"]=df.iloc[n,6]
                df_origin.loc[m,"호가"]=df.iloc[n,7] 
                print("확인:",df_origin.iloc[m,0:8].to_numpy())
                df = df.drop(df.index[n])
                df = df.reset_index(drop=True)
                print(n,"df행삭제")
                reset=="true1"
                # break
            
        elif df_origin.iloc[m,0:4].tolist()==df.iloc[n,0:4].tolist(): #동일 부동산
            print("부동산명 또는 내용다름",m,n)
            print(df_origin.iloc[m,0:8].to_numpy())
            print(df.iloc[n,0:8].to_numpy())
            
            if df_origin.loc[m,"내용"]==df.iloc[n,6]: #내용 같고, 부동산이 다르거나
                new_row=df.iloc[n,0:8]
                # new_row = {"동": df.iloc[n,0], "평구분": df.iloc[n,1], "층": df.iloc[n,2], "방향": df.iloc[n,3],"부동산명": df.iloc[n,4],"내용":df.iloc[n,5],"확인날짜": df.iloc[n,6],"호가": df.iloc[n,7]}
                print(len(df_origin))
                if m+1<len(df_origin):  #중간
                    df_top = df.iloc[:m]
                    df_bottom = df.iloc[m:]
                    df_origin = pd.concat([df_top, pd.DataFrame([new_row]), df_bottom], ignore_index=True)
                    df = df.drop(df.index[n])
                    df = df.reset_index(drop=True)
                    print(n,"df행삭제")
                    reset=="true1"
                    # break
                else:  #마지막
                    df_origin1.iloc[k]=new_row
                    df = df.drop(df.index[n])
                    df = df.reset_index(drop=True)
                    print(n,"df행삭제")
                    k=k+1
                    reset=="true1"
                    # break
            
            elif df_origin.loc[m,"부동산명"]==df.iloc[n,5]: #내용 다르고, 부동산이 같음
                print("내용 및 부동산명 다름")
                df_origin.loc[m,"내용"]=df.iloc[n,6]
                print("확인:",df_origin.iloc[m,0:8].to_numpy())
                df = df.drop(df.index[n])
                df = df.reset_index(drop=True)
                print(n,"df행삭제")
                reset=="true1"
                # break
            
            else: #둘다 다름
                print("내용 및 부동산명 둘다 다름")
                new_row=df.iloc[n,0:8]
                # new_row = {"동": df.iloc[n,0], "평구분": df.iloc[n,1], "층": df.iloc[n,2], "방향": df.iloc[n,3],"부동산명": df.iloc[n,4],"내용":df.iloc[n,5],"확인날짜": df.iloc[n,6],"호가": df.iloc[n,7]}
                print(len(df_origin))
                if m+1<len(df_origin):  #중간
                    df_top = df_origin.iloc[:m]
                    df_bottom = df_origin.iloc[m:]
                    df_origin = pd.concat([df_top, pd.DataFrame([new_row]), df_bottom], ignore_index=True)
                    print("추가:",new_row.to_numpy())
                    print("확인:",df_origin.iloc[m,0:8].to_numpy())
                    print("삭제:",df.iloc[n,:].to_numpy())
                    df = df.drop(df.index[n])
                    df = df.reset_index(drop=True)
                    print(n,"df행삭제")
                    reset=="true1"
                    # break
                else:  #마지막
                    df_origin1.iloc[k+1]=new_row
                    df = df.drop(df.index[n])
                    df = df.reset_index(drop=True)
                    print(n,"마지막 추가")
                    k=k+1
                    reset=="true1"
                    # break
                
    for n in range(len(df)):
        print("신규등록")
        print("m:" , m,"/",len(df_origin)-1, ",n:",n,"/",len(df)-1 , ",k:",k)  
        if reset=="true1" or n==len(df) or reset=="true":
            break        
        
        print("df_origin:",df_origin.iloc[m,0:8].to_numpy())
        print("df:",df.iloc[n,0:8].to_numpy())   
 
        new_row=df.iloc[n,0:8]
        # new_row = {"동": df.iloc[n,0], "평구분": df.iloc[n,1], "층": df.iloc[n,2], "방향": df.iloc[n,3],"부동산명": df.iloc[n,4],"내용":df.iloc[n,5],"확인날짜": df.iloc[n,6],"호가": df.iloc[n,7]}

        if m+1<len(df_origin):  #중간
            df_top = df_origin.iloc[:m]
            df_bottom = df_origin.iloc[m:]
            df_origin = pd.concat([df_top, pd.DataFrame([new_row]), df_bottom], ignore_index=True)
            df = df.drop(df.index[n])
            df = df.reset_index(drop=True)
            print(n,"df행삭제")

        else:  #마지막
            df_origin1.iloc[k]=new_row
            df = df.drop(df.index[n])
            df = df.reset_index(drop=True)
            print(n,"마지막 추가")
            k=k+1

df_origin = pd.concat([df_origin, df_origin1], ignore_index=True)
df_origin = df_origin.drop_duplicates(keep='last') 

df_origin["호가_확인날짜"]=df_origin["호가"]+"("+df_origin["확인날짜"]+")"
print(df_origin["호가_확인날짜"])

# for m in range(len(df_origin)):
#     for n in range(len(df_origin)):
#         if df_origin.loc[m,"부동산명"]==df.iloc[n,5]
    
df_origin.to_excel('제니스매물.xlsx', index=False)
print("저장완료")