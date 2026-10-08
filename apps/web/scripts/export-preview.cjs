// API가 계산한 합성 시나리오를 실제 React 컴포넌트로 렌더링한다.
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
Module._extensions['.ts'] = (module, filename) => {
  module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, filename);
};
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
  const { portfolio_views } = JSON.parse(execFileSync(python,
    [path.join(repo, 'scripts/export_dashboard_review_data.py')], { cwd: repo, encoding: 'utf8' }));
  const styles = new Set();
  const views = {};
  for (const source of ['demo', 'actual']) for (const horizon of ['m5', 'm30']) for (const share of [0, 25, 50, 60, 75, 100]) {
    const markup = renderToStaticMarkup(React.createElement(ChakraProvider, { value: defaultSystem },
      React.createElement(loaded.exports.Dashboard, { initialData: portfolio_views[source][horizon][String(share)], initialSource: source, initialHorizon: horizon, initialSpyPercent: share })));
    views[`${source}:${horizon}:${share}`] = markup.replace(/<style[^>]*>([\s\S]*?)<\/style>/g, (_, css) => { styles.add(scoped(css)); return ''; }).replace(/<input /g, '<input disabled ');
  }
  const markup = views['demo:m30:60'];
  const isFragment = process.argv.includes('--fragment');
  const globals = scoped(fs.readFileSync(path.join(web, 'app/globals.css'), 'utf8'));
  const overrides = `#${rootId}{color-scheme:light;color:#20222c;background:#f6f7f9;font-family:Arial,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;--sg-bg:#f6f7f9;--sg-ink:#20222c;--sg-muted:#717585;--sg-line:#e9ebf0;--sg-brand:#5d50e8;}#${rootId} .app-shell{min-height:0;}#${rootId} .sidebar{position:relative;top:auto;height:auto;align-self:stretch;}#${rootId} .skip-link{display:none;}#${rootId} button{cursor:inherit;}#${rootId} .refresh-button{display:none;}#${rootId} [data-lucide]{display:inline-block;width:18px;height:18px;}`;
  const data = JSON.stringify(views).replace(/</g, '\\u003c');
  const controls = fs.readFileSync(path.join(__dirname, 'preview-controls.js'), 'utf8');
  const fragment = `<div id="${rootId}">\n<style>${[...styles].join('\n')}\n${globals}\n${overrides}</style>\n<p style="padding:12px 20px;font-size:13px;background:#eeeaff">오프라인 미리보기: 예시 비중 버튼·구간·자료 모드를 전환할 수 있습니다. 직접 비중·평가액 입력은 실행 앱에서 지원합니다.</p><div id="shockgraph-preview-view">${markup}</div>\n<script type="application/json" id="shockgraph-preview-data">${data}</script>\n<script>${controls}</script>\n</div>\n`;
  const output = path.resolve(process.argv[2] || path.join(repo, 'docs/ui/portfolio-risk-dashboard.html'));
  const content = isFragment ? fragment : `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ShockGraph 포트폴리오 분석 · 합성 데모 미리보기</title></head><body style="margin:0">${fragment}</body></html>`;
  fs.writeFileSync(output, content);
  console.log(`합성 시나리오 화면 미리보기: ${output} (${Buffer.byteLength(content)} bytes)`);
})().catch(error => { console.error(error.message); process.exitCode = 1; });
