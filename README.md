# ScaleInterceptor

Passive BLE sniffer for the **Xiaomi Mi Smart Scale 2** (XMTZC04HM).

This repository accompanies a full reverse-engineering write-up of the scale:
hardware teardown, UART protocol analysis, BLE advertisement decoding and the
reasoning behind every byte of the frame.

**→ [Blog post: Smart Scale Reverse Engineering](https://joanmengibarprats.com/blog/smart_scale)**

## Scripts

| Script | Role in the write-up |
|---|---|
| `capture_raw.py` | First capture tool: dumps raw advertisement bytes as they arrive |
| `captura_guiada.py` | Guided experiment session: isolates one variable per phase |
| `scale_interceptor.py` | Final tool: identifies the scale (guided discovery) and logs stabilized weighings to a CSV |

## Quick start

```bash
pip install bleak
python scale_interceptor.py            # guided discovery: step on the scale to find its MAC
python scale_interceptor.py --help
python scale_interceptor.py --mac 70:87:9E:35:9D:F0    # log weighings to mi_peso.csv
More reverse engineering
- Firmware Extraction guide (https://joanmengibarprats.com/blog/firmware_extraction)
