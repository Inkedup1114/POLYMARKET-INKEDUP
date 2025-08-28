"""Debug connection pool issues."""

import asyncio

from inkedup_bot.connection_pool import ConnectionPoolManager


async def debug_pool():
    """Debug connection pool creation and basic operations."""
    print("Creating SQLite connection pool...")

    pool = ConnectionPoolManager.create_pool(":memory:", pool_size=2)
    print(f"Pool created: {type(pool).__name__}")

    print("Initializing pool...")
    await pool.initialize()
    print("Pool initialized")

    print("Testing connection acquisition...")
    async with pool.acquire_connection() as conn:
        print(f"Connection acquired: {type(conn)}")

        # Test simple query
        print("Running test query...")
        async with conn.execute("SELECT 1") as cursor:
            result = await cursor.fetchone()
            print(f"Query result: {result}")

    print("Connection released")

    print("Getting pool status...")
    status = await pool.get_pool_status()
    print(f"Pool status: {status}")

    print("Closing pool...")
    await pool.close()
    print("Pool closed successfully")


if __name__ == "__main__":
    asyncio.run(debug_pool())
