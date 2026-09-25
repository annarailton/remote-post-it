"""Get the connected printer to print 'Hello, World!'

To run: 

    uv run scripts/hello_world.py
"""

import getpass
import os
from pathlib import Path
import subprocess
import tempfile

from dotenv import load_dotenv
from pyboxen import boxen

MESSAGE = "Hello, World!"

def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    device_uri = os.environ.get("DEVICE_URI")
    if not device_uri:
        raise SystemExit("Set DEVICE_URI in the project .env file or environment.")

    box = boxen(MESSAGE, style="square", padding=(1, 2), color="")
    # Remove terminal-width padding so it cannot wrap onto extra receipt lines
    box = "\n".join(line.rstrip() for line in box.splitlines()) + "\n"

    # Initialise, select CP437, print, feed ten lines, then cut.
    # \x1bt\x00 selects CP437: \x1b is ESC, t selects the code table, and \x00 selects table 0.
    # \x1bd is the ESC/POS feed-lines command; \x0a is hexadecimal for 10.
    receipt = b"\x1b@\x1bt\x00" + box.encode("cp437") + b"\x1bd\x0a\x1dV\x01"
    with tempfile.NamedTemporaryFile(suffix=".escpos") as spool:
        spool.write(receipt)
        spool.flush()
        result = subprocess.run(
            [
                "/usr/libexec/cups/backend/usb",
                "1",
                getpass.getuser(),
                "Hello, World",
                "1",
                "",
                spool.name,
            ],
            env={**os.environ, "DEVICE_URI": device_uri},
            timeout=30,
            check=True,
        )
    print(f"USB print backend completed successfully (exit {result.returncode}).")


if __name__ == "__main__":
    main()
