// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import { createParamDecorator, ExecutionContext } from '@nestjs/common';

/**
 * @CurrentUser() parameter decorator — extracts user identity from the request.
 *
 * Standalone mode: reads from `req.user` (set by your auth middleware).
 * Hosted mode (Glassy): BetterAuth middleware sets `req.user` on the request object.
 *
 * Usage:
 *   @Get() getProfile(@CurrentUser('id') userId: string) { ... }
 *   @Get() getProfile(@CurrentUser() user: any) { ... }
 */
export const CurrentUser = createParamDecorator(
  (data: string | undefined, ctx: ExecutionContext) => {
    const request = ctx.switchToHttp().getRequest();
    const user = request.user;
    return data ? user?.[data] : user;
  },
);
