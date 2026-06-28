import { storage } from "@/src/utils/storage";

const BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;
export const TOKEN_KEY = "sn_token";

async function authHeader() {
  const t = await storage.secureGet(TOKEN_KEY, "");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function req(path: string, method = "GET", body?: any) {
  const headers: any = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
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
