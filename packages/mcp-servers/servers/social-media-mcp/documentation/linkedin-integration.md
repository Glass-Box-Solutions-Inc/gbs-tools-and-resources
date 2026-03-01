# LinkedIn Integration Documentation

## Overview

The LinkedIn integration allows the Social Media MCP Server to post content to LinkedIn accounts. This document outlines how the integration works, the authentication process, and how to troubleshoot common issues.

## Authentication

The LinkedIn client uses OAuth 2.0 for authentication with the following credentials:

1. Client ID
2. Client Secret
3. Access Token

These credentials are stored in the configuration and used to authenticate API requests.

## Key Components

### LinkedInClient Class

Located in `src/platforms/linkedin/client.ts`, this class handles all interactions with the LinkedIn API:

- **Authentication**: Manages token verification and authentication state
- **Posting**: Handles posting content to LinkedIn
- **Trending Topics**: Retrieves trending topics from LinkedIn
- **Engagement Metrics**: Gets engagement data for posts

## Posting to LinkedIn

The `postShare` method handles posting content to LinkedIn:

```typescript
async postShare(content: Content): Promise<PostResult> {
  logger.info('Posting share', { content: content.text.substring(0, 30) + '...' });

  try {
    // Use rate limit manager to handle API rate limits
    const result = await rateLimitManager.executeRequest({
      api: 'linkedin',
      endpoint: 'postShare',
      method: 'POST',
      priority: 'high',
      retryCount: 0,
      maxRetries: config.rateLimit.maxRetries,
      execute: async () => {
        try {
          // Get user profile first
          const meResponse = await this.apiRequest('get', '/me');
          const userId = meResponse.data.id;
          
          if (this.debug) {
            logger.info('LinkedIn API Debug: User profile', { userId });
          }
          
          // Create share
          const shareResponse = await this.apiRequest('post', '/rest/posts', {
            author: `urn:li:person:${userId}`,
            lifecycleState: 'PUBLISHED',
            specificContent: {
              'com.linkedin.ugc.ShareContent': {
                shareCommentary: {
                  text: content.text
                },
                shareMediaCategory: 'NONE'
              }
            },
            visibility: {
              'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'
            }
          });
          
          return shareResponse.data;
        } catch (apiError) {
          // Fall back to mock implementation for testing
          logger.info('Falling back to mock implementation for posting share');
          
          // Generate a mock share response
          const mockShare = {
            id: `urn:li:share:mock-${Date.now()}`,
            created: { time: Date.now() },
            lastModified: { time: Date.now() },
            text: { text: content.text }
          };
          
          if (this.debug) {
            logger.info('LinkedIn API Debug: Mock share response', { response: mockShare });
          }
          
          return mockShare;
        }
      }
    });

    // Get share ID
    const shareId = result.id;
    
    if (!shareId) {
      throw new Error('No share ID returned from LinkedIn API');
    }
    
    // Check if this is a mock response
    const isMock = typeof shareId === 'string' && shareId.includes('mock-');
    
    // Generate share URL
    const shareUrl = isMock 
      ? `https://www.linkedin.com/feed/update/mock/${shareId}`
      : `https://www.linkedin.com/feed/update/${shareId}`;
    
    logger.info('Share posted successfully', { id: shareId });
    
    // Return post result
    return {
      platform: SocialPlatform.LINKEDIN,
      success: true,
      postId: shareId,
      url: shareUrl,
      timestamp: new Date(),
      isMock
    };
  } catch (error) {
    logger.error('Error posting share', { 
      error: error instanceof Error ? error.message : String(error) 
    });
    
    return {
      platform: SocialPlatform.LINKEDIN,
      success: false,
      error: error instanceof Error ? error.message : String(error),
      timestamp: new Date(),
    };
  }
}
```

## API Request Helper

The LinkedIn client uses a helper method for making API requests:

```typescript
private async apiRequest(method: string, url: string, data?: any): Promise<any> {
  try {
    // Create request config
    const config: AxiosRequestConfig = {
      method,
      url,
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.accessToken}`,
        'X-Restli-Protocol-Version': '2.0.0'
      }
    };
    
    // Add data if provided
    if (data) {
      config.data = data;
    }
    
    if (this.debug) {
      logger.info('LinkedIn API Request', { 
        method, 
        url, 
        headers: config.headers,
        data: data ? 'data provided' : 'no data'
      });
    }
    
    // Make request
    const response = await this.client.request(config);
    
    if (this.debug) {
      logger.info('LinkedIn API Response', { 
        status: response.status,
        data: response.data ? 'data received' : 'no data'
      });
    }
    
    return response;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      logger.error('LinkedIn API Error', { 
        response: {
          status: error.response?.status,
          statusText: error.response?.statusText,
          data: error.response?.data
        }
      });
    } else {
      logger.error('LinkedIn API Error', { 
        error: error instanceof Error ? error.message : String(error) 
      });
    }
    
    throw error;
  }
}
```

## Content Limitations

LinkedIn has a character limit of 3,000 characters for posts. If your content exceeds this limit, the API will return an error. Make sure your content fits within this limit.

## Configuration

The LinkedIn client is configured in `src/config/index.ts`:

```typescript
linkedin: {
  credentials: {
    clientId: process.env.LINKEDIN_CLIENT_ID || '',
    clientSecret: process.env.LINKEDIN_CLIENT_SECRET || '',
    accessToken: process.env.LINKEDIN_ACCESS_TOKEN || '',
  },
  debug: true,
},
```

## LinkedIn API Endpoints

The LinkedIn API uses the following endpoints for posting content:

- `/me` - Get the current user's profile
- `/rest/posts` - Create a new post

## Authentication Update

To update the LinkedIn authentication with the new credentials provided:

1. Client ID: `78io7mffdgsnd9`
2. Client Secret: `LINKEDIN_CLIENT_SECRET_REDACTED`

These have been updated in the configuration file. However, LinkedIn requires a proper OAuth 2.0 access token, which cannot be obtained programmatically without user interaction.

### Getting a Valid Access Token

To get a valid access token, use the OAuth helper script:

1. Navigate to the scripts directory:
   ```bash
   cd scripts
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run the LinkedIn OAuth script:
   ```bash
   npm run linkedin-oauth
   ```

4. Follow the instructions in the terminal:
   - The script will open a browser window to the LinkedIn authorization page
   - Log in to LinkedIn and authorize the application
   - LinkedIn will display the authorization code on their page
   - Copy the authorization code and paste it back into the terminal
   - The script will exchange the code for an access token
   - The access token will be displayed in the terminal

5. Update the access token in the configuration:
   - Option 1: Add it to your `.env` file:
     ```
     LINKEDIN_ACCESS_TOKEN=your_access_token_here
     ```
   - Option 2: Update it directly in `src/config/index.ts`

6. Navigate back to the main project directory and rebuild the application:
   ```bash
   cd ..
   npm run build
   ```

7. Run the application again to test the LinkedIn integration

### Troubleshooting OAuth

- **Redirect URI Error**: Make sure your LinkedIn application is properly configured with the correct redirect URI (`https://www.linkedin.com/developers/tools/oauth/redirect`). For detailed instructions on fixing redirect URI issues, see [LinkedIn Redirect URI Configuration](./linkedin-redirect-uri.md).
- **Scope Error**: If you encounter a "unauthorized_scope_error" error, it means the scope you're requesting is not authorized for your application. See [LinkedIn OAuth Scopes](./linkedin-scope.md) for information on how to fix scope-related issues.
- **Token Exchange Error**: Check that your client ID and client secret are correct.
- **Browser Opening Issues**: The script now includes enhanced browser detection and fallback mechanisms:
  - First tries to open in the default browser
  - If that fails, tries specific browsers (Chrome, Edge, Firefox)
  - If all browser attempts fail, falls back to platform-specific commands
  - As a last resort, displays the URL for manual opening
  - This helps avoid issues where LinkedIn tries to open in the app instead of a browser
- **Authorization Code Not Displayed**: If LinkedIn doesn't display the authorization code after authentication:
  - Make sure you're using the correct redirect URI (`https://www.linkedin.com/developers/tools/oauth/redirect`)
  - Check that your LinkedIn application is properly configured
  - Try clearing your browser cookies and cache, then try again

## Troubleshooting

### Authentication Issues

If you're experiencing authentication issues:

1. Check that your access token is valid
2. Verify that your client ID and client secret are correct
3. Look for authentication errors in the logs

Common authentication errors:

- `401 Unauthorized` - Invalid access token
- `403 Forbidden` - Insufficient permissions

### Content Issues

If your posts are failing:

1. Check the character count (must be under 3,000 characters)
2. Ensure there are no formatting issues
3. Check for any API-specific errors in the logs

### Mock Mode

The client will fall back to mock mode if:

1. No access token is provided
2. Authentication fails
3. The API returns an error

In mock mode, posts will appear successful but will have a URL like `https://www.linkedin.com/feed/update/mock/urn:li:share:mock-1234567890` and will be marked with `isMock: true` in the response.

## Current Status

The LinkedIn integration is currently using mock mode due to an invalid access token. To fix this, we need to update the access token in the configuration.
