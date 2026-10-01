import assert from 'node:assert/strict';
import { test } from 'node:test';
import { newIssues, parseIssues, runSpelling } from '../../scripts/check_spelling.mjs';

// Deliberately invalid words used to verify the spelling gate.
// cspell:ignore existingtypo newtypo

test('existing debt permits removals but blocks more occurrences and other files', () => {
    const baseline = [{ file: 'old.py', word: 'existingtypo', count: 2 }];
    assert.deepEqual(newIssues([{ ...baseline[0], count: 1 }], baseline), []);
    assert.deepEqual(newIssues([{ ...baseline[0], count: 3 }], baseline), [{ ...baseline[0], count: 1 }]);
    assert.deepEqual(newIssues([{ ...baseline[0], file: 'new.py', count: 1 }], baseline),
        [{ file: 'new.py', word: 'existingtypo', count: 1 }]);
    assert.equal(newIssues([{ file: 'old.py', word: 'newtypo', count: 1 }], baseline).length, 1);
});

test('counts duplicate words while normalizing Windows paths', () => {
    assert.deepEqual(parseIssues('app\\file.py:1:2 - Unknown word (existingtypo)\napp/file.py:2:2 - Unknown word (existingtypo)\n'),
        [{ file: 'app/file.py', word: 'existingtypo', count: 2 }]);
    assert.throws(() => parseIssues('Configuration error'), /Unexpected cSpell output/);
});

test('missing checker and missing files fail instead of passing as an empty result', () => {
    assert.throws(() => runSpelling(process.cwd(), ['README.md'], 'missing-cspell.mjs'), /cSpell failed/);
    assert.throws(() => runSpelling(process.cwd(), ['missing-input-file.md']), /cSpell failed/);
});
