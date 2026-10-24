// Use the existing Vite/esbuild JSX transformer with Node's built-in test runner.
import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import { transformSync } from 'esbuild';

registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('.jsx')) {
      const source = readFileSync(new URL(url), 'utf8');
      return { format: 'module', shortCircuit: true,
        source: transformSync(source, { loader: 'jsx', jsx: 'automatic', format: 'esm' }).code };
    }
    if (url.endsWith('.json') && url.includes('/src/mock/')) {
      return { format: 'module', shortCircuit: true,
        source: `export default ${readFileSync(new URL(url), 'utf8')};` };
    }
    return nextLoad(url, context);
  },
});
