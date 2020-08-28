# git push -u origin master

import pymysql

db = pymysql.connect(host="localhost", user="root", passwd="rnldhks0214",db='temp',charset='utf8')
              
cur =db.cursor()
        
#sql="create table woan2("\
#    "title varchar(100),"\
#    "content text,"\
#    "primary key(title))"

sql="delete from woan1"

cur.execute(sql)

db.commit()
