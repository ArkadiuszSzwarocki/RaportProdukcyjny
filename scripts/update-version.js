import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

function getGitHash() {
  try {
    return execSync('git rev-parse --short HEAD').toString().trim();
  } catch (e) {
    return 'unknown';
  }
}

function getGitBranch() {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD').toString().trim();
  } catch (e) {
    return 'unknown';
  }
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function main() {
  const hash = getGitHash();
  const branch = getGitBranch();
  const ts = new Date().toISOString().replace('T', ' ').substring(0, 19);
  const content = `${branch} ${hash} (${ts})`;
  const publicDir = path.join(__dirname, '..', 'public');
  if (!fs.existsSync(publicDir)) fs.mkdirSync(publicDir);
  const target = path.join(publicDir, 'version.txt');
  fs.writeFileSync(target, content, 'utf8');
  console.log('Wrote', target, '->', content);
}

main();
