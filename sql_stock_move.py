import pandas as pd
from openpyxl import load_workbook
from openpyxl import Workbook
import openpyxl
import pymysql

import tkinter
from tkinter import filedialog




# data=pd.read_excel('E:\\VSC\\CODE\\Stock\\basic_20150101.xlsx',engine='openpyxl')
# print(data)


def main(data,name):

    # targetFile = openpyxl.load_workbook(openFile(), data_only=True)

    # targetSheet = data#['Sheet1']
    # print("작업을 수행할 시트 :", targetSheet.title)

    connectDB = pymysql.connect(user='root',password='sgw0214',host='localhost', database='new_schema', charset='utf8', port=3306)# 
    cur = connectDB.cursor()

    # 데이터베이스에 테이블이 없으면 생성
    columns = ", ".join([f"`{col}` VARCHAR(255)" for col in data.columns])
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS `{name}` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        {columns}
    )
    """
    cur.execute(create_table_query)

    # 데이터 삽입 쿼리 준비
    insert_query = f"""
    INSERT INTO `{name}` ({', '.join(data.columns)})
    VALUES ({', '.join(['%s'] * len(data.columns))})
    """

    # 데이터 삽입
    for i, row in data.iterrows():
        cur.execute(insert_query, tuple(row))          

    # 변경 사항 저장
    connectDB.commit()

    # 커서 및 데이터베이스 연결 종료
    cur.close()
    connectDB.close()
    
    # for i in range(1, 101, 1):
    #     1


# if __name__ == "__main__":

#     main()

path = 'E:/VSC/CODE/Stock/'
path1 = 'E:/VSC/CODE/Stock/csv/'

# for year in range(2024, 2025):
#         for month in range(9,13):
#             for day in range(1, 32):
#                 tdate = year * 10000 + month * 100 + day * 1
#                 print(year,month,day)
#                 # 엑셀 파일 경로를 지정
#                 data = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
#                 # csv로 변환한 후 파일명과 저장 경로 지정
#                 data.to_csv(path1 + 'basic_' + str(tdate) + '.csv', index=None, header=True ,encoding='cp949')
#                 data = data.fillna('')
#                 main(data,'basic_' + str(tdate))
#                 print('Success')
                
                
for year in range(2015, 2024):

    print(year)
    # 엑셀 파일 경로를 지정
    data = pd.read_excel(path + str(year) + '.xlsx')
    # csv로 변환한 후 파일명과 저장 경로 지정
    data.to_csv(path1 + str(year) + '.csv', index=None, header=True ,encoding='cp949')
    data = data.fillna('')
    main(data,"T_"+str(year))
    print('Success')



                # try:
                #     print(year,month,day)
                #     # 엑셀 파일 경로를 지정
                #     data = pd.read_excel(path + 'basic_' + str(tdate) + '.xlsx')
                #     # csv로 변환한 후 파일명과 저장 경로 지정
                #     data.to_csv(path1 + 'basic_' + str(tdate) + '.csv', index=None, header=True ,encoding='cp949')
                #     print('Success')
                #     main(data)
                # except:
                #     print('Pass')
