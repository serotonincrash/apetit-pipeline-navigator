import { defineConfig } from "orval";

const input = "../docs/openapi.json";

export default defineConfig({
  client: {
    input,
    output: {
      target: "src/api/generated/client.ts",
      schemas: "src/api/generated/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: { path: "src/api/fetcher.ts", name: "fetcher" },
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
  mocks: {
    input,
    output: {
      target: "mocks/handlers.ts",
      schemas: "src/api/generated/model",
      client: "fetch",
      mock: true,
      clean: true,
    },
  },
});
