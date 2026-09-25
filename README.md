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

## TODO

### Printer and Raspberry Pi

- [ ] Connect the existing original Raspberry Pi Model B to the printer over USB and prove it can print one ticket.
- [ ] Check the Pi's supported Python version and USB printing approach; the current project requires Python 3.13 and the test script uses a fixed CUPS backend path.
- [ ] Keep the Pi running continuously and start its print service automatically after a reboot.
- [ ] Have the Pi fetch jobs from the hosted service over an outbound connection, without opening the home network to incoming connections.

### Hosted web app

- [ ] Choose hosting for the web app and persistent queue, independent of the Pi so tasks can be submitted while it is offline.
- [ ] Sort out Firebase for `todo.railton.dev`
- [ ] Create a very minimal web app that can print "Hello, World!" remotely.
- [ ] Support Chrome on phone and desktop.
- [ ] Add Google sign-in and restrict access to my Google account only; this is a single-user app.

### Task entry and ticket format

- [ ] Add a small multiline text box for the task, with automatic wrapping on the printed ticket.
- [ ] Add an optional category dropdown: Work, Council, Life Admin.
- [ ] Add an optional date-only deadline, printed with an ordinal day and abbreviated month, e.g. `26th Sept 2026`.
- [ ] Print the deadline on the ticket only; no reminders or scheduled printing.
- [ ] Submit for printing immediately when the form is sent, rather than holding tasks for a separate print action.

### Queue and history

- [ ] Save submitted jobs in a persistent queue.
- [ ] Flag when the printer is unavailable and show that the submitted job is queued.
- [ ] Print queued jobs automatically when the printer becomes available.
- [ ] Retain a very simple print history with job status.

## Stuff not dealing with yet

- A connection drops after a job is sent, leaving it unclear whether the ticket printed. Handling this uncertainty and preventing duplicate prints on retry are deferred.
- Decide how printer availability and job statuses will be detected and reported.
- Decide how to handle characters the printer's selected character set cannot represent.