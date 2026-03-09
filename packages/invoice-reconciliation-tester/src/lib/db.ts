// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Prisma client singleton. Reuses a single connection across the lifetime of the
// process to avoid exhausting the connection pool.

import { PrismaClient } from "@prisma/client";

let prisma: PrismaClient;

function getPrisma(): PrismaClient {
  if (!prisma) {
    prisma = new PrismaClient();
  }
  return prisma;
}

export const db = getPrisma();
