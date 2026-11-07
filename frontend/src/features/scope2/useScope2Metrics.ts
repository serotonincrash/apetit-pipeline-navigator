import { useListMetrics } from "@/api/generated/client";

export const SCOPE2_NAMES = {
  use: "scope2_electricity.electricity_use_mwh",
  location: "scope2_electricity.location_based_tco2e",
  market: "scope2_electricity.market_based_tco2e",
  locationDifference: "compare_inventory.location_based_difference_tco2e",
  marketDifference: "compare_inventory.market_based_difference_tco2e",
} as const;

/** The Scope 2 metrics of one result set, one query per metric name. */
export function useScope2Metrics(resultSetId: string) {
  const query = { query: { enabled: resultSetId !== "" } };
  const params = (name: string) => ({ name, limit: 1000 });
  const use = useListMetrics(resultSetId, params(SCOPE2_NAMES.use), query);
  const location = useListMetrics(resultSetId, params(SCOPE2_NAMES.location), query);
  const market = useListMetrics(resultSetId, params(SCOPE2_NAMES.market), query);
  const locationDifference = useListMetrics(
    resultSetId,
    params(SCOPE2_NAMES.locationDifference),
    query,
  );
  const marketDifference = useListMetrics(
    resultSetId,
    params(SCOPE2_NAMES.marketDifference),
    query,
  );
  const all = [use, location, market, locationDifference, marketDifference];
  return {
    use: use.data?.items ?? [],
    location: location.data?.items ?? [],
    market: market.data?.items ?? [],
    locationDifference: locationDifference.data?.items ?? [],
    marketDifference: marketDifference.data?.items ?? [],
    isPending: all.some((item) => item.isPending && item.fetchStatus !== "idle"),
    isError: all.some((item) => item.isError),
    refetch: () => {
      for (const item of all) void item.refetch();
    },
  };
}
