// 실제 API 계산 결과를 같은 React 컴포넌트로 미리 렌더링한 상태 간 전환이다.
// 직접 입력은 실행 앱에서 지원한다. 실제 자료 pending은 합성 결과로 대체하지 않는다.
(() => {
  const root = document.getElementById('shockgraph-preview');
  const target = root.querySelector('#shockgraph-preview-view');
  const views = JSON.parse(root.querySelector('#shockgraph-preview-data').textContent);
  let source = 'demo', horizon = 'm30', share = 60;
  target.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.source) source = button.dataset.source;
    else if (button.dataset.horizon) horizon = button.dataset.horizon;
    else if (button.dataset.spyWeight !== undefined) share = Number(button.dataset.spyWeight);
    else return;
    target.innerHTML = views[`${source}:${horizon}:${share}`];
  });
})();
