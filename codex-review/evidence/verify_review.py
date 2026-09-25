"""Verify source/archive preservation and the new report's local Markdown links."""
from datetime import UTC, datetime
from pathlib import Path
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote, urlsplit

root = Path(__file__).resolve().parents[2]
review = root / 'codex-review'
baseline = json.loads((review / 'evidence/source-baseline.json').read_text())
archive = json.loads((review / 'evidence/archive-manifest.json').read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

source_errors = [name for name, expected in baseline['files'].items()
                 if not (root / name).is_file() or sha(root / name) != expected]
archive_errors = [item['path'] for item in archive['files']
                  if not (root / archive['archive'] / item['path']).is_file()
                  or sha(root / archive['archive'] / item['path']) != item['sha256']]
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
untracked = subprocess.check_output(
    ['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=root
).decode().split('\0')
unexpected = [p for p in untracked if p and not p.startswith('codex-review/')
              and p not in baseline['files']]
link_errors = []
checked = 0
reports = sorted(review.glob('*.md'))
for report in reports:
    for match in re.finditer(r'\[[^\]]*\]\(([^)]+)\)', report.read_text()):
        target = match.group(1).strip('<>')
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith('#'):
            continue
        target_path = unquote(parsed.path)
        if not target_path:
            continue
        checked += 1
        if not (report.parent / target_path).exists():
            link_errors.append({'report': report.name, 'target': target})
result = {
    'checked_at_utc': datetime.now(UTC).isoformat(),
    'head': head,
    'head_unchanged': head == baseline['head'],
    'source_files_checked': len(baseline['files']),
    'source_changed_or_missing': source_errors,
    'archive_files_checked': len(archive['files']),
    'archive_changed_or_missing': archive_errors,
    'unexpected_files_outside_review': unexpected,
    'reports_checked': [p.name for p in reports],
    'local_links_checked': checked,
    'broken_local_links': link_errors,
}
result['ok'] = not (source_errors or archive_errors or unexpected or link_errors) and result['head_unchanged']
(review / 'evidence/preservation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['ok'] else 1)
