import { useNavigate, useRouterState, useSearch } from "@tanstack/react-router";
import { useEffect } from "react";
import { setRecipe, useRecipe } from "@/api/recipe";
import { Select } from "@/components/ui/select";
import { isRecipeId, RECIPE_IDS, recipeName } from "@/lib/recipes";

/** The recipe picker. The choice scopes every screen, and the address carries it so links keep it. */
export function RecipeSwitcher() {
  const navigate = useNavigate();
  const recipe = useRecipe();
  const inAddress = useSearch({ strict: false, select: (search) => search.recipe });
  const section = useRouterState({ select: (state) => state.location.pathname.split("/")[1] });

  useEffect(() => {
    if (inAddress !== recipe) {
      void navigate({ to: ".", search: (previous) => ({ ...previous, recipe }), replace: true });
    }
  }, [inAddress, recipe, navigate]);

  return (
    <Select
      aria-label="Recipe"
      value={recipe}
      onChange={(event) => {
        const chosen = event.target.value;
        if (!isRecipeId(chosen)) return;
        setRecipe(chosen);
        // Screens every recipe has stay open. The rest go to the role's landing screen.
        if (section === "runs") void navigate({ to: "/runs", search: { recipe: chosen } });
        else if (section === "report") void navigate({ to: "/report", search: { recipe: chosen } });
        else if (section === "review") {
          void navigate({ to: "/review/data", search: { recipe: chosen, status: "open" } });
        } else void navigate({ to: "/", search: { recipe: chosen } });
      }}
    >
      {RECIPE_IDS.map((id) => (
        <option key={id} value={id}>
          {recipeName(id)}
        </option>
      ))}
    </Select>
  );
}
