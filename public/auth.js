import { isOwner, OWNER_EMAIL } from './auth-policy.js';

const panel = document.querySelector('#auth-panel');
const content = document.querySelector('#protected-content');
const message = document.querySelector('#auth-status');
const signIn = document.querySelector('#sign-in');
const signOutButton = document.querySelector('#sign-out');
let authorized = false;
let revision = 0;
const ownerListeners = new Set();

export function ownerSession() {
  return authorized ? revision : null;
}

export function onOwnerChange(listener) {
  ownerListeners.add(listener);
  listener(ownerSession());
  return () => ownerListeners.delete(listener);
}

function notifyOwner() {
  for (const listener of ownerListeners) listener(ownerSession());
}

function lock() {
  authorized = false;
  content.hidden = true;
  panel.hidden = false;
  notifyOwner();
}

function clearPrivateContent() {
  document.querySelector('#ticket-form')?.reset();
  for (const button of document.querySelectorAll('[data-category]')) {
    button.setAttribute('aria-pressed', 'false');
  }
  document.querySelector('#ticket-history')?.replaceChildren();
  for (const selector of ['#form-status', '#history-status']) {
    const element = document.querySelector(selector);
    if (element) element.textContent = '';
  }
}

export function requireOwner() {
  if (!authorized) {
    lock();
    message.textContent = 'Please sign in to continue.';
  }
  return authorized;
}

async function initialize() {
  try {
    const [{ initializeApp }, sdk, response] = await Promise.all([
      import('https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js'),
      fetch('/__/firebase/init.json'),
    ]);
    if (!response.ok) throw new Error('Firebase configuration unavailable');
    const auth = sdk.getAuth(initializeApp(await response.json()));
    await sdk.setPersistence(auth, sdk.browserLocalPersistence);
    const provider = new sdk.GoogleAuthProvider();
    provider.setCustomParameters({ login_hint: OWNER_EMAIL, prompt: 'select_account' });

    sdk.onIdTokenChanged(auth, async (user) => {
      const currentRevision = ++revision;
      lock();
      if (!user) {
        clearPrivateContent();
        if (!message.textContent.startsWith('Access is restricted')) {
          message.textContent = '';
        }
        return;
      }
      try {
        const { claims } = await user.getIdTokenResult();
        if (currentRevision !== revision) return;
        if (!isOwner(claims)) {
          clearPrivateContent();
          message.textContent = 'Access is restricted to the owner of this app. Choose another Google account.';
          await sdk.signOut(auth);
          return;
        }
        authorized = true;
        panel.hidden = true;
        content.hidden = false;
        notifyOwner();
      } catch {
        if (currentRevision !== revision) return;
        lock();
        clearPrivateContent();
        message.textContent = 'Unable to verify your account. Please sign in again.';
      }
    }, () => {
      lock();
      clearPrivateContent();
      message.textContent = 'Unable to check your sign-in. Please reload and try again.';
    });

    signIn.disabled = false;
    signIn.addEventListener('click', async () => {
      signIn.disabled = true;
      message.textContent = 'Opening Google sign-in…';
      try {
        await sdk.signInWithPopup(auth, provider);
      } catch (error) {
        lock();
        message.textContent = error.code === 'auth/popup-blocked'
          ? 'Allow the Google sign-in popup, then try again.'
          : error.code === 'auth/popup-closed-by-user'
            ? 'Sign-in cancelled. Try again when you’re ready.'
            : 'Sign-in failed. Please try again.';
      } finally {
        signIn.disabled = false;
      }
    });

    signOutButton.addEventListener('click', async () => {
      ++revision;
      lock();
      clearPrivateContent();
      try {
        await sdk.signOut(auth);
        message.textContent = 'You’re signed out.';
      } catch {
        message.textContent = 'Sign-out could not complete. Please reload and try again.';
      }
    });
  } catch {
    lock();
    message.textContent = 'Sign-in is unavailable. Check your connection and reload.';
  }
}

initialize();
