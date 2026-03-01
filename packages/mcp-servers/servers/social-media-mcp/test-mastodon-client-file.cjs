// Test script for Mastodon client with mock fallback
const fs = require('fs').promises;
const mastodonClient = require('./build/src/platforms/mastodon/client.js').default;

// Define platform constants directly
const MASTODON = 'mastodon';

// Function to write logs to a file
async function writeLog(message) {
  await fs.appendFile('mastodon-test-log.txt', message + '\n');
}

async function testMastodonClient() {
  await writeLog('Testing Mastodon client with mock fallback...');
  
  try {
    // Create test content
    const content = {
      text: `Test toot from Social Media MCP Server - ${new Date().toISOString()}`,
      platform: MASTODON
    };
    
    // Post to Mastodon
    await writeLog(`Posting to Mastodon... ${content.text}`);
    const postResult = await mastodonClient.postStatus(content);
    
    // Log result
    await writeLog(`Mastodon post result: ${JSON.stringify(postResult, null, 2)}`);
    
    // Get trending tags
    await writeLog('Getting trending tags from Mastodon...');
    const trendingTags = await mastodonClient.getTrendingTags(5);
    
    // Log trending tags
    await writeLog(`Mastodon trending tags: ${JSON.stringify(trendingTags, null, 2)}`);
    
    // If post was successful, get engagement metrics
    if (postResult.success && postResult.postId) {
      await writeLog(`Getting engagement metrics for post: ${postResult.postId}`);
      const metrics = await mastodonClient.getEngagementMetrics(postResult.postId);
      
      // Log metrics
      await writeLog(`Mastodon engagement metrics: ${JSON.stringify(metrics, null, 2)}`);
    }
    
    await writeLog('Test completed successfully!');
  } catch (error) {
    await writeLog(`Error testing Mastodon client: ${error.message}`);
  }
}

// Clear the log file first
fs.writeFile('mastodon-test-log.txt', '').then(() => {
  // Run the test
  testMastodonClient().catch(async error => {
    await writeLog(`Unhandled error: ${error.message}`);
  });
});
