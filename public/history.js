import { requireOwner, ownerSession, onOwnerChange } from './auth.js';
import { loadHistory, reprintTicket, storageError } from './tickets.js';

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'];

function formatDeadline(value) {
  if (!value) return '—';
  const [year, month, day] = value.split('-').map(Number);
  const suffix = day % 100 >= 11 && day % 100 <= 13
    ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[day % 10] || 'th');
  return `${day}${suffix} ${months[month - 1]} ${year}`;
}

export function renderHistory(tickets) {
  const body = document.querySelector('#ticket-history');
  const status = document.querySelector('#history-status');
  body.replaceChildren();
  status.textContent = '';

  if (!tickets.length) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 5;
    cell.className = 'empty-history';
    cell.textContent = 'No ticket history to show.';
    return;
  }

  for (const ticket of [...tickets].sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt))) {
    const row = body.insertRow();
    const submitted = new Date(ticket.submittedAt).toLocaleString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
    for (const value of [submitted, ticket.task, ticket.category || '—', formatDeadline(ticket.deadline)]) {
      row.insertCell().textContent = value;
    }
    const jobStatus = document.createElement('small');
    jobStatus.className = 'job-status';
    // queued: saved in Firestore, waiting for the Pi.
    // sending: the Pi is attempting to send the ticket to the printer.
    // sent: handed to the printer successfully; physical printing is not confirmed.
    // failed: the Pi encountered an error while attempting to print.
    jobStatus.textContent = ({ queued: 'Queued', sending: 'Sending', sent: 'Sent to printer', failed: 'Failed' })[ticket.status] || 'Unknown status';
    row.cells[0].append(jobStatus);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'print reprint';
    button.textContent = 'Reprint';
    button.disabled = ticket.status === 'sending';
    button.setAttribute('aria-label', `Reprint: ${ticket.task}`);
    button.addEventListener('click', async () => {
      if (button.disabled || loading || !requireOwner()) return;
      const session = ownerSession();
      button.disabled = true;
      status.textContent = 'Saving reprint…';
      try {
        await reprintTicket(ticket.id);
        if (ownerSession() !== session) return;
        await refreshHistory(session);
        if (ownerSession() === session) status.textContent = 'Reprint queued.';
      } catch (error) {
        if (ownerSession() === session) status.textContent = storageError(error);
      } finally {
        button.disabled = false;
      }
    });
    row.insertCell().append(button);
  }
}

const previous = document.querySelector('#history-previous');
const next = document.querySelector('#history-next');
const pageLabel = document.querySelector('#history-page');
let cursors = [null];
let page = 0;
let nextCursor = null;
let loading = false;
let request = 0;

function updatePagination() {
  previous.disabled = loading || page === 0;
  next.disabled = loading || nextCursor === null;
  pageLabel.textContent = `Page ${page + 1}`;
}

async function refreshHistory(session, targetPage = page) {
  const currentRequest = ++request;
  loading = true;
  updatePagination();
  try {
    const result = await loadHistory(cursors[targetPage]);
    if (ownerSession() !== session || request !== currentRequest) return;
    page = targetPage;
    nextCursor = result.nextCursor;
    cursors = cursors.slice(0, page + 1);
    if (nextCursor) cursors.push(nextCursor);
    renderHistory(result.tickets);
  } finally {
    if (request === currentRequest) {
      loading = false;
      updatePagination();
    }
  }
}

async function changePage(targetPage) {
  if (loading || !requireOwner()) return;
  const session = ownerSession();
  const status = document.querySelector('#history-status');
  status.textContent = 'Loading history…';
  try {
    await refreshHistory(session, targetPage);
  } catch (error) {
    if (ownerSession() === session) status.textContent = storageError(error);
  }
}
previous.addEventListener('click', () => {
  if (!previous.disabled) return changePage(page - 1);
});
next.addEventListener('click', () => {
  if (!next.disabled) return changePage(page + 1);
});

onOwnerChange(session => {
  ++request;
  cursors = [null];
  page = 0;
  nextCursor = null;
  loading = false;
  updatePagination();
  document.querySelector('#ticket-history').replaceChildren();
  const status = document.querySelector('#history-status');
  status.textContent = '';
  if (session === null) return;
  status.textContent = 'Loading history…';
  refreshHistory(session).catch(error => {
    if (ownerSession() === session) status.textContent = storageError(error);
  });
});
