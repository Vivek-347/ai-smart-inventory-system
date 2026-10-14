import mysql.connector

def getConnection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="inventory_ai"
    )
    return conn