import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import { getPersona } from "@/api/persona";
import { SourcesProvider } from "@/components/SourcesContext";
import { TopBar } from "@/components/TopBar";
import { DataReviewPage, type ReviewSearch } from "@/features/review/DataReviewPage";
import { RiskPage, type RiskSearch } from "@/features/risk/RiskPage";
import { RunDetailPage } from "@/features/runs/RunDetailPage";
import { RunsPage } from "@/features/runs/RunsPage";
import type { Measure } from "@/lib/risk";

function text(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

const rootRoute = createRootRoute({
  validateSearch: (search: Record<string, unknown>): { sources?: string } => ({
    sources: text(search.sources),
  }),
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
    if (getPersona().role === "sustainability_specialist") throw redirect({ to: "/risk" });
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
    return <RiskPage search={riskRoute.useSearch()} />;
  },
});

const routeTree = rootRoute.addChildren([indexRoute, runsRoute, runRoute, reviewRoute, riskRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
