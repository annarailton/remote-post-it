#!/usr/bin/env python3
"""Single-printer worker for Python 3.7+. This code lives on the Raspberry Pi"""

import argparse
import base64
import datetime
import fcntl
import json
import logging
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, NoReturn, Optional, Union, cast

LOG = logging.getLogger('ticket-printer')
STOP = threading.Event()
TOKEN_URL = 'https://oauth2.googleapis.com/token'
API = 'https://firestore.googleapis.com/v1/'
PROJECT_ID = 'remote-post-it-47117'
PRINTER_DEVICE = '/dev/usb/lp0'

# JSON at the REST boundary is heterogeneous; keep concrete types elsewhere.
Document = Dict[str, Any]
Fields = Dict[str, Dict[str, Any]]


class ApiError(Exception):
    """An HTTP failure with a status code but no sensitive response content."""
    def __init__(self, code: int) -> None:
        """Initialise an API error.

        Args:
            code: HTTP status code returned by Google.
        """
        self.code = code
        super().__init__('Google API returned HTTP {}'.format(code))


def request_json(
    url: str, body: Optional[bytes], headers: Optional[Dict[str, str]] = None,
    method: str = 'POST',
) -> Any:
    """Send an HTTP request and decode its JSON response.

    Args:
        url: Endpoint URL.
        body: Encoded request body as bytes, or None for no body.
        headers: Optional mapping of HTTP headers.
        method: HTTP method

    Returns:
        The decoded JSON response, usually a dictionary or list.

    Raises:
        ApiError: The server returns an HTTP error status.
        urllib.error.URLError: The connection fails.
        OSError: A socket operation fails or times out.
        ValueError: The response is not valid JSON.
    """
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Do not log request bodies, tokens, keys or personal ticket text.
        raise ApiError(error.code) from None


def b64(value: bytes) -> bytes:
    """Encode bytes as unpadded URL-safe Base64 for a JWT.

    Args:
        value: Bytes to encode.

    Returns:
        URL-safe Base64 bytes without trailing padding.
    """
    return base64.urlsafe_b64encode(value).rstrip(b'=')


class ServiceAccount:
    """Load a service-account key and cache short-lived OAuth access tokens."""
    def __init__(self, path: Union[str, Path], project: str) -> None:
        """Load credentials for the expected Firebase project.

        Args:
            path: Path to the service-account JSON key file.
            project: Expected Google Cloud project ID.

        Raises:
            OSError: The key file cannot be read.
            ValueError: JSON is invalid or credentials do not match the project.
        """
        with open(path) as stream:
            self.key: Dict[str, str] = json.load(stream)
        if self.key.get('type') != 'service_account' or self.key.get('project_id') != project:
            raise ValueError('Use a service-account key from the configured Firebase project.')
        self.token: Optional[str] = None
        self.expires: float = 0

    def access_token(self) -> str:
        """Return a cached token or obtain a fresh one using OpenSSL signing.

        Returns:
            A Google OAuth access-token string with the datastore scope.

        Raises:
            KeyError: Required credential or token-response fields are missing.
            OSError: A key-file, OpenSSL launch or network operation fails.
            subprocess.SubprocessError: Signing fails or exceeds its timeout.
            ApiError: Google rejects the token request.
            ValueError: The token response is malformed.
        """
        if self.token and time.monotonic() < self.expires:
            return self.token
        now = int(time.time())
        header = {'alg': 'RS256', 'typ': 'JWT', 'kid': self.key['private_key_id']}
        claims = {'iss': self.key['client_email'], 'scope': 'https://www.googleapis.com/auth/datastore',
                  'aud': TOKEN_URL, 'iat': now, 'exp': now + 3600}
        unsigned = b'.'.join(b64(json.dumps(part).encode('utf-8')) for part in (header, claims))
        # NamedTemporaryFile is private (0600). OpenSSL performs RSA signing;
        # no compiled Python crypto dependencies are needed on the ARMv6 Pi.
        with tempfile.NamedTemporaryFile() as key_file:
            key_file.write(self.key['private_key'].encode('ascii'))
            key_file.flush()
            signed = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', key_file.name],
                                    input=unsigned, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    check=True, timeout=15).stdout
        assertion = (unsigned + b'.' + b64(signed)).decode('ascii')
        result = request_json(TOKEN_URL, urllib.parse.urlencode({
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': assertion,
        }).encode('ascii'), {'Content-Type': 'application/x-www-form-urlencoded'})
        self.token = cast(str, result['access_token'])
        self.expires = time.monotonic() + int(result['expires_in']) - 60
        return self.token


class Firestore:
    """Access the default Firestore database through its REST API."""
    def __init__(self, project: str, credentials: ServiceAccount) -> None:
        """Configure the database path and token provider.

        Args:
            project: Google Cloud project ID.
            credentials: ServiceAccount used to obtain OAuth access tokens.
        """
        self.root = 'projects/{}/databases/(default)/documents'.format(project)
        self.credentials = credentials

    def request(self, path: str, payload: Dict[str, Any], method: str = 'POST') -> Any:
        """Send an authenticated JSON request, refreshing once after HTTP 401.

        Args:
            path: Resource path relative to the Firestore v1 API, including any query.
            payload: JSON-serialisable request data.
            method: HTTP method, defaulting to POST.

        Returns:
            The decoded JSON response.

        Raises:
            ApiError: The request fails, including a repeated authentication failure.
            OSError: A credential or network operation fails.
            ValueError: Request or response data cannot be encoded or decoded.
            subprocess.SubprocessError: Access-token signing fails.
        """
        for attempt in range(2):
            try:
                return request_json(API + path, json.dumps(payload).encode('utf-8'), {
                    'Authorization': 'Bearer ' + self.credentials.access_token(),
                    'Content-Type': 'application/json',
                }, method)
            except ApiError as error:
                if error.code != 401 or attempt:
                    raise
                self.credentials.expires = 0

    def next_job(self) -> Optional[Document]:
        """Fetch the oldest queued ticket without claiming or changing it.

        Returns:
            A Firestore document dictionary, or None when the queue is empty.

        Raises:
            ApiError: Firestore rejects the query.
        """
        result = self.request(self.root + ':runQuery', {'structuredQuery': {
            'from': [{'collectionId': 'jobs'}],
            'where': {'fieldFilter': {'field': {'fieldPath': 'status'}, 'op': 'EQUAL',
                                      'value': {'stringValue': 'queued'}}},
            'orderBy': [{'field': {'fieldPath': 'submittedAt'}, 'direction': 'ASCENDING'}],
            'limit': 1,
        }})
        return next((entry['document'] for entry in result if 'document' in entry), None)

    def update(self, document: Document, fields: Fields) -> Document:
        """Update selected fields only if the document has not changed.

        Args:
            document: Firestore document containing its name and updateTime.
            fields: Mapping of field names to Firestore REST typed values.

        Returns:
            The updated document, including its new updateTime.

        Raises:
            ApiError: The write fails, including a failed update-time precondition.
            KeyError: The document lacks name or updateTime.
        """
        # Compare-and-set prevents two workers claiming the same queue entry.
        params = [('updateMask.fieldPaths', field) for field in fields]
        params.append(('currentDocument.updateTime', document['updateTime']))
        return cast(Document, self.request(document['name'] + '?' + urllib.parse.urlencode(params),
                                           {'fields': fields}, 'PATCH'))


def value(document: Document, field: str) -> Optional[str]:
    """Read a string field from a Firestore REST document.

    Args:
        document: Firestore document dictionary.
        field: Name of the field to read.

    Returns:
        The string value, or None for missing, null or non-string fields.
    """
    data = document.get('fields', {}).get(field, {})
    return cast(Optional[str], data.get('stringValue'))


def safe_text(text: str) -> str:
    """Normalise whitespace and remove printer command control characters.

    Args:
        text: Task text to sanitise.

    Returns:
        Text with normalised newlines, tabs replaced by spaces, and ASCII
        controls removed except for newline.
    """
    # Never pass control characters from task text to the ESC/POS printer.
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    return ''.join(char for char in text if char == '\n' or (ord(char) >= 32 and ord(char) != 127))


def receipt(document: Document, width: int = 42) -> bytes:
    """Format a ticket as a centred CP437 box with ESC/POS feed and cut bytes.

    Is at least nice rows so the printed ticket is a reasonable size.

    Args:
        document: Firestore document containing task and optional category/deadline.
        width: Total box width in character columns, including both borders.
            Must leave room for task padding and any border labels.

    Returns:
        Printer-ready bytes. The box has at least nine rows including borders;
        characters outside CP437 are replaced with question marks.

    Raises:
        ValueError: Task, category, deadline or text-wrapping width is invalid.
    """
    task = value(document, 'task')
    if not isinstance(task, str) or not task.strip() or len(task) > 1000:
        raise ValueError('Invalid task text')
    # Width includes both vertical borders. Reserve two spaces on each side
    # of the task; centring shorter lines gives them additional side padding.
    inner_width = width - 2
    text_width = inner_width - 4
    lines: List[str] = []
    for paragraph in safe_text(task).split('\n'):
        lines.extend(textwrap.wrap(paragraph, width=text_width) or [''])
    category = value(document, 'category')
    if category and category not in ('Council', 'Work', 'Life admin'):
        raise ValueError('Invalid category')
    deadline = value(document, 'deadline')
    deadline_label: Optional[str] = None
    if deadline:
        date = datetime.datetime.strptime(deadline, '%Y-%m-%d').date()
        day = date.day
        suffix = 'th' if 11 <= day % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        month = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec')[date.month - 1]
        deadline_label = 'Deadline: {}{} {} {}'.format(day, suffix, month, date.year)

    def border(left: str, right: str, label: Optional[str]) -> str:
        """Build a horizontal border with an optional centred label.

        Want to leave a space either side of the label box and fill the
        remaining edge with horizontal rules. Label box-less lines have 
        continuous edges.

        Args:
            left: Left corner character.
            right: Right corner character.
            label: Label text, or None for a continuous border.

        Returns:
            A border string using the enclosing receipt's inner width.
        """
        middle = ' {} '.format(label) if label else ''
        return left + middle.center(inner_width, '─') + right

    blank = '│' + ' ' * inner_width + '│'
    # Internal vertical padding: subtract the two border rows and task rows
    # from the minimum height of nine. Always keep at least two blank rows
    # total, so longer tasks still have one above and one below.
    # A one-line task gets three blank rows above and three below.
    padding = max(2, 9 - 2 - len(lines))
    above = padding // 2
    # Put any odd extra blank row below the task.
    below = padding - above
    lines = ([border('┌', '┐', category.upper() if category else None)]
             + [blank] * above
             + ['│' + line.center(inner_width) + '│' for line in lines]
             + [blank] * below + [border('└', '┘', deadline_label)])
    # ESC a 1 centres the entire box across the printer's printable area;
    # line.center() above centres the task inside the box instead.
    # ESC d 7 feeds paper AFTER the bottom border, outside the box. This adjusts
    # the bottom paper margin before cutting, not the internal vertical padding.
    # Seven lines is a calibration estimate from the sample ticket. The physical
    # gap between print head and cutter also affects top and bottom margins.
    # Initialise and select CP437 before printing; finish with a partial cut.
    # Characters outside CP437 are replaced with '?' rather than failing the job.
    return b'\x1b@\x1bt\x00\x1ba\x01' + ('\n'.join(lines) + '\n').encode('cp437', errors='replace') + b'\x1bd\x07\x1dV\x01'


def open_printer(path: str) -> int:
    """Open an existing character device for blocking writes.

    Args:
        path: USB printer device path, normally /dev/usb/lp0.

    Returns:
        An open file descriptor that the caller must close.

    Raises:
        OSError: The device is unavailable, inaccessible or not a character device.
    """
    fd = os.open(path, os.O_WRONLY)
    if not stat.S_ISCHR(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError('Printer path is not a character device')
    return fd


def print_bytes(fd: int, payload: bytes, timeout: float = 30) -> None:
    """Write the entire payload, allowing a bounded time for USB completion.

    Call from the main thread on Unix; this temporarily uses the SIGALRM timer.
    The descriptor remains open for the caller to close.

    Args:
        fd: Open printer file descriptor.
        payload: Printer-ready bytes.
        timeout: Positive time limit in seconds for the whole write.

    Raises:
        TimeoutError: The time limit expires; some bytes may already be printed.
        OSError: USB writing fails or accepts zero bytes.
        ValueError: Signal handling is attempted outside the main thread.
    """
    # SIGALRM bounds a blocking Linux USB write without closing it prematurely.
    # The worker performs all printing on its main thread.
    def timed_out(*_: object) -> NoReturn:
        """Interrupt a stalled write when the alarm fires.

        Args:
            *_: Unused signal number and current stack frame.

        Raises:
            TimeoutError: The printer write exceeded its time limit.
        """
        raise TimeoutError('Printer write timed out')

    previous_handler = signal.signal(signal.SIGALRM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        sent = 0
        while sent < len(payload):
            count = os.write(fd, payload[sent:])
            if count == 0:
                raise OSError('Printer accepted zero bytes')
            sent += count
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def process_one(db: Firestore, device: str) -> bool:
    """Claim and attempt one queued ticket, then record its outcome.

    A missing printer leaves the job queued. Formatting or print errors are
    recorded as failed. An uncertain claim or outcome write may leave the job
    sending; this function never automatically prints that job again.

    Args:
        db: Firestore client used to query and conditionally update jobs.
        device: USB printer device path.

    Returns:
        False if the queue is empty; True if a job was attempted or its claim
        was lost to another update, so the queue can be checked again immediately.

    Raises:
        ApiError: A query, claim or outcome update fails, except claim conflicts.
        OSError: Device access or a network operation fails.
    """
    document = db.next_job()
    if document is None:
        return False
    # If disconnected or permissions are missing, leave the ticket queued.
    fd = open_printer(device)
    try:
        try:
            claimed = db.update(document, {'status': {'stringValue': 'sending'}})
        except ApiError as error:
            if error.code in (409, 412):
                return True  # Another worker changed it; fetch the queue again.
            raise
        LOG.info('Sending job %s', document['name'].rsplit('/', 1)[-1])
        try:
            print_bytes(fd, receipt(document))
        except (OSError, ValueError, TimeoutError):
            outcome: Fields = {'status': {'stringValue': 'failed'}, 'sentAt': {'nullValue': None},
                       'error': {'stringValue': 'Printing failed; check the printer before reprinting. Some output may have printed.'}}
        else:
            outcome = {'status': {'stringValue': 'sent'}, 'error': {'nullValue': None},
                       'sentAt': {'timestampValue': datetime.datetime.now(datetime.timezone.utc).isoformat()}}
        # Never print again if this write fails. The job remains 'sending' until
        # manually reviewed, avoiding duplicates after uncertain delivery.
        db.update(claimed, outcome)
        LOG.info('Job %s', outcome['status']['stringValue'])
        return True
    finally:
        os.close(fd)


def run(db: Firestore, device: str, once: bool = False) -> None:
    """Poll the queue until stopped, draining jobs without idle delays.

    Idle polls wait five seconds. Recoverable errors back off from five to
    sixty seconds; a successful iteration resets the delay.

    Args:
        db: Firestore client.
        device: USB printer device path.
        once: If True, attempt one queue iteration and propagate its errors.

    Raises:
        ApiError: An API operation fails in once mode.
        OSError: A device or network operation fails in once mode.
        ValueError: Invalid data is encountered in once mode.
        subprocess.SubprocessError: Token signing fails in once mode.
    """
    delay = 5
    while not STOP.is_set():
        try:
            processed = process_one(db, device)
            delay = 5
            if once:
                return
            if not processed:
                STOP.wait(5)
        except (ApiError, OSError, ValueError, subprocess.SubprocessError) as error:
            LOG.error('%s; job not automatically retried if already claimed', str(error) if isinstance(error, ApiError) else type(error).__name__)
            if once:
                raise
            STOP.wait(delay)
            delay = min(delay * 2, 60)


def main() -> None:
    """Parse command-line options and run a check, test print or queue worker.

    Configures logging, handles stop signals, and holds a per-user lock to
    prevent simultaneous worker instances. Credentials are not needed for a
    local test print.

    Raises:
        SystemExit: Arguments are invalid or another instance holds the lock.
        OSError: A required file, printer or network resource is unavailable.
        ValueError: Credentials or response data are invalid.
        ApiError: A check or single-job API request fails.
        subprocess.SubprocessError: Token signing fails outside continuous mode.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Check USB access and query Firestore without printing or changing jobs')
    mode.add_argument('--test-print', action='store_true', help='Print a local test ticket without accessing Firestore')
    mode.add_argument('--once', action='store_true', help='Process at most one queued job and exit')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: STOP.set())
    # Covers both manual runs and systemd for user pi.
    lock_path = Path.home() / '.remote-post-it.lock'
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, 'Another printer worker is already running.\n')
        if args.test_print:
            fd = open_printer(PRINTER_DEVICE)
            try:
                print_bytes(fd, receipt({'fields': {
                    'task': {'stringValue': 'Finish the TODO printer'},
                    'category': {'stringValue': 'Work'},
                    'deadline': {'stringValue': '2026-09-26'},
                }}))
            finally:
                os.close(fd)
            return
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not credentials_path:
            parser.error('Set GOOGLE_APPLICATION_CREDENTIALS to the service-account JSON file.')
        db = Firestore(PROJECT_ID, ServiceAccount(credentials_path, PROJECT_ID))
        if args.check:
            fd = open_printer(PRINTER_DEVICE)
            os.close(fd)
            pending = db.next_job() is not None
            LOG.info('USB access and Firestore query OK. Queued ticket present: %s. Nothing printed.', pending)
            return
        run(db, PRINTER_DEVICE, args.once)


if __name__ == '__main__':
    main()
