import { requireOwner } from './auth.js';

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'];

function formatDeadline(value) {
  if (!value) return '—';
  const [year, month, day] = value.split('-').map(Number);
  const suffix = day % 100 >= 11 && day % 100 <= 13
    ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[day % 10] || 'th');
  return `${day}${suffix} ${months[month - 1]} ${year}`;
}

// Connect this renderer to Firestore once authentication and storage are ready.
// submittedAt is an ISO timestamp; deadline is an optional YYYY-MM-DD date.
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
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'print reprint';
    button.textContent = 'Reprint';
    button.setAttribute('aria-label', `Reprint: ${ticket.task}`);
    button.addEventListener('click', () => {
      if (!requireOwner()) return;
      status.textContent = 'Printing isn’t connected yet. This ticket has not been sent again.';
    });
    row.insertCell().append(button);
  }
}

renderHistory([]);
