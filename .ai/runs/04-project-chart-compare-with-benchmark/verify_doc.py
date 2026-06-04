import sys
from zipfile import ZipFile, is_zipfile

path = ".ai/docs/04-project-chart-compare-with-benchmark_명세서.docx"

try:
    assert is_zipfile(path), "File is not a valid zip file"
    with ZipFile(path) as zf:
        names = set(zf.namelist())
        assert "[Content_Types].xml" in names, "[Content_Types].xml not found in zip"
        assert "word/document.xml" in names, "word/document.xml not found in zip"
        
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        
        assert xml.strip(), "Document XML content is empty"
        
        tbl_count = xml.count("<w:tbl>")
        assert tbl_count >= 2, f"Expected at least 2 tables, found {tbl_count}"
        
        h1_count = xml.count('w:val="Heading1"')
        assert h1_count >= 7, f"Expected at least 7 Heading 1 sections, found {h1_count}"
        
        forbidden_placeholders = [
            "[내용]", "04-project-chart-compare-with-benchmark", "src/path/to/file.py", "tests/test_xxx.py", "패키지명"
        ]
        
        found_placeholders = [token for token in forbidden_placeholders if token in xml]
        assert not found_placeholders, f"Forbidden placeholders found: {found_placeholders}"
        
    print(f"VERIFICATION SUCCESSFUL: {path}")
    print(f"Tables count: {tbl_count}")
    print(f"Heading 1 count: {h1_count}")
    sys.exit(0)
except AssertionError as e:
    print(f"VERIFICATION FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"UNEXPECTED ERROR: {e}")
    sys.exit(2)
