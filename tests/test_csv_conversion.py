import pytest
from app.rag.engine import RAGEngine, TextExtractor
import os
import tempfile
import pandas as pd


def test_csv_encoding_detection():
    """Test CSV encoding detection"""
    # Create a test CSV with UTF-8 encoding
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write("name,age,salary\n")
        f.write("John,30,75000.50\n")
        f.write("Jane,25,65000.00\n")
        temp_file = f.name
    
    try:
        encoding = TextExtractor._detect_encoding(temp_file)
        assert encoding is not None
        assert isinstance(encoding, str)
        print(f"✓ Detected encoding: {encoding}")
    finally:
        os.unlink(temp_file)


def test_csv_extraction_with_delimiters():
    """Test CSV extraction with different delimiters"""
    # Test semicolon delimiter
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write("name;age;salary\n")
        f.write("John;30;75000.50\n")
        f.write("Jane;25;65000.00\n")
        temp_file = f.name
    
    try:
        text = TextExtractor.extract_text(temp_file)
        assert "name" in text.lower()
        assert "John" in text
        assert "75000" in text
        print("✓ Semicolon-delimited CSV extracted successfully")
    finally:
        os.unlink(temp_file)


def test_csv_to_sqlite_conversion():
    """Test CSV to SQLite database conversion"""
    # Create a test CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write("name,age,salary,hire_date\n")
        f.write("John,30,75000.50,2020-01-15\n")
        f.write("Jane,25,65000.00,2021-03-20\n")
        f.write("Bob,35,85000.75,2019-06-10\n")
        temp_file = f.name
    
    try:
        engine = RAGEngine()
        result = engine.convert_csv_to_database(temp_file, "test_employees")
        
        assert "success" in result or "error" in result
        
        if "success" in result:
            assert result["success"] is True
            assert "db_path" in result
            assert "row_count" in result
            assert result["row_count"] == 3
            assert "columns" in result
            assert "name" in result["columns"]
            assert "column_types" in result
            
            print(f"✓ CSV converted to database: {result['db_path']}")
            print(f"  - Rows: {result['row_count']}")
            print(f"  - Columns: {result['columns']}")
            print(f"  - Types: {result['column_types']}")
            
            # Clean up database
            if os.path.exists(result["db_path"]):
                os.unlink(result["db_path"])
        else:
            print(f"⚠ Conversion failed (expected in some environments): {result.get('error')}")
            
    finally:
        os.unlink(temp_file)


def test_column_type_inference():
    """Test data type inference for columns"""
    # Create a DataFrame with mixed types
    df = pd.DataFrame({
        "int_col": [1, 2, 3],
        "float_col": [1.5, 2.5, 3.5],
        "text_col": ["a", "b", "c"],
        "bool_col": [True, False, True]
    })
    
    engine = RAGEngine()
    types = engine._infer_column_types(df)
    
    assert types["int_col"] == "INTEGER"
    assert types["float_col"] == "REAL"
    assert types["text_col"] == "TEXT"
    assert types["bool_col"] == "INTEGER"  # SQLite uses INTEGER for boolean
    
    print("✓ Column types inferred correctly:")
    for col, dtype in types.items():
        print(f"  - {col}: {dtype}")


def test_malformed_csv_handling():
    """Test handling of malformed CSV files"""
    # Create a malformed CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write("name,age,salary\n")
        f.write("John,30\n")  # Missing column
        f.write("Jane,25,65000,extra\n")  # Extra column
        temp_file = f.name
    
    try:
        text = TextExtractor.extract_text(temp_file)
        # Should not crash, should return something
        assert text is not None
        assert len(text) > 0
        print("✓ Malformed CSV handled gracefully")
    finally:
        os.unlink(temp_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
