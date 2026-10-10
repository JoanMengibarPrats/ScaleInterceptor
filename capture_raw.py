import asyncio
from bleak import BleakScanner

MAC = "70:87:9E:35:9D:F0"  # the MAC address we found with bluetoothctl

def on_packet(device, adv_data):
    # only care about our scale
    if device.address.upper() != MAC:
        return

    # an advertisement can contain several data sections
    for uuid, payload in adv_data.service_data.items():
        print(f"[{uuid}]  {payload.hex(' ')}")

async def main():
    scanner = BleakScanner(detection_callback=on_packet)
    await scanner.start()

    while True:
        await asyncio.sleep(1)

asyncio.run(main())