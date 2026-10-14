import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export function parseIssues(output) {
    const counts = new Map();
    for (const line of output.split(/\r?\n/).filter(Boolean)) {
        const match = /^(.*):(\d+):(\d+) - Unknown word \(([^)]+)\)$/.exec(line);
        if (!match) throw new Error(`Unexpected cSpell output: ${line}`);
        const file = match[1].replaceAll('\\', '/');
        const word = match[4];
        const key = JSON.stringify([file, word]);
        const issue = counts.get(key) || { file, word, count: 0 };
        issue.count += 1;
        counts.set(key, issue);
    }
    return [...counts.values()].sort((a, b) =>
        a.file.localeCompare(b.file, 'en') || a.word.localeCompare(b.word, 'en'));
}

export function newIssues(current, baseline) {
    const allowed = new Map(baseline.map(({ file, word, count }) => [JSON.stringify([file, word]), count]));
    return current.flatMap((issue) => {
        const previous = allowed.get(JSON.stringify([issue.file, issue.word])) || 0;
        return issue.count > previous ? [{ ...issue, count: issue.count - previous }] : [];
    });
}

export function runSpelling(root, files, executable = fileURLToPath(import.meta.resolve('cspell/bin.mjs'))) {
    const result = spawnSync(process.execPath, [
        executable, '--config', '.cspell.json', '--no-config-search',
        '--file-list', 'stdin', '--dot', '--no-progress', '--no-summary',
        '--no-color', '--no-show-suggestions', '--relative', '--no-cache',
    ], { cwd: root, input: files.join('\n'), encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
    if (result.error || ![0, 1].includes(result.status) || result.stderr.trim()) {
        throw new Error(`cSpell failed: ${result.error || result.stderr || result.status}`);
    }
    const issues = parseIssues(result.stdout);
    if (result.status === 1 && issues.length === 0) throw new Error('cSpell failed without spelling diagnostics.');
    return issues;
}

function main() {
    const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
    const git = spawnSync('git', ['ls-files', '-z'], { cwd: root, encoding: 'utf8' });
    if (git.error || git.status !== 0) throw new Error(`Cannot list tracked files: ${git.error || git.stderr}`);
    const baseline = JSON.parse(readFileSync(resolve(root, '.cspell-baseline.json'), 'utf8'));
    if (baseline.version !== 1 || !Array.isArray(baseline.issues)) throw new Error('Invalid spelling baseline.');
    const current = runSpelling(root, git.stdout.split('\0').filter(Boolean));
    const added = newIssues(current, baseline.issues);
    const total = current.reduce((sum, issue) => sum + issue.count, 0);
    console.log(`cSpell: ${total} existing occurrences; ${added.length} new or increased file/word entries.`);
    for (const issue of added) console.error(`${issue.file}: ${issue.word} (+${issue.count})`);
    process.exitCode = added.length ? 1 : 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
