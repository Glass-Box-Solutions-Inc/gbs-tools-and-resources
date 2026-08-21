import { describe, expect, it } from "vitest";
import { postgresConfigFromEnvironment } from "../src/tokens/durable/azure/runtime-config";

describe("postgresConfigFromEnvironment", () => {
  it("uses certificate-verifying TLS when PGSSLMODE=require", () => {
    const config = postgresConfigFromEnvironment({
      PGHOST: "database.example.test",
      PGUSER: "phi-worker",
      PGPASSWORD: "test-password",
      PGDATABASE: "phi-control-plane",
      PGSSLMODE: "require",
    });

    expect(config.ssl).toBe(true);
    expect(config.ssl).not.toEqual(
      expect.objectContaining({ rejectUnauthorized: false }),
    );
  });
});
