# Remove Post-it printer

Prints tickets out with web-connected thermal printer. Because I can't write TODO Post-it notes if I'm not at my desk.

## Setup

```bash
uv sync --locked
```

Create a `.env` file in the project root containing the USB printer address:

```dotenv
DEVICE_URI=usb://Printer/POS-80?serial=YOUR_PRINTER_SERIAL
```

## Print a test receipt

```bash
uv run scripts/hello_world.py
```
