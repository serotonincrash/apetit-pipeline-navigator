import { Link } from "@tanstack/react-router";
import { Fragment, type ReactNode } from "react";
import type { PersonaRole } from "@/api/generated/model";
import { usePersona } from "@/api/persona";
import { useRecipe } from "@/api/recipe";
import { PersonaSwitcher } from "@/components/PersonaSwitcher";
import { RecipeSwitcher } from "@/components/RecipeSwitcher";
import type { RecipeId } from "@/lib/recipes";

const LINK = "px-3 py-3 text-muted-foreground hover:text-foreground";
const ACTIVE = { className: "px-3 py-3 font-medium text-foreground border-b-2 border-primary" };
const ANY_SEARCH = { includeSearch: false };

type Screen = "runs" | "review" | "risk" | "scope2" | "actions" | "report";

const TABS: Record<Screen, ReactNode> = {
  runs: (
    <Link to="/runs" className={LINK} activeProps={ACTIVE} activeOptions={ANY_SEARCH}>
      Runs
    </Link>
  ),
  review: (
    <Link
      to="/review/data"
      search={{ status: "open" }}
      className={LINK}
      activeProps={ACTIVE}
      activeOptions={ANY_SEARCH}
    >
      Data review
    </Link>
  ),
  scope2: (
    <Link to="/scope2" className={LINK} activeProps={ACTIVE} activeOptions={ANY_SEARCH}>
      Scope 2
    </Link>
  ),
  actions: (
    <Link to="/actions" className={LINK} activeProps={ACTIVE} activeOptions={ANY_SEARCH}>
      Actions
    </Link>
  ),
  risk: (
    <Link to="/risk" className={LINK} activeProps={ACTIVE} activeOptions={ANY_SEARCH}>
      Risk view
    </Link>
  ),
  report: (
    <Link to="/report" className={LINK} activeProps={ACTIVE} activeOptions={ANY_SEARCH}>
      Report
    </Link>
  ),
};

/** The tabs of each recipe, in order. */
const SCREENS_BY_RECIPE: Record<RecipeId, Screen[]> = {
  farm_climate_risk: ["review", "runs", "risk", "actions", "report"],
  energy_meter_check: ["review", "runs", "scope2", "report"],
};

/** Each role's own screens come first. Both roles can read every screen. */
const OWN_SCREENS: Record<PersonaRole, Screen[]> = {
  data_specialist: ["review", "runs"],
  sustainability_specialist: ["risk", "scope2", "actions", "report"],
};

function tabs(screens: Screen[]) {
  return screens.map((screen) => <Fragment key={screen}>{TABS[screen]}</Fragment>);
}

export function TopBar() {
  const screens = SCREENS_BY_RECIPE[useRecipe()];
  const ownScreens = OWN_SCREENS[usePersona().role];
  const own = ownScreens.filter((screen) => screens.includes(screen));
  const other = screens.filter((screen) => !ownScreens.includes(screen));
  return (
    <header className="flex items-center justify-between border-b px-6 print:hidden">
      <nav aria-label="Main" className="flex items-center">
        <span className="mr-4 font-semibold">Climate and nature navigator</span>
        {tabs(own)}
        <span aria-hidden="true" className="mx-2 h-5 border-l" />
        {tabs(other)}
      </nav>
      <div className="flex items-center gap-3">
        <RecipeSwitcher />
        <PersonaSwitcher />
      </div>
    </header>
  );
}
