"""Validate the anonymous submission snapshot and its reported results."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse
import csv, hashlib, json, re

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = {'.gitignore', '.nojekyll', 'README.md', 'index.html', 'app.js', 'styles.css',
          'benchmark.js', 'serve.py', 'package.json', 'assets', 'data', 'film', 'scripts'}
METHODS = {'planner', 'oneshot', 'genplan', 'codex', 'claude', 'source'}
CLIP_METHODS = {'claude', 'codex', 'genplan'}
BACKENDS = {'Hand-engineered TAMP', 'Opus 5', 'Codex · GPT-5.6 Sol', 'Claude Code · Opus 5'}
EMAIL = '328601582+r8508271-lang@users.noreply.github.com'

def require(path):
    p = ROOT / path.split('?')[0].split('#')[0]
    assert p.is_file(), f'Missing asset: {path}'
    return p

def sha(path):
    return hashlib.sha256(require(path).read_bytes()).hexdigest()

def public_files():
    for name in PUBLIC:
        p = ROOT / name
        for f in ([p] if p.is_file() else p.rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts and f.suffix != '.pyc':
                yield f

def allowed_url(url):
    u = urlparse(url.rstrip('.,;'))
    if u.hostname in {'127.0.0.1', 'localhost'}: return True
    if u.hostname == 'r8508271-lang.github.io': return True
    if u.hostname == 'anonymous.4open.science' and u.path.startswith('/r/agentamp-3481'): return True
    if u.hostname == 'github.com' and u.path.rstrip('/').removesuffix('.git') == '/r8508271-lang/r8508271-lang.github.io': return True
    return False

class Assets(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key not in {'href', 'src', 'poster'} or not value: continue
            if value.startswith(('http:', 'https:')):
                assert allowed_url(value), 'Unexpected public link'
            elif not value.startswith(('#', 'data:')): require(value)

def main():
    Assets().feed(require('index.html').read_text())
    for p in public_files():
        assert not p.is_symlink() and p.stat().st_size < 95 * 1024 * 1024, 'Unsafe asset'
        if p.suffix not in {'.html', '.js', '.css', '.json', '.md', '.txt'}: continue
        # Third-party font attribution is retained as required by its license.
        if p.name == 'OFL.txt': continue
        text = p.read_text()
        assert not re.search(r'/home/|/Users/|AIza[\w-]{30}|gh[pousr]_[\w]{25}', text), 'Private path or token'
        assert all(m == EMAIL for m in re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)), 'Unexpected email'
        for url in re.findall(r'https?://[^\s<>"\)\]]+', text):
            assert allowed_url(url), f'Unexpected external URL in {p.relative_to(ROOT)}'
    data = json.loads(require('data/benchmark.json').read_text())
    assert len(data['environments']) == 28 and {m['id'] for m in data['methods']} == METHODS
    assert {m['backend'] for m in data['methods']} <= BACKENDS
    assert data['protocol']['programs'] == 700 and data['protocol']['episodes'] == 70000
    assert sha('assets/paper.pdf') == data['source']['sha256']
    for env in data['environments']:
        assert set(env['results']) == METHODS
        for value in env['results'].values():
            assert value is None or 0 <= value['min'] <= value['mean'] <= value['max'] <= 1
    with require('data/benchmark.csv').open() as stream: rows = list(csv.DictReader(stream))
    assert len(rows) == 168
    for row, (env, method) in zip(rows, ((e, m) for e in data['environments'] for m in data['methods'])):
        assert row['environment'] == env['name'] and row['backend'] == method['backend']
        r = env['results'][method['id']]
        for key, csv_key in [('mean', 'mean_success'), ('min', 'min_run_success'), ('max', 'max_run_success')]:
            assert row[csv_key] == (str(r[key]) if r else '')
    timing = data['efficiency']
    assert timing['environments'] == 13 and timing['matchedSeeds'] == 44
    assert timing['claude'] == {'mean': 4.002, 'min': 0.043, 'max': 29.177}
    assert timing['source'] == {'mean': 27.900, 'min': 0.065, 'max': 96.640}
    examples = json.loads(require('data/policy-examples.json').read_text())
    ids = {e['id'] for e in data['environments']}
    assert {e['id'] for e in examples['environments']} == ids
    clips = []
    for env in examples['environments']:
        vs = env['videos']; clips.extend(vs)
        assert len(vs) == 3 and not env['unavailable']
        assert {v['method'] for v in vs} | {v['method'] for v in env['unavailable']} == CLIP_METHODS
        for key in ['instanceSeed', 'episode']:
            assert len({v['source'][key] for v in vs}) == 1
        states = [v['source'].get('initialStateSha256') for v in vs]
        assert (all(states) and len(set(states)) == 1) or len({v['source']['initialFrameSha256'] for v in vs}) == 1
        for clip in vs:
            assert clip['solved'] == clip['source']['archivedSolved']
            assert sha(clip['video']) == clip['source']['videoSha256']
            require(clip['poster'])
            if clip['method'] == 'codex' and env['id'] in examples['codexRerunEnvironments']:
                assert clip['source']['collection'] == 'Codex Reruns'
    assert len(clips) == 84
    assert {p.name for p in (ROOT / 'assets/policies').iterdir()} == {Path(v[k]).name for v in clips for k in ('video', 'poster')}
    manifest = json.loads(require('data/environment-descriptions/sources.json').read_text())
    rendered = {e['id']: e for e in json.loads(require('data/environment-descriptions.json').read_text())['environments']}
    assert {e['id'] for e in manifest['environments']} == set(rendered) == ids
    for env in manifest['environments']:
        assert sha(env['rawFile']) == env['sha256'] == rendered[env['id']]['sha256']
    for item in json.loads(require('data/gallery.json').read_text()):
        require(f"film/assets/clips/{item['file']}.mp4"); require(f"assets/posters/{item['file']}.jpg")
    audit = json.loads(require('data/submission-audit.json').read_text())
    assert audit['paperSha256'] == data['source']['sha256'] and audit['policyClipCount'] == 84
    print('PASS: anonymous links, submission PDF, 28 environments, six methods, 168 results, 84 matched policy clips, descriptions, assets, and Table III.')

if __name__ == '__main__': main()
