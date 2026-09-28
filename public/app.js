import { requireOwner, ownerSession } from './auth.js';

import { saveTicket, storageError } from './tickets.js';

let saving = false;
const form = document.querySelector('#ticket-form');
const task = document.querySelector('#task');
const category = document.querySelector('#category');
const categoryButtons = document.querySelectorAll('[data-category]');
const deadline = document.querySelector('#deadline');
const status = document.querySelector('#form-status');

for (const button of document.querySelectorAll('[data-deadline-offset]')) {
  button.addEventListener('click', () => {
    const date = new Date();
    date.setDate(date.getDate() + Number(button.dataset.deadlineOffset));
    deadline.value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    deadline.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

for (const button of categoryButtons) {
  button.addEventListener('click', () => {
    category.value = category.value === button.dataset.category ? '' : button.dataset.category;
    for (const option of categoryButtons) {
      option.setAttribute('aria-pressed', String(option.dataset.category === category.value));
    }
    status.textContent = '';
  });
}

form.addEventListener('input', () => {
  task.setCustomValidity('');
  status.textContent = '';
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (saving || !requireOwner()) return;
  if (!task.value.trim()) {
    task.setCustomValidity('Enter a task description.');
    task.reportValidity();
    return;
  }
  const session = ownerSession();
  const controls = [...form.querySelectorAll('input, textarea, button')];
  const ticket = { task: task.value, category: category.value, deadline: deadline.value };
  saving = true;
  controls.forEach(control => { control.disabled = true; });
  status.textContent = 'Saving…';
  try {
    await saveTicket(ticket);
    if (ownerSession() !== session) return;
    form.reset();
    categoryButtons.forEach(button => button.setAttribute('aria-pressed', 'false'));
    status.textContent = 'Sent to the printer 🫡';
  } catch (error) {
    if (ownerSession() === session) status.textContent = storageError(error);
  } finally {
    saving = false;
    controls.forEach(control => { control.disabled = false; });
  }
});
