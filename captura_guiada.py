import asyncio
import csv
from collections import Counter
from datetime import datetime

from bleak import BleakScanner

SCALE_MAC = "70:87:9E:35:9D:F0"  # the MAC address we found with bluetoothctl
OUT_FILE = "capture_log.txt"
SUMMARY_FILE = "summary.csv"

PHASES = [
    ("PHASE 1", "EMPTY SCALE", "Make sure nobody is on the scale and press Enter", None, 12),
    ("PHASE 2", "NORMAL WEIGHING", "Step on. When the LCD settles, type the weight it shows:", "lcd", 15),
    ("PHASE 3", "KNOWN WEIGHT", "Step off, grab the bottle, step back on with it. Weight on the LCD:", "lcd", 15),
    ("PHASE 4", "REBOOT", "Step off, remove the batteries for 3 seconds, put them back and press Enter", None, 20),
    ("PHASE 5", "WEIGHT REMOVED", "Step on, wait until it settles and step off. Press Enter once you step off", None, 15),
]

packets = []
repeats = 0
out_file = None
counters = {"total": 0, "scale": 0}


def flush_packet():
    global repeats
    if not packets:
        return
    p = packets[-1]
    t = datetime.now().strftime("%H:%M:%S")
    suffix = f" (x{repeats + 1})" if repeats > 0 else ""
    line = f"[{t}] RSSI {p['rssi']} dBm | {p['hex']}{suffix}"
    print(line)
    if out_file:
        out_file.write(line + "\n")
        out_file.flush()
    repeats = 0


def on_packet(device, adv_data):
    global repeats
    try:
        counters["total"] += 1
        if device.address.upper() != SCALE_MAC:
            return
        counters["scale"] += 1
        for uuid, payload in adv_data.service_data.items():
            if "181d" not in str(uuid).lower():
                continue
            hex_data = " ".join(f"{b:02x}" for b in payload)
            if packets and packets[-1]["hex"] == hex_data:
                repeats += 1
                return
            flush_packet()
            packets.append({"hex": hex_data, "rssi": adv_data.rssi})
    except Exception as error:
        print(f"[!] callback error: {error}")


def analyze_phase(phase_id, lcd_value):
    result = {"phase": phase_id, "lcd": lcd_value, "hex": "-", "reps": 0}
    if not packets:
        return result
    most_common = Counter(p["hex"] for p in packets).most_common(1)[0][0]
    result["hex"] = most_common
    result["reps"] = sum(1 for p in packets if p["hex"] == most_common)
    return result


async def main():
    global out_file, packets, repeats

    scanner = BleakScanner(detection_callback=on_packet)
    await scanner.start()

    with open(OUT_FILE, "a", encoding="utf-8") as f:
        out_file = f
        header = f"\n=== Guided session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | MAC {SCALE_MAC} ===\n"
        f.write(header)
        print(header.rstrip())

        results = []
        try:
            for phase_id, title, prompt, kind, seconds in PHASES:
                packets = []
                repeats = 0
                counters["total"] = 0
                counters["scale"] = 0
                print(f"\n{'=' * 60}\n{phase_id} | {title}")

                lcd_value = None
                if kind == "lcd":
                    lcd_value = (await asyncio.to_thread(input, f"{prompt} ")).strip().replace(",", ".")
                else:
                    await asyncio.to_thread(input, f"{prompt} (press Enter)")

                phase_header = f"\n### {phase_id} | {title}" + (f" | LCD: {lcd_value}" if lcd_value else "") + "\n"
                f.write(phase_header)
                print(phase_header.rstrip())

                print(f"> capturing {seconds}s...")
                try:
                    await scanner.stop()
                except Exception:
                    pass
                await scanner.start()
                await asyncio.sleep(seconds)
                flush_packet()
                print(f"> packets seen: {counters['total']} (from the scale: {counters['scale']})")

                results.append(analyze_phase(phase_id, lcd_value))
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nSession stopped.")
        finally:
            await scanner.stop()

    print(f"\n{'=' * 60}\nSESSION SUMMARY\n{'=' * 60}")
    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as c:
        writer = csv.writer(c)
        writer.writerow(["phase", "lcd", "most_common_hex", "repeats"])
        for r in results:
            writer.writerow([r["phase"], r["lcd"], r["hex"], r["reps"]])
            print(f"{r['phase']:<8} | LCD: {str(r['lcd']):<7} | most common hex: {r['hex']:<28} | repeats: {r['reps']}")

    print(f"\nFull log in {OUT_FILE} | Table in {SUMMARY_FILE}")


if __name__ == "__main__":
    asyncio.run(main())