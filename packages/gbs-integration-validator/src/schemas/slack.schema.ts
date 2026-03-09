// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
//
// Zod schemas for validating Slack API response shapes.
// Used by the Slack validator to confirm Web API returns expected data.

import { z } from "zod";

export const SlackAuthTestSchema = z.object({
  ok: z.boolean(),
  url: z.string().optional(),
  team: z.string().optional(),
  user: z.string().optional(),
  team_id: z.string().optional(),
  user_id: z.string().optional(),
  bot_id: z.string().optional(),
  is_enterprise_install: z.boolean().optional(),
});

export const SlackChannelSchema = z.object({
  id: z.string(),
  name: z.string(),
  is_channel: z.boolean().optional(),
  is_private: z.boolean().optional(),
  is_archived: z.boolean().optional(),
  created: z.number().optional(),
  num_members: z.number().optional(),
});

export const SlackConversationsListSchema = z.object({
  ok: z.boolean(),
  channels: z.array(SlackChannelSchema),
  response_metadata: z
    .object({
      next_cursor: z.string().optional(),
    })
    .optional(),
});

export const SlackUserSchema = z.object({
  id: z.string(),
  name: z.string(),
  real_name: z.string().optional(),
  is_bot: z.boolean().optional(),
  deleted: z.boolean().optional(),
});

export const SlackUsersListSchema = z.object({
  ok: z.boolean(),
  members: z.array(SlackUserSchema),
});
