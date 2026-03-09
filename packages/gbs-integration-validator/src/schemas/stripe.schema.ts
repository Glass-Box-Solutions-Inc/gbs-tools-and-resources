// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Zod schemas for validating Stripe API response shapes.
// Used by the Stripe validator to confirm SDK responses match expectations.

import { z } from "zod";

export const StripeAccountSchema = z.object({
  id: z.string(),
  object: z.literal("account"),
  business_type: z.string().nullable().optional(),
  charges_enabled: z.boolean(),
  payouts_enabled: z.boolean(),
  country: z.string().optional(),
  default_currency: z.string().optional(),
  email: z.string().nullable().optional(),
  type: z.string().optional(),
});

export const StripeChargeSchema = z.object({
  id: z.string(),
  object: z.literal("charge"),
  amount: z.number(),
  currency: z.string(),
  status: z.string(),
  created: z.number(),
  paid: z.boolean(),
});

export const StripeChargesListSchema = z.object({
  object: z.literal("list"),
  data: z.array(StripeChargeSchema),
  has_more: z.boolean(),
  url: z.string(),
});

export const StripeBalanceSchema = z.object({
  object: z.literal("balance"),
  available: z.array(
    z.object({
      amount: z.number(),
      currency: z.string(),
    }),
  ),
  pending: z.array(
    z.object({
      amount: z.number(),
      currency: z.string(),
    }),
  ),
});
