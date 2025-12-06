"""Tests for JSON, XML, and YAML document parsers.

Mission B13.9: Format Support - JSON, XML, YAML
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.document_parser import DocumentParser


class TestJSONParser:
    """Test suite for JSON file parsing."""

    def test_parse_simple_json_object(self, tmp_path: Path) -> None:
        """Parse simple JSON object."""
        file_path = tmp_path / "test.json"
        content = '{"name": "Test", "value": 42}'
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert '"name": "Test"' in result
        assert '"value": 42' in result

    def test_parse_json_array(self, tmp_path: Path) -> None:
        """Parse JSON array of objects."""
        file_path = tmp_path / "test.json"
        content = '[{"id": 1, "name": "first"}, {"id": 2, "name": "second"}]'
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert '"id": 1' in result
        assert '"name": "first"' in result
        assert '"id": 2' in result

    def test_parse_nested_json(self, tmp_path: Path) -> None:
        """Parse deeply nested JSON structure."""
        file_path = tmp_path / "test.json"
        content = '{"config": {"database": {"host": "localhost", "port": 5432}}}'
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert '"host": "localhost"' in result
        assert '"port": 5432' in result

    def test_parse_json_unicode(self, tmp_path: Path) -> None:
        """Parse JSON with unicode characters."""
        file_path = tmp_path / "test.json"
        content = '{"greeting": "Hello, 世界!", "emoji": "🎉"}'
        file_path.write_text(content, encoding="utf-8")

        result = DocumentParser.parse(file_path)

        assert "世界" in result
        assert "🎉" in result

    def test_parse_invalid_json_returns_error(self, tmp_path: Path) -> None:
        """Invalid JSON returns error message with original content."""
        file_path = tmp_path / "test.json"
        content = '{"broken": invalid}'
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "[JSON Parse Error:" in result
        assert '{"broken": invalid}' in result


class TestXMLParser:
    """Test suite for XML file parsing."""

    def test_parse_simple_xml(self, tmp_path: Path) -> None:
        """Parse simple XML document."""
        file_path = tmp_path / "test.xml"
        content = '<?xml version="1.0"?><root><item>Hello</item></root>'
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "<root>" in result
        assert "Hello" in result

    def test_parse_nested_xml(self, tmp_path: Path) -> None:
        """Parse nested XML structure."""
        file_path = tmp_path / "test.xml"
        content = """<?xml version="1.0"?>
<config>
    <database>
        <host>localhost</host>
        <port>5432</port>
    </database>
</config>"""
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "<config>" in result
        assert "<database>" in result
        assert "localhost" in result
        assert "5432" in result

    def test_parse_xml_with_attributes(self, tmp_path: Path) -> None:
        """Parse XML with element attributes."""
        file_path = tmp_path / "test.xml"
        content = '<items><item id="1">First</item><item id="2">Second</item></items>'
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "First" in result
        assert "Second" in result

    def test_parse_xml_with_namespace(self, tmp_path: Path) -> None:
        """Parse XML with namespace prefix."""
        file_path = tmp_path / "test.xml"
        content = '<root xmlns:ns="http://example.com"><ns:item>Data</ns:item></root>'
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "Data" in result

    def test_parse_invalid_xml_returns_error(self, tmp_path: Path) -> None:
        """Invalid XML returns error message with original content."""
        file_path = tmp_path / "test.xml"
        content = "<root><unclosed>"
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "[XML Parse Error:" in result
        assert "<root><unclosed>" in result


class TestYAMLParser:
    """Test suite for YAML file parsing."""

    def test_parse_simple_yaml(self, tmp_path: Path) -> None:
        """Parse simple YAML document."""
        file_path = tmp_path / "test.yaml"
        content = "name: Test\nvalue: 42"
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "name:" in result
        assert "Test" in result
        assert "42" in result

    def test_parse_yaml_with_yml_extension(self, tmp_path: Path) -> None:
        """Parse YAML file with .yml extension."""
        file_path = tmp_path / "test.yml"
        content = "config:\n  debug: true"
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "config:" in result
        assert "debug:" in result

    def test_parse_nested_yaml(self, tmp_path: Path) -> None:
        """Parse deeply nested YAML structure."""
        file_path = tmp_path / "test.yaml"
        content = """database:
  host: localhost
  port: 5432
  credentials:
    user: admin
    password: secret
"""
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "database:" in result
        assert "localhost" in result
        assert "5432" in result
        assert "admin" in result

    def test_parse_yaml_list(self, tmp_path: Path) -> None:
        """Parse YAML with list/array syntax."""
        file_path = tmp_path / "test.yaml"
        content = """items:
  - name: first
    value: 1
  - name: second
    value: 2
"""
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "items:" in result
        assert "first" in result
        assert "second" in result

    def test_parse_multi_document_yaml(self, tmp_path: Path) -> None:
        """Parse multi-document YAML file."""
        file_path = tmp_path / "test.yaml"
        content = """---
doc: first
---
doc: second
"""
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "Document 1" in result
        assert "Document 2" in result
        assert "first" in result
        assert "second" in result

    def test_parse_yaml_unicode(self, tmp_path: Path) -> None:
        """Parse YAML with unicode characters."""
        file_path = tmp_path / "test.yaml"
        content = 'greeting: "Hello, 世界!"\nemoji: "🎉"'
        file_path.write_text(content, encoding="utf-8")

        result = DocumentParser.parse(file_path)

        assert "世界" in result
        assert "🎉" in result

    def test_parse_invalid_yaml_returns_error(self, tmp_path: Path) -> None:
        """Invalid YAML returns error message with original content."""
        file_path = tmp_path / "test.yaml"
        content = "broken:\n  - item\n bad indent"
        file_path.write_text(content)

        result = DocumentParser.parse(file_path)

        assert "[YAML Parse Error:" in result
        assert "broken:" in result


class TestFormatSupport:
    """Test suite for format detection."""

    @pytest.mark.parametrize(
        "extension,expected",
        [
            (".json", True),
            (".xml", True),
            (".yaml", True),
            (".yml", True),
            (".pdf", True),
            (".docx", True),
            (".unknown", False),
            (".exe", False),
        ],
    )
    def test_is_format_supported(self, extension: str, expected: bool, tmp_path: Path) -> None:
        """Check format support detection."""
        file_path = tmp_path / f"test{extension}"
        assert DocumentParser.is_format_supported(file_path) == expected

    def test_is_format_supported_with_none(self) -> None:
        """Check None path returns False."""
        assert DocumentParser.is_format_supported(None) is False
