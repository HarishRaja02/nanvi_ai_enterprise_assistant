import psycopg

try:
    conn = psycopg.connect("postgresql://postgres:admin@localhost:5432/nanvi")
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = cur.fetchall()
    print("Tables in nanvi:", tables)
    for (t,) in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"  {t}: {cnt} rows")
    conn.close()
except Exception as e:
    print("Error:", e)
