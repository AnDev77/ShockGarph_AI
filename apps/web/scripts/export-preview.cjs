// API의 기존 집계를 실제 React 컴포넌트로 렌더링해 화면 리뷰에 사용한다.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { execFileSync } = require('node:child_process');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { ChakraProvider, defaultSystem } = require('@chakra-ui/react');
const postcss = require('postcss');
const web = path.resolve(__dirname, '..');
const repo = path.resolve(web, '../..');
const rootId = 'shockgraph-preview';
const componentPath = path.join(web, 'components/dashboard.tsx');
const compiled = ts.transpileModule(fs.readFileSync(componentPath, 'utf8'), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const loaded = new Module(componentPath, module);
loaded.filename = componentPath;
loaded.paths = Module._nodeModulePaths(path.dirname(componentPath));
loaded._compile(compiled, componentPath);
function scoped(css) {
  const tree = postcss.parse(css);
  tree.walkRules(rule => {
    if (rule.parent.type === 'atrule' && /keyframes/.test(rule.parent.name)) return;
    rule.selectors = rule.selectors.map(selector => {
      if ([':root', 'html', 'body', ':host'].includes(selector)) return `#${rootId}`;
      return `#${rootId} ${selector}`;
    });
  });
  return tree.toString();
}
(async () => {
  const python = process.env.PREVIEW_PYTHON || path.join(repo, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const { research, analysis, market, report } = JSON.parse(execFileSync(python,
    [path.join(repo, 'scripts/export_dashboard_review_data.py')], { cwd: repo, encoding: 'utf8' }));
  let markup = renderToStaticMarkup(React.createElement(ChakraProvider, { value: defaultSystem },
    React.createElement(loaded.exports.Dashboard, { initialData: { research, analysis, market } })));
  const styles = [];
  markup = markup.replace(/<style[^>]*>([\s\S]*?)<\/style>/g, (_, css) => { styles.push(scoped(css)); return ''; });
  const isFragment = process.argv.includes('--fragment');
  if (isFragment) {
    const icons = { pulse: 'activity', grid: 'layout-grid', chart: 'chart-line', news: 'newspaper', book: 'book-open', arrow: 'arrow-right', refresh: 'refresh-cw', layers: 'layers' };
    markup = markup.replace(/<svg([^>]*data-icon="([^"]+)"[^>]*)>[\s\S]*?<\/svg>/g,
      (_, attrs, name) => `<i data-lucide="${icons[name] ?? 'chart-line'}" aria-hidden="true"></i>`);
  }
  const globals = scoped(fs.readFileSync(path.join(web, 'app/globals.css'), 'utf8'));
  const overrides = `#${rootId}{color-scheme:light;color:#20222c;background:#f6f7f9;font-family:Arial,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;--sg-bg:#f6f7f9;--sg-ink:#20222c;--sg-muted:#717585;--sg-line:#e9ebf0;--sg-brand:#5d50e8;}#${rootId} .app-shell{min-height:0;}#${rootId} .sidebar{position:relative;top:auto;height:auto;align-self:stretch;}#${rootId} .skip-link{display:none;}#${rootId} button{cursor:inherit;}#${rootId} .refresh-button{display:none;}#${rootId} [data-lucide]{display:inline-block;width:18px;height:18px;}`;
  const data = JSON.stringify(report.diagnostic.comparison).replace(/</g, '\\u003c');
  const controls = fs.readFileSync(path.join(__dirname, 'preview-controls.js'), 'utf8');
  const fragment = `<div id="${rootId}">\n<style>${styles.join('\n')}\n${globals}\n${overrides}</style>\n${markup}\n<script type="application/json" id="shockgraph-preview-data">${data}</script>\n<script>${controls}</script>\n</div>\n`;
  const output = path.resolve(process.argv[2] || path.join(repo, 'docs/ui/market-expectation-dashboard.html'));
  const content = isFragment ? fragment : `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ShockGraph 과거 평가 화면 미리보기</title></head><body style="margin:0">${fragment}</body></html>`;
  fs.writeFileSync(output, content);
  console.log(`기존 집계 기반 화면 미리보기: ${output} (${Buffer.byteLength(content)} bytes)`);
})().catch(error => { console.error(error.message); process.exitCode = 1; });
