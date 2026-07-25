"""Tests del kill switch / watchdog."""
from __future__ import annotations

from trading_system.risk import KillSwitch, KillSwitchConfig


def test_ok_when_no_conditions():
    ks = KillSwitch(KillSwitchConfig())
    assert ks.check()[0] is True
    ks.record_trade(-1000)
    assert ks.check()[0] is True  # sin límites configurados


def test_max_daily_loss_trips():
    ks = KillSwitch(KillSwitchConfig(max_daily_loss=500))
    ks.record_trade(-300)
    assert ks.tripped is False
    ks.record_trade(-250)  # acumulado -550 < -500
    ok, reason = ks.check()
    assert ok is False and "diaria" in reason.lower()


def test_max_consecutive_losses_trips():
    ks = KillSwitch(KillSwitchConfig(max_consecutive_losses=3))
    ks.record_trade(-10)
    ks.record_trade(-10)
    assert ks.tripped is False
    ks.record_trade(-10)
    assert ks.tripped is True
    assert "consecutiv" in ks.reason.lower()


def test_win_resets_consecutive_losses():
    ks = KillSwitch(KillSwitchConfig(max_consecutive_losses=3))
    ks.record_trade(-10)
    ks.record_trade(-10)
    ks.record_trade(50)   # gana -> resetea la racha
    ks.record_trade(-10)
    assert ks.tripped is False


def test_max_drawdown_trips():
    ks = KillSwitch(KillSwitchConfig(max_drawdown=300))
    ks.record_trade(500)    # equity 500 (pico)
    ks.record_trade(-200)   # equity 300, dd 200
    assert ks.tripped is False
    ks.record_trade(-150)   # equity 150, dd 350 >= 300
    assert ks.tripped is True


def test_manual_flag_file_trips(tmp_path):
    flag = tmp_path / "STOP"
    ks = KillSwitch(KillSwitchConfig(flag_file=str(flag)))
    assert ks.check()[0] is True
    flag.write_text("stop")
    ok, reason = ks.check()
    assert ok is False and "manual" in reason.lower()


def test_reset_clears_trip():
    ks = KillSwitch(KillSwitchConfig(max_consecutive_losses=1))
    ks.record_trade(-10)
    assert ks.tripped is True
    ks.reset()
    assert ks.tripped is False
    assert ks.check()[0] is True
