const form = document.querySelector('#ticket-form');
const task = document.querySelector('#task');
const category = document.querySelector('#category');
const categoryButtons = document.querySelectorAll('[data-category]');
const status = document.querySelector('#form-status');

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

form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!task.value.trim()) {
    task.setCustomValidity('Enter a task description.');
    task.reportValidity();
    return;
  }
  // Connect this to the persistent queue once authentication and storage are ready.
  status.textContent = 'Printing isn’t connected yet. Your task has not been sent.';
});
