import mysql.connector
import os

#Connect VSCode to MySQL Database.
def connect_database():
    try:
        connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
        )

        if connection.is_connected():
            print("✅ Database connected!")

        return connection

    except mysql.connector.Error as err:
        print(f"❌ Database failed to connect: {err}")
        return None
    
#Create Profile for User. (IGNORE if user already has a profile.)
def create_profile(user):
    db = connect_database()
    cursor = db.cursor()

    sql = """
    INSERT IGNORE INTO users
    (user_id, username, display_name, avatar_url)
    VALUES (%s, %s, %s, %s);
    """

    values = (
        user.id,
        user.name,
        user.display_name,
        user.display_avatar.url
    )

    cursor.execute(sql, values)
    db.commit()

    cursor.close()
    db.close()