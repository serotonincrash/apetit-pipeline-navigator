import { Link } from "@tanstack/react-router";
import { Fragment, type ReactNode } from "react";
import type { PersonaRole } from "@/api/generated/model";
import { usePersona } from "@/api/persona";
import { PersonaSwitcher } from "@/components/PersonaSwitcher";

const LINK = "px-3 py-3 text-muted-foreground hover:text-foreground";
const ACTIVE = { className: "px-3 py-3 font-medium text-foreground border-b-2 border-primary" };
const ANY_SEARCH = { includeSearch: false };

type Screen = "runs" | "review" | "risk" | "actions" | "report";

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

/** Each role's own screens come first. Both roles can read every screen. */
const SCREENS_BY_ROLE: Record<PersonaRole, { own: Screen[]; other: Screen[] }> = {
  data_specialist: { own: ["review", "runs"], other: ["risk", "actions", "report"] },
  sustainability_specialist: { own: ["risk", "actions", "report"], other: ["review", "runs"] },
};

function tabs(screens: Screen[]) {
  return screens.map((screen) => <Fragment key={screen}>{TABS[screen]}</Fragment>);
}

export function TopBar() {
  const { own, other } = SCREENS_BY_ROLE[usePersona().role];
  return (
    <header className="flex items-center justify-between border-b px-6 print:hidden">
      <nav aria-label="Main" className="flex items-center">
        <span className="mr-4 font-semibold">Climate and nature navigator</span>
        {tabs(own)}
        <span aria-hidden="true" className="mx-2 h-5 border-l" />
        {tabs(other)}
      </nav>
      <PersonaSwitcher />
    </header>
  );
}
