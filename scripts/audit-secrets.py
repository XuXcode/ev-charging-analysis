"""Read-only secret audit; output locations/counts only, never secret values."""

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {
    ".git",
    ".workbuddy",
    ".idea",
    "node_modules",
    ".conda",
    ".runtime",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
}
KEY_LITERAL = re.compile(
    rb"(?:AMAP_WEBSERVICE_KEY|VITE_AMAP_KEY|VITE_AMAP_SECURITY_CODE|securityJsCode|\bkey)\b[\"']?\s*[:=]\s*[\"']?([a-f0-9]{32})",
    re.IGNORECASE,
)
DB_LITERAL = re.compile(rb"mysql(?:\+pymysql)?://[^\s/:]+:([^\s@]+)@", re.IGNORECASE)


def suspected_literal(content):
    if KEY_LITERAL.search(content):
        return True
    for match in DB_LITERAL.finditer(content):
        value = match.group(1)
        decoded = value.decode("utf-8", errors="ignore")
        documented_placeholder = (
            decoded.upper().startswith("URL") and "编码" in decoded and "密码" in decoded
        )
        if not documented_placeholder and value not in {
            b"replace_me",
            b"password",
            b"CHANGE_ME",
            b"your_password",
        }:
            return True
    return False


def git(*arguments):
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments], capture_output=True, check=True
    ).stdout


def audit():
    values = {}
    for filename in ("backend/.env", "fortend/.env.local"):
        path = ROOT / filename
        if path.exists():
            values.update(dotenv_values(path))
    secrets = {v for k, v in values.items() if v and ("KEY" in k or "SECURITY" in k)}
    database_url = values.get("DATABASE_URL", "")
    password = urlsplit(database_url).password
    if password:
        secrets.add(unquote(password))
    # Avoid treating short/local example values as unique credentials.
    secrets = {v.encode() for v in secrets if len(v) >= 8}
    hits = []
    scanned = 0
    paths = []
    for directory, subdirectories, filenames in os.walk(ROOT):
        subdirectories[:] = [name for name in subdirectories if name not in IGNORED_DIRS]
        paths.extend(Path(directory) / name for name in filenames)
    for path in paths:
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if path.stat().st_size > 20_000_000:
            continue
        content = path.read_bytes()
        scanned += 1
        if any(secret in content for secret in secrets):
            hits.append({"scope": "working_tree", "path": str(path.relative_to(ROOT))})
        if suspected_literal(content) and path.name != ".env.example":
            hits.append({"scope": "suspected_literal", "path": str(path.relative_to(ROOT))})
        if path.suffix in {".js", ".vue"} and re.search(
            rb"(?:AMAP_WEBSERVICE_KEY|DATABASE_URL)\s*[:=]\s*['\"][^'\"]{8,}", content
        ):
            hits.append(
                {
                    "scope": "frontend_private_config",
                    "path": str(path.relative_to(ROOT)),
                }
            )
    objects = git("rev-list", "--objects", "--all").decode().splitlines()
    history_blobs = 0
    for line in objects:
        object_id, _, name = line.partition(" ")
        if not name or git("cat-file", "-t", object_id).strip() != b"blob":
            continue
        content = git("cat-file", "blob", object_id)
        history_blobs += 1
        if any(secret in content for secret in secrets):
            hits.append({"scope": "git_history", "path": name, "object": object_id})
        if suspected_literal(content) and Path(name).name != ".env.example":
            hits.append({"scope": "history_literal", "path": name, "object": object_id})
    ignored = {}
    for filename in (".env", "fortend/.env.local", "backend/.env"):
        result = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "--quiet", filename],
            capture_output=True,
            check=False,
        )
        ignored[filename] = result.returncode == 0
    tracked_env = [
        path
        for path in git("ls-files").decode().splitlines()
        if Path(path).name.startswith(".env") and Path(path).name != ".env.example"
    ]
    private_values = {values.get("AMAP_WEBSERVICE_KEY", "")}
    if password:
        private_values.add(unquote(password))
    private_secrets = {value.encode() for value in private_values if len(value) >= 8}
    build_files = list((ROOT / "fortend/dist").rglob("*"))
    build_scanned = 0
    for path in build_files:
        if not path.is_file():
            continue
        build_scanned += 1
        if any(secret in path.read_bytes() for secret in private_secrets):
            hits.append({"scope": "build_private_secret", "path": str(path.relative_to(ROOT))})
    report = {
        "scannedFiles": scanned,
        "historyBlobs": history_blobs,
        "buildFiles": build_scanned,
        "privateBuildSecretsChecked": len(private_secrets),
        "configuredSecretsChecked": len(secrets),
        "ignoredEnvironmentFiles": ignored,
        "trackedSecretEnvironmentFiles": tracked_env,
        "locations": hits,
        "passed": not hits and not tracked_env and all(ignored.values()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    (ROOT / "docs/reports" / "SECURITY_AUDIT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    raise SystemExit(0 if audit()["passed"] else 1)
