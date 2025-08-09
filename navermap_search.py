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
from openpyxl import load_workbook,Workbook
import math
import smtplib
import sched
from email.mime.text import MIMEText
import datetime
import inspect
import sys
# from datetime import datetime,date
# # import pyautogui as pg
import re
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

start = time.time()

# 위도, 경도 반환 함수
def geocoding(address):
    try:        
        geo_local = Nominatim(user_agent='South Korea')
        geo = geo_local.geocode(address)
        sleep(2)
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
    
    # css를 찾을때 까지 5초 대기
    time_wait(5, 'div.input_box > input.input_search',driver)

    # 검색창 찾기
    search = driver.find_element(By.CSS_SELECTOR, 'div.input_box > input.input_search')
    search.send_keys(key_word)  
    search.send_keys(Keys.ENTER) 
    sleep(2)

    try:
        try:
            print("searchIframe_CSS")
            lon, lat = None, None
            print("lon, lat 초기화")
            store_name = key_word
            road_address_fi= key_word
            lon,lat=geocoding(road_address_fi)
            print(f"도로명, 'title': '{key_word}', 'address':'{key_word}', 'lat':'{lat}','lng':'{lon}'")
            # dictionary 생성
            store_dict = {'가게 정보': []}
            if lat==0: 
                # frame 변경
                time_wait(5, 'iframe#searchIframe',driver)
                switch_frame('searchIframe',driver) #entryIframe
                sleep(2)     

                # dictionary 생성
                store_dict = {'가게 정보': []}
                
                # 시작시간        
                print('[크롤링 시작...]')

                # 크롤링
                store_list = driver.find_elements(By.CSS_SELECTOR, 'li.VLTHu')
                # 도로명 초기화
                road_address = ''
                print(driver.find_elements(By.CSS_SELECTOR, '.lWwyx > a'))
                # if driver.find_elements(By.CSS_SELECTOR, '.lWwyx > a')!= None:#len(store_list) >1 
                if driver.find_elements(By.CSS_SELECTOR, '.YwYLL')!=[]:
                    names = driver.find_elements(By.CSS_SELECTOR, '.YwYLL')  #  장소명1  
                    sleep(2)
                else:
                    names = driver.find_elements(By.CSS_SELECTOR, '.TYaxT')  #  장소명2 
                    sleep(2)

                # 가게명 가져오기
                store_name = names[0].text
                print("searchIframe",store_name)
                
                # 주소 버튼 누르기
                address_buttons = driver.find_elements(By.CSS_SELECTOR, '.lWwyx > a')
                address_buttons[0].click()
                
                # 로딩 기다리기
                sleep(2)

                # 주소 눌렀을 때 도로명, 지번 나오는 div
                addr0 = driver.find_element(By.CSS_SELECTOR, "span.Pb4bU")
                sleep(2)
                addr1 = driver.find_elements(By.CSS_SELECTOR, '.AbTyi> div')
                sleep(2)
                # 도로명            
                road = addr1[0].text 
                road_address = road[3:-2].replace("\n", "")
                road_address_fi=addr0.text+" "+road_address
                print(road_address_fi)
                lon,lat=geocoding(road_address_fi)
                print(f"도로명 재시도1, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                if lat==0:
                    road = addr1[0].text 
                    road_address = road[3:-2].replace("\n", "")
                    road_address_fi=road_address
                    road_address_fi=remove_duplicate_words(road_address_fi)
                    lon,lat=geocoding(road_address_fi)
                    print(f"도로명 재시도2, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                    if lat==0:
                        pattern = r"(\S+[로길])\s(\d+(-\d+)?)"
                        match = re.search(pattern, road_address_fi)
                        sleep(2)
                        if match:
                            road = match.group(1)  # "일현로"
                            number = match.group(2)  # "89" 또는 "89-2"
                            full = f"{road} {number}"
                            print("📍 도로명 주소:", full)
                            road_address_fi=full
                        else:
                            print("❌ 도로명 주소를 찾을 수 없습니다.")
                        lon,lat=geocoding(road_address_fi)
                        print(f"도로명 재시도3, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                        if lat==0:
                            road = addr1[1].text 
                            road_address = road[3:-2].replace("\n", "")
                            road_address_fi=addr0.text+" "+road_address
                            road_address_fi=remove_duplicate_words(road_address_fi)
                            lon,lat=geocoding(road_address_fi)
                            print(f"도로명 재시도4, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                            if lat==0:
                                road = addr1[1].text 
                                road_address = road[3:-2].replace("\n", "")
                                road_address_fi=road_address
                                road_address_fi=remove_duplicate_words(road_address_fi)
                                lon,lat=geocoding(road_address_fi)                             
                                print(f"도로명 재시도5, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                                # if lat==0:
                                #     store_name=key_word
                                #     road_address_fi=key_word
                                #     lat=geocoding(road_address_fi)[1]
                                #     lon=geocoding(road_address_fi)[0]                                
                                #     print(f"도로명 재시도6, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")
                
            # lat=geocoding(road_address_fi)[1]
            # lon=geocoding(road_address_fi)[0]
            # dict에 데이터 집어넣기
            dict_temp = {
                'name': store_name,
                'road_address': road_address_fi,
                'latitude' : lat,
                'longitude' : lon}
            store_dict['가게 정보'].append(dict_temp)
            # print(dict_temp)  
              
        except Exception as e:        
            # time_wait(5, 'iframe#entryIframe',driver)
            print("entryIframe")
            try:
                try:
                    print("entryIframe_CSS")
                    lon, lat = None, None
                    print("lon, lat 초기화")
                    switch_frame('entryIframe',driver) #entryIframe
                    sleep(2)                    
                    store_name=key_word
                    print("entryIframe",store_name)
                    # 주소 버튼 누르기
                    address_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.PkgBl') #vV_z_
                    address_buttons[0].click()
                    # 로딩 기다리기
                    sleep(2)       
                    # 주소 눌렀을 때 도로명, 지번 나오는 div
                    addr1 = driver.find_elements(By.CSS_SELECTOR, '.Y31Sf> div')
                    sleep(2)
                    road = addr1[0].text 
                    road_address = road[3:-2].replace("\n", "")
                    road_address_fi=road_address
                    print(road_address_fi)
                    lon,lat=geocoding(road_address_fi)                             
                    print(f"도로명 재시도1, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                    if lat==0:
                        pattern = r"(\S+[로길])\s(\d+(-\d+)?)"
                        match = re.search(pattern, road_address_fi)
                        sleep(2)
                        if match:
                            road = match.group(1)  # "일현로"
                            number = match.group(2)  # "89" 또는 "89-2"
                            full = f"{road} {number}"
                            print("📍 도로명 주소:", full)
                            road_address_fi=full
                        else:
                            print("❌ 도로명 주소를 찾을 수 없습니다.")
                        lon,lat=geocoding(road_address_fi)
                        print(f"도로명 재시도2, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                        if lat==0:
                            road = addr1[1].text 
                            road_address = road[2:-2].replace("\n", "")
                            road_address_fi=road_address
                            road_address_fi=remove_duplicate_words(road_address_fi)
                            lon,lat=geocoding(road_address_fi)
                            print(f"도로명 재시도3, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                            # if lat==0:
                            #     road_address_fi=key_word
                            #     lon,lat=geocoding(road_address_fi)
                            #     print(f"도로명 재시도4, 'title': '{store_name}', 'address':'{road_address_fi}', 'lat':'{lat}','lng':'{lon}'")

                    # dict에 데이터 집어넣기
                    dict_temp = {
                        'name': store_name,
                        'road_address': road_address_fi,
                        'latitude' : lat,
                        'longitude' : lon}
                    store_dict['가게 정보'].append(dict_temp)
                    
                except Exception as e: 
                    try:
                        print("entryIframe_Script")
                        scripts = driver.find_elements(By.TAG_NAME, 'script')
                        lon, lat = None, None
                        print("lon, lat 초기화")
                        for script in scripts:
                            inner = script.get_attribute("innerHTML")
                            print(inner)

                            if inner and '"lon":' in inner and '"lat":' in inner:
                                # 정규식으로 "lon":"126.7698144","lat":"37.6968808" 같은 패턴 찾기
                                match = re.search(r'"lon":"(.*?)","lat":"(.*?)"', inner) #'"lon"\s*:\s*([\d.]+)\s*,\s*"lat"\s*:\s*([\d.]+)'
                                sleep(2)
                                if match:
                                    lat = float(match.group(1))  # 경도
                                    lon = float(match.group(2))  # 위도
                                    break

                        if lon and lat:
                            print("📍 경도 (longitude):", lon)
                            print("📍 위도 (latitude):", lat)
                        else:
                            print("❌ 좌표를 찾을 수 없습니다.")
                            raise Exception("❌ 경도/위도를 찾지 못했습니다.")
                        # dict에 데이터 집어넣기
                        dict_temp = {
                            'name': store_name,
                            'road_address': road_address_fi,
                            'latitude' : lat,
                            'longitude' : lon}
                        store_dict['가게 정보'].append(dict_temp)  
                    
                    except Exception as e: 
                        print("searchIframe_Script")
                        time_wait(5, 'iframe#searchIframe',driver)
                        switch_frame('searchIframe',driver) #entryIframe
                        sleep(2)      
                        address_buttons = driver.find_element(By.CLASS_NAME, 'ApCpt').click() #ApCpt
                        sleep(2) 
                        driver.switch_to.default_content()
                        time_wait(5, 'iframe#entryIframe', driver)
                        switch_frame('entryIframe', driver)
                        sleep(2)
                        # url = driver.current_url
                        # print("현재 URL:", url)
                        scripts = driver.find_elements(By.TAG_NAME, 'script')
                        sleep(2)
                        lon, lat = None, None
                        print("lon, lat 초기화")

                        for script in scripts:
                            inner = script.get_attribute("innerHTML")
                            print(inner)

                            if inner and '"lon":' in inner and '"lat":' in inner:
                                # 정규식으로 "lon":"126.7698144","lat":"37.6968808" 같은 패턴 찾기
                                match = re.search(r'"lon":"(.*?)","lat":"(.*?)"', inner) #'"lon"\s*:\s*([\d.]+)\s*,\s*"lat"\s*:\s*([\d.]+)'
                                sleep(2)
                                if match:
                                    lat = float(match.group(1))  # 경도
                                    lon = float(match.group(2))  # 위도
                                    break

                        if lon and lat:
                            print("📍 경도 (longitude):", lon)
                            print("📍 위도 (latitude):", lat)
                        else:
                            print("❌ 좌표를 찾을 수 없습니다.")
                            raise Exception("❌ 경도/위도를 찾지 못했습니다.")
                        # dict에 데이터 집어넣기
                        dict_temp = {
                            'name': store_name,
                            'road_address': road_address_fi,
                            'latitude' : lat,
                            'longitude' : lon}
                        store_dict['가게 정보'].append(dict_temp)   
            except Exception as e:
                print(e)  

    except Exception as e:
        print(e)


    print('[데이터 수집 완료]\n소요 시간 :', time.time() - start)
    driver.quit()  # 작업이 끝나면 창을 닫는다.\
    return lat, lon

def remove_duplicate_words(address):
    words = address.split()
    result = []
    for word in words:
        if len(result) == 0 or word != result[-1]:
            result.append(word)
    return ' '.join(result)


def dismin(url):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))  #ChromeDriverManager().install()
        driver.get(url) 
        time_wait(5, 'div.route_summary_box > div.route_summary_info_duration',driver)
        dism1 = driver.find_element(By.CSS_SELECTOR, 'div.route_summary_box > div.route_summary_info_duration')
        sleep(5)
        dism1_text=dism1.text

        print(dism1_text)
        driver.quit()    
        return time_filter(dism1_text)
    except UnboundLocalError as e:
        print(e)

def time_filter(timetext):
    hours = re.search(r'(\d+)\s*시간', timetext)
    minutes = re.search(r'(\d+)\s*분', timetext)
    
    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    
    return h * 60 + m
    

df=DataFrame()
point_hist=DataFrame()
# point_list=["엘지디스플레이 파주공장","일산동양아파트101동","대윤프라자","탄7현큰마을대림아파트 일현로 140",
#             "광성교회","파리바게뜨 일산역점","탄현마을부영3단지아파트","일산에듀포레푸르지오아파트","SK엔크린 삼정셀프주유소"] #출근
point_list=["엘지디스플레이 파주공장","컴포즈커피 일산하이파크시티점","일산탄현쌍용스윗닷홈아파트정문","마라공방 일산탄현점",
            "대윤프라자","덕이동 318-9","메가MGC커피 일산한뫼초점","링키영어 탄현점","탄현마을한신6단지아파트입구","탄현청해수산"] #퇴근
df=DataFrame(index=point_list,columns=point_list)
point_hist=DataFrame(index=point_list,columns=["lat","lng"])

from itertools import combinations
result = list(combinations(point_list, 2))  # 2개씩 순서 없이 뽑기
print(result)

for k in result:
    key_word = list(k) #['대화마을 7단지','두산위브더제니스 일산'] # 검색어
    my_list=[]
    for i in key_word:
        print(i)

        if point_hist.loc[i,'lng']>=0:
            my_list.append(point_hist.loc[i,'lat'])
            my_list.append(point_hist.loc[i,'lng'])
            print(f'print(my_list):{my_list}')
        else:    
            ml=search_lnglat(i)
            point_hist.loc[i,'lat']=ml[0]
            point_hist.loc[i,'lng']=ml[1]
            print(f'point_hist:{point_hist},ml:{ml}')
            my_list.extend(ml)
            print(f'print(my_list):{my_list}')
        
        
    print(my_list)    
    url="https://map.naver.com/p/directions/"+str(my_list[0])+","+str(my_list[1])+","+quote(key_word[0])+",/"+str(my_list[2])+","+str(my_list[3])+","+quote(key_word[1])+",/-/car/0?c=11.00,0,0,0,dh"
    print(url)
    
    df.loc[key_word[0],key_word[1]]= dismin(url)
    df.to_csv("./거리산출결과_탄현_퇴근.csv")
    print(time.time()-start)   
    print(df)
    
print(geocoding("파리바게뜨 일산역점"))

df1=pd.read_csv("./거리산출결과_탄현_퇴근.csv" )
print(df1)
# df1=df1.drop(columns=['Unnamed: 0'])
df1=df1.set_index('Unnamed: 0')
print(df1)
print(df1.columns)

df1=df1[['엘지디스플레이 파주공장']+df1.loc['엘지디스플레이 파주공장'].dropna().sort_values(ascending=True).index.to_list()]
df1=df1.reindex(['엘지디스플레이 파주공장']+df1.loc['엘지디스플레이 파주공장'].dropna().sort_values(ascending=True).index.to_list())
print(df1)

point_cnt=6
from itertools import combinations
point_case = list(combinations(df1,point_cnt)) 
point_case1=[ i for i in point_case if i[0]=="엘지디스플레이 파주공장"]
print(point_case1)
       
    
df2=pd.DataFrame()
df2["경로"]=point_case1


for i in range(len(point_case1)):
    for k in range(point_cnt-1):
        # print(df1.loc[point_case1[i][k],point_case1[i][k+1]])
        if pd.isna(df1.loc[point_case1[i][k],point_case1[i][k+1]])==True:
            df2.loc[i,"시간"+str(k+1)]=df1.loc[point_case1[i][k+1],point_case1[i][k]]
        else:
            df2.loc[i,"시간"+str(k+1)]=df1.loc[point_case1[i][k],point_case1[i][k+1]]
print(df2)
df2=df2.dropna()
df2["시간합"]=df2["시간1"]+df2["시간2"]+df2["시간3"]+df2["시간4"]
df2=df2.sort_values(by="시간합").reset_index(drop=True)
print(df2)

df2["라벨"]=0
n=1
for i,j in zip(range(len(df2)-1),df2["경로"]):
    if df2.loc[i,"라벨"]==0:
        df2.loc[i,"라벨"]=n
        print("first")
        print(i,df2.loc[i,"경로"],n)

    for k in range(1,len(df2)):
        m=0
        # print(k)
        for l in range(point_cnt-1):
            if df2.iloc[k,0][l+1] in j:
                m+=1
        if m==0:
            if df2.loc[k,"라벨"]==0:
                df2.loc[k,"라벨"]=n
                print("against")
                print(i,k,df2.loc[k,"경로"],n)
                # n+=1
        elif k==len(df2)-1:
            n+=1
     
print(df2)

# 라벨별 평균 계산
avg_time = df2.groupby('라벨')['시간합'].mean()

# 평균값을 원래 데이터프레임에 매핑하여 새 컬럼 추가
df2['라벨별_평균시간'] = df2['라벨'].map(avg_time)
print(df2)
df2.to_excel("./정렬결과_탄현_퇴근.xlsx",index=False)



