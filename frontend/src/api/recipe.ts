import { useSyncExternalStore } from "react";
import { DEFAULT_RECIPE, isRecipeId, type RecipeId } from "@/lib/recipes";

const KEY = "navigator.recipe";

let current: RecipeId = read();
const listeners = new Set<() => void>();

function read(): RecipeId {
  try {
    const stored = localStorage.getItem(KEY);
    if (isRecipeId(stored)) return stored;
  } catch {
    // Storage can be blocked; the app then opens on the default recipe.
  }
  return DEFAULT_RECIPE;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setRecipe(next: RecipeId): void {
  if (next === current) return;
  current = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // Kept in memory for this visit.
  }
  for (const listener of listeners) listener();
}

export function getRecipe(): RecipeId {
  return current;
}

export function useRecipe(): RecipeId {
  return useSyncExternalStore(subscribe, () => current);
}
