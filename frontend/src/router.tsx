import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  retainSearchParams,
} from "@tanstack/react-router";
import { getPersona } from "@/api/persona";
import { getRecipe, setRecipe } from "@/api/recipe";
import { RecipeGate } from "@/components/RecipeGate";
import { SourcesProvider } from "@/components/SourcesContext";
import { TopBar } from "@/components/TopBar";
import { ActionsPage, type ActionsSearch } from "@/features/actions/ActionsPage";
import { ReportPage } from "@/features/report/ReportPage";
import { ReportRedirect } from "@/features/report/ReportRedirect";
import { DataReviewPage, type ReviewSearch } from "@/features/review/DataReviewPage";
import { RiskPage, type RiskSearch } from "@/features/risk/RiskPage";
import { RunDetailPage } from "@/features/runs/RunDetailPage";
import { RunsPage } from "@/features/runs/RunsPage";
import { Scope2Page, type Scope2Search } from "@/features/scope2/Scope2Page";
import { isRecipeId, type RecipeId } from "@/lib/recipes";
import type { Measure } from "@/lib/risk";

function text(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

const rootRoute = createRootRoute({
  validateSearch: (search: Record<string, unknown>): { sources?: string; recipe?: RecipeId } => ({
    sources: text(search.sources),
    recipe: isRecipeId(search.recipe) ? search.recipe : undefined,
  }),
  search: { middlewares: [retainSearchParams(["recipe"])] },
  // A link carries its recipe, so opening it switches the app to that recipe.
  beforeLoad: ({ search }) => {
    if (search.recipe) setRecipe(search.recipe);
  },
  component: () => (
    <SourcesProvider>
      <TopBar />
      <Outlet />
    </SourcesProvider>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    if (getPersona().role === "sustainability_specialist") {
      throw redirect({ to: getRecipe() === "energy_meter_check" ? "/scope2" : "/risk" });
    }
    throw redirect({ to: "/review/data", search: { status: "open" } });
  },
});

const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs",
  component: RunsPage,
});

function RunDetailRoute() {
  const { runId } = runRoute.useParams();
  return <RunDetailPage runId={runId} />;
}

const runRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs/$runId",
  component: RunDetailRoute,
});

const reviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/review/data",
  validateSearch: (search: Record<string, unknown>): ReviewSearch => ({
    rule: text(search.rule),
    table: text(search.table),
    status: text(search.status),
    selected: text(search.selected),
  }),
  component: function ReviewRoute() {
    return <DataReviewPage search={reviewRoute.useSearch()} />;
  },
});

const MEASURE_IDS: Measure[] = ["cost", "tail", "emissions"];

const riskRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/risk",
  validateSearch: (search: Record<string, unknown>): RiskSearch => ({
    set: text(search.set),
    crop: text(search.crop),
    region: text(search.region),
    measure: MEASURE_IDS.find((id) => id === search.measure),
    ssp126: text(search.ssp126),
    ssp245: text(search.ssp245),
    ssp585: text(search.ssp585),
    panel: search.panel === "assumptions" ? "assumptions" : undefined,
  }),
  component: function RiskRoute() {
    return (
      <RecipeGate recipe="farm_climate_risk" screen="Risk view">
        <RiskPage search={riskRoute.useSearch()} />
      </RecipeGate>
    );
  },
});

const actionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/actions",
  validateSearch: (search: Record<string, unknown>): ActionsSearch => ({
    set: text(search.set),
    scenario: text(search.scenario),
  }),
  component: function ActionsRoute() {
    return (
      <RecipeGate recipe="farm_climate_risk" screen="Actions">
        <ActionsPage search={actionsRoute.useSearch()} />
      </RecipeGate>
    );
  },
});

const scope2Route = createRoute({
  getParentRoute: () => rootRoute,
  path: "/scope2",
  validateSearch: (search: Record<string, unknown>): Scope2Search => ({
    set: text(search.set),
  }),
  component: function Scope2Route() {
    return (
      <RecipeGate recipe="energy_meter_check" screen="Scope 2">
        <Scope2Page search={scope2Route.useSearch()} />
      </RecipeGate>
    );
  },
});

const reportIndexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/report",
  component: ReportRedirect,
});

const reportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/report/$resultSetId",
  component: function ReportRoute() {
    return <ReportPage resultSetId={reportRoute.useParams().resultSetId} />;
  },
});

const routeTree = rootRoute.addChildren([
  actionsRoute,
  indexRoute,
  runsRoute,
  runRoute,
  reviewRoute,
  riskRoute,
  scope2Route,
  reportIndexRoute,
  reportRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
