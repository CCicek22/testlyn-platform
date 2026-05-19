"use client";

/**
 * Firebase Auth client SDK initialization.
 *
 * When NEXT_PUBLIC_DEV_AUTH_BYPASS=true, a fake token is returned without
 * talking to Firebase. Real Firebase credentials come from
 * NEXT_PUBLIC_FIREBASE_* env vars (see .env.local.example).
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  GithubAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  type Auth,
  type User,
} from "firebase/auth";

const DEV_BYPASS =
  process.env["NEXT_PUBLIC_DEV_AUTH_BYPASS"] === "true";

let app: FirebaseApp | undefined;
let auth: Auth | undefined;

if (!DEV_BYPASS) {
  const firebaseConfig = {
    apiKey: process.env["NEXT_PUBLIC_FIREBASE_API_KEY"],
    authDomain: process.env["NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN"],
    projectId: process.env["NEXT_PUBLIC_FIREBASE_PROJECT_ID"],
    storageBucket: process.env["NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET"],
    messagingSenderId: process.env["NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID"],
    appId: process.env["NEXT_PUBLIC_FIREBASE_APP_ID"],
  };

  app = getApps()[0] ?? initializeApp(firebaseConfig);
  auth = getAuth(app);
}

// ─── Token retrieval ───────────────────────────────────────────────────────

/** Returns the IdP JWT, or a static fake token in dev-bypass mode.
 *
 * Awaits `authStateReady()` so callers don't race the IndexedDB restore on
 * page navigation — without this, the first React Query on a freshly mounted
 * route can see `currentUser === null` for ~10ms after a hard reload and
 * throw UnauthenticatedError, which surfaces as a query error and (because
 * `AuthProvider` is still hydrating) can briefly flash an empty page before
 * the user state settles.
 */
export async function getIdToken(forceRefresh = false): Promise<string | null> {
  if (DEV_BYPASS) {
    return "dev-bypass-token";
  }
  if (!auth) return null;
  await auth.authStateReady();
  const user = auth.currentUser;
  if (!user) return null;
  return user.getIdToken(forceRefresh);
}

// ─── Auth actions ──────────────────────────────────────────────────────────

export async function signInWithGoogle(): Promise<void> {
  if (!auth) throw new Error("Firebase not initialized");
  const provider = new GoogleAuthProvider();
  await signInWithPopup(auth, provider);
}

export async function signInWithGithub(): Promise<void> {
  if (!auth) throw new Error("Firebase not initialized");
  const provider = new GithubAuthProvider();
  await signInWithPopup(auth, provider);
}

export async function signInWithEmail(
  email: string,
  password: string
): Promise<void> {
  if (!auth) throw new Error("Firebase not initialized");
  await signInWithEmailAndPassword(auth, email, password);
}

export async function signUpWithEmail(
  email: string,
  password: string
): Promise<void> {
  if (!auth) throw new Error("Firebase not initialized");
  await createUserWithEmailAndPassword(auth, email, password);
}

export async function signOutUser(): Promise<void> {
  if (DEV_BYPASS) return;
  if (!auth) return;
  await signOut(auth);
}

// ─── Auth state observer ───────────────────────────────────────────────────

export function onAuthState(callback: (user: User | null) => void): () => void {
  if (DEV_BYPASS) {
    // Immediately call with a synthetic dev user, return no-op unsubscribe
    const fakeUser = {
      uid: "dev-uid",
      email: "dev@testlyn.io",
      displayName: "Dev User",
    } as unknown as User;
    callback(fakeUser);
    return () => {};
  }
  if (!auth) {
    callback(null);
    return () => {};
  }
  return onAuthStateChanged(auth, callback);
}

export { auth };
