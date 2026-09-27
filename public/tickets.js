import { ownerSession } from './auth.js';

// Lite makes server requests without a persistent browser cache or offline writes.
async function database() {
  const sdk = await import('https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore-lite.js');
  return { sdk, jobs: sdk.collection(sdk.getFirestore(), 'jobs') };
}

function checkSession(session) {
  if (session === null || ownerSession() !== session) throw new Error('Sign-in changed. Please try again.');
}

export function ticketFields({ task, category, deadline }) {
  task = task.trim();
  category = category || null;
  deadline = deadline || null;
  if (!task || task.length > 1000) throw new Error('Enter a task of 1–1000 characters.');
  if (![null, 'Council', 'Work', 'Life admin'].includes(category)) throw new Error('Choose a valid category.');
  if (deadline !== null && (!/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(deadline)
    || Number.isNaN(Date.parse(`${deadline}T00:00:00Z`))
    || new Date(`${deadline}T00:00:00Z`).toISOString().slice(0, 10) !== deadline)) {
    throw new Error('Choose a valid deadline.');
  }
  return { task, category, deadline };
}

export async function saveTicket(ticket) {
  const session = ownerSession();
  checkSession(session);
  const fields = ticketFields(ticket);
  const { sdk, jobs } = await database();
  checkSession(session);
  return sdk.addDoc(jobs, {
    ...fields, submittedAt: sdk.serverTimestamp(), status: 'queued',
    sentAt: null, error: null, reprintOf: null,
  });
}

export async function reprintTicket(id) {
  const session = ownerSession();
  checkSession(session);
  const { sdk, jobs } = await database();
  checkSession(session);
  // Reuse the same history row and preserve its original submission date.
  return sdk.updateDoc(sdk.doc(jobs, id), { status: 'queued', sentAt: null, error: null });
}

export async function loadHistory(after = null) {
  const session = ownerSession();
  checkSession(session);
  const { sdk, jobs } = await database();
  checkSession(session);
  const constraints = [sdk.orderBy('submittedAt', 'desc')];
  // A document cursor also disambiguates tickets with identical timestamps.
  if (after) constraints.push(sdk.startAfter(after));
  const snapshot = await sdk.getDocs(sdk.query(jobs, ...constraints, sdk.limit(51)));
  checkSession(session);
  const docs = snapshot.docs.slice(0, 50);
  return {
    tickets: docs.map(doc => ({ ...doc.data(), id: doc.id, submittedAt: doc.data().submittedAt.toDate() })),
    nextCursor: snapshot.docs.length > 50 ? docs.at(-1) : null,
  };
}

export function storageError(error) {
  return error.code === 'permission-denied'
    ? 'Access denied. Check that the latest Firestore rules are deployed.'
    : 'Could not confirm the request. Check your connection and History before trying again.';
}
