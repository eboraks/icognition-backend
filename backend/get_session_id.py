import asyncio
import os
import sys

# Add the current directory to sys.path to allow imports
sys.path.append(os.getcwd())

from app.db.database import async_session
from app.models import ChatSession
from sqlalchemy import select

async def run():
    async with async_session() as s:
        stmt = select(ChatSession.id).order_by(ChatSession.id.desc()).limit(1)
        r = await s.execute(stmt)
        session_id = r.scalar_one_or_none()
        if session_id:
            print(f"SESSION_ID={session_id}")
        else:
            print("No sessions found.")

if __name__ == "__main__":
    asyncio.run(run())
