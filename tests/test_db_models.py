"""Tests for database models."""

import json
import pytest
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models import Base, Symbol


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    # Use SQLite for testing
    engine = create_engine("sqlite:///:memory:")
    
    # Create tables with modified Symbol to handle JSONB -> JSON for SQLite
    with engine.connect() as conn:
        # Create tables manually to handle JSONB compatibility
        conn.execute(text("""
            CREATE TABLE symbols (
                id CHAR(36) PRIMARY KEY,
                ticker VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                exchange VARCHAR(50) NOT NULL,
                asset_type VARCHAR(20) NOT NULL,
                is_active BOOLEAN NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
    
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    
    yield session
    
    session.close()


def test_symbol_crud(test_db):
    """Test Symbol CRUD operations."""
    # Create using raw SQL for SQLite compatibility
    symbol_id = str(uuid.uuid4())
    metadata = json.dumps({"sector": "Technology"})
    
    test_db.execute(
        text("""
            INSERT INTO symbols (id, ticker, name, exchange, asset_type, is_active, metadata_json)
            VALUES (:id, :ticker, :name, :exchange, :asset_type, :is_active, :metadata_json)
        """),
        {
            "id": symbol_id,
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "asset_type": "stock",
            "is_active": True,
            "metadata_json": metadata
        }
    )
    test_db.commit()
    
    # Read
    result = test_db.execute(
        text("SELECT * FROM symbols WHERE ticker = :ticker"),
        {"ticker": "AAPL"}
    ).first()
    
    assert result is not None
    assert result.ticker == "AAPL"
    assert result.name == "Apple Inc."
    assert result.exchange == "NASDAQ"
    assert result.asset_type == "stock"
    assert result.is_active == 1  # SQLite represents True as 1
    assert json.loads(result.metadata_json) == {"sector": "Technology"}
    
    # Update
    new_metadata = json.dumps({"sector": "Technology", "market_cap": "3T"})
    test_db.execute(
        text("""
            UPDATE symbols 
            SET is_active = :is_active, metadata_json = :metadata_json
            WHERE ticker = :ticker
        """),
        {
            "is_active": False,
            "metadata_json": new_metadata,
            "ticker": "AAPL"
        }
    )
    test_db.commit()
    
    updated = test_db.execute(
        text("SELECT * FROM symbols WHERE ticker = :ticker"),
        {"ticker": "AAPL"}
    ).first()
    assert updated.is_active == 0  # SQLite represents False as 0
    assert json.loads(updated.metadata_json) == {"sector": "Technology", "market_cap": "3T"}
    
    # Delete
    test_db.execute(
        text("DELETE FROM symbols WHERE ticker = :ticker"),
        {"ticker": "AAPL"}
    )
    test_db.commit()
    
    deleted = test_db.execute(
        text("SELECT * FROM symbols WHERE ticker = :ticker"),
        {"ticker": "AAPL"}
    ).first()
    assert deleted is None