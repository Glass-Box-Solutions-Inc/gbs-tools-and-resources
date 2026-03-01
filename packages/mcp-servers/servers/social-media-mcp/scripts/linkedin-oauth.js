#!/usr/bin/env node

/**
 * LinkedIn OAuth 2.0 Authentication Script
 * 
 * This script handles the OAuth 2.0 flow for LinkedIn to obtain an access token.
 * It will:
 * 1. Open a browser for the user to authenticate with LinkedIn
 * 2. Prompt the user to copy the authorization code from LinkedIn's page
 * 3. Exchange the authorization code for an access token
 * 4. Log the access token for the user to add to the configuration
 */

import axios from 'axios';
import open, { apps } from 'open';
import dotenv from 'dotenv';
import readline from 'readline';
import { exec } from 'child_process';
import os from 'os';

// Load environment variables
dotenv.config();

/**
 * Try to open the URL in a specific browser
 * This is a fallback in case the default browser approach doesn't work
 */
async function tryOpenInBrowser(url) {
  // Try with default browser first
  try {
    console.log('\n🌐 Attempting to open in default browser...');
    await open(url, {
      app: {
        name: apps.browser
      }
    });
    return true;
  } catch (err) {
    console.error('\n⚠️ Could not open in default browser:', err.message);
  }

  // Try with specific browsers based on platform
  const platform = os.platform();
  let browsers = [];

  if (platform === 'win32') {
    browsers = [
      { name: 'chrome', path: 'chrome' },
      { name: 'edge', path: 'msedge' },
      { name: 'firefox', path: 'firefox' },
      // Common Windows browser paths
      { name: 'Chrome', path: 'C:/Program Files/Google/Chrome/Application/chrome.exe' },
      { name: 'Edge', path: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' },
      { name: 'Firefox', path: 'C:/Program Files/Mozilla Firefox/firefox.exe' }
    ];
  } else if (platform === 'darwin') { // macOS
    browsers = [
      { name: 'chrome', path: 'google chrome' },
      { name: 'safari', path: 'safari' },
      { name: 'firefox', path: 'firefox' }
    ];
  } else { // Linux and others
    browsers = [
      { name: 'chrome', path: 'google-chrome' },
      { name: 'firefox', path: 'firefox' },
      { name: 'chromium', path: 'chromium-browser' }
    ];
  }

  // Try each browser
  for (const browser of browsers) {
    try {
      console.log(`\n🌐 Attempting to open in ${browser.name}...`);
      await open(url, {
        app: {
          name: browser.path
        }
      });
      return true;
    } catch (err) {
      console.error(`\n⚠️ Could not open in ${browser.name}:`, err.message);
    }
  }

  // If all attempts fail, use a platform-specific command as last resort
  try {
    console.log('\n🌐 Attempting to open with platform-specific command...');
    if (platform === 'win32') {
      exec(`start "" "${url}"`);
    } else if (platform === 'darwin') {
      exec(`open "${url}"`);
    } else {
      exec(`xdg-open "${url}"`);
    }
    return true;
  } catch (err) {
    console.error('\n⚠️ Could not open with platform-specific command:', err.message);
  }

  // If all attempts fail, show the URL for manual opening
  console.log('\n📋 Please manually open this URL in your browser:');
  console.log(url);
  return false;
}

/**
 * Create a readline interface for user input
 */
function createReadlineInterface() {
  return readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });
}

/**
 * Prompt the user for input
 */
function prompt(rl, question) {
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      resolve(answer);
    });
  });
}

/**
 * Main function to run the OAuth flow
 */
async function runOAuthFlow() {
  // LinkedIn OAuth configuration
  const config = {
    clientId: process.env.LINKEDIN_CLIENT_ID || '78io7mffdgsnd9',
    clientSecret: process.env.LINKEDIN_CLIENT_SECRET || 'LINKEDIN_CLIENT_SECRET_REDACTED',
    redirectUri: 'https://www.linkedin.com/developers/tools/oauth/redirect',
    scope: 'r_liteprofile w_member_social',
  };

  console.log('\n🚀 LinkedIn OAuth Flow');
  console.log('\n📝 Instructions:');
  console.log('1. The browser will open and redirect you to LinkedIn');
  console.log('2. Log in to LinkedIn and authorize the application');
  console.log('3. LinkedIn will display the authorization code on the page');
  console.log('4. Copy the authorization code and paste it back here');
  console.log('5. The script will exchange the code for an access token');
  console.log('\n⏳ Opening browser...\n');

  // Construct the authorization URL
  const authUrl = `https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=${config.clientId}&redirect_uri=${encodeURIComponent(config.redirectUri)}&scope=${encodeURIComponent(config.scope)}&state=random_state_string`;

  // Open the browser
  await tryOpenInBrowser(authUrl);

  // Create readline interface
  const rl = createReadlineInterface();

  try {
    // Prompt the user for the authorization code
    console.log('\n⚠️ After authorizing the application, LinkedIn will display the authorization code.');
    console.log('Look for a code that looks like: AQTFPPdqZs-y7...');
    const code = await prompt(rl, '\n📋 Please enter the authorization code: ');

    if (!code) {
      console.error('\n❌ No authorization code provided. Exiting...');
      process.exit(1);
    }

    console.log('\n⏳ Exchanging authorization code for access token...');

    // Exchange the authorization code for an access token
    try {
      const tokenResponse = await axios.post('https://www.linkedin.com/oauth/v2/accessToken', null, {
        params: {
          grant_type: 'authorization_code',
          code,
          redirect_uri: config.redirectUri,
          client_id: config.clientId,
          client_secret: config.clientSecret,
        },
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      // Extract the access token and other information
      const { access_token, expires_in, refresh_token } = tokenResponse.data;

      // Log the access token
      console.log('\n✅ Authentication successful!');
      console.log('\n📋 Access Token Information:');
      console.log('==========================');
      console.log(`Access Token: ${access_token}`);
      console.log(`Expires In: ${expires_in} seconds (${Math.floor(expires_in / 60 / 60)} hours)`);
      if (refresh_token) {
        console.log(`Refresh Token: ${refresh_token}`);
      } else {
        console.log('Refresh Token: Not provided');
      }
      console.log('==========================');

      console.log('\n📝 Next Steps:');
      console.log('1. Copy the access token');
      console.log('2. Update the LINKEDIN_ACCESS_TOKEN in your configuration:');
      console.log('   - Option 1: Add it to your .env file:');
      console.log('     LINKEDIN_ACCESS_TOKEN=your_access_token_here');
      console.log('   - Option 2: Update it directly in src/config/index.ts');
      console.log('3. Rebuild the application:');
      console.log('   npm run build');
      console.log('4. Run the application again to test the LinkedIn integration');
    } catch (error) {
      console.error('\n❌ Error exchanging code for token:');
      if (error.response) {
        console.error(`Status: ${error.response.status}`);
        console.error('Response:', error.response.data);
      } else {
        console.error(error.message);
      }
    }
  } finally {
    // Close the readline interface
    rl.close();
  }
}

// Run the OAuth flow
runOAuthFlow().catch(error => {
  console.error('\n❌ Uncaught Exception:');
  console.error(error);
  process.exit(1);
});
