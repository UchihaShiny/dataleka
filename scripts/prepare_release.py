"""Build a deterministic source snapshot. Real .env files are excluded before reads."""
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'dataleka'
BLOCKED = {'.git', '.idea', '.venv', 'node_modules', 'secrets', 'data', 'logs',
           'bin', '__pycache__', 'test-results', 'playwright-report', '.pytest_cache'}
SAVED = {'webapp/reports.json', 'webapp/analyses.json'}
SENSITIVE = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AIza[A-Za-z0-9_-]{35}|sk-ant-[A-Za-z0-9_-]{30,}')


def eligible(name):
    path = Path(name)
    return (bool(name) and not path.is_absolute() and '..' not in path.parts
            and not any(part in BLOCKED or part.startswith('.env') for part in path.parts)
            and name not in SAVED and path.suffix.lower() not in {'.key', '.pem', '.p12', '.pfx'})


def build_release(root=ROOT):
    root = Path(root).resolve()
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
    files = {}
    for name in sorted(set(names)):
        if not eligible(name):
            continue
        path = root / name
        # Resolve ancestors too: a directory symlink must never escape the source tree.
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            continue
        if path.stat().st_size > 5_000_000:
            raise ValueError(f'File quá lớn; cần xem xét: {name}')
        content = path.read_bytes()
        if SENSITIVE.search(content):
            raise ValueError(f'Phát hiện mẫu credential; dừng đóng gói: {name}')
        files[name] = content
    out = root / 'data' / 'release'
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f'{PROJECT}-source.zip'
    temporary = out / f'{PROJECT}-source.zip.tmp'
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            info = zipfile.ZipInfo(f'{PROJECT}/{name}', date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = name.endswith('.sh')
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            z.writestr(info, content)
    temporary.replace(archive)
    manifest = {'archive': archive.name, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
                'note': 'Source snapshot only; credentials/runtime/saves excluded. Not proof of GitHub upload.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return archive, manifest


if __name__ == '__main__':
    archive, manifest = build_release()
    print(f'{len(manifest["files"])} source files: {archive}\nSHA256: {manifest["sha256"]}')
