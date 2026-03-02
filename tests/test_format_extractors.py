"""Tests for XML and Parquet format extractors."""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.engine import TextExtractor


class TestXMLExtractor:
    """Tests for the XML text extractor."""

    def test_simple_xml(self, tmp_path):
        xml_content = """<?xml version="1.0"?>
<company>
    <name>Acme Corp</name>
    <founded>1990</founded>
</company>"""
        f = tmp_path / "test.xml"
        f.write_text(xml_content)
        result = TextExtractor.extract_text(str(f))
        assert "XML File:" in result
        assert "Acme Corp" in result
        assert "1990" in result

    def test_nested_xml(self, tmp_path):
        xml_content = """<?xml version="1.0"?>
<company>
    <department>
        <name>Sales</name>
        <employee>
            <name>John</name>
            <salary>50000</salary>
        </employee>
    </department>
</company>"""
        f = tmp_path / "nested.xml"
        f.write_text(xml_content)
        result = TextExtractor.extract_text(str(f))
        assert "Sales" in result
        assert "John" in result
        assert "50000" in result

    def test_xml_with_attributes(self, tmp_path):
        xml_content = """<?xml version="1.0"?>
<employees>
    <employee id="123" role="manager">
        <name>Alice</name>
    </employee>
</employees>"""
        f = tmp_path / "attrs.xml"
        f.write_text(xml_content)
        result = TextExtractor.extract_text(str(f))
        assert "123" in result
        assert "manager" in result
        assert "Alice" in result

    def test_xml_with_namespaces(self, tmp_path):
        xml_content = """<?xml version="1.0"?>
<root xmlns:ns="http://example.com/ns">
    <ns:item>value</ns:item>
</root>"""
        f = tmp_path / "ns.xml"
        f.write_text(xml_content)
        result = TextExtractor.extract_text(str(f))
        assert "item" in result
        assert "value" in result

    def test_xml_empty_elements(self, tmp_path):
        xml_content = """<?xml version="1.0"?>
<root>
    <empty/>
    <data>content</data>
</root>"""
        f = tmp_path / "empty.xml"
        f.write_text(xml_content)
        result = TextExtractor.extract_text(str(f))
        assert "content" in result

    def test_xml_cdata(self, tmp_path):
        xml_content = """<?xml version="1.0"?>
<root>
    <description><![CDATA[This is <bold>CDATA</bold> content]]></description>
</root>"""
        f = tmp_path / "cdata.xml"
        f.write_text(xml_content)
        result = TextExtractor.extract_text(str(f))
        assert "CDATA" in result

    def test_malformed_xml_raises(self, tmp_path):
        xml_content = "<root><unclosed>"
        f = tmp_path / "bad.xml"
        f.write_text(xml_content)
        with pytest.raises(Exception):
            TextExtractor.extract_text(str(f))


class TestParquetExtractor:
    """Tests for the Parquet text extractor."""

    @pytest.fixture(autouse=True)
    def check_pyarrow(self):
        pytest.importorskip("pyarrow")

    def test_small_parquet(self, tmp_path):
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({
            "name": ["Alice", "Bob", "Charlie"],
            "age": [30, 25, 35],
            "city": ["NYC", "SF", "LA"],
        })
        f = tmp_path / "test.parquet"
        pq.write_table(table, str(f))

        result = TextExtractor.extract_text(str(f))
        assert "Parquet File:" in result
        assert "Rows: 3" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "name" in result

    def test_parquet_schema(self, tmp_path):
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"x": [1, 2], "y": [3.14, 2.72]})
        f = tmp_path / "schema.parquet"
        pq.write_table(table, str(f))

        result = TextExtractor.extract_text(str(f))
        assert "Columns: x, y" in result

    def test_parquet_compression(self, tmp_path):
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"val": list(range(100))})
        f = tmp_path / "compressed.parquet"
        pq.write_table(table, str(f), compression="snappy")

        result = TextExtractor.extract_text(str(f))
        assert "Rows: 100" in result

    def test_unsupported_extension(self, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported file type"):
            TextExtractor.extract_text(str(f))
