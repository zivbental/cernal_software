"""Check local Markdown links/anchors in active project documentation.

Historical originals, vendored sources and notebooks are intentionally outside this
active-guide check. They retain original contexts; inventory links pin their source.
Run: python docs/tools/check_links.py
"""

import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def unfenced(text):
    return re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)


def anchors(path):
    text = unfenced(path.read_text(encoding="utf-8"))
    found = set(re.findall(r"(?:id|name)=[\"\']([^\"\']+)", text))
    counts = {}
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        heading = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", heading)
        heading = re.sub(r"<[^>]*>", "", heading).lower().strip()
        slug = "".join(
            c for c in heading if c in "-_ " or not unicodedata.category(c).startswith(("P", "S"))
        ).replace(" ", "-")
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        found.add(slug + (f"-{n}" if n else ""))
    return found


def main():
    paths = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "CLAUDE.md"]
    paths += sorted((ROOT / "clients").rglob("README.md"))
    paths += sorted((ROOT / "src/engine/gates/notebooks").rglob("README.md"))
    paths += sorted(p for p in (ROOT / "docs").rglob("*.md") if "archive" not in p.parts)
    issues = []
    checked = 0
    for path in paths:
        text = unfenced(path.read_text(encoding="utf-8"))
        links = re.findall(r"!?\[[^\]]*\]\(([^\n]+?)\)", text)
        links += re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(\S+)", text)
        for link in links:
            link = link.strip().split(' "', 1)[0].strip("<>")
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            if not url.path and not url.fragment:
                continue
            checked += 1
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.exists():
                issues.append(f"{path.relative_to(ROOT)}: missing {link}")
            elif url.fragment and target.suffix == ".md" and "archive" not in target.parts:
                if unquote(url.fragment) not in anchors(target):
                    issues.append(f"{path.relative_to(ROOT)}: missing anchor {link}")
    print(f"Checked {len(paths)} active Markdown files and {checked} local links.")
    for issue in issues:
        print(issue)
    return bool(issues)


if __name__ == "__main__":
    raise SystemExit(main())
