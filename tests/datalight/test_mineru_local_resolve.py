from pathlib import Path

from datalight.ingest.mineru_local import expected_mineru_markdown, find_mineru_markdown

def test_expected_path_matches_spec():
    intermediate = Path("/tmp/w")
    stem = "doc"
    backend = "vlm-x"
    md = expected_mineru_markdown(intermediate, stem, backend)
    assert md == intermediate / stem / backend / f"{stem}.md"

def test_find_markdown_falls_back_to_mineru_auto_dir(tmp_path):
    stem = "doc"
    md = tmp_path / stem / "auto" / f"{stem}.md"
    md.parent.mkdir(parents=True)
    md.write_text("# parsed\n", encoding="utf-8")

    assert find_mineru_markdown(tmp_path, stem, "pipeline") == md
