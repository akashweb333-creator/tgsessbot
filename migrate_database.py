"""
Comprehensive Database Migration Script
Ensures all columns exist in the database tables
"""

import sys
import os

# Add the parent directory to the path
sys.path.insert(0, '/mnt/user-data/uploads')

from sqlalchemy import create_engine, text, inspect, MetaData
import config
from database import Base

def migrate_database():
    """Migrate database to latest schema"""
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    inspector = inspect(engine)
    
    print("=" * 70)
    print("DATABASE MIGRATION TOOL")
    print("=" * 70)
    print(f"\nDatabase URL: {config.DATABASE_URL}")
    print(f"Checking tables and columns...\n")
    
    # Get all table names
    existing_tables = inspector.get_table_names()
    print(f"Existing tables: {existing_tables}\n")
    
    # Check sessions table
    if 'sessions' in existing_tables:
        print("Checking 'sessions' table...")
        columns = {col['name']: col for col in inspector.get_columns('sessions')}
        print(f"  Current columns: {list(columns.keys())}")
        
        required_columns = {
            'country': "VARCHAR(50) DEFAULT 'Other'",
            'has_2fa': "BOOLEAN DEFAULT FALSE",
            'two_fa_password': "VARCHAR(255)",
            'is_sold': "BOOLEAN DEFAULT FALSE",
            'buyer_id': "INTEGER",
            'price': "FLOAT DEFAULT 1.0",
            'sold_at': "TIMESTAMP"
        }
        
        with engine.connect() as conn:
            for col_name, col_def in required_columns.items():
                if col_name not in columns:
                    print(f"  ❌ Missing column: {col_name}")
                    print(f"     Adding {col_name}...")
                    try:
                        # Different syntax for different databases
                        if config.DATABASE_URL.startswith('postgresql'):
                            conn.execute(text(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_def}"))
                        else:  # SQLite
                            # SQLite doesn't support DEFAULT in ALTER TABLE, so we split it
                            col_type = col_def.split(' DEFAULT ')[0]
                            conn.execute(text(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        print(f"     ✅ Added {col_name}")
                    except Exception as e:
                        print(f"     ❌ Error adding {col_name}: {e}")
                        conn.rollback()
                else:
                    print(f"  ✅ {col_name} exists")
        
        print()
    else:
        print("⚠️  'sessions' table doesn't exist. Creating all tables...")
        Base.metadata.create_all(engine)
        print("✅ All tables created!")
        return True
    
    # Verify final state
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    
    for table in ['users', 'transactions', 'sessions', 'purchases']:
        if table in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns(table)]
            print(f"\n{table}:")
            print(f"  Columns: {', '.join(columns)}")
    
    print("\n" + "=" * 70)
    print("✅ MIGRATION COMPLETED!")
    print("=" * 70)
    print("\nYour database is now up to date. You can restart your bot.")
    
    return True

if __name__ == "__main__":
    try:
        migrate_database()
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ MIGRATION FAILED!")
        print("=" * 70)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()