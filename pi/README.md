# Pi printer service

Run as `pi` with Python 3.7+, `openssl`, internet access and the USB printer at `/dev/usb/lp0`. No Python packages are needed.

## Setup

Clone the repo on the Pi or `scp` over the `pi` directory.

```bash
git clone https://github.com/annarailton/remote-post-it.git /home/pi/remote-post-it
```

Place the Firestore service-account key at `/home/pi/.config/remote-post-it/service-account.json`, outside the repo. For a replacement key, use the existing `ticket-printer` service account in `remote-post-it-47117`, which has `datastore.entities.get`, `datastore.entities.list` and `datastore.entities.update` permissions. The repo's Firestore indexes must be deployed.

```bash
chmod 700 /home/pi/.config/remote-post-it
chmod 600 /home/pi/.config/remote-post-it/service-account.json
sudo install -m 644 /home/pi/remote-post-it/pi/ticket-printer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ticket-printer   # service starts automatically at boot
systemctl status ticket-printer --no-pager
```

The service runs as `pi` with printer group `lp`, prints queued tickets and starts automatically at boot.

## Updates and logs

After updating the repo:

```bash
sudo systemctl restart ticket-printer
```

Follow logs with `journalctl -u ticket-printer -f`. Stop with `sudo systemctl stop ticket-printer`.
