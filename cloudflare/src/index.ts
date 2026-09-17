import { Container, ContainerProxy, getContainer } from "@cloudflare/containers";

export { ContainerProxy };

interface Env {
  CRE_GAME: DurableObjectNamespace<CreGameContainer>;
  COOKIE_SECRET: string;
  SESSION_SECRET: string;
  PROFESSOR_PASSCODE: string;
  GOOGLE_APPLICATION_CREDENTIALS_JSON: string;
}

export class CreGameContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "10m";
  enableInternet = true;

  envVars = {
    NODE_ENV: "production",
    STORE: "firestore",
    ENGINE_URL: "http://127.0.0.1:8081",
    COOKIE_SECRET: this.env.COOKIE_SECRET,
    SESSION_SECRET: this.env.SESSION_SECRET,
    PROFESSOR_PASSCODE: this.env.PROFESSOR_PASSCODE,
    GOOGLE_CLOUD_PROJECT: "cre-605",
    GOOGLE_APPLICATION_CREDENTIALS_JSON: this.env.GOOGLE_APPLICATION_CREDENTIALS_JSON,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const container = getContainer(env.CRE_GAME);
    await container.startAndWaitForPorts({
      ports: [8080],
      startOptions: { enableInternet: true },
    });
    return container.fetch(request);
  },
};
