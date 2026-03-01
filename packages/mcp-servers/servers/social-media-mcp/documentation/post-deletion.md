# Post Deletion Functionality

## Overview

This document outlines the implementation plan for adding post deletion functionality to the Social Media MCP Server. Currently, the system supports posting content to various social media platforms but lacks the ability to delete posts.

## Implementation Plan

### 1. Update Mastodon Client

Add a `deleteStatus` method to the `MastodonClient` class in `src/platforms/mastodon/client.ts`:

```typescript
/**
 * Delete a status from Mastodon
 * @param statusId The ID of the status to delete
 * @returns A result object indicating success or failure
 */
async deleteStatus(statusId: string): Promise<{ success: boolean; error?: string }> {
  logger.info('Deleting status', { statusId });

  try {
    // Wait for authentication to complete before proceeding
    const isAuthenticated = await this.waitForAuth();
    logger.info('Authentication status before deleting', { isAuthenticated });
    
    // Use rate limit manager to handle API rate limits
    const result = await rateLimitManager.executeRequest({
      api: 'mastodon',
      endpoint: 'deleteStatus',
      method: 'DELETE',
      priority: 'high',
      retryCount: 0,
      maxRetries: config.rateLimit.maxRetries,
      execute: async () => {
        try {
          // Check if authenticated
          if (!isAuthenticated) {
            throw new Error('Not authenticated with Mastodon API');
          }

          if (this.debug) {
            logger.info('Mastodon API Debug: About to delete status', {
              statusId
            });
          }
          
          // Delete status
          await this.client.v1.statuses.$select(statusId).delete();
          
          if (this.debug) {
            logger.info('Mastodon API Debug: Status deleted successfully');
          }
          
          return { success: true };
        } catch (apiError) {
          logger.error('Error deleting status from Mastodon API', {
            error: apiError instanceof Error ? apiError.message : String(apiError)
          });
          
          // Fall back to mock implementation for testing
          logger.info('Falling back to mock implementation for deleting status');
          
          // Check if this is a mock status ID
          const isMock = statusId.startsWith('mock-');
          
          if (isMock) {
            if (this.debug) {
              logger.info('Mastodon API Debug: Mock status deleted successfully');
            }
            
            return { success: true };
          } else {
            return { 
              success: false, 
              error: apiError instanceof Error ? apiError.message : String(apiError)
            };
          }
        }
      }
    });

    logger.info('Status deletion result', { success: result.success });
    
    return result;
  } catch (error) {
    logger.error('Error deleting status', { 
      statusId,
      error: error instanceof Error ? error.message : String(error) 
    });
    
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error)
    };
  }
}
```

### 2. Update LinkedIn Client

Add a `deleteShare` method to the `LinkedInClient` class in `src/platforms/linkedin/client.ts`:

```typescript
/**
 * Delete a share from LinkedIn
 * @param shareId The ID of the share to delete
 * @returns A result object indicating success or failure
 */
async deleteShare(shareId: string): Promise<{ success: boolean; error?: string }> {
  logger.info('Deleting share', { shareId });

  try {
    // Use rate limit manager to handle API rate limits
    const result = await rateLimitManager.executeRequest({
      api: 'linkedin',
      endpoint: 'deleteShare',
      method: 'DELETE',
      priority: 'high',
      retryCount: 0,
      maxRetries: config.rateLimit.maxRetries,
      execute: async () => {
        try {
          // LinkedIn API doesn't support deleting posts through the v2 API
          // This would require the Marketing Developer Platform access
          throw new Error('LinkedIn API does not support deleting posts through the v2 API');
        } catch (apiError) {
          logger.error('Error deleting share from LinkedIn API', {
            error: apiError instanceof Error ? apiError.message : String(apiError)
          });
          
          // Fall back to mock implementation for testing
          logger.info('Falling back to mock implementation for deleting share');
          
          // Check if this is a mock share ID
          const isMock = shareId.includes('mock-');
          
          if (isMock) {
            if (config.linkedin.debug) {
              logger.info('LinkedIn API Debug: Mock share deleted successfully');
            }
            
            return { success: true };
          } else {
            return { 
              success: false, 
              error: 'LinkedIn API does not support deleting posts through the v2 API'
            };
          }
        }
      }
    });

    logger.info('Share deletion result', { success: result.success });
    
    return result;
  } catch (error) {
    logger.error('Error deleting share', { 
      shareId,
      error: error instanceof Error ? error.message : String(error) 
    });
    
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error)
    };
  }
}
```

### 3. Create Delete Script

Create a new script `delete-post.js` in the root directory:

```javascript
import { createComponentLogger } from './build/utils/logger.js';
import linkedinClient from './build/platforms/linkedin/client.js';
import mastodonClient from './build/platforms/mastodon/client.js';
import { SocialPlatform } from './build/types/index.js';
import historyManager from './build/history/manager.js';

const logger = createComponentLogger('DeletePost');

/**
 * Delete a post from a social media platform
 * @param {string} postId - The ID of the post to delete
 * @param {string} platform - The platform to delete from (mastodon, linkedin, twitter)
 */
async function deletePost(postId, platform) {
  logger.info('Deleting post', { postId, platform });
  
  try {
    let result;
    
    switch (platform.toLowerCase()) {
      case 'mastodon':
        result = await mastodonClient.deleteStatus(postId);
        break;
      case 'linkedin':
        result = await linkedinClient.deleteShare(postId);
        break;
      case 'twitter':
        // Twitter deletion not yet implemented
        result = { success: false, error: 'Twitter deletion not yet implemented' };
        break;
      default:
        result = { success: false, error: `Unknown platform: ${platform}` };
    }
    
    if (result.success) {
      console.log(`Successfully deleted post ${postId} from ${platform}`);
      
      // Update history if needed
      try {
        const updated = historyManager.updatePostStatus(postId, platform, 'deleted');
        if (updated) {
          console.log('History updated successfully');
        }
      } catch (historyError) {
        console.error('Error updating history:', historyError.message);
      }
    } else {
      console.error(`Failed to delete post ${postId} from ${platform}: ${result.error}`);
    }
    
    return result;
  } catch (error) {
    logger.error('Error in delete post function', { 
      error: error instanceof Error ? error.message : String(error) 
    });
    console.error('Error:', error instanceof Error ? error.message : String(error));
    
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

// Check if this script is being run directly
if (process.argv[1].includes('delete-post.js')) {
  // Get command line arguments
  const args = process.argv.slice(2);
  
  if (args.length < 2) {
    console.error('Usage: node delete-post.js <postId> <platform>');
    process.exit(1);
  }
  
  const postId = args[0];
  const platform = args[1];
  
  // Run the delete function
  deletePost(postId, platform)
    .then(result => {
      process.exit(result.success ? 0 : 1);
    })
    .catch(error => {
      console.error('Unhandled error:', error);
      process.exit(1);
    });
}

// Export for use in other modules
export default deletePost;
```

### 4. Update History Manager

Add a `updatePostStatus` method to the `HistoryManager` class in `src/history/manager.ts`:

```typescript
/**
 * Update the status of a post in the history
 * @param postId The ID of the post to update
 * @param platform The platform the post is on
 * @param status The new status of the post (e.g., 'deleted')
 * @returns True if the post was found and updated, false otherwise
 */
updatePostStatus(postId: string, platform: string, status: string): boolean {
  logger.info('Updating post status in history', { postId, platform, status });
  
  try {
    // Load history
    const history = this.loadHistory();
    
    // Find the post in history
    let found = false;
    
    for (const entry of history) {
      // Check if this entry has the post
      const platformEnum = this.getPlatformEnum(platform);
      
      if (platformEnum && entry.platforms.includes(platformEnum)) {
        const content = entry.content[platformEnum];
        
        if (content && content.postId === postId) {
          // Update the status
          content.status = status;
          found = true;
          break;
        }
      }
    }
    
    if (found) {
      // Save the updated history
      this.saveHistory(history);
      logger.info('Post status updated in history', { postId, platform, status });
      return true;
    } else {
      logger.warn('Post not found in history', { postId, platform });
      return false;
    }
  } catch (error) {
    logger.error('Error updating post status in history', { 
      postId, 
      platform, 
      status,
      error: error instanceof Error ? error.message : String(error) 
    });
    return false;
  }
}

/**
 * Convert a platform string to the corresponding enum value
 * @param platform The platform string
 * @returns The platform enum value, or undefined if not found
 */
private getPlatformEnum(platform: string): SocialPlatform | undefined {
  switch (platform.toLowerCase()) {
    case 'twitter':
      return SocialPlatform.TWITTER;
    case 'mastodon':
      return SocialPlatform.MASTODON;
    case 'linkedin':
      return SocialPlatform.LINKEDIN;
    default:
      return undefined;
  }
}
```

## Usage

Once implemented, you can delete posts using the following command:

```bash
node delete-post.js <postId> <platform>
```

For example:

```bash
node delete-post.js 114118098200668360 mastodon
```

## Limitations

- LinkedIn API does not support deleting posts through the v2 API. This would require the Marketing Developer Platform access.
- Twitter deletion is not yet implemented.
- The history update functionality assumes that the history manager has been updated to include post IDs in the history entries.

## Future Improvements

1. Add a UI for managing and deleting posts
2. Implement batch deletion for multiple posts
3. Add scheduling for automatic post deletion after a certain time
4. Implement Twitter post deletion when the Twitter API client is fully implemented
5. Add support for deleting posts with media attachments
