#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

EXPECTED_KEYS = {
    "app_name",
    "company_name",
    "connection_mode",
    "enable_installation",
    "enable_settings",
    "permission_clipboard",
    "permission_file_system",
    "permission_file_transfer",
    "permission_remote_input",
    "permission_remote_text",
    "permissions_mode",
    "platform",
    "profile_id",
    "profile_name",
    "rustdesk_version",
    "schema_version",
    "source_commit",
    "support_link",
    "theme_mode",
    "update_link",
}
DISPLAY_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&'()_-]{0,63}$")
SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def load_spec(raw: str, expected_sha256: str, expected_source: str) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > 8192 or DIGEST.fullmatch(expected_sha256) is None:
        raise ValueError("invalid build specification envelope")
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != expected_sha256:
        raise ValueError("build specification integrity mismatch")
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid build specification JSON") from exc
    if not isinstance(spec, dict) or set(spec) != EXPECTED_KEYS:
        raise ValueError("invalid build specification fields")
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if canonical != raw:
        raise ValueError("non-canonical build specification")
    if SOURCE_COMMIT.fullmatch(expected_source) is None or spec["source_commit"] != expected_source:
        raise ValueError("build specification source mismatch")
    if spec["schema_version"] != 1 or spec["platform"] != "windows-x64" or spec["rustdesk_version"] != "1.4.9":
        raise ValueError("unsupported build specification target")
    if not isinstance(spec["profile_id"], int) or isinstance(spec["profile_id"], bool) or spec["profile_id"] <= 0:
        raise ValueError("invalid build profile identifier")
    for field in ("profile_name", "app_name", "company_name"):
        if not isinstance(spec[field], str) or DISPLAY_TEXT.fullmatch(spec[field]) is None:
            raise ValueError("invalid build display text")
    expected_policy = {
        "connection_mode": "bidirectional",
        "enable_installation": True,
        "enable_settings": True,
        "theme_mode": "system",
        "permissions_mode": "default",
        "permission_file_transfer": True,
        "permission_remote_input": True,
        "permission_remote_text": True,
        "permission_file_system": False,
        "permission_clipboard": True,
        "support_link": None,
        "update_link": None,
    }
    if any(spec[name] != value for name, value in expected_policy.items()):
        raise ValueError("unsupported pilot build policy")
    return spec


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"source template mismatch: {path.as_posix()}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def apply_spec(root: Path, spec: dict[str, Any], digest: str) -> None:
    app_name = spec["app_name"]
    company_name = spec["company_name"]
    runner = root / "flutter/windows/runner/Runner.rc"
    replace_once(runner, 'VALUE "CompanyName", "Purslane Tech Pte. Ltd." "\\0"', f'VALUE "CompanyName", "{company_name}" "\\0"')
    replace_once(runner, 'VALUE "FileDescription", "RustDesk Remote Desktop" "\\0"', f'VALUE "FileDescription", "{app_name} Secure Remote Support" "\\0"')
    replace_once(runner, 'VALUE "LegalCopyright", "Copyright © 2026 Purslane Tech Pte. Ltd. All rights reserved." "\\0"', f'VALUE "LegalCopyright", "Copyright © 2026 {company_name}. All rights reserved." "\\0"')
    replace_once(runner, 'VALUE "ProductName", "RustDesk" "\\0"', f'VALUE "ProductName", "{app_name}" "\\0"')

    cargo = root / "Cargo.toml"
    replace_once(cargo, 'ProductName = "JBODTECH Support"', f'ProductName = "{app_name}"')
    replace_once(cargo, 'FileDescription = "JBODTECH Secure Remote Support"', f'FileDescription = "{app_name} Secure Remote Support"')

    config = root / "libs/hbb_common/src/config.rs"
    replace_once(
        config,
        'RwLock::new("JBODTECH Support".to_owned())',
        f'RwLock::new("{app_name}".to_owned())',
    )
    manifest = {
        "app_name": app_name,
        "company_name": company_name,
        "profile_id": spec["profile_id"],
        "source_commit": spec["source_commit"],
        "spec_sha256": digest,
        "signature_state": "unsigned",
    }
    output = root / "res/jbodtech/applied-build-spec.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    raw = os.environ.get("BUILD_SPEC_JSON", "")
    spec = load_spec(raw, args.expected_sha256, args.expected_source)
    apply_spec(args.root, spec, args.expected_sha256)


if __name__ == "__main__":
    main()
