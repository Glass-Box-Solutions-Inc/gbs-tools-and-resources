# Social Media MCP Scripts

This directory contains utility scripts for the Social Media MCP Server.

## LinkedIn OAuth Script

The `linkedin-oauth.js` script handles the OAuth 2.0 flow for LinkedIn to obtain an access token. This is necessary because LinkedIn requires a proper OAuth 2.0 access token for API access, which cannot be obtained programmatically without user interaction.

### Prerequisites

- Node.js 16 or higher
- npm or yarn

### Installation

```bash
# Navigate to the scripts directory
cd scripts

# Install dependencies
npm install
```

### Usage

```bash
# Run the LinkedIn OAuth script
npm run linkedin-oauth
```

### What the Script Does

1. Attempts to open a browser window to the LinkedIn authorization page
   - First tries the default browser
   - If that fails, tries specific browsers (Chrome, Edge, Firefox)
   - If all browser attempts fail, falls back to platform-specific commands
   - As a last resort, displays the URL for manual opening
2. Prompts you to log in to LinkedIn and authorize the application
3. LinkedIn displays the authorization code on their page
4. You copy the authorization code and paste it back into the terminal
5. The script exchanges the authorization code for an access token
6. Displays the access token in the terminal

### After Getting the Access Token

Once you have the access token:

1. Copy the access token from the terminal
2. Update the `LINKEDIN_ACCESS_TOKEN` in your configuration:
   - Option 1: Add it to your `.env` file:
     ```
     LINKEDIN_ACCESS_TOKEN=your_access_token_here
     ```
   - Option 2: Update it directly in `src/config/index.ts`:
     ```typescript
     linkedin: {
       credentials: {
         clientId: process.env.LINKEDIN_CLIENT_ID || '78io7mffdgsnd9',
         clientSecret: process.env.LINKEDIN_CLIENT_SECRET || 'LINKEDIN_CLIENT_SECRET_REDACTED',
         accessToken: process.env.LINKEDIN_ACCESS_TOKEN || 'your_access_token_here',
         refreshToken: process.env.LINKEDIN_REFRESH_TOKEN || '',
       } as LinkedInCredentials,
       // ...
     },
     ```
3. Navigate back to the main project directory and rebuild the application:
   ```bash
   cd ..
   npm run build
   ```
4. Run the application again to test the LinkedIn integration

### Troubleshooting

- **Authentication Error**: Make sure your LinkedIn application is properly configured with the correct redirect URI (`https://www.linkedin.com/developers/tools/oauth/redirect`). For detailed instructions on fixing redirect URI issues, see [LinkedIn Redirect URI Configuration](../documentation/linkedin-redirect-uri.md).
- **Scope Error**: If you encounter a "unauthorized_scope_error" error, it means the scope you're requesting is not authorized for your application. See [LinkedIn OAuth Scopes](../documentation/linkedin-scope.md) for information on how to fix scope-related issues.
- **Token Exchange Error**: Check that your client ID and client secret are correct.
- **Browser Opening Issues**: If the script fails to open a browser automatically:
  - Check if you have a default browser set in your system settings
  - Try manually opening the URL displayed in the terminal
  - If LinkedIn opens in the app instead of the browser, the script will try multiple browsers to find one that works
- **Authorization Code Not Displayed**: If LinkedIn doesn't display the authorization code after authentication:
  - Make sure you're using the correct redirect URI (`https://www.linkedin.com/developers/tools/oauth/redirect`)
  - Check that your LinkedIn application is properly configured
  - Try clearing your browser cookies and cache, then try again
