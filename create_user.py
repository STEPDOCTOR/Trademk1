#!/usr/bin/env python3
"""Create a test user for autonomous trading."""
import asyncio
from uuid import uuid4
from sqlalchemy import select
from app.db.postgres import init_postgres, close_postgres
from app.db.optimized_postgres import optimized_db
from app.models.user import User
from app.auth.security import get_password_hash

async def create_user():
    """Create a test user."""
    await init_postgres()
    
    async with optimized_db.get_session() as db:
        # Check if user exists
        result = await db.execute(
            select(User).where(User.email == "trader@example.com")
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"User already exists: {existing.email}")
        else:
            # Create user
            user = User(
                id=uuid4(),
                email="trader@example.com",
                hashed_password=get_password_hash("SecurePass123"),
                full_name="Auto Trader",
                is_active=True,
                is_superuser=False,
                is_verified=True
            )
            db.add(user)
            await db.commit()
            print(f"Created user: {user.email}")
    
    await close_postgres()

if __name__ == "__main__":
    asyncio.run(create_user())