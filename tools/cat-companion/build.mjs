import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {writeFile} from 'node:fs/promises';
const assets = fileURLToPath(new URL('../../app/assets/themes/', import.meta.url));
const result=await build({entryPoints:[`${assets}/cat-companion.js`],write:false,
  outfile:`${assets}/cat-companion.bundle.js`, bundle:true,
  format:'esm', target:'es2020', minify:true, legalComments:'eof',
  nodePaths:[fileURLToPath(new URL('./node_modules',import.meta.url))]});
// Three's embedded GLSL contains trailing spaces; normalize generated output.
for(const file of result.outputFiles)await writeFile(file.path,file.text.replace(/[ \t]+$/gm,''));
