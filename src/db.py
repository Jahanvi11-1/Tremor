"""
FalkorDB connection module for Tremor.
Establishes connection and provides graph interface.
"""

import os
from dotenv import load_dotenv
from falkordb import FalkorDB

# Load environment variables
load_dotenv()

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_GRAPH = os.getenv("FALKORDB_GRAPH", "tremor")


def get_connection():
    """
    Get FalkorDB connection.
    
    Returns:
        FalkorDB: Connected database instance
    """
    db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    return db


def get_graph(db=None):
    """
    Get or create the Tremor graph.
    
    Args:
        db: Optional existing FalkorDB connection
        
    Returns:
        Graph: The Tremor graph instance
    """
    if db is None:
        db = get_connection()
    
    graph = db.select_graph(FALKORDB_GRAPH)
    return graph


def test_connection():
    """
    Test FalkorDB connection and print diagnostics.
    """
    print("Connecting to FalkorDB...")
    print(f"  Host: {FALKORDB_HOST}")
    print(f"  Port: {FALKORDB_PORT}")
    print(f"  Graph: {FALKORDB_GRAPH}")
    print()
    
    try:
        # Connect
        db = get_connection()
        print("✓ Connected to FalkorDB")
        
        # Get graph
        graph = get_graph(db)
        print(f"✓ Graph '{FALKORDB_GRAPH}' ready")
        
        # Test query
        result = graph.query("RETURN 1 AS test")
        test_value = result.result_set[0][0]
        
        if test_value == 1:
            print("✓ Test query successful")
        else:
            print(f"✗ Test query returned unexpected value: {test_value}")
        
        print()
        print("FalkorDB connection verified!")
        
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        raise


if __name__ == "__main__":
    test_connection()
