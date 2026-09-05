import psycopg2
conn=psycopg2.connect('postgresql://postgres:hijal@localhost:5432/freightcore')
cur=conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
tables=cur.fetchall()
print([t[0] for t in tables])
conn.close()
