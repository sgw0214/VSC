#git push -u origin master
# -*- coding: utf-8 -*-
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
import inspect
import sys
# from datetime import datetime,date
# # import pyautogui as pg

import json

from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from geopy.geocoders import Nominatim
from selenium.webdriver.chrome.service import Service
from urllib.parse import quote


    
    # 네이버 지도 검색 페이지 열기


start = time.time()


# 위도, 경도 반환 함수
def geocoding(address):
    try:        
        geo_local = Nominatim(user_agent='South Korea')
        geo = geo_local.geocode(address)
        x_y = [geo.latitude, geo.longitude]
        return x_y

    except:
        return [0,0]

def time_wait(num, code,driver):
    try:
        
        wait = WebDriverWait(driver, num).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, code)))
    except:
        print(code, '태그를 찾지 못하였습니다.')
        driver.quit()
    return wait

# frame 변경 메소드
def switch_frame(frame,driver):
    
    driver.switch_to.default_content()  # frame 초기화
    driver.switch_to.frame(frame)  # frame 변경

# 페이지 다운
def page_down(num,driver):
    body = driver.find_element(By.CSS_SELECTOR, 'body')
    body.click()
    for i in range(num):
        body.send_keys(Keys.PAGE_DOWN)

def search_lnglat(key_word):
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))  #ChromeDriverManager().install()
    driver.get("https://map.naver.com/v5/search") 
    
    # css를 찾을때 까지 10초 대기
    time_wait(10, 'div.input_box > input.input_search',driver)

    # 검색창 찾기
    search = driver.find_element(By.CSS_SELECTOR, 'div.input_box > input.input_search')
    search.send_keys(key_word)  
    search.send_keys(Keys.ENTER) 

    sleep(10)

    # frame 변경
    time_wait(10, 'iframe#searchIframe',driver)
    switch_frame('searchIframe',driver)

    sleep(10)

    page_down(40,driver)
    sleep(5)

    # 가게 리스트
    store_list = driver.find_elements(By.CSS_SELECTOR, 'li.VLTHu')
    # 페이지 리스트
    next_btn = driver.find_elements(By.CSS_SELECTOR, '.zRM9F> a')

    # dictionary 생성
    store_dict = {'가게 정보': []}
    # 시작시간
    start = time.time()
    print('[크롤링 시작...]')

    # 크롤링 (페이지 리스트 만큼)
    for btn in range(len(next_btn))[1:]:  # next_btn[0] = 이전 페이지 버튼 무시 -> [1]부터 시작
        store_list = driver.find_elements(By.CSS_SELECTOR, 'li.VLTHu')
        
        names = driver.find_elements(By.CSS_SELECTOR, '.YwYLL')  #  장소명
        for data in range(len(store_list)): 

            sleep(2)
            try:
                # 도로명 초기화
                road_address = ''
                # 가게명 가져오기
                store_name = names[data].text
                print(store_name)
            
                # 주소 버튼 누르기
                address_buttons = driver.find_elements(By.CSS_SELECTOR, '.lWwyx > a')
                address_buttons[data].click()

                
                # 로딩 기다리기
                sleep(2)

                # 주소 눌렀을 때 도로명, 지번 나오는 div
                addr = driver.find_elements(By.CSS_SELECTOR, '.AbTyi> div')
            
                sleep(2)
                # 도로명
                road = addr[0].text 
                road_address = road[3:-2]
            
                sleep(2)
                print({'id':data, 'title': store_name, 'address':road_address, 'lat':geocoding(road_address)[0],'lng':geocoding(road_address)[1]})
                # dict에 데이터 집어넣기
                dict_temp = {
                    'name': store_name,
                    'road_address': road_address,
                    'latitude' : geocoding(road_address)[0],
                    'longitude' : geocoding(road_address)[1]}
                store_dict['가게 정보'].append(dict_temp)

                if data==0:
                    break
            except Exception as e:
                print(e)
                
        # 다음 페이지 버튼 누를 수 없으면 종료
        if not next_btn or not next_btn[-1].is_enabled():
            break

        # if names[-1]:  # 마지막 가게일 경우 다음버튼 클릭
        #     next_btn[-1].click()
        #     sleep(2)

        else:
            print('페이지 인식 못함')
            break

    print('[데이터 수집 완료]\n소요 시간 :', time.time() - start)
    driver.quit()  # 작업이 끝나면 창을 닫는다.\
    return geocoding(road_address)[1], geocoding(road_address)[0]

def dismin(url):
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))  #ChromeDriverManager().install()
    driver.get(url) 
    time_wait(10, 'div.route_summary_box > div.route_summary_info_duration',driver)
    dism1 = driver.find_element(By.CSS_SELECTOR, 'div.route_summary_box > div.route_summary_info_duration')
    sleep(10)
    print(dism1.text)
    driver.quit()  # 작업이 끝나면 창을 닫는다.\

    
my_list=[]
key_word = ['대화마을 7단지','두산위브더제니스 일산']# 검색어
for i in key_word:
    print(i)
    ml=search_lnglat(i)
    print(ml)
    my_list.extend(ml)
print(my_list)    
url="https://map.naver.com/p/directions/"+str(my_list[0])+","+str(my_list[1])+","+quote(key_word[0])+",/"+str(my_list[2])+","+str(my_list[3])+","+quote(key_word[1])+",/-/car/0?c=11.00,0,0,0,dh"
# url="https://map.naver.com/p/directions/126.9405487,37.5951089,%EC%84%9C%EC%9A%B8%EC%97%AD%20%EA%B2%BD%EC%9D%98%EC%A4%91%EC%95%99%EC%84%A0,/126.7609492,37.694007,%ED%83%84%ED%98%84%EC%97%AD%20%EA%B2%BD%EC%9D%98%EC%A4%91%EC%95%99%EC%84%A0,/-/car/0?c=11.00,0,0,0,dh"
print(url)
dismin(url)







#<div class="route_summary_info_duration"><strong class="StyledReadableDuration-sc-16wltj8-0 hwCdEF type_car"><span class="item_value">34</span><span class="item_unit">분</span></strong><span class="item_distance">20km</span></div>
# json 파일로 저장
#with open('data/geongjy_store_data.json', 'w', encoding='utf-8') as f:
 #   json.dump(store_dict, f, indent=4, ensure_ascii=False)

# def stock_an():
#     i=57427
#     k=0
#     stock_an=pd.DataFrame()
#     url1 = 'https://finance.naver.com/research/company_list.naver'
#     html1 = urlopen(url1).read()
#     html1 = html1.decode('euc-kr') 
#     src1= BeautifulSoup(html1, "html.parser"    )
#     stock_item=src1.find_all(class_="stock_item")
#     date=src1.find_all(class_="date")
#     m=0
#     for k in range(len(stock_item)) :
#         stock_an.loc[k,['일자']]=date[k*2].text #[k*2+1]
#         stock_an.loc[k,['종목']]=stock_item[k].text
#     for i in range(len(src1.find_all("tr"))):
#         # print(src1.find_all("tr")[5].find_all("td")[1])
#         if i==5 or i==6 or i==7 or i==13 or i==14 or i==15 or i==21 or i==22 or i==23 or i==29 or i==30 or i==31 or i==37 or i==38 or i==39 or i>44  :
#             pass
#         else:
#             path=src1.find_all("tr")[i+2].find_all("td")[1]
#             print(path)
#             print(stock_an.loc[m,['종목']])
#             path=str(path) 
#             path1=path[path.find("""=""")+2:path.find("""">""")]
#             url2 = "https://finance.naver.com/research/"+path1
#             html2 = urlopen(url2)
#             src2= BeautifulSoup(html2.read(), "html.parser")
#             strno=math.ceil(len(str(src2.find_all("p")[3].text))/50)
#             strno1=math.ceil(len(str(src2.find_all("p")[2].text))/50)
#             strno2=math.ceil(len(str(src2.find_all("tr")[3].find_all("div")[0].text.strip()))/50)
#             # print(str(src2.find_all(class_="source"))[19:25])
#             if str(src2.find_all("p")[2].text)== "":
#                 for n in range(strno):
#                     if n==0:
#                         research=str(src2.find_all("p")[3].text)[:50]
#                     else:
#                         research=research+str(src2.find_all("p")[3].text)[50*n:50*(n+1)]
#                 stock_an.loc[m,['내용']]=research
#                 m=m+1
#             else:#str(src2.find_all(class_="source"))[19:26]=="한국기업데이터"  or str(src2.find_all(class_="source"))[19:26]=="IBK투자증권" or str(src2.find_all(class_="source"))[19:26]=="케이프투자증권"
#                 for n in range(strno2):
#                     if n==0:
#                         research=str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[:50]
#                     else:
#                         research=research+str(src2.find_all("tr")[3].find_all("div")[0].text.strip())[50*n:50*(n+1)]
#                 stock_an.loc[m,['내용']]=research
#                 m=m+1

#     stock_an_html=stock_an.to_html(index=False, justify='center')
#     total=stock_an_html

#     # s = smtplib.SMTP('smtp.gmail.com', 587)
#     # s.starttls()
#     # s.login('sgw0214@gmail.com', 'thdfcvhemyjyxfik')
#     # msg = MIMEText(stock_an_html,'html')
#     # msg['Subject'] = '종목분석'+"_"+datetime.datetime.strftime(datetime.datetime.today() ,'%Y%m%d')
#     # s.sendmail("sgw0214@gmail.com", "sgw0214@gmail.com", msg.as_string())
#     # s.sendmail("sgw0214@lgdisplay.com", "sgw0214@lgdisplay.com", msg.as_string())
#     # s.sendmail("jwseo@pocons.co.kr", "jwseo@pocons.co.kr", msg.as_string())
#     # s.quit()
#     print("종목분석완료")
#     return stock_an

# stock_an().to_csv("E:\VSC\CODE\stock_an.csv")











print(time.time()-start)