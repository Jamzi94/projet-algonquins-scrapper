import { storage } from "@/src/utils/storage";

// URL du backend issue de la configuration Expo.
// Peut être absente (variable d'environnement non définie) : dans ce cas on refuse
// de construire des URLs invalides du type "undefined/api" plutôt que d'échouer
// silencieusement sur chaque requête.
const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL;
const BASE = BACKEND_URL ? `${BACKEND_URL}/api` : null;
export const TOKEN_KEY = "sn_token";

if (!BACKEND_URL) {
  // Avertissement clair au démarrage pour faciliter le diagnostic.
  console.error(
    "[api] Configuration manquante : EXPO_PUBLIC_BACKEND_URL n'est pas définie. " +
      "Les appels au backend échoueront tant que cette variable d'environnement n'est pas renseignée."
  );
}

async function authHeader() {
  const t = await storage.secureGet(TOKEN_KEY, "");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function req(path: string, method = "GET", body?: any) {
  // On refuse de construire une URL invalide si la base n'est pas configurée.
  if (!BASE) {
    throw new Error(
      "Configuration manquante : EXPO_PUBLIC_BACKEND_URL n'est pas définie."
    );
  }

  const headers: any = { "Content-Type": "application/json", ...(await authHeader()) };

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e: any) {
    // Erreur réseau (fetch qui rejette : pas de connexion, serveur injoignable, etc.).
    // On renvoie une Error réseau lisible et homogène au lieu de laisser fuiter
    // une promesse non gérée.
    throw new Error(
      `Erreur réseau : impossible de joindre le serveur${e && e.message ? ` (${e.message})` : ""}.`
    );
  }

  const text = await res.text();
  let data: any;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}

export const api = {
  get: (p: string) => req(p),
  post: (p: string, b?: any) => req(p, "POST", b),
  put: (p: string, b?: any) => req(p, "PUT", b),
  del: (p: string) => req(p, "DELETE"),
};

export const setToken = (t: string) => storage.secureSet(TOKEN_KEY, t);
export const clearToken = () => storage.secureRemove(TOKEN_KEY);

export const wsUrl = (roomId: string) =>
  `${(process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/^http/, "ws")}/api/ws/rooms/${roomId}`;
