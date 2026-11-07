import { useSyncExternalStore } from "react";
import type { PersonaRole } from "./generated/model";

export interface StoredPersona {
  role: PersonaRole;
  name: string;
}

const KEY = "navigator.persona";
const DEFAULT: StoredPersona = { role: "data_specialist", name: "" };

let current: StoredPersona = read();
let askingForName = false;
const listeners = new Set<() => void>();

function read(): StoredPersona {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredPersona>;
      if (parsed.role === "data_specialist" || parsed.role === "sustainability_specialist") {
        return { role: parsed.role, name: parsed.name ?? "" };
      }
    }
  } catch {
    // Storage can be blocked; the app then asks again each visit.
  }
  return DEFAULT;
}

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setPersona(next: StoredPersona): void {
  current = next;
  askingForName = false;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Kept in memory for this visit.
  }
  emit();
}

export function getPersona(): StoredPersona {
  return current;
}

export function usePersona(): StoredPersona {
  return useSyncExternalStore(subscribe, () => current);
}

export function useAskingForName(): boolean {
  return useSyncExternalStore(subscribe, () => askingForName);
}

/** True when a name is set. Otherwise the top bar asks for it and the caller stops. */
export function requireName(): boolean {
  if (current.name.trim()) return true;
  askingForName = true;
  emit();
  return false;
}

export function personaHeader(): Record<string, string> {
  if (!current.name.trim()) return {};
  return { "X-Persona": `${current.role}:${encodeURIComponent(current.name.trim())}` };
}
