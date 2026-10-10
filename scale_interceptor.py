#!/usr/bin/env python3
"""Passive sniffer for the Xiaomi Mi Smart Scale 2 (XMTZC04HM).

Listens for BLE advertisement packets of the 0x181D service (Weight Scale),
extracts the weight and logs each stabilized weighing to a CSV file,
exactly once per event.

Run it without arguments to scan and find your scale first, then pass its
MAC address to start logging:

Usage:
    sudo python3 scale_interceptor.py --discover
    sudo python3 scale_interceptor.py --mac 70:87:9E:35:9D:F0 [--csv mi_peso.csv] [--quiet]
"""

import argparse
import asyncio
import csv
import datetime
from pathlib import Path

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

SERVICE_UUID = "181D"
STABILIZED_BIT = 0x20  # 0010 0000: bit 5 of the control byte
LOAD_REMOVED_BIT = 0x80  # 1000 0000: bit 7 of the control byte
KG_FACTOR = 0.005  # Xiaomi conversion factor (raw / 200)


def has_scale_service(uuid: str) -> bool:
    """True if the given service UUID is the Weight Scale service (181d), case-insensitive."""
    return SERVICE_UUID in str(uuid).upper()


def parse_xiaomi_scale(payload: bytes) -> dict | None:
    """Parse a 0x181D service data payload.

    Format:
        [0]    control byte (bit 5 = weight stabilized, bit 7 = load removed)
        [1:3]  weight, little-endian, divided by 200
        [3:5]  year, little-endian (1970 when the clock was never synced)
        [5]    month (1-12)
        [6]    day (1-31)
        [7]    hour
        [8]    minute
        [9]    second

    Returns None if the payload is too short to be a valid frame.
    """
    if len(payload) < 3:
        return None

    control = payload[0]
    raw = int.from_bytes(payload[1:3], byteorder="little")

    scale_time = None
    if len(payload) >= 10:
        year = int.from_bytes(payload[3:5], byteorder="little")
        month, day, hour, minute, second = payload[5:10]
        scale_time = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"

    return {
        "control": control,
        "raw": raw,
        "is_stabilized": bool(control & STABILIZED_BIT),
        "load_removed": bool(control & LOAD_REMOVED_BIT),
        "weight_kg": round(raw * KG_FACTOR, 2),
        "scale_time": scale_time,
    }


class ScaleLogger:
    """Logs each stabilized weighing to a CSV file, without duplicates."""

    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self._last_saved_kg: float | None = None
        self._last_stabilized = False
        self._header_written = csv_path.exists()
        self.weighings_saved = 0

    def process(self, device: BLEDevice, adv_data: AdvertisementData, mac: str, quiet: bool) -> None:
        if device.address.upper() != mac.upper():
            return

        for uuid, payload in adv_data.service_data.items():
            if not has_scale_service(uuid):
                continue

            data = parse_xiaomi_scale(payload)
            if data is None:
                continue

            self._maybe_save(data, quiet)
            self._last_stabilized = data["is_stabilized"]

    def _maybe_save(self, data: dict, quiet: bool) -> None:
        # New weighing event: stabilized, load present, weight different from the last one saved
        is_new_event = (
            data["is_stabilized"]
            and not data["load_removed"]
            and data["weight_kg"] > 0
            and (data["weight_kg"] != self._last_saved_kg or not self._last_stabilized)
        )
        if not is_new_event:
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not self._header_written:
                writer.writerow(["timestamp", "weight_kg"])
                self._header_written = True
            writer.writerow([timestamp, f"{data['weight_kg']:.2f}"])

        self._last_saved_kg = data["weight_kg"]
        self.weighings_saved += 1
        if not quiet:
            print(f"{data['weight_kg']:.2f} kg")


