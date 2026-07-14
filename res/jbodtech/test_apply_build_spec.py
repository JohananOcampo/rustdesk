import hashlib
import json
from pathlib import Path

import pytest

from apply_build_spec import apply_spec, load_spec


SOURCE = "d41bf3e14fd2136a2ac1fdbbdf8dd40160210730"


def valid_spec():
    return {
        "app_name": "JBODTECH Support",
        "company_name": "JBODTECH Computer Services",
        "connection_mode": "bidirectional",
        "enable_installation": True,
        "enable_settings": True,
        "permission_clipboard": True,
        "permission_file_system": False,
        "permission_file_transfer": True,
        "permission_remote_input": True,
        "permission_remote_text": True,
        "permissions_mode": "default",
        "platform": "windows-x64",
        "profile_id": 1,
        "profile_name": "Standard Pilot",
        "rustdesk_version": "1.4.9",
        "schema_version": 1,
        "source_commit": SOURCE,
        "support_link": None,
        "theme_mode": "system",
        "update_link": None,
    }


def encoded(spec):
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fixture_root(tmp_path: Path) -> Path:
    files = {
        "flutter/windows/runner/Runner.rc": '''VALUE "CompanyName", "Purslane Tech Pte. Ltd." "\\0"
VALUE "FileDescription", "RustDesk Remote Desktop" "\\0"
VALUE "LegalCopyright", "Copyright © 2026 Purslane Tech Pte. Ltd. All rights reserved." "\\0"
VALUE "ProductName", "RustDesk" "\\0"
''',
        "Cargo.toml": 'ProductName = "JBODTECH Support"\nFileDescription = "JBODTECH Secure Remote Support"\n',
        "libs/hbb_common/src/config.rs": 'RwLock::new("JBODTECH Support".to_owned())\n',
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def test_load_and_apply_closed_spec_updates_windows_branding(tmp_path):
    raw = encoded(valid_spec())
    digest = hashlib.sha256(raw.encode()).hexdigest()
    spec = load_spec(raw, digest, SOURCE)
    root = fixture_root(tmp_path)
    apply_spec(root, spec, digest)
    runner = (root / "flutter/windows/runner/Runner.rc").read_text()
    assert '"JBODTECH Computer Services"' in runner
    assert '"JBODTECH Support"' in runner
    assert "Purslane" not in runner and '"RustDesk"' not in runner
    assert 'ProductName = "JBODTECH Support"' in (root / "Cargo.toml").read_text()
    manifest = json.loads((root / "res/jbodtech/applied-build-spec.json").read_text())
    assert manifest == {
        "app_name": "JBODTECH Support",
        "company_name": "JBODTECH Computer Services",
        "profile_id": 1,
        "signature_state": "unsigned",
        "source_commit": SOURCE,
        "spec_sha256": digest,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_name", 'Injected"; rm -rf'),
        ("connection_mode", "outbound"),
        ("support_link", "https://support.jbodtech.com"),
        ("permission_file_system", True),
    ],
)
def test_pilot_rejects_injection_and_unimplemented_policy(field, value):
    spec = valid_spec()
    spec[field] = value
    raw = encoded(spec)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with pytest.raises(ValueError):
        load_spec(raw, digest, SOURCE)


def test_pilot_rejects_digest_and_source_mismatch():
    raw = encoded(valid_spec())
    with pytest.raises(ValueError, match="integrity"):
        load_spec(raw, "0" * 64, SOURCE)
    with pytest.raises(ValueError, match="source"):
        load_spec(raw, hashlib.sha256(raw.encode()).hexdigest(), "a" * 40)
