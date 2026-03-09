// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    globals: false,
    environment: "node",
    testTimeout: 10000,
  },
});
