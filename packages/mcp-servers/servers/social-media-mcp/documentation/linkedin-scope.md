# LinkedIn OAuth Scopes

## Understanding the Error

When you encounter the error:

```
unauthorized_scope_error: Scope "r_liteprofile" is not authorized for your application
```

This means that the scope you're requesting in your OAuth flow is not authorized for your LinkedIn application. Each LinkedIn application has specific scopes that it's authorized to use, and you can only request those scopes during the OAuth flow.

## Where the Scope is Set

In our OAuth script (`scripts/linkedin-oauth.js`), the scope is set in the configuration object:

```javascript
// LinkedIn OAuth configuration
const config = {
  clientId: process.env.LINKEDIN_CLIENT_ID || '78io7mffdgsnd9',
  clientSecret: process.env.LINKEDIN_CLIENT_SECRET || 'LINKEDIN_CLIENT_SECRET_REDACTED',
  redirectUri: 'http://localhost:8080/callback',
  scope: 'w_member_social', // Only using w_member_social scope
};
```

## Common LinkedIn OAuth Scopes

LinkedIn provides various OAuth scopes for different purposes:

- `w_member_social`: Write and interact with network updates and messaging
- `r_liteprofile`: Read basic profile information
- `r_emailaddress`: Read email address
- `r_basicprofile`: Read basic profile information (deprecated)
- `r_fullprofile`: Read full profile information (deprecated)
- `rw_company_admin`: Manage company pages
- `w_organization_social`: Post, comment and like posts on behalf of an organization

## How to Fix the Error

We've updated the script to only use the `w_member_social` scope, which is likely authorized for your application since it's needed for posting content. If you encounter scope-related errors, you have two options:

### Option 1: Update the LinkedIn Developer Portal

1. Log in to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Select your application
3. Go to the "Products" tab
4. Enable the products that correspond to the scopes you need
5. Save your changes

### Option 2: Update the OAuth Script

If you know which scopes are authorized for your application, you can update the script to only use those scopes:

1. Open `scripts/linkedin-oauth.js`
2. Find the `config` object
3. Update the `scope` value to match the scopes authorized for your application
4. Save the file

## Checking Authorized Scopes

To check which scopes are authorized for your LinkedIn application:

1. Log in to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Select your application
3. Go to the "Products" tab
4. Look at the enabled products to determine which scopes are available

## Minimum Required Scope

For the Social Media MCP Server to post content to LinkedIn, the minimum required scope is:

- `w_member_social`: This scope allows the application to post content on behalf of the user

If your application doesn't have this scope authorized, you'll need to enable the corresponding product in the LinkedIn Developer Portal.
