# ScaleInterceptor

Passive BLE sniffer for the **Xiaomi Mi Smart Scale 2** (XMTZC04HM).

The scale broadcasts every measurement over BLE advertisements (service `0x181D`) **without any authentication**. This script passively listens for those frames, decodes the weight and logs each stabilized weighing to a CSV file — exactly once per event.

This tool is part of a full reverse-engineering write-up: [blog post](https://joanmengibarprats.com/blog/smart_scale).

## Requirements

- Python 3.9+
- A Linux machine with a Bluetooth adapter (BLE passive scanning requires root privileges)
- `bleak`

## Installation

```bash
# Option A: system package (Debian/Kali)
sudo apt install python3-bleak

# Option B: virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Find your scale (guided discovery)

Run without `--mac` (or with `--discover`): the tool watches the air with a single fresh watcher while you step on the scale, detects your weight and prints the MAC address:

```bash
sudo python3 scale_interceptor.py --discover
```

```
============================================================
DISCOVERY | Let's find your scale
============================================================

STEP 1 | Make sure nobody is on the scale, then press Enter

STEP 2 | Watcher started - step on the scale NOW and stay on it.
  ads: 12
Scale detected! 70:87:9E:35:9D:F0 | 76.90 kg
============================================================
SCALE FOUND: 70:87:9E:35:9D:F0
Use it with: python scale_interceptor.py --mac 70:87:9E:35:9D:F0
============================================================
```

### Sniffer mode

```bash
sudo python3 scale_interceptor.py --mac 70:87:9E:35:9D:F0
```

Step on the scale and every stabilized weighing will be printed and logged to `mi_peso.csv`:

```
Listening for the scale... (Ctrl+C to exit)
77.60 kg
80.35 kg
2 weighing(s) saved to mi_peso.csv
```

Only stabilized weighings with the load present are logged. Frames flagged as *load removed* keep the last weight briefly, so they are ignored.

### Options

| Flag        | Default       | Description                          |
|-------------|---------------|--------------------------------------|
| `--mac`     | none          | Scale MAC address — run without it to scan first |
| `--csv`     | `mi_peso.csv` | Output CSV file                      |
| `--quiet`   | off           | Only write the CSV, print nothing    |
| `--discover`| off           | Guided discovery to identify your scale |
| `-t`        | `60`          | Watch duration per attempt in seconds   |

CSV format:

```csv
timestamp,weight_kg
2026-10-07 19:31:12,78.05
```

Exit with Ctrl+C: the scanner stops gracefully and prints how many weighings were saved, on both Linux and Windows.

## Protocol

The scale broadcasts Xiaomi's service data under the Weight Scale service UUID `0x181D`:

| Bytes  | Meaning                                                       |
|--------|---------------------------------------------------------------|
| `[0]`  | Control byte — bit 5 (`0x20`) = stabilized, bit 7 (`0x80`) = load removed |
| `[1:3]`| Weight, little-endian, divided by `200` (5 g per raw unit)    |
| `[3:5]`| Year, little-endian (`1970` when the clock was never synced)  |
| `[5]`  | Month (1-12)                                                  |
| `[6]`  | Day (1-31)                                                    |
| `[7]`  | Hour                                                          |
| `[8]`  | Minute                                                        |
| `[9]`  | Second                                                        |

Example: `a2 fa 3c b2 07 01 01 02 27 1e` → control `0xA2` (stabilized, load removed), weight `0x3CFA` = 15610 → `78.05 kg`, scale clock `1970-01-01 02:39:30` (never synced).

Notes from real captures:
- While settling, the scale emits frames with the stabilized bit clear and a drifting weight — store only the stabilized ones.
- *Load removed* frames keep the last weight briefly, then drop to ~0.1 kg. Treat them as "nobody on the scale".
- The control byte `0x02` (bit 1 set) was observed while the weight fluctuates; it is not documented in the reference below.
- The byte-order detail: the same weight travels **big-endian** over the scale's internal UART bus (`15 9A`) and **little-endian** over BLE (`9A 15`).

Reference: [Xiaomi scale advertisement protocol](https://github.com/Ash-2k3/Scale/).

## Running the tests

```bash
python -m unittest tests/test_parser.py
```

## License

[MIT](LICENSE)
