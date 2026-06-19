import { chromium } from "playwright";
import fs from "fs";
import path from "path";

// Simple command-line argument parser
const args = {};
for (let i = 2; i < process.argv.length; i++) {
  const arg = process.argv[i];
  if (arg.startsWith("--")) {
    const key = arg.slice(2);
    const val = process.argv[i + 1];
    if (val && !val.startsWith("--")) {
      args[key] = val;
      i++;
    } else {
      args[key] = true;
    }
  }
}

const action = args.action;
const baseUrl = args.url || process.env.STAGING_URL || "https://staging.app.adjudica.ai";
const email = args.email || process.env.E2E_TEST_USER_EMAIL || "lawyer@adjudica.ai";
const password = args.password || process.env.E2E_TEST_USER_PASSWORD || "password123";
const authStatePath = args["auth-state"] || path.join(process.env.HOME || "/home/sky", ".adjudica_staging_auth.json");
const firmSlug = args["firm-slug"] || "smith-associates";
const matterId = args["matter-id"];
const filePath = args["file-path"];
const targetPath = args["target-path"] || "/";

async function getBrowserContext() {
  const loadExtension = args["with-extension"];
  const headless = args.headless !== undefined ? args.headless === "true" : !loadExtension;
  
  let launchArgs = [];
  let extensionPath = "";
  
  if (loadExtension) {
    const extBase = "/home/sky/.config/google-chrome/Profile 1/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn";
    if (fs.existsSync(extBase)) {
      const versions = fs.readdirSync(extBase).filter(f => fs.statSync(path.join(extBase, f)).isDirectory());
      if (versions.length > 0) {
        extensionPath = path.join(extBase, versions[0]);
        launchArgs.push(
          `--disable-extensions-except=${extensionPath}`,
          `--load-extension=${extensionPath}`
        );
        console.error(`Loading Claude Extension from ${extensionPath}`);
      }
    }
  }

  if (loadExtension || args["persistent"]) {
    const tempUserDataDir = path.join(fs.realpathSync("/tmp"), `playwright-user-data-${Math.random().toString(36).slice(2)}`);
    const context = await chromium.launchPersistentContext(tempUserDataDir, {
      headless,
      args: launchArgs,
      storageState: fs.existsSync(authStatePath) ? authStatePath : undefined
    });
    return { browser: { close: () => context.close() }, context };
  } else {
    const browser = await chromium.launch({ headless, args: launchArgs });
    const context = fs.existsSync(authStatePath)
      ? await browser.newContext({ storageState: authStatePath })
      : await browser.newContext();
    return { browser, context };
  }
}

async function run() {
  if (action === "login") {
    console.error(`Starting login action for ${email} at ${baseUrl}`);
    const { browser, context } = await getBrowserContext();
    const page = await context.newPage();
    try {
      await page.goto(`${baseUrl}/auth/login`);
      await page.waitForLoadState("networkidle");
      await page.getByLabel(/email/i).fill(email);
      await page.getByLabel(/password/i).first().fill(password);
      
      const authResponsePromise = page.waitForResponse(
        (res) => res.url().includes("/auth/login") && res.status() > 0,
        { timeout: 15000 }
      );
      await page.getByRole("button", { name: /login|sign in|log in/i }).click();
      await authResponsePromise;
      
      await page.waitForURL(
        (url) => !url.pathname.includes("/auth/") && url.pathname !== "/",
        { timeout: 15000 }
      );
      
      await context.storageState({ path: authStatePath });
      console.log(JSON.stringify({
        success: true,
        email,
        landingUrl: page.url(),
        authStatePath,
        message: "Successfully authenticated and saved storage state."
      }));
    } catch (e) {
      console.log(JSON.stringify({
        success: false,
        error: e.message,
        message: "Login flow failed."
      }));
      process.exit(1);
    } finally {
      await browser.close();
    }
  } 
  
  else if (action === "navigate") {
    const { browser, context } = await getBrowserContext();
    const page = await context.newPage();
    try {
      const url = `${baseUrl}${targetPath}`;
      await page.goto(url);
      await page.waitForLoadState("networkidle");
      const title = await page.title();
      console.log(JSON.stringify({
        success: true,
        url,
        title,
        status: 200,
        message: `Successfully navigated to ${url}`
      }));
    } catch (e) {
      console.log(JSON.stringify({
        success: false,
        error: e.message
      }));
      process.exit(1);
    } finally {
      await browser.close();
    }
  }

  else if (action === "upload") {
    if (!matterId) {
      console.log(JSON.stringify({ success: false, error: "Missing --matter-id" }));
      process.exit(1);
    }
    if (!filePath || !fs.existsSync(filePath)) {
      console.log(JSON.stringify({ success: false, error: `File not found: ${filePath}` }));
      process.exit(1);
    }
    
    const { browser, context } = await getBrowserContext();
    const page = await context.newPage();
    try {
      const targetUrl = `${baseUrl}/firm/${firmSlug}/matter/${matterId}`;
      await page.goto(targetUrl);
      await page.waitForLoadState("networkidle");
      
      const fileInput = page.locator('input[type="file"]');
      await fileInput.setInputFiles(filePath);
      await page.waitForTimeout(3000); // Wait for upload/confirm handlers to complete
      
      console.log(JSON.stringify({
        success: true,
        file: path.basename(filePath),
        targetUrl,
        message: `Uploaded file to matter ${matterId} successfully.`
      }));
    } catch (e) {
      console.log(JSON.stringify({
        success: false,
        error: e.message
      }));
      process.exit(1);
    } finally {
      await browser.close();
    }
  }

  else {
    console.log(JSON.stringify({
      success: false,
      error: `Unknown action: ${action}`
    }));
    process.exit(1);
  }
}

run();
