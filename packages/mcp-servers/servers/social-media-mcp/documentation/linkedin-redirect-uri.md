# LinkedIn Redirect URI Configuration

## Understanding the Error

When you encounter the error:

```
The redirect_uri does not match the registered value
```

This means that the redirect URI we're using in our OAuth script doesn't match the one that's registered in the LinkedIn Developer Portal for your application.

## Where the Redirect URI is Set

In our OAuth script (`scripts/linkedin-oauth.js`), the redirect URI is set in the configuration object:

```javascript
// LinkedIn OAuth configuration
const config = {
  clientId: process.env.LINKEDIN_CLIENT_ID || '78io7mffdgsnd9',
  clientSecret: process.env.LINKEDIN_CLIENT_SECRET || 'LINKEDIN_CLIENT_SECRET_REDACTED',
  redirectUri: 'https://www.linkedin.com/developers/tools/oauth/redirect',
  scope: 'w_member_social',
};
```

## Current Implementation

We've updated our OAuth script to use LinkedIn's default redirect URI:

```
https://www.linkedin.com/developers/tools/oauth/redirect
```

This is a special redirect URI provided by LinkedIn for testing purposes. When using this redirect URI:

1. LinkedIn will display the authorization code on their page after authentication
2. You'll need to manually copy this code and paste it back into the terminal
3. The script will then exchange the code for an access token

## How to Fix the Error

If you're still encountering the redirect URI error, you have two options:

### Option 1: Use LinkedIn's Default Redirect URI (Recommended)

Our script is now configured to use LinkedIn's default redirect URI. This should work for most LinkedIn applications without any additional configuration.

### Option 2: Update the LinkedIn Developer Portal

If you want to use a custom redirect URI:

1. Log in to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Select your application
3. Go to the "Auth" tab
4. Under "OAuth 2.0 settings", find the "Authorized redirect URLs" section
5. Add your custom redirect URI (e.g., `http://localhost:8080/callback`)
6. Save your changes
7. Update the `redirectUri` value in `scripts/linkedin-oauth.js` to match your custom redirect URI

## Checking the Registered Redirect URI

To check what redirect URI is currently registered for your LinkedIn application:

1. Log in to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Select your application
3. Go to the "Auth" tab
4. Under "OAuth 2.0 settings", look for the "Authorized redirect URLs" section
5. Note the URLs listed there

## Common Redirect URI Formats

LinkedIn applications commonly use these redirect URI formats:

- `https://www.linkedin.com/developers/tools/oauth/redirect` (LinkedIn's default)
- `http://localhost:8080/callback`
- `http://localhost:3000/callback`
- `http://localhost:3000/oauth/callback`
- `https://example.com/oauth/callback`

The important thing is that the redirect URI in our script matches exactly what's registered in the LinkedIn Developer Portal.
