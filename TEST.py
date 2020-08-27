# git push -u origin master

#import MySQLdb
import mysql.connector

def save_record(title, article, date, writer, cnt):
        # Open database connection
        db = mysql.connector.connect(host="localhost", user="root", passwd="rnldhs0214",db="test_mysql")
        db.set_character_set('utf8')
        # Prepare a cursor object using cursor( method
        cursor =db.cursor()
        # # Prepare SQL query to INSERT a record into the database
        sql= "INSERT INTO document(title, article, wdate, writer, vcnt)\ VALUES (%s, %s, %s, %s, %s)" %("'"+title+"'","'"+article+"'","'"+date+"'","'"+writer+"'", "'"+cnt+"'")
        try:
            #Execute the SQL command
            cursor.execute(sql)

            #Commit changes in the database
            db.commit()
            # cursor.execute("""SELECI title, article, date, writer, vcnt FROM document""")
            # print (cursor.fetchall())
        except Exception as e:
            print(str(e))
            # Rollback in case there is any error******
            db.rollback()
            # Disconnect from database
        db.close()