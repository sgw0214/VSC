# git push -u origin master

#import mysqldb
#import mysql.connector
import pymysql

#def save_record(title, article, date, writer, cnt):
        # Open database connection
db = pymysql.connect(host="localhost:3306", user="root", passwd="rnldhks0214",db='temp',charset='utf8')
        #db.set_character_set('utf8')
        # Prepare a cursor object using cursor( method
cur =db.cursor()
        # # Prepare SQL query to INSERT a record into the database
        #sql= "INSERT INTO document(title, article, wdate, writer, vcnt)\ VALUES (%s, %s, %s, %s, %s)" %("'"+title+"'","'"+article+"'","'"+date+"'","'"+writer+"'", "'"+cnt+"'")
sql="create table woan("\
    "title varchar(100),"\
    "content text,"\
    "primary key(title))"
            #try:
            #Execute the SQL command
cur.execute(sql)

            #Commit changes in the database
db.commit()
            # cursor.execute("""SELECI title, article, date, writer, vcnt FROM document""")
            # print (cursor.fetchall())
        #except Exception as e:
        #    print(str(e))
            # Rollback in case there is any error******
        #    db.rollback()
            # Disconnect from database
db.close()