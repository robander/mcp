import argparse
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def load_server_module():
    module_path = Path(__file__).with_name("oracle-db-doc-mcp-server.py")
    spec = importlib.util.spec_from_file_location("oracle_db_doc_mcp_server", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def server():
    return load_server_module()


def test_search_tool_delegates_to_index(server, monkeypatch):
    monkeypatch.setattr(
        server,
        "search_index",
        lambda query, limit: [f"{query}:{limit}"],
    )

    assert server.search_oracle_database_documentation("create table", 3) == [
        "create table:3"
    ]


def test_search_index_respects_limit(server, monkeypatch):
    hits = [SimpleNamespace(text=f"hit-{idx}") for idx in range(5)]
    monkeypatch.setattr(server, "INDEX", SimpleNamespace(search=lambda text: hits))

    assert server.search_index("anything", 2) == ["hit-0", "hit-1"]


def test_maintain_content_returns_for_missing_or_unsupported_paths(server, tmp_path):
    missing = tmp_path / "missing"
    server.maintain_content(str(missing))

    unsupported = tmp_path / "input.txt"
    unsupported.write_text("not supported")
    server.maintain_content(str(unsupported))


def test_maintain_content_skips_when_checksum_and_version_match(
    server, tmp_path, monkeypatch
):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "topic.html").write_text("<h1>Topic</h1>")

    monkeypatch.setattr(server, "get_file_content", lambda path: "same")
    monkeypatch.setattr(server, "shasum_directory", lambda path: "same")
    monkeypatch.setattr(server, "INDEX_VERSION", "same")
    monkeypatch.setattr(server, "update_content", MagicMock())

    server.maintain_content(str(docs_dir))

    server.update_content.assert_not_called()


def test_maintain_content_reindexes_directory_and_zip(server, tmp_path, monkeypatch):
    writes = []
    monkeypatch.setattr(server, "CONTENT_CHECKSUM_FILE", tmp_path / "checksum")
    monkeypatch.setattr(server, "INDEX_VERSION_FILE", tmp_path / "version")
    monkeypatch.setattr(server, "INDEX_FILE", tmp_path / "index.db")
    monkeypatch.setattr(server, "get_file_content", lambda path: "old")
    monkeypatch.setattr(server, "shasum_directory", lambda path: "new")
    monkeypatch.setattr(server, "update_content", MagicMock())
    monkeypatch.setattr(
        server,
        "write_file_content",
        lambda path, content: writes.append((path.name, content)),
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "topic.html").write_text("<h1>Topic</h1>")
    server.maintain_content(str(docs_dir))

    archive = tmp_path / "docs.zip"
    with zipfile.ZipFile(archive, "w") as zip_ref:
        zip_ref.writestr("topic.html", "<h1>Topic</h1>")
    server.maintain_content(str(archive))

    assert server.update_content.call_count == 2
    assert ("checksum", "new") in writes
    assert ("version", server.INDEX_VERSION) in writes


def test_update_content_processes_all_files_and_optimizes(server, tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    first = docs_dir / "a.html"
    second = docs_dir / "b.txt"
    first.write_text("<h1>A</h1>")
    second.write_text("B")
    processed = []
    monkeypatch.setattr(server, "process_file", lambda path: processed.append(path))
    monkeypatch.setattr(server, "optimize_index", MagicMock())

    server.update_content(docs_dir)

    assert set(processed) == {first, second}
    server.optimize_index.assert_called_once_with()


def test_process_file_indexes_only_content_html(server, tmp_path, monkeypatch):
    indexed = []
    monkeypatch.setattr(server, "convert_to_markdown_chunks", lambda path: ["chunk"])
    monkeypatch.setattr(server, "update_index", lambda chunks: indexed.append(chunks))

    server.process_file(tmp_path / "note.txt")
    readme = tmp_path / "readme.html"
    readme.write_text("<h1>Readme</h1>")
    server.process_file(readme)
    topic = tmp_path / "topic.htm"
    topic.write_text("<h1>Topic</h1>")
    server.process_file(topic)

    assert indexed == [["chunk"]]


def test_optimize_and_update_index_use_pocketsearch_apis(server, tmp_path, monkeypatch):
    fake_search = MagicMock()
    monkeypatch.setattr(server, "INDEX_FILE", tmp_path / "index.db")
    monkeypatch.setattr(server, "PocketSearch", MagicMock(return_value=fake_search))

    server.optimize_index()

    server.PocketSearch.assert_called_once_with(db_name=server.INDEX_FILE, writeable=True)
    fake_search.optimize.assert_called_once_with()

    inserts = []

    class FakeWriter:
        def __init__(self, db_name):
            self.db_name = db_name

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def insert(self, text):
            inserts.append((self.db_name, text))

    monkeypatch.setattr(server, "PocketWriter", FakeWriter)
    server.update_index(["one", "two"])

    assert inserts == [(server.INDEX_FILE, "one"), (server.INDEX_FILE, "two")]


def test_checksum_includes_relative_paths_and_content(server, tmp_path):
    docs_dir = tmp_path / "docs"
    nested = docs_dir / "nested"
    nested.mkdir(parents=True)
    (docs_dir / "b.html").write_text("B")
    (nested / "a.html").write_text("A")

    first = server.shasum_directory(docs_dir)
    (nested / "a.html").write_text("changed")
    second = server.shasum_directory(docs_dir)

    assert first != second


def test_convert_to_markdown_chunks_handles_sections_and_fallback(
    server, tmp_path, monkeypatch
):
    topic = tmp_path / "topic.html"
    topic.write_text(
        "<h3>Intro</h3><p>See <a href='https://example.com/abc'>link</a>.</p>"
        "<h4>Details</h4><p>More text.</p>"
    )
    monkeypatch.setattr(server, "PREPROCESS", "BASIC")

    chunks = server.convert_to_markdown_chunks(topic)

    assert chunks[0].startswith("Intro")
    assert "https://example.com" not in chunks[0]
    assert any(chunk.startswith("Details") for chunk in chunks)

    plain = tmp_path / "plain.html"
    plain.write_text("<p>No headings here</p>")
    assert server.convert_to_markdown_chunks(plain) == ["No headings here"]


def test_convert_to_markdown_chunks_uses_advanced_preprocess(
    server, tmp_path, monkeypatch
):
    topic = tmp_path / "advanced.html"
    topic.write_text("<nav>remove</nav><h1>Keep</h1><p>Body</p>")
    monkeypatch.setattr(server, "PREPROCESS", "ADVANCED")
    monkeypatch.setattr(
        server,
        "preprocess_html",
        lambda html: html.replace("<nav>remove</nav>", ""),
    )

    assert server.convert_to_markdown_chunks(topic) == ["Keep\n====\n\nBody"]


def test_remove_markdown_urls_and_preprocess_html(server):
    cleaned = server.remove_markdown_urls(
        "See [docs](https://example.com/path) and "
        "https://example.com/0123456789abcdef plus https://example.com/plain"
    )
    assert cleaned == "See docs and plus"

    html = """
    <html><head><script>x()</script><style>.x{}</style></head>
    <body>
      <header>Header</header><nav>Navigation</nav><footer>Footer</footer>
      <div class="breadcrumb">Crumb</div><div id="sidebar-main">Side</div>
      <p>JavaScript must be enabled to correctly display this content</p>
      <main><h1>Useful Topic</h1><p>Keep this text.</p></main>
    </body></html>
    """
    processed = server.preprocess_html(html)

    assert "Useful Topic" in processed
    assert "Keep this text" in processed
    assert "Navigation" not in processed
    assert "JavaScript must be enabled" not in processed


def test_file_helpers_and_folder_creation(server, tmp_path, monkeypatch):
    resources = tmp_path / "home" / "resources"
    monkeypatch.setattr(server, "RESOURCES_DIR", resources)

    server.build_folder_structure()
    assert resources.exists()

    missing = tmp_path / "missing.txt"
    assert server.get_file_content(missing) == "N/A"

    target = tmp_path / "content.txt"
    server.write_file_content(target, "value")
    assert server.get_file_content(target) == "value"


def test_parse_args_for_index_and_http_mode(server, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "idx", "-path", "/docs", "-preprocess", "advanced"],
    )
    args = server.parse_args()
    assert args.command == "idx"
    assert args.path == "/docs"
    assert args.preprocess == "advanced"

    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "mcp", "-mode", "http", "-host", "127.0.0.1", "-port", "9000"],
    )
    args = server.parse_args()
    assert args.command == "mcp"
    assert args.mode == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 9000


def test_main_index_mode(server, tmp_path, monkeypatch):
    monkeypatch.setattr(
        server,
        "parse_args",
        lambda: argparse.Namespace(
            command="idx",
            log_level="debug",
            path="/docs",
            preprocess="advanced",
        ),
    )
    monkeypatch.setattr(server, "HOME_DIR", tmp_path)
    monkeypatch.setattr(server, "build_folder_structure", MagicMock())
    monkeypatch.setattr(server.logging, "basicConfig", MagicMock())
    monkeypatch.setattr(server, "maintain_content", MagicMock())

    server.main()

    assert server.PREPROCESS == "ADVANCED"
    server.maintain_content.assert_called_once_with("/docs")


def test_main_mcp_modes(server, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "HOME_DIR", tmp_path)
    monkeypatch.setattr(server, "build_folder_structure", MagicMock())
    monkeypatch.setattr(server.logging, "basicConfig", MagicMock())

    missing_index = tmp_path / "missing.db"
    monkeypatch.setattr(server, "INDEX_FILE", missing_index)
    monkeypatch.setattr(
        server,
        "parse_args",
        lambda: argparse.Namespace(
            command="mcp",
            log_level="error",
            mode="stdio",
            host="0.0.0.0",
            port=8000,
        ),
    )
    run_mock = MagicMock()
    monkeypatch.setattr(server.mcp, "run", run_mock)

    server.main()
    run_mock.assert_not_called()

    index_file = tmp_path / "index.db"
    index_file.write_text("index")
    monkeypatch.setattr(server, "INDEX_FILE", index_file)
    monkeypatch.setattr(server, "PocketSearch", MagicMock(return_value="index"))

    server.main()
    run_mock.assert_called_once_with(transport="stdio", show_banner=False)
    assert server.INDEX == "index"

    run_mock.reset_mock()
    monkeypatch.setattr(
        server,
        "parse_args",
        lambda: argparse.Namespace(
            command="mcp",
            log_level="error",
            mode="http",
            host="127.0.0.1",
            port=9000,
        ),
    )
    server.main()

    run_mock.assert_called_once_with(
        transport="http",
        host="127.0.0.1",
        port=9000,
        show_banner=False,
    )
