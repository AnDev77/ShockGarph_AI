// 화면 리뷰용 로컬 선택. API 호출 없이 기존 네 조합의 보고서 수치만 사용한다.
(() => {
  const root = document.getElementById('shockgraph-preview');
  const data = JSON.parse(root.querySelector('#shockgraph-preview-data').textContent);
  const groups = root.querySelectorAll('.segmented');
  let asset = 'SPY';
  let horizon = 'm5';
  const fixed = value => Number(value).toFixed(6);
  const signed = value => (value > 0 ? '+' : '') + fixed(value);
  function update() {
    const metric = data[`${asset}:${horizon}`];
    const labels = ['과거 발생비율 모델', 'Kalshi 확률 추가 모델'];
    const values = [metric.historical_crps, metric.kalshi_crps];
    const max = Math.max(...values);
    root.querySelector('.asset-comparison .score-bars').innerHTML = values.map((value, index) => `<div class="score-row"><div class="score-heading"><span><i class="legend ${index ? 'kalshi' : 'history'}"></i>${labels[index]}</span><strong>${fixed(value)}</strong></div><div class="score-track" aria-hidden="true"><div class="score-fill ${index ? 'kalshi' : 'history'}" style="width:${max ? value / max * 100 : 0}%"></div></div></div>`).join('');
    const selected = root.querySelector('.selected-asset');
    const ticker = selected.querySelector('.ticker-icon');
    ticker.textContent = asset === 'SPY' ? 'S' : 'T';
    ticker.className = `ticker-icon ${asset === 'SPY' ? 'spy' : 'tlt'}`;
    selected.querySelector('strong').innerHTML = `${asset} <span>${asset === 'SPY' ? '미국 주식' : '장기 국채'}</span>`;
    selected.querySelector('p').textContent = `발표 후 ${horizon === 'm5' ? '5분' : '30분'} · 수익률 분포 오차 (CRPS)`;
    root.querySelector('.asset-ci').textContent = `오차 차이 ${signed(metric.mean_crps_difference)} · 95% 구간 [${metric.paired_event_bootstrap95.map(fixed).join(', ')}]`;
    groups.forEach((group, index) => group.querySelectorAll('button').forEach((button, option) => {
      const isSelected = index === 0 ? button.textContent === asset : option === (horizon === 'm5' ? 0 : 1);
      button.setAttribute('aria-pressed', String(isSelected));
      button.classList.toggle('selected', isSelected);
    }));
  }
  groups[0].querySelectorAll('button').forEach(button => button.addEventListener('click', () => { asset = button.textContent; update(); }));
  groups[1].querySelectorAll('button').forEach((button, index) => button.addEventListener('click', () => { horizon = index ? 'm30' : 'm5'; update(); }));
})();
