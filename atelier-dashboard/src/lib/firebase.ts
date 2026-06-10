import { initializeApp, getApps, getApp, type FirebaseApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider, type Auth } from 'firebase/auth';
import { getFirestore, connectFirestoreEmulator } from 'firebase/firestore';

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

const isFirebaseConfigured = !!(
  firebaseConfig.apiKey &&
  firebaseConfig.authDomain &&
  firebaseConfig.projectId
);

let auth: Auth | null = null;
let googleProvider: GoogleAuthProvider | null = null;
let firebaseApp: FirebaseApp | null = null;

if (isFirebaseConfigured) {
  try {
    const app: FirebaseApp = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
    firebaseApp = app;
    auth = getAuth(app);
    googleProvider = new GoogleAuthProvider();

    // Local-dev only: route Firestore to the emulator when configured. Lets the
    // AT-042 sign-off handshake (submitApproval write -> watchSignoff onSnapshot
    // dismiss) and the board/agent-activity subscriptions be exercised without a
    // real authenticated Firestore project. Gated entirely by an env var that is
    // absent in every deployed build, so production behaviour is unchanged. Must
    // run before any getFirestore() usage elsewhere (this module loads first).
    const emulatorHost = process.env.NEXT_PUBLIC_FIRESTORE_EMULATOR_HOST;
    if (emulatorHost) {
      const [host, portStr] = emulatorHost.split(':');
      try {
        connectFirestoreEmulator(getFirestore(app), host || '127.0.0.1', Number(portStr) || 8080);
      } catch (emulatorError: unknown) {
        console.error('Failed to connect Firestore emulator:', emulatorError);
      }
    }
  } catch (error: unknown) {
    console.error('Failed to initialize Firebase SDK:', error);
  }
}

export { auth, googleProvider, isFirebaseConfigured, firebaseApp };
