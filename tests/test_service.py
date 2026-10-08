from __future__ import annotations

from pathlib import Path

import pytest

from moonlighter.service import (
    MANAGED_HEADER,
    ServiceError,
    SystemctlResult,
    install_units,
    normalize_interval,
    render_service_unit,
    render_timer_unit,
    resolve_moon_executable,
    service_unit_path,
    timer_unit_path,
    uninstall_units,
)


def test_resolve_moon_executable_rejects_relative_explicit_path() -> None:
    with pytest.raises(ServiceError, match="must be absolute"):
        resolve_moon_executable("moon")


def test_render_service_unit_uses_absolute_moon_path() -> None:
    text = render_service_unit(Path("/usr/local/bin/moon"))

    assert MANAGED_HEADER in text
    assert "Type=oneshot" in text
    assert "ExecStart=/usr/local/bin/moon work" in text


def test_render_service_unit_rejects_relative_moon_path() -> None:
    with pytest.raises(ServiceError, match="must be absolute"):
        render_service_unit(Path("moon"))


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [("30s", "30s"), ("10m", "10min"), ("10min", "10min"), ("1h", "1h")],
)
def test_normalize_interval(raw: str, normalized: str) -> None:
    assert normalize_interval(raw) == normalized


@pytest.mark.parametrize("raw", ["0m", "soon", "10 minutes\nExecStart=evil", "-1m"])
def test_normalize_interval_rejects_unsafe_values(raw: str) -> None:
    with pytest.raises(ServiceError, match="interval must be"):
        normalize_interval(raw)


def test_render_timer_unit_uses_default_interval() -> None:
    text = render_timer_unit()

    assert MANAGED_HEADER in text
    assert "OnBootSec=2min" in text
    assert "OnUnitActiveSec=10min" in text
    assert "Unit=moon.service" in text
    assert "WantedBy=timers.target" in text


def test_install_units_writes_to_user_systemd_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    service_path, timer_path = install_units(Path("/bin/moon"), "5m")

    assert service_path == tmp_path / "config" / "systemd" / "user" / "moon.service"
    assert timer_path == tmp_path / "config" / "systemd" / "user" / "moon.timer"
    assert "ExecStart=/bin/moon work" in service_path.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=5min" in timer_path.read_text(encoding="utf-8")


def test_install_units_refuses_non_managed_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    path = service_unit_path()
    path.parent.mkdir(parents=True)
    path.write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")

    with pytest.raises(ServiceError, match="refusing to overwrite"):
        install_units(Path("/bin/moon"))


def test_uninstall_units_refuses_non_managed_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    path = timer_unit_path()
    path.parent.mkdir(parents=True)
    path.write_text("[Timer]\nOnBootSec=1min\n", encoding="utf-8")

    with pytest.raises(ServiceError, match="refusing to remove"):
        uninstall_units()


def test_uninstall_units_removes_managed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    install_units(Path("/bin/moon"))

    assert uninstall_units() == (True, True)
    assert not service_unit_path().exists()
    assert not timer_unit_path().exists()


def test_systemctl_result_type() -> None:
    result = SystemctlResult(
        args=("systemctl", "--user", "status"), returncode=0, stdout="", stderr=""
    )

    assert result.returncode == 0
