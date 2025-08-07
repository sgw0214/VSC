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

    sleep(5)

    # frame 변경
    time_wait(10, 'iframe#searchIframe',driver)
    switch_frame('searchIframe',driver)

    sleep(5)

    #page_down(40,driver)
    #sleep(5)

    # 가게 리스트
    store_list = driver.find_elements(By.CSS_SELECTOR, 'li.VLTHu')
    
    # 페이지 리스트
    next_btn = driver.find_elements(By.CSS_SELECTOR, '.zRM9F> a')

    # dictionary 생성
    store_dict = {'가게 정보': []}
    
    # 시작시간
    
    print('[크롤링 시작...]')
    
    # driver.switch_to.default_content()
    # time_wait(driver, 10, 'iframe#entryIframe')
    # driver.switch_to.frame('entryIframe')
    # time.sleep(3)

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
                addr0 = driver.find_element(By.CSS_SELECTOR, "span.Pb4bU")
                sleep(2)
                
                addr = driver.find_elements(By.CSS_SELECTOR, '.AbTyi> div')
                sleep(2)
                
                # 도로명            
                road = addr[0].text 
                road_address = road[3:-2].replace("\n", "")
                road_address_fi=addr0.text+" "+road_address
                print(road_address_fi)
                sleep(2)
                print({'id':data, 'title': store_name, 'address':road_address_fi, 'lat':geocoding(road_address_fi)[0],'lng':geocoding(road_address_fi)[1]})
                if geocoding(road_address_fi)[0]==0:
                    road = addr[1].text 
                    road_address = road[3:-2].replace("\n", "")
                    road_address_fi=addr0.text+" "+road_address
                    road_address_fi=remove_duplicate_words(road_address_fi)
                    print(f"도로명 재시도1,'id':{data}, 'title': {store_name}, 'address':{road_address_fi}, 'lat':{geocoding(road_address_fi)[0]},'lng':{geocoding(road_address_fi)[1]}")
                    if geocoding(road_address_fi)[0]==0:
                        store_name=key_word
                        road_address_fi=key_word
                        print(f"도로명 재시도2,'id':{data}, 'title': {store_name}, 'address':{road_address_fi}, 'lat':{geocoding(road_address_fi)[0]},'lng':{geocoding(road_address_fi)[1]}")
                        # if geocoding(road_address_fi)[0]==0:
                            
                        
                # dict에 데이터 집어넣기
                dict_temp = {
                    'name': store_name,
                    'road_address': road_address_fi,
                    'latitude' : geocoding(road_address_fi)[0],
                    'longitude' : geocoding(road_address_fi)[1]}
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
    return geocoding(road_address_fi)[1], geocoding(road_address_fi)[0]

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
        time_wait(10, 'div.route_summary_box > div.route_summary_info_duration',driver)
        dism1 = driver.find_element(By.CSS_SELECTOR, 'div.route_summary_box > div.route_summary_info_duration')
        sleep(10)
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
point_list=["탄현마을부영3단지아파트","일산동양아파트101동","대윤프라자","탄현큰마을대림아파트 일현로 140","광성교회","리드인 독서논술 일산","일산에듀포레푸르지오아파트","SK엔크린 삼정셀프주유소"]
# point_list=["엘지디스플레이 파주공장","일산동양아파트101동","대윤프라자","탄현큰마을대림아파트 일현로 140","광성교회","리드인 독서논술 일산","탄현마을부영3단지아파트","일산에듀포레푸르지오아파트","SK엔크린 삼정셀프주유소"]
df=DataFrame(index=point_list,columns=point_list)
point_hist=DataFrame(index=point_list,columns=["lng","lat"])

from itertools import combinations
result = list(combinations(point_list, 2))  # 2개씩 순서 없이 뽑기
print(result)

for k in result:
    key_word = list(k) #['대화마을 7단지','두산위브더제니스 일산'] # 검색어
    my_list=[]
    for i in key_word:
        print(i)

        if point_hist.loc[i,'lng']>=0:
            my_list.append(point_hist.loc[i,'lng'])
            my_list.append(point_hist.loc[i,'lat'])
            print(f'print(my_list):{my_list}')
        else:    
            ml=search_lnglat(i)
            point_hist.loc[i,'lng']=ml[0]
            point_hist.loc[i,'lat']=ml[1]
            print(f'point_hist:{point_hist},ml:{ml}')
            my_list.extend(ml)
            print(f'print(my_list):{my_list}')
        
        
    print(my_list)    
    url="https://map.naver.com/p/directions/"+str(my_list[0])+","+str(my_list[1])+","+quote(key_word[0])+",/"+str(my_list[2])+","+str(my_list[3])+","+quote(key_word[1])+",/-/car/0?c=11.00,0,0,0,dh"
    print(url)
    
    df.loc[key_word[0],key_word[1]]= dismin(url)
    print(time.time()-start)   
    print(df)

    