async def discover(timeout: int) -> None:
    """Guided discovery: identify the scale's MAC address automatically."""
    print("=" * 60)
    print("DISCOVERY | Let's find your scale")
    print("=" * 60)

    # No scanning yet: the radio must stay fresh for the measuring window
    await asyncio.to_thread(input, "\nSTEP 1 | Make sure nobody is on the scale, then press Enter")

    found = {"mac": None, "weight": None}
    per_dev: dict = {}

    def watch_callback(device: BLEDevice, adv_data: AdvertisementData) -> None:
        addr = device.address.upper()
        per_dev[addr] = per_dev.get(addr, 0) + 1
        if found["mac"] is not None:
            return
        for uuid, payload in (adv_data.service_data or {}).items():
            if not has_scale_service(uuid):
                continue
            data = parse_xiaomi_scale(payload)
            if data is None:
                continue
            found["mac"] = addr
            found["weight"] = data["weight_kg"]
            print(f"\nScale detected! {found['mac']} | {found['weight']:.2f} kg")

    scanner = BleakScanner(detection_callback=watch_callback)
    try:
        await scanner.start()
    except BleakError:
        print("Bluetooth is not available. Check that the adapter is on and retry.")
        return

    try:
        print("\nSTEP 2 | Warming up the watcher...")
        warm = 0
        while sum(per_dev.values()) == 0 and warm < 15:
            await asyncio.sleep(1)
            warm += 1
        if sum(per_dev.values()) == 0:
            print("The watcher is not receiving anything. Check that Bluetooth is on and retry.")
            return
        print(f"Watcher ready (ads: {sum(per_dev.values())}). Step on the scale NOW and stay on it.")

        rounds = 0
        while found["mac"] is None and rounds < 2:
            slept = 0
            while slept < timeout and found["mac"] is None:
                await asyncio.sleep(1)
                slept += 1
                if slept % 10 == 0:
                    print(f"  ads: {sum(per_dev.values())}")
            if found["mac"] is None:
                await asyncio.to_thread(
                    input,
                    "\nNot found yet. Step OFF the scale and step ON again to wake it up, then press Enter",
                )
                print("> watching again...")
            rounds += 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        try:
            await scanner.stop()
        except Exception:
            pass

    if found["mac"] is None:
        print("\nCould not detect any weight data.")
        total = sum(per_dev.values())
        if total == 0:
            print("No advertisements at all: check that Bluetooth is on and the adapter is in range.")
        else:
            print(f"Advertisements seen: {total}")
            for addr, count in sorted(per_dev.items(), key=lambda kv: kv[1], reverse=True)[:5]:
                print(f"  {addr}: {count} ads")
            print("None of them carried weight data (181d).")
            print("Make sure the LCD lights up when you step on and stay on it while")
            print("it measures. Low batteries can also weaken the radio.")
        return

    print("=" * 60)
    print(f"SCALE FOUND: {found['mac']} | {found['weight']:.2f} kg")
    print(f"Use it with: python scale_interceptor.py --mac {found['mac']}")
    print("=" * 60)


async def run_sniffer(args: argparse.Namespace) -> None:
    logger = ScaleLogger(Path(args.csv))

    if not args.quiet:
        print("Listening for the scale... (Ctrl+C to exit)")

    def callback(device: BLEDevice, adv_data: AdvertisementData) -> None:
        try:
            logger.process(device, adv_data, args.mac, args.quiet)
        except Exception:
            pass

    scanner = BleakScanner(detection_callback=callback)
    try:
        await scanner.start()
    except BleakError:
        print("Bluetooth is not available. Check that the adapter is on and retry.")
        return

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        try:
            await scanner.stop()
        except Exception:
            pass

    if not args.quiet:
        print(f"{logger.weighings_saved} weighing(s) saved to {args.csv}")


async def main(args: argparse.Namespace) -> None:
    if args.discover or args.mac is None:
        await discover(args.timeout)
    else:
        await run_sniffer(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Passive BLE sniffer for the Xiaomi Mi Smart Scale 2",
        epilog=(
            "Examples:\n"
            "  python scale_interceptor.py\n"
            "  python scale_interceptor.py --discover -t 30\n"
            "  python scale_interceptor.py --mac 70:87:9E:35:9D:F0\n"
            "  python scale_interceptor.py --mac 70:87:9E:35:9D:F0 --csv weight_log.csv\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mac", default=None, help="Scale MAC address (run without it to scan first)")
    parser.add_argument("--csv", default="mi_peso.csv", help="Output CSV file")
    parser.add_argument("--quiet", action="store_true", help="Do not print weights, only write the CSV")
    parser.add_argument("--discover", action="store_true", help="Guided discovery to identify your scale")
    parser.add_argument("-t", "--timeout", type=int, default=60, help="Watch duration per attempt in seconds")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
