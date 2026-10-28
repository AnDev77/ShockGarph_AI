const allowedSymbols = Object.freeze({
  QQQ: {
    chart: "NASDAQ:QQQ",
    url: "https://www.tradingview.com/symbols/NASDAQ-QQQ/",
  },
  SPY: {
    chart: "AMEX:SPY",
    url: "https://www.tradingview.com/symbols/AMEX-SPY/",
  },
});

const chart = document.querySelector("tv-advanced-chart");
const link = document.querySelector("#chart-link");
const buttons = document.querySelectorAll("button[data-symbol]");

for (const button of buttons) {
  button.addEventListener("click", () => {
    const symbol = button.dataset.symbol;
    const asset = allowedSymbols[symbol];
    if (!asset) return;

    chart.setAttribute("symbol", asset.chart);
    link.href = asset.url;
    link.firstChild.textContent = `TradingView에서 ${symbol} 보기 `;
    for (const candidate of buttons) {
      candidate.setAttribute("aria-pressed", String(candidate === button));
    }
  });
}
