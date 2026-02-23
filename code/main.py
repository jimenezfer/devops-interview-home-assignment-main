from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncpg
import redis.asyncio as redis
import json
import os
import asyncio

COMPANY_NAME = os.getenv("COMPANY_NAME", "My Company")

app = FastAPI(
    title=f"{COMPANY_NAME} API",
    description=f"API for {COMPANY_NAME}",
    version="1.0.0",
)


# Database connections
db_pool = None
redis_client = None

CACHE_TTL = 60  # seconds


# Models
class UserCreate(BaseModel):
    name: str
    email: str


# Startup/Shutdown
async def _wait_for_postgres(max_attempts=30, delay=1):
    for attempt in range(max_attempts):
        try:
            return await asyncpg.create_pool(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                database=os.getenv("POSTGRES_DB", "mydb"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            )
        except (ConnectionRefusedError, asyncpg.PostgresConnectionError, OSError):
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(delay)


@app.on_event("startup")
async def startup():
    global db_pool, redis_client
    db_pool = await _wait_for_postgres()
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


@app.on_event("shutdown")
async def shutdown():
    await db_pool.close()
    await redis_client.close()


# User endpoints
@app.post("/users")
async def create_user(user: UserCreate):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id, name, email",
            user.name, user.email
        )
    return dict(row)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # TODO: Implement this, use cache if available
    return {}

@app.get("/users")
async def list_users():
    # TODO: Implement this, use cache if available
    return []

# Run with: uvicorn main:app --reload