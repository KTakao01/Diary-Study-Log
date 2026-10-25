"""Check that every article can be reached from the built GitHub Pages index."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / '_site'
BASE = '/Diary-Study-Log/'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'article-link' in attrs.get('class', '').split():
            self.articles.append((attrs['data-source'], attrs['href']))
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.assets.append(attrs['href'])
        if tag == 'script' and 'src' in attrs:
            self.assets.append(attrs['src'])


def output_path(url):
    path = unquote(urlsplit(url).path)
    assert path.startswith(BASE), f'Missing project base path: {url}'
    target = (SITE / path[len(BASE):]).resolve()
    assert target.is_relative_to(SITE.resolve()), f'Invalid output path: {url}'
    return target


index = SITE / 'index.html'
parser = Links()
parser.feed(index.read_text())
expected = {
    path.relative_to(ROOT).as_posix()
    for folder in ('DailyReport', 'WeeklyReport', 'MonthlyReport')
    for path in (ROOT / folder).rglob('*.md')
}
sources = [source for source, _ in parser.articles]
actual = [output_path(url) for _, url in parser.articles]
assert len(sources) == len(set(sources)), 'Duplicate source articles'
assert len(actual) == len(set(actual)), 'Duplicate article links'
assert set(sources) == expected, f'Article mismatch: missing={expected-set(sources)}, extra={set(sources)-expected}'
for path in actual + [output_path(url) for url in parser.assets]:
    assert path.is_file(), f'Missing built file: {path.relative_to(SITE)}'
for folder in ('AuditLog', "Year'sPlan", 'scripts', '.agents', '.github', '.vscode'):
    assert not (SITE / folder).exists(), f'Non-article folder published: {folder}'
for filename in ('AGENTS.html', 'AGENTS.md', 'README.html', 'README.md'):
    assert not (SITE / filename).exists(), f'Non-article file published: {filename}'
for path in actual:
    html = path.read_text()
    assert '<!doctype html>' in html.lower(), f'Missing page layout: {path}'
    assert f'href="{BASE}"' in html, f'Missing article-list navigation: {path}'
print(f'OK: {len(actual)} articles, all index links and assets, navigation, and excluded files.')
