/**
 * Entrypoint.
 *
 * Boots, then says who it is. The health log line names the store and the engine URL
 * on purpose: the two most likely misconfigurations are "pointed at the wrong
 * Firestore project" and "pointed at the wrong engine", and both are invisible from
 * a page that renders fine until someone submits a decision.
 */

import { loadConfig } from "./config.js";
import { createContext } from "./context.js";
import { buildServer } from "./server.js";
import { EngineClient } from "./engineClient.js";
import { MemoryStore } from "./store/memory.js";
import { FirestoreStore } from "./store/firestore.js";
import type { Store } from "./store/types.js";

const config = loadConfig();

const store: Store =
  process.env.STORE === "memory"
    ? new MemoryStore()
    : new FirestoreStore({
        ...(process.env.GOOGLE_CLOUD_PROJECT ? { projectId: process.env.GOOGLE_CLOUD_PROJECT } : {}),
      });

await store.ensureReady();

const engine = new EngineClient({
  baseUrl: config.engineUrl,
  token: config.engineToken,
  ...(process.env.ENGINE_AUDIENCE ? { audience: process.env.ENGINE_AUDIENCE } : {}),
});

const app = buildServer({ config, context: createContext({ store, engine, config }) });

const shutdown = async (signal: string): Promise<void> => {
  console.log(`received ${signal}, shutting down`);
  await app.close();
  await store.close();
  process.exit(0);
};
process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));

await app.listen({ port: config.port, host: config.host });
console.log(
  `cre-investment-committee game service listening on :${config.port} ` +
    `(store=${store.kind}, engine=${config.engineUrl})`,
);
