from __future__ import annotations

import uiautomator2 as u2

Device = u2.Device

touch_cache: dict[str, tuple[str, int, int]] = {}


def find_touch_device(device: u2.Device) -> tuple[str, int, int] | None:
    """Returns (device_path, max_x, max_y) of the first multitouch input device."""
    serial = device.serial
    if serial in touch_cache:
        return touch_cache[serial]
    out = device.shell("getevent -pl 2>&1").output
    dev = None
    max_x = max_y = 32767
    for line in out.split("\n"):
        if "add device" in line:
            dev = line.split(":")[-1].strip()
            max_x = max_y = 32767
        if dev and "ABS_MT_POSITION_X" in line and "max" in line:
            max_x = int(line.split("max")[1].split(",")[0].strip())
        if dev and "ABS_MT_POSITION_Y" in line and "max" in line:
            touch_cache[serial] = (dev, max_x, max_y)
            return touch_cache[serial]
    return None


def sendevent_tap(device: u2.Device, x: int, y: int) -> None:
    """Tap at screen pixel (x, y) using raw kernel sendevent."""
    touch = find_touch_device(device)
    if touch is None:
        raise LookupError("No multitouch input device found")
    dev, max_x, max_y = touch
    info = device.info
    screen_w = info["displayWidth"]
    screen_h = info["displayHeight"]
    assert isinstance(screen_w, int) and isinstance(screen_h, int)
    dx = int(x / screen_w * max_x)
    dy = int(y / screen_h * max_y)
    script = "\n".join(
        [
            "#!/system/bin/sh",
            f"sendevent {dev} 3 47 0",  # ABS_MT_SLOT=0
            f"sendevent {dev} 3 57 1",  # ABS_MT_TRACKING_ID=1 (touch down)
            f"sendevent {dev} 3 48 100",  # ABS_MT_TOUCH_MAJOR=100
            f"sendevent {dev} 3 58 512",  # ABS_MT_PRESSURE=512
            f"sendevent {dev} 3 53 {dx}",  # ABS_MT_POSITION_X
            f"sendevent {dev} 3 54 {dy}",  # ABS_MT_POSITION_Y
            f"sendevent {dev} 1 330 1",  # BTN_TOUCH=1 (finger down)
            f"sendevent {dev} 0 0 0",  # SYN_REPORT
            f"sendevent {dev} 3 47 0",  # ABS_MT_SLOT=0
            f"sendevent {dev} 3 57 4294967295",  # ABS_MT_TRACKING_ID=-1 (touch up)
            f"sendevent {dev} 1 330 0",  # BTN_TOUCH=0 (finger up)
            f"sendevent {dev} 0 0 0",  # SYN_REPORT
        ]
    )
    device.shell(
        f"printf '%s\\n' '{script}'"
        f" > /data/local/tmp/tap.sh"
        f" && chmod +x /data/local/tmp/tap.sh"
        f" && /data/local/tmp/tap.sh"
    )
