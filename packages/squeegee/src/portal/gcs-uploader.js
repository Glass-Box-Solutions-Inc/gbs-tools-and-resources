/**
 * Portal GCS Uploader
 *
 * Uploads rendered portal output to a Google Cloud Storage bucket
 * for serving by Glass Box Hub.
 *
 * @file src/portal/gcs-uploader.js
 * @module portal/gcs-uploader
 */

'use strict';

const { Storage } = require('@google-cloud/storage');
const fs = require('fs').promises;
const fsSync = require('fs');
const path = require('path');

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.csv': 'text/csv; charset=utf-8',
  '.pdf': 'application/pdf',
};

/**
 * Upload a directory to GCS bucket
 * @param {string} sourceDir - Local directory to upload
 * @param {string} bucketName - GCS bucket name
 * @param {string} [prefix=''] - Optional prefix in bucket
 * @param {Object} [options={}]
 * @param {boolean} [options.dryRun=false] - If true, only log what would be uploaded
 * @returns {Promise<Object>} - { files_uploaded, bytes_uploaded }
 */
async function uploadToGCS(sourceDir, bucketName, prefix = '', options = {}) {
  if (options.dryRun) {
    console.log(`Portal GCS: DRY RUN — would upload ${sourceDir} to gs://${bucketName}/${prefix}`);
    const files = await listFilesRecursive(sourceDir);
    return { files_uploaded: files.length, bytes_uploaded: 0, dry_run: true };
  }

  const storage = new Storage();
  const bucket = storage.bucket(bucketName);
  let filesUploaded = 0;
  let bytesUploaded = 0;

  const files = await listFilesRecursive(sourceDir);

  for (const filePath of files) {
    const relativePath = path.relative(sourceDir, filePath);
    const gcsPath = prefix ? `${prefix}/${relativePath}` : relativePath;
    const ext = path.extname(filePath).toLowerCase();
    const contentType = CONTENT_TYPES[ext] || 'application/octet-stream';

    try {
      const fileContent = await fs.readFile(filePath);
      const blob = bucket.file(gcsPath);

      await blob.save(fileContent, {
        contentType,
        metadata: {
          cacheControl: ext === '.html' ? 'no-cache' : 'public, max-age=3600',
        },
      });

      filesUploaded++;
      bytesUploaded += fileContent.length;
    } catch (err) {
      console.error(`Portal GCS: Failed to upload ${relativePath}: ${err.message}`);
    }
  }

  console.log(`Portal GCS: Uploaded ${filesUploaded} files (${(bytesUploaded / 1024).toFixed(1)} KB) to gs://${bucketName}/${prefix}`);
  return { files_uploaded: filesUploaded, bytes_uploaded: bytesUploaded };
}

/**
 * Recursively list all files in a directory
 * @param {string} dir
 * @returns {Promise<string[]>}
 */
async function listFilesRecursive(dir) {
  const files = [];

  if (!fsSync.existsSync(dir)) return files;

  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFilesRecursive(fullPath)));
    } else {
      files.push(fullPath);
    }
  }

  return files;
}

module.exports = {
  uploadToGCS,
  listFilesRecursive,
};
