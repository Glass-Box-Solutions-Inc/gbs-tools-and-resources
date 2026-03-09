// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Prisma client singleton. Re-uses the same PrismaClient instance across the
// process lifetime to avoid exhausting database connections in development
// (where module reloads would otherwise create new clients).

import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log:
      process.env.NODE_ENV === "development"
        ? ["query", "error", "warn"]
        : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
