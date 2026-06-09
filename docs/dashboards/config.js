/**
 * Firebase project configuration for Atelier dashboards.
 *
 * Firebase API keys are client-side identifiers — they are intentionally
 * public and must be embedded in the browser application. Security is
 * enforced by Firebase Security Rules, Authentication, and App Check,
 * not by key secrecy. See: https://firebase.google.com/docs/projects/api-keys
 *
 * Project:  atelier-build-2026
 * App ID:   1:537337457799:web:109c0fdfb86e780bc65c22
 * App name: Atelier (registered via Firebase console)
 *
 * Note: An earlier app (1:537337457799:web:75dece0efe07d589c65c22) was
 * registered programmatically and is a duplicate. That app can be deleted
 * from the Firebase console under Project Settings -> Your apps.
 */

window.__FIREBASE_CONFIG__ = {
  // nosemgrep: generic.secrets.security.detected-generic-api-key.detected-generic-api-key -- Firebase web apiKey is a public client identifier by design (see header); secrecy is not the control surface.
  apiKey: 'AIzaSyCviGMimUnuCUpJKO0uXbhQDdlfMvby2i0',
  authDomain: 'atelier-build-2026.firebaseapp.com',
  projectId: 'atelier-build-2026',
  storageBucket: 'atelier-build-2026.firebasestorage.app',
  messagingSenderId: '537337457799',
  appId: '1:537337457799:web:109c0fdfb86e780bc65c22',
  measurementId: 'G-EHP16HDJFG',
};

window.__ATELIER_API_BASE__ = 'https://api.atelier.autonomous-agent.dev';
