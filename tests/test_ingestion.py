from pathlib import Path
import unittest

from irkrs.ingestion import (
    PythonChunker,
    PythonParser,
    RepositoryDiscovery,
    SymbolExtractor,
)


class IngestionTests(unittest.TestCase):
    def test_repository_discovery_finds_python_files(self) -> None:
        repo_root = Path("examples/sample_repo")

        entries = RepositoryDiscovery(repo_root).discover()

        self.assertEqual([entry.path for entry in entries], ["auth.py"])
        self.assertEqual(entries[0].language, "python")
        self.assertGreater(entries[0].size_bytes, 0)

    def test_parser_and_symbol_extractor(self) -> None:
        parser = PythonParser()
        parsed = parser.parse_file(
            "examples/sample_repo/auth.py",
            repo_root="examples/sample_repo",
        )

        symbols = SymbolExtractor(parsed).extract()
        names = {(symbol.kind, symbol.qualified_name) for symbol in symbols}

        self.assertIn(("import", "hashlib"), names)
        self.assertIn(("class", "User"), names)
        self.assertIn(("method", "User.__init__"), names)
        self.assertIn(("function", "hash_password"), names)
        self.assertIn(("async_function", "authenticate"), names)

    def test_chunker_keeps_top_level_blocks_together(self) -> None:
        parser = PythonParser()
        parsed = parser.parse_file(
            "examples/sample_repo/auth.py",
            repo_root="examples/sample_repo",
        )

        chunks = PythonChunker().chunk(parsed)

        self.assertEqual(
            [chunk.name for chunk in chunks],
            ["User", "hash_password", "authenticate"],
        )
        user_chunk = chunks[0]
        self.assertEqual(user_chunk.kind, "class")
        self.assertIn("def __init__", user_chunk.content)


if __name__ == "__main__":
    unittest.main()
