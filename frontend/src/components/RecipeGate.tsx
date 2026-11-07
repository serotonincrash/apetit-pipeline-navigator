import type { ReactNode } from "react";
import { setRecipe, useRecipe } from "@/api/recipe";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { type RecipeId, recipeName } from "@/lib/recipes";

interface RecipeGateProps {
  recipe: RecipeId;
  screen: string;
  children: ReactNode;
}

/** Shows a screen only for its own recipe. Any other recipe gets a note and a way to switch. */
export function RecipeGate({ recipe, screen, children }: RecipeGateProps) {
  if (useRecipe() === recipe) return children;
  return (
    <main className="mx-auto max-w-5xl px-6 py-6">
      <EmptyState title={`${screen} belongs to ${recipeName(recipe)}.`}>
        <Button variant="primary" onClick={() => setRecipe(recipe)}>
          Switch to {recipeName(recipe)}
        </Button>
      </EmptyState>
    </main>
  );
}
