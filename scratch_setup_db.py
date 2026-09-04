import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect(host="127.0.0.1", port=5434, user="postgres", database="postgres")
    try:
        await conn.execute("DROP DATABASE IF EXISTS freightcore WITH (FORCE);")
        await conn.execute("CREATE DATABASE freightcore OWNER freightcore;")
        print("Database freightcore recreated successfully.")
    except Exception as e:
        print("DB Reset Error:", e)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
