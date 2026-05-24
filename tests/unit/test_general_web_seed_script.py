from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/seed_general_web_eval.sh")


def test_general_web_seed_script_covers_multiple_real_domains():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "https://docs.python.org/3/tutorial/index.html" in text
    assert "https://docs.github.com/en/get-started/start-your-journey/hello-world" in text
    assert "https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching" in text
    assert "https://www.usa.gov/passport" in text
    assert "https://www.irs.gov/filing/free-file-do-your-federal-taxes-for-free" in text
    assert "--domain software_docs" in text
    assert "--domain web_platform_docs" in text
    assert "--domain public_service" in text
    assert "--doc-type help_article" in text
