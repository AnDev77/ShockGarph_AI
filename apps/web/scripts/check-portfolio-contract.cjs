// 잘못된 출처·비중·확률·분위수·기여도의 API 응답은 화면 표시 전에 거절한다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { execFileSync } = require('node:child_process');
const ts = require('typescript');
const repo = path.resolve(__dirname, '../../..');
const file = path.resolve(__dirname, '../components/portfolio-contract.ts');
const loaded = new Module(file, module);
loaded._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, file);
const python = process.env.PREVIEW_PYTHON || path.join(repo, '.venv/bin/python');
const data = JSON.parse(execFileSync(python, ['scripts/export_dashboard_review_data.py'], { cwd: repo, encoding: 'utf8' }));
let checked = 0;
for (const source of ['demo', 'actual']) for (const horizon of ['m5', 'm30']) for (const spyPercent of [0, 25, 50, 60, 75, 100]) {
  const report = data.portfolio_views[source][horizon][spyPercent].portfolio;
  loaded.exports.readPortfolioReport(report, { source, horizon, spyPercent, valuation: 10000 });
  checked++;
}
const valid = data.portfolio_views.demo.m30[60].portfolio;
const context = { source: 'demo', horizon: 'm30', spyPercent: 60, valuation: 10000 };
for (const corrupt of [
  r => { r.provenance.source_kind = 'licensed_historical'; },
  r => { r.weights.SPY = 0.5; },
  r => { r.result.quantiles.q10 = r.result.quantiles.q90 + 0.01; },
  r => { r.result.probability_up = 0.99; r.result.probability_down = 0.99; },
  r => { r.assets[0].return_contribution += 0.01; },
  r => { r.result.amount_range_usd[0] -= 100; },
]) {
  const malformed = structuredClone(valid); corrupt(malformed);
  assert.throws(() => loaded.exports.readPortfolioReport(malformed, context)); checked++;
}
const pending = data.portfolio_views.actual.m30[60].portfolio;
for (const blockers of [[{ code: 'snapshot_missing', label: '자료 연결 대기' }], []]) {
  loaded.exports.readPortfolioReport({ ...pending, blockers }, { ...context, source: 'actual' }); checked++;
}
for (const blockers of [[{ code: '../private/path', label: '잘못된 코드' }], [{ code: 'snapshot_missing', label: 123 }]]) {
  assert.throws(() => loaded.exports.readPortfolioReport({ ...pending, blockers }, { ...context, source: 'actual' })); checked++;
}
console.log(`포트폴리오 응답 계약 ${checked}개 상태 확인`);
