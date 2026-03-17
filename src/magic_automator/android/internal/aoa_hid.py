"""
AOA2 HID touchscreen — tap at absolute pixel coordinates via USB, no root required.

Protocol reference: https://source.android.com/docs/core/interaction/accessories/aoa2
HID descriptor reference: https://www.usb.org/document-library/device-class-definition-hid-111
"""

from __future__ import annotations

import struct
import time
from typing import cast

import uiautomator2 as u2
import usb.core
import usb.util

# AOA2 USB control transfer request codes
ACCESSORY_REGISTER_HID = 54
ACCESSORY_UNREGISTER_HID = 55
ACCESSORY_SET_HID_REPORT_DESC = 56
ACCESSORY_SEND_HID_EVENT = 57

CTRL_OUT_VENDOR = usb.util.CTRL_OUT | usb.util.CTRL_TYPE_VENDOR  # 0x40

TIMEOUT_MS = 1000
HID_ID = 1

# Single-touch digitizer HID report descriptor with contact count + contact ID.
# Report format (7 bytes):
#   [contact_count: u8, tip_switch + in_range + 6 bits padding: u8,
#    contact_id: u8, X: u16 LE, Y: u16 LE]
# Logical range 0–32767 for both axes.
TOUCH_REPORT_DESC = bytes(
    [
        0x05,
        0x0D,  # Usage Page (Digitizer)
        0x09,
        0x04,  # Usage (Touch Screen)
        0xA1,
        0x01,  # Collection (Application)
        # Contact count
        0x09,
        0x54,  #   Usage (Contact Count)
        0x15,
        0x00,  #   Logical Minimum (0)
        0x25,
        0x01,  #   Logical Maximum (1)
        0x75,
        0x08,  #   Report Size (8)
        0x95,
        0x01,  #   Report Count (1)
        0x81,
        0x02,  #   Input (Data, Variable, Absolute)
        0x09,
        0x22,  #   Usage (Finger)
        0xA1,
        0x02,  #   Collection (Logical)
        # Tip switch
        0x09,
        0x42,  #     Usage (Tip Switch)
        0x15,
        0x00,  #     Logical Minimum (0)
        0x25,
        0x01,  #     Logical Maximum (1)
        0x75,
        0x01,  #     Report Size (1)
        0x95,
        0x01,  #     Report Count (1)
        0x81,
        0x02,  #     Input (Data, Variable, Absolute)
        # In Range
        0x09,
        0x32,  #     Usage (In Range)
        0x81,
        0x02,  #     Input (Data, Variable, Absolute)
        # Padding (6 bits)
        0x95,
        0x06,  #     Report Count (6)
        0x81,
        0x03,  #     Input (Constant, Variable)
        # Contact ID
        0x09,
        0x51,  #     Usage (Contact Identifier)
        0x75,
        0x08,  #     Report Size (8)
        0x95,
        0x01,  #     Report Count (1)
        0x15,
        0x00,  #     Logical Minimum (0)
        0x25,
        0x01,  #     Logical Maximum (1)
        0x81,
        0x02,  #     Input (Data, Variable, Absolute)
        # X
        0x05,
        0x01,  #     Usage Page (Generic Desktop)
        0x09,
        0x30,  #     Usage (X)
        0x15,
        0x00,  #     Logical Minimum (0)
        0x26,
        0xFF,
        0x7F,  #     Logical Maximum (32767)
        0x75,
        0x10,  #     Report Size (16)
        0x95,
        0x01,  #     Report Count (1)
        0x81,
        0x02,  #     Input (Data, Variable, Absolute)
        # Y
        0x09,
        0x31,  #     Usage (Y)
        0x15,
        0x00,  #     Logical Minimum (0)
        0x26,
        0xFF,
        0x7F,  #     Logical Maximum (32767)
        0x75,
        0x10,  #     Report Size (16)
        0x95,
        0x01,  #     Report Count (1)
        0x81,
        0x02,  #     Input (Data, Variable, Absolute)
        0xC0,  #   End Collection
        0xC0,  # End Collection
    ]
)


class Hid:
    """
    Registers as a USB HID touchscreen via AOA2 and sends absolute tap events.

    Requires USB access to the Android device (udev rule or root on host).
    Does NOT require root on the Android device.
    """

    def __init__(self, device: u2.Device):
        info = cast(dict[str, object], device.info)
        screen_width = info["displayWidth"]
        screen_height = info["displayHeight"]
        assert isinstance(screen_width, int) and isinstance(screen_height, int)
        self._screen_width = screen_width
        self._screen_height = screen_height
        usb_dev = find_usb_device(cast(str, device.serial))
        if usb_dev is None:
            raise LookupError(f"No USB device for serial {device.serial!r}")
        self._dev = usb_dev
        self._registered = False
        self._register()

    def _ctrl(self, request: int, value: int, index: int, data: bytes | None = None) -> None:
        self._dev.ctrl_transfer(
            CTRL_OUT_VENDOR,
            request,
            value,
            index,
            data_or_wLength=data if data is not None else 0,
            timeout=TIMEOUT_MS,
        )

    def _register(self) -> None:
        self._ctrl(ACCESSORY_REGISTER_HID, HID_ID, len(TOUCH_REPORT_DESC))
        self._ctrl(ACCESSORY_SET_HID_REPORT_DESC, HID_ID, 0, TOUCH_REPORT_DESC)
        self._registered = True

    def _send_report(self, contact_count: int, tip_in_range: int, x: int, y: int) -> None:
        report = struct.pack("<BBBHH", contact_count, tip_in_range, 0, x, y)
        self._ctrl(ACCESSORY_SEND_HID_EVENT, HID_ID, 0, report)

    def _to_hid(self, x: int, y: int) -> tuple[int, int]:
        return int(x / self._screen_width * 32767), int(y / self._screen_height * 32767)

    def down(self, x: int, y: int) -> None:
        """Finger down at screen pixel coordinates."""
        self._send_report(1, 0x03, *self._to_hid(x, y))

    def move_to(self, x: int, y: int) -> None:
        """Move finger to screen pixel coordinates (must be down)."""
        self._send_report(1, 0x03, *self._to_hid(x, y))

    def up(self, x: int, y: int) -> None:
        """Finger up at screen pixel coordinates."""
        self._send_report(0, 0x00, *self._to_hid(x, y))

    def tap(self, x: int, y: int, duration: float = 0.05) -> None:
        """Tap at screen pixel coordinates."""
        self.down(x, y)
        time.sleep(duration)
        self.up(x, y)

    def close(self) -> None:
        if self._registered:
            self._ctrl(ACCESSORY_UNREGISTER_HID, HID_ID, 0)
            self._registered = False

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def hid_tap(device: u2.Device, x: int, y: int) -> None:
    """Tap at screen pixel (x, y) via AOA2 USB HID. No root required."""
    with Hid(device) as hid:
        hid.tap(x, y)


def find_usb_device(serial: str) -> usb.core.Device | None:
    """Find a USB device by its serial number string."""
    devices = usb.core.find(find_all=True)
    if devices is None:
        return None
    for dev in devices:
        assert isinstance(dev, usb.core.Device)
        try:
            if usb.util.get_string(dev, getattr(dev, "iSerialNumber")) == serial:
                return dev
        except (usb.core.USBError, ValueError):
            continue
    return None
