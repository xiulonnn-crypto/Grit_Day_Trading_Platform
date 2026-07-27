(() => {
  "use strict";

  const integerFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const numberFormat = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  const percentFormat = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  const pageSize = 20;
  const weekdays = ["一", "二", "三", "四", "五", "六", "日"];
  const timeFilterLabels = {
    all: "全部",
    month: "本月",
    week: "本周",
    custom: "特定时间段"
  };
  const modeLabels = {
    all: "全部订单",
    profit: "仅看盈利单",
    loss: "仅看亏损单"
  };
  const categoryLabels = {
    opening_signal: "开仓信号",
    closing_signal: "平仓信号",
    misoperation: "误操作"
  };
  const reasonLabels = {
    chased_breakout: "追突破过急",
    weak_confirmation: "确认不足",
    against_context: "逆势入场",
    poor_location: "入场位置差",
    stop_too_late: "止损过慢",
    profit_reversed: "盈利回吐",
    exit_signal_ignored: "平仓信号未执行",
    exit_plan_unclear: "平仓计划不清",
    wrong_side_or_symbol: "方向或标的点错",
    oversized_position: "仓位过大",
    duplicate_order: "重复下单",
    plan_not_followed: "未按计划执行"
  };
  const timeWindows = [
    { key: "early_session", label: "早盘高动能", detail: "09:30-10:30", start: 570, end: 630 },
    {
      key: "late_morning_transition",
      label: "早盘至中盘过渡",
      detail: "10:30-11:30",
      start: 630,
      end: 690
    },
    {
      key: "lunch_hour_squeeze",
      label: "中盘死寂垃圾时间",
      detail: "11:30-13:30",
      start: 690,
      end: 810
    },
    {
      key: "early_afternoon_drift",
      label: "尾盘蓄势期",
      detail: "13:30-15:00",
      start: 810,
      end: 900
    },
    { key: "power_hour", label: "尾盘生死时速", detail: "15:00-16:00", start: 900, end: 960 }
  ];
  const outsideWindow = {
    key: "outside_regular",
    label: "非常规",
    detail: "09:30前/16:00后",
    start: 0,
    end: 1440
  };
  const atrRows = [
    { key: "extreme", label: "极端冲击", detail: "> 3.0 x ATR" },
    { key: "high", label: "高波动", detail: "1.5-3.0 x ATR" },
    { key: "normal", label: "常规波动", detail: "0.5-1.5 x ATR" },
    { key: "low", label: "低波动", detail: "< 0.5 x ATR" },
    { key: "missing", label: "缺 ATR 证据", detail: "缺开仓前 20 根 ATR" }
  ];
  const shareRows = [
    { key: "very_large", label: "超大单", detail: "> 500 股" },
    { key: "large", label: "大单", detail: "201-500 股" },
    { key: "medium_large", label: "中大单", detail: "101-200 股" },
    { key: "medium", label: "中单", detail: "51-100 股" },
    { key: "small", label: "小单", detail: "≤ 50 股" },
    { key: "missing", label: "缺股数证据", detail: "股数缺失或非正数" }
  ];

  const state = {
    snapshot: null,
    activeTab: "data",
    dataTimeMode: "all",
    sharedTimeMode: "all",
    customDataStart: "",
    customDataEnd: "",
    customSharedStart: "",
    customSharedEnd: "",
    calendarMonth: "",
    selectedDate: "",
    selectedSymbol: "",
    profitLossMode: "all",
    matrixDimension: "atr",
    sortMode: "time_desc",
    page: 1
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatInteger(value) {
    return integerFormat.format(Number(value || 0));
  }

  function formatNumber(value) {
    return value === null || value === undefined || !Number.isFinite(Number(value))
      ? "N/A"
      : numberFormat.format(Number(value));
  }

  function formatPnl(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${numberFormat.format(number)}`;
  }

  function formatPercent(value) {
    return value === null || value === undefined || !Number.isFinite(Number(value))
      ? "N/A"
      : `${percentFormat.format(Number(value) * 100)}%`;
  }

  function tone(value) {
    const number = Number(value || 0);
    if (number > 0) return "ok";
    if (number < 0) return "bad";
    return "neutral";
  }

  function dateFromKey(value) {
    const [year, month, day] = String(value).split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function dateKey(value) {
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${value.getFullYear()}-${month}-${day}`;
  }

  function addDays(value, amount) {
    const next = new Date(value);
    next.setDate(next.getDate() + amount);
    return next;
  }

  function monthStart(value) {
    const date = dateFromKey(value);
    return dateKey(new Date(date.getFullYear(), date.getMonth(), 1));
  }

  function monthEnd(value) {
    const date = dateFromKey(value);
    return dateKey(new Date(date.getFullYear(), date.getMonth() + 1, 0));
  }

  function shiftMonth(value, amount) {
    const date = dateFromKey(value);
    return dateKey(new Date(date.getFullYear(), date.getMonth() + amount, 1));
  }

  function weekStart(value) {
    const date = dateFromKey(value);
    const weekday = date.getDay();
    return dateKey(addDays(date, weekday === 0 ? -6 : 1 - weekday));
  }

  function weekEnd(value) {
    return dateKey(addDays(dateFromKey(weekStart(value)), 6));
  }

  function normalizeRange(start, end) {
    if (start && end && start > end) return { start: end, end: start };
    return { start: start || null, end: end || null };
  }

  function rangeFor(mode, customStart, customEnd) {
    const current = state.snapshot.as_of_date;
    if (mode === "month") return { start: monthStart(current), end: monthEnd(current) };
    if (mode === "week") return { start: weekStart(current), end: weekEnd(current) };
    if (mode === "custom") return normalizeRange(customStart, customEnd);
    return { start: null, end: null };
  }

  function groupDate(group) {
    return String(group.closed_at || group.opened_at || "").slice(0, 10);
  }

  function inRange(group, range) {
    const value = groupDate(group);
    if (range.start && value < range.start) return false;
    if (range.end && value > range.end) return false;
    return true;
  }

  function closedGroups() {
    return state.snapshot.trade_groups.filter(
      (group) => group.status === "closed" && group.pnl !== null
    );
  }

  function groupsForScope(scope) {
    const range =
      scope === "data"
        ? rangeFor(state.dataTimeMode, state.customDataStart, state.customDataEnd)
        : rangeFor(state.sharedTimeMode, state.customSharedStart, state.customSharedEnd);
    return closedGroups().filter((group) => inRange(group, range));
  }

  function rangeLabel(range, allLabel) {
    if (range.start && range.end) return `${range.start} 至 ${range.end}`;
    if (range.start) return `${range.start} 之后`;
    if (range.end) return `${range.end} 之前`;
    return allLabel;
  }

  function summaryFromGroups(groups) {
    const wins = groups.filter((group) => Number(group.pnl) > 0);
    const losses = groups.filter((group) => Number(group.pnl) < 0);
    const grossProfit = wins.reduce((total, group) => total + Number(group.pnl), 0);
    const grossLoss = Math.abs(losses.reduce((total, group) => total + Number(group.pnl), 0));
    const pnl = groups.reduce((total, group) => total + Number(group.pnl || 0), 0);
    const quantity = groups.reduce((total, group) => total + Number(group.total_quantity || 0), 0);
    const fillCount = groups.reduce((total, group) => total + Number(group.fill_count || 0), 0);
    const winRate = groups.length ? wins.length / groups.length : 0;
    const lossRate = groups.length ? losses.length / groups.length : 0;
    const averageProfit = wins.length ? grossProfit / wins.length : 0;
    const averageLoss = losses.length ? grossLoss / losses.length : 0;
    const expectedValue = groups.length
      ? winRate * averageProfit - lossRate * averageLoss
      : null;
    const maxDrawdown = groups.reduce((current, group) => {
      const drawdown = group.position_drawdown || {};
      return drawdown.status === "available" && Number.isFinite(Number(drawdown.max_drawdown))
        ? Math.max(current, Number(drawdown.max_drawdown))
        : current;
    }, 0);
    return {
      fill_count: fillCount,
      trade_group_count: groups.length,
      traded_quantity: quantity,
      pnl,
      win_rate: winRate,
      profit_factor: grossLoss > 0 ? grossProfit / grossLoss : null,
      expected_value_per_trade: expectedValue,
      net_profit_per_share: quantity > 0 ? pnl / quantity : null,
      max_single_day_drawdown: maxDrawdown
    };
  }

  function metricHtml(label, value, note = "", metricTone = "") {
    return `<article class="metric ${metricTone}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </article>`;
  }

  function summaryStripHtml(summary, note) {
    return `<section class="kpis reviewDashboard dataReviewSummaryStrip cloudMetricStrip" aria-label="有记录以来汇总指标">
      ${metricHtml("成交股数", formatInteger(summary.traded_quantity), `仅来自 committed fills · ${note}`)}
      ${metricHtml("PnL", formatPnl(summary.pnl), "", tone(summary.pnl))}
      ${metricHtml("胜率", formatPercent(summary.win_rate))}
      ${metricHtml("盈亏比", summary.profit_factor === null ? (summary.pnl > 0 ? "∞" : "N/A") : formatNumber(summary.profit_factor))}
      ${metricHtml("单笔期望值", formatNumber(summary.expected_value_per_trade), "", tone(summary.expected_value_per_trade))}
      ${metricHtml("每股净收益", formatNumber(summary.net_profit_per_share), "", tone(summary.net_profit_per_share))}
      ${metricHtml("持仓最大回撤", formatNumber(summary.max_single_day_drawdown), "", summary.max_single_day_drawdown > 0 ? "warn" : "")}
    </section>`;
  }

  function timeFilterHtml(scope, mode, customStart, customEnd, label, extra = "") {
    const buttons = Object.entries(timeFilterLabels)
      .map(
        ([key, text]) =>
          `<button aria-pressed="${mode === key}" class="smallButton ${mode === key ? "active" : ""}" data-time-mode="${key}" data-time-scope="${scope}" type="button">${text}</button>`
      )
      .join("");
    const custom =
      mode === "custom"
        ? `<div class="lossReviewCustomRange">
            <label><span>开始</span><input data-custom-date="start" data-time-scope="${scope}" type="date" value="${escapeHtml(customStart)}"></label>
            <label><span>结束</span><input data-custom-date="end" data-time-scope="${scope}" type="date" value="${escapeHtml(customEnd)}"></label>
          </div>`
        : "";
    return `<div class="lossReviewTimeFilter" aria-label="${scope === "data" ? "数据下钻全局时间筛选" : "共享日期筛选"}">
      <div class="lossReviewTimeFilterButtons" role="group" aria-label="共享日期范围">${buttons}</div>
      ${custom}
      ${extra}
      <span class="toolbarMeta">${escapeHtml(label)}</span>
    </div>`;
  }

  function groupBy(groups, keyFn) {
    const result = new Map();
    groups.forEach((group) => {
      const key = keyFn(group);
      result.set(key, [...(result.get(key) || []), group]);
    });
    return result;
  }

  function calendarDays(monthValue, groups) {
    const byDate = groupBy(groups, groupDate);
    const start = dateFromKey(monthStart(monthValue));
    const leading = (start.getDay() + 6) % 7;
    const gridStart = addDays(start, -leading);
    const prefix = monthStart(monthValue).slice(0, 7);
    return Array.from({ length: 42 }, (_, index) => {
      const date = addDays(gridStart, index);
      const key = dateKey(date);
      const dayGroups = byDate.get(key) || [];
      return {
        key,
        day: date.getDate(),
        current: key.startsWith(prefix),
        summary: dayGroups.length ? summaryFromGroups(dayGroups) : null
      };
    });
  }

  function renderDataPanel() {
    const container = document.getElementById("data-review-panel");
    const groups = groupsForScope("data");
    const range = rangeFor(state.dataTimeMode, state.customDataStart, state.customDataEnd);
    const filteredDates = new Set(groups.map(groupDate));
    if (!filteredDates.has(state.selectedDate)) {
      state.selectedDate =
        [...filteredDates].sort((left, right) => right.localeCompare(left))[0] ||
        state.snapshot.as_of_date;
      state.calendarMonth = monthStart(state.selectedDate);
    }
    const dayGroups = groups.filter((group) => groupDate(group) === state.selectedDate);
    const symbolMap = groupBy(dayGroups, (group) => group.symbol);
    const symbols = [...symbolMap.keys()].sort();
    if (!symbols.includes(state.selectedSymbol)) state.selectedSymbol = symbols[0] || "";
    const selectedGroups = symbolMap.get(state.selectedSymbol) || dayGroups;
    const selectedSummary = summaryFromGroups(selectedGroups);
    const monthLabel = (() => {
      const date = dateFromKey(state.calendarMonth);
      return `${date.getFullYear()}年${String(date.getMonth() + 1).padStart(2, "0")}月`;
    })();
    const dayButtons = calendarDays(state.calendarMonth, groups)
      .map((day) => {
        const classes = [
          "dataReviewCalendarDay",
          day.key === state.selectedDate ? "active" : "",
          day.current ? "" : "outside",
          day.summary ? "" : "empty"
        ]
          .filter(Boolean)
          .join(" ");
        return `<button aria-pressed="${day.key === state.selectedDate}" class="${classes}" data-calendar-date="${day.key}" ${day.summary ? "" : "disabled"} type="button">
          <strong>${day.day}</strong>
          ${
            day.summary
              ? `<small>${formatInteger(day.summary.traded_quantity)} 股</small><span class="${tone(day.summary.pnl)}">${formatPnl(day.summary.pnl)}</span>`
              : "<small>无订单</small>"
          }
        </button>`;
      })
      .join("");
    const symbolRows =
      symbols.length > 0
        ? symbols
            .map((symbol) => {
              const summary = summaryFromGroups(symbolMap.get(symbol) || []);
              return `<article class="drillSecondaryItem ${symbol === state.selectedSymbol ? "active" : ""}">
                <div><strong>${escapeHtml(symbol)}</strong><small>订单数 ${formatInteger(summary.fill_count)} · 股数 ${formatInteger(summary.traded_quantity)} · PnL ${formatPnl(summary.pnl)}</small></div>
                <button class="linkButton" data-select-symbol="${escapeHtml(symbol)}" type="button">进入复盘</button>
              </article>`;
            })
            .join("")
        : `<div class="emptyState"><div><strong>该日没有标的</strong><p>当前时间范围没有 committed 成交可用于标的下钻</p></div></div>`;
    const symbolOptions = symbols
      .map(
        (symbol) =>
          `<option ${symbol === state.selectedSymbol ? "selected" : ""} value="${escapeHtml(symbol)}">${escapeHtml(symbol)}</option>`
      )
      .join("");
    container.innerHTML = `<div class="dataReviewDrilldown">
      ${timeFilterHtml("data", state.dataTimeMode, state.customDataStart, state.customDataEnd, rangeLabel(range, "全部订单"))}
      ${summaryStripHtml(summaryFromGroups(groups), rangeLabel(range, "全部订单"))}
      <section class="dataReviewCalendarPanel" aria-label="数据下钻月日历">
        <header class="dataReviewCalendarHeader">
          <div><h3>▣ 月日历下钻</h3><p class="panelNote">点击有订单的日期方块，右侧立即切到该日标的下钻</p></div>
          <div class="dataReviewCalendarNav" aria-label="月份切换">
            <button aria-label="上个月" class="smallButton iconOnly" data-calendar-shift="-1" type="button">‹</button>
            <strong>${monthLabel}</strong>
            <button aria-label="下个月" class="smallButton iconOnly" data-calendar-shift="1" type="button">›</button>
          </div>
        </header>
        <div class="dataReviewCalendarLayout">
          <div class="dataReviewCalendarGrid" role="grid" aria-label="每日订单日历">
            ${weekdays.map((label) => `<div class="dataReviewCalendarWeekday">${label}</div>`).join("")}
            ${dayButtons}
          </div>
          <div class="dataReviewCalendarDetail">
            <div class="drillDetailHead">
              <div><strong>${escapeHtml(state.selectedDate)} 日统计</strong><small>选择标的进入当前复盘模块</small></div>
              <span class="sourcePill">${formatInteger(symbols.length)} 个标的</span>
            </div>
            <dl class="summaryMiniFacts">
              <div><dt>订单数</dt><dd>${formatInteger(summaryFromGroups(dayGroups).fill_count)}</dd></div>
              <div><dt>股数</dt><dd>${formatInteger(summaryFromGroups(dayGroups).traded_quantity)}</dd></div>
              <div><dt>PnL</dt><dd class="${tone(summaryFromGroups(dayGroups).pnl)}">${formatPnl(summaryFromGroups(dayGroups).pnl)}</dd></div>
            </dl>
            <div class="drillSecondaryList">${symbolRows}</div>
          </div>
        </div>
      </section>
      <section class="kpis currentReviewKpis cloudSelectedDateControls" aria-label="当前复盘模块指标">
        <label class="dateControl"><span>当前复盘日期</span><input data-selected-date type="date" value="${escapeHtml(state.selectedDate)}"></label>
        <label class="dateControl"><span>当前复盘标的</span><select data-selected-symbol>${symbolOptions}</select></label>
        ${metricHtml("成交股数", formatInteger(selectedSummary.traded_quantity), "BUY/SELL 平仓数量")}
        ${metricHtml("PnL", formatPnl(selectedSummary.pnl), "", tone(selectedSummary.pnl))}
        ${metricHtml("胜率", formatPercent(selectedSummary.win_rate))}
        ${metricHtml("盈亏比", selectedSummary.profit_factor === null ? (selectedSummary.pnl > 0 ? "∞" : "N/A") : formatNumber(selectedSummary.profit_factor))}
        ${metricHtml("持仓最大回撤", formatNumber(selectedSummary.max_single_day_drawdown), "", selectedSummary.max_single_day_drawdown > 0 ? "warn" : "")}
      </section>
    </div>`;
  }

  function minuteOfDay(group) {
    const match = String(group.closed_at || group.opened_at || "").match(/[T\s](\d{2}):(\d{2})/);
    return match ? Number(match[1]) * 60 + Number(match[2]) : null;
  }

  function timeWindowKey(group) {
    const minute = minuteOfDay(group);
    if (minute === null) return outsideWindow.key;
    return timeWindows.find((window) => minute >= window.start && minute < window.end)?.key || outsideWindow.key;
  }

  function atrRowKey(group) {
    const value = Number(group.position_drawdown?.entry_atr_multiple);
    if (!Number.isFinite(value)) return "missing";
    if (value > 3) return "extreme";
    if (value >= 1.5) return "high";
    if (value >= 0.5) return "normal";
    return "low";
  }

  function shareRowKey(group) {
    const value = Number(group.total_quantity);
    if (!Number.isFinite(value) || value <= 0) return "missing";
    if (value > 500) return "very_large";
    if (value > 200) return "large";
    if (value > 100) return "medium_large";
    if (value > 50) return "medium";
    return "small";
  }

  function buildMatrix(groups, dimension, mode) {
    const rows = dimension === "shares" ? shareRows : atrRows;
    const hasOutside = groups.some((group) => timeWindowKey(group) === outsideWindow.key);
    const windows = hasOutside ? [...timeWindows, outsideWindow] : timeWindows;
    const cells = new Map();
    rows.forEach((row) =>
      windows.forEach((window) =>
        cells.set(`${window.key}:${row.key}`, {
          key: `${window.key}:${row.key}`,
          window,
          row,
          count: 0,
          totalPnl: 0,
          lossAmount: 0,
          largestLoss: null,
          tradedQuantity: 0
        })
      )
    );
    groups.forEach((group) => {
      const rowKey = dimension === "shares" ? shareRowKey(group) : atrRowKey(group);
      const cell = cells.get(`${timeWindowKey(group)}:${rowKey}`);
      if (!cell) return;
      const pnl = Number(group.pnl || 0);
      cell.count += 1;
      cell.totalPnl += pnl;
      cell.lossAmount += mode === "all" ? Math.abs(pnl) : Math.abs(Math.min(pnl, 0));
      cell.tradedQuantity += Number(group.total_quantity || 0);
      if (cell.largestLoss === null || pnl < cell.largestLoss) cell.largestLoss = pnl;
    });
    const totalLossAmount = [...cells.values()].reduce((total, cell) => total + cell.lossAmount, 0);
    let maxLoss = null;
    let maxProfit = null;
    let maxLossAmount = 0;
    [...cells.values()].forEach((cell) => {
      cell.lossShare = totalLossAmount > 0 ? cell.lossAmount / totalLossAmount : 0;
      maxLossAmount = Math.max(maxLossAmount, cell.lossAmount);
      if (cell.count && cell.totalPnl < 0 && (!maxLoss || cell.totalPnl < maxLoss.totalPnl)) maxLoss = cell;
      if (cell.count && cell.totalPnl > 0 && (!maxProfit || cell.totalPnl > maxProfit.totalPnl)) maxProfit = cell;
    });
    const visibleRows = rows.filter(
      (row) => row.key !== "missing" || windows.some((window) => cells.get(`${window.key}:${row.key}`).count)
    );
    return { rows: visibleRows, windows, cells, maxLoss, maxProfit, maxLossAmount, dimension };
  }

  function matrixIntensity(cell, maxLossAmount) {
    if (!cell.count || maxLossAmount <= 0) return 0;
    const ratio = cell.lossAmount / maxLossAmount;
    if (ratio >= 0.75) return 4;
    if (ratio >= 0.5) return 3;
    if (ratio >= 0.25) return 2;
    return 1;
  }

  function zoneLabel(cell) {
    return cell ? `${cell.window.label} × ${cell.row.label} · ${formatPnl(cell.totalPnl)}` : "暂无";
  }

  function matrixHtml(groups, mode) {
    const dimension = mode === "all" ? state.matrixDimension : "atr";
    const matrix = buildMatrix(groups, dimension, mode);
    const dimensionSwitch =
      mode === "all"
        ? `<div class="lossReviewMatrixDimensionSwitch" role="radiogroup" aria-label="热力时间矩阵参数切换">
            ${["atr", "shares"]
              .map(
                (value) => `<label class="lossReviewMatrixDimensionOption ${dimension === value ? "active" : ""}">
                  <input ${dimension === value ? "checked" : ""} data-matrix-dimension="${value}" name="allOrdersTimeMatrixDimension" type="radio" value="${value}">
                  <span>${value === "atr" ? "ATR 时间矩阵" : "股数时间矩阵"}</span>
                </label>`
              )
              .join("")}
          </div>`
        : "";
    const summary =
      mode === "all"
        ? `<strong class="${matrix.maxProfit ? "ok" : "neutral"}">最大盈利区：${escapeHtml(zoneLabel(matrix.maxProfit))}</strong>
           <small class="${matrix.maxLoss ? "bad" : "neutral"}">最大亏损区：${escapeHtml(zoneLabel(matrix.maxLoss))}</small>`
        : mode === "profit"
          ? `<strong class="${matrix.maxProfit ? "ok" : "neutral"}">最大盈利区：${escapeHtml(zoneLabel(matrix.maxProfit))}</strong>`
          : `<strong class="${matrix.maxLoss ? "bad" : "neutral"}">最大亏损区：${escapeHtml(zoneLabel(matrix.maxLoss))}</strong>`;
    let grid = `<div class="lossReviewMatrixCorner"></div>${matrix.windows
      .map(
        (window) =>
          `<div class="lossReviewMatrixAxis lossReviewMatrixColumnHead"><strong>${escapeHtml(window.label)}</strong><small>${escapeHtml(window.detail)}</small></div>`
      )
      .join("")}`;
    matrix.rows.forEach((row) => {
      grid += `<div class="lossReviewMatrixAxis lossReviewMatrixRowHead"><strong>${escapeHtml(row.label)}</strong><small>${escapeHtml(row.detail)}</small></div>`;
      matrix.windows.forEach((window) => {
        const cell = matrix.cells.get(`${window.key}:${row.key}`);
        grid += `<div class="lossReviewMatrixCell intensity${matrixIntensity(cell, matrix.maxLossAmount)} ${cell.count ? "" : "empty"} readOnly" role="gridcell">
          <strong>${formatInteger(cell.count)}</strong>
          <span class="${tone(cell.totalPnl)}">${formatPnl(cell.totalPnl)}</span>
          <small>${formatPercent(cell.lossShare)} · 最大 ${cell.largestLoss === null ? "N/A" : formatPnl(cell.largestLoss)}</small>
        </div>`;
      });
    });
    if (mode === "all") {
      grid += `<div class="lossReviewMatrixAxis lossReviewMatrixRowHead lossReviewMatrixSummaryHead"><strong>X 轴汇总</strong><small>收益合计</small></div>`;
      matrix.windows.forEach((window) => {
        const values = matrix.rows.map((row) => matrix.cells.get(`${window.key}:${row.key}`));
        const count = values.reduce((total, cell) => total + cell.count, 0);
        const pnl = values.reduce((total, cell) => total + cell.totalPnl, 0);
        const quantity = values.reduce((total, cell) => total + cell.tradedQuantity, 0);
        grid += `<div class="lossReviewMatrixColumnSummary ${count ? "" : "empty"}"><span>收益</span><strong class="${tone(pnl)}">${formatPnl(pnl)}</strong><small>${formatInteger(count)} 笔${dimension === "shares" ? ` · ${formatInteger(quantity)} 股` : ""}</small></div>`;
      });
    }
    return `<section class="lossReviewMatrixPanel" aria-label="${escapeHtml(modeLabels[mode])}热力时间矩阵">
      <header class="lossReviewMatrixHeader">
        <div><h3>${escapeHtml(modeLabels[mode])}热力时间矩阵</h3><p class="panelNote">按美股常规盘五大微观结构窗口 × ${dimension === "shares" ? "每笔订单股数" : "开仓 ATR Multiple"}查看${escapeHtml(modeLabels[mode])}分布</p>${dimensionSwitch}</div>
        <div class="lossReviewMatrixSummary"><span class="sourcePill">${escapeHtml(modeLabels[mode])}</span>${summary}</div>
      </header>
      <div class="lossReviewMatrixScroll">
        <div class="lossReviewMatrixGrid" role="grid" style="grid-template-columns:minmax(150px,.9fr) repeat(${matrix.windows.length},minmax(112px,1fr))">${grid}</div>
      </div>
      <p class="lossReviewMatrixNote">${dimension === "shares" ? "纵轴按 committed fills 交易组的配对股数分档；缺失或非正数进入缺股数证据。" : "纵轴使用本地分钟线归档计算的开仓 1min K 振幅 / 前 20 根 ATR；缺证据不会回退为美元亏损。"}</p>
    </section>`;
  }

  function reasonSummary(groups, keyFn, labelFn) {
    const map = new Map();
    groups.forEach((group) => {
      const key = keyFn(group);
      const current = map.get(key) || { key, label: labelFn(group), count: 0, pnl: 0 };
      current.count += 1;
      current.pnl += Number(group.pnl || 0);
      map.set(key, current);
    });
    return [...map.values()].sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
  }

  function reasonsHtml(groups) {
    const primary = reasonSummary(
      groups,
      (group) => group.review?.reason_category || "unreviewed",
      (group) => categoryLabels[group.review?.reason_category] || "待复盘"
    );
    const secondary = reasonSummary(
      groups,
      (group) => group.review?.reason_code || "unreviewed",
      (group) => reasonLabels[group.review?.reason_code] || "待复盘"
    );
    const card = (title, items) => `<section class="cloudReasonCard"><div class="drillDetailHead"><div><strong>${title}</strong><small>只读 Review Journal 汇总</small></div><span class="sourcePill">${formatInteger(groups.length)} 笔</span></div>
      <ul class="cloudReasonList">${items
        .map(
          (item) =>
            `<li><div><strong>${escapeHtml(item.label)}</strong><small>${formatInteger(item.count)} 笔 · ${formatPercent(item.count / Math.max(groups.length, 1))}</small></div><strong class="${tone(item.pnl)}">${formatPnl(item.pnl)}</strong></li>`
        )
        .join("")}</ul></section>`;
    return `<div class="cloudReasonGrid">${card("一级原因", primary)}${card("二级原因", secondary)}</div>`;
  }

  function orderListHtml(groups, mode) {
    const sorted = [...groups].sort((left, right) => {
      if (state.sortMode === "loss_desc") {
        const amount = Math.abs(Number(right.pnl || 0)) - Math.abs(Number(left.pnl || 0));
        if (amount) return amount;
      }
      return String(right.closed_at || right.opened_at).localeCompare(String(left.closed_at || left.opened_at));
    });
    const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
    state.page = Math.min(Math.max(1, state.page), pages);
    const start = (state.page - 1) * pageSize;
    const rows = sorted.slice(start, start + pageSize);
    const cards = rows
      .map((group) => {
        const category = categoryLabels[group.review?.reason_category] || (Number(group.pnl) < 0 ? "待复盘" : "不适用");
        const reason = reasonLabels[group.review?.reason_code] || (Number(group.pnl) < 0 ? "未分类" : "不适用");
        return `<article class="cloudTradeItem">
          <div><span>交易</span><strong>${escapeHtml(groupDate(group))} · ${escapeHtml(group.symbol)}</strong><small>${group.direction === "LONG" ? "多头" : "空头"} · ${formatInteger(group.total_quantity)} 股 · ${formatNumber(group.holding_minutes)} 分钟</small></div>
          <div><span>PnL</span><strong class="${tone(group.pnl)}">${formatPnl(group.pnl)}</strong><small>${formatInteger(group.fill_count)} fills</small></div>
          <div><span>开仓 → 平仓</span><strong>${formatNumber(group.avg_entry_price)} → ${formatNumber(group.avg_exit_price)}</strong><small>账户字段已脱敏</small></div>
          <div><span>持仓最大回撤</span><strong>${formatNumber(group.position_drawdown?.max_drawdown)}</strong><small>${escapeHtml(group.evaluation?.grade || "N/A")} 级</small></div>
          <div><span>复盘归因</span><strong>${escapeHtml(category)}</strong><small>${escapeHtml(reason)}</small></div>
        </article>`;
      })
      .join("");
    return `<section class="lossReviewListPanel" aria-label="${escapeHtml(modeLabels[mode])}列表明细">
      <div class="cloudOrderToolbar">
        <div><strong>${escapeHtml(modeLabels[mode])}列表</strong><p class="panelNote">默认按时间倒序，每页 20 笔；账户字段按公开页面规则脱敏</p></div>
        <span class="sourcePill">${formatInteger(Math.min(start + 1, sorted.length))}-${formatInteger(Math.min(start + pageSize, sorted.length))} / ${formatInteger(sorted.length)} 笔</span>
      </div>
      <div class="lossReviewListToolbar">
        <div class="lossReviewSortControl" role="group" aria-label="订单排序">
          <button aria-pressed="${state.sortMode === "time_desc"}" class="smallButton ${state.sortMode === "time_desc" ? "active" : ""}" data-sort-mode="time_desc" type="button">按时间倒序</button>
          <button aria-pressed="${state.sortMode === "loss_desc"}" class="smallButton ${state.sortMode === "loss_desc" ? "active" : ""}" data-sort-mode="loss_desc" type="button">${mode === "all" ? "按盈亏绝对值倒序" : mode === "profit" ? "按盈利金额倒序" : "按亏损金额倒序"}</button>
        </div>
        <span class="toolbarMeta">20 笔/页</span>
      </div>
      <div class="cloudOrderList">${cards || '<div class="emptyState"><div><strong>没有符合筛选的订单</strong><p>调整日期范围或盈亏范围后再查看。</p></div></div>'}</div>
      <div class="cloudPagination" aria-label="订单分页">
        <button class="smallButton" data-page-shift="-1" ${state.page <= 1 ? "disabled" : ""} type="button">上一页</button>
        <span>第 ${formatInteger(state.page)} / ${formatInteger(pages)} 页</span>
        <button class="smallButton" data-page-shift="1" ${state.page >= pages ? "disabled" : ""} type="button">下一页</button>
      </div>
    </section>`;
  }

  function renderProfitLossPanel() {
    const container = document.getElementById("loss-review-panel");
    const scopeGroups = groupsForScope("shared");
    const range = rangeFor(state.sharedTimeMode, state.customSharedStart, state.customSharedEnd);
    const modeGroups =
      state.profitLossMode === "profit"
        ? scopeGroups.filter((group) => Number(group.pnl) > 0)
        : state.profitLossMode === "loss"
          ? scopeGroups.filter((group) => Number(group.pnl) < 0)
          : scopeGroups;
    const reviewed = modeGroups.filter((group) => group.review).length;
    const pnl = modeGroups.reduce((total, group) => total + Number(group.pnl || 0), 0);
    const modeSwitch = `<div class="profitLossReviewModeSwitch" role="radiogroup" aria-label="盈亏单筛选">${["all", "profit", "loss"]
      .map(
        (mode) => `<label class="profitLossReviewModeOption ${state.profitLossMode === mode ? "active" : ""}">
          <input ${state.profitLossMode === mode ? "checked" : ""} data-profit-loss-mode="${mode}" name="profitLossReviewMode" type="radio" value="${mode}">
          <span>${modeLabels[mode]}</span>
        </label>`
      )
      .join("")}</div>`;
    container.innerHTML = `<div class="lossReviewDrilldown cloudLossReview">
      <header class="lossReviewDrillHeader cloudLossHeader"><div><h2>⚠ 盈亏复盘</h2><p class="panelNote">默认查看全部订单；也可只看盈利单或亏损单</p></div><span class="sourcePill">Review Journal</span></header>
      ${timeFilterHtml("shared", state.sharedTimeMode, state.customSharedStart, state.customSharedEnd, rangeLabel(range, "全部闭合交易"), modeSwitch)}
      <dl class="compactFacts lossReviewSummaryGrid lossReviewSummaryRow">
        <div><dt>${escapeHtml(modeLabels[state.profitLossMode])}</dt><dd>${formatInteger(modeGroups.length)}</dd></div>
        <div><dt>${state.profitLossMode === "loss" ? "已复盘" : "盈利单"}</dt><dd>${state.profitLossMode === "loss" ? formatInteger(reviewed) : formatInteger(scopeGroups.filter((group) => Number(group.pnl) > 0).length)}</dd></div>
        <div><dt>${state.profitLossMode === "loss" ? "待复盘" : "亏损单"}</dt><dd>${state.profitLossMode === "loss" ? formatInteger(modeGroups.length - reviewed) : formatInteger(scopeGroups.filter((group) => Number(group.pnl) < 0).length)}</dd></div>
        <div><dt>${state.profitLossMode === "all" ? "盈亏合计" : state.profitLossMode === "profit" ? "盈利合计" : "亏损合计"}</dt><dd class="${tone(pnl)}">${formatPnl(pnl)}</dd></div>
      </dl>
      ${matrixHtml(modeGroups, state.profitLossMode)}
      ${state.profitLossMode === "loss" ? reasonsHtml(modeGroups) : '<div class="emptyState"><div><strong>暂无原因分类</strong><p>仅亏损单维护 Review Journal 归因；盈利单和全部订单视图不写入亏损原因。</p></div></div>'}
      ${orderListHtml(modeGroups, state.profitLossMode)}
    </div>`;
  }

  const generationMeta = {
    not_requested: ["等待会话摘要", "确定性规则已就绪，可在本次会话中生成并写入当前证据摘要。", "info"],
    unconfigured: ["等待会话摘要", "当前范围尚无本会话摘要；量化执行规则仍可直接使用。", "info"],
    pending: ["摘要生成中", "正在用脱敏聚合证据生成摘要。", "info"],
    completed: ["已完成", "摘要已通过规则 ID 和无新增数字校验。", "ok"],
    failed: ["摘要不可用", "摘要生成或校验失败；确定性量化规则未受影响。", "danger"],
    stale: ["证据已变化", "旧会话摘要不再代表当前范围，量化规则已按新证据刷新。", "warn"]
  };

  function actionGridHtml(actions) {
    return `<dl class="cloudActionGrid">${(actions || [])
      .map(
        (action) =>
          `<div><dt>${escapeHtml(action.label)}</dt><dd>${escapeHtml(action.value)}</dd></div>`
      )
      .join("")}</dl>`;
  }

  function ruleColumnHtml(title, rules, kind) {
    return `<section class="cloudSummaryRuleColumn ${kind}">
      <div class="drillDetailHead"><strong>${escapeHtml(title)}</strong><span class="sourcePill">${formatInteger(rules.length)} 条</span></div>
      <div class="cloudSummaryRuleCards">${rules
        .map(
          (rule) => `<article class="cloudSummaryRuleCard">
            <span class="sourcePill">${escapeHtml(rule.family)}</span>
            <h4>${escapeHtml(rule.title)}</h4>
            <p>${escapeHtml(rule.condition)}</p>
            ${actionGridHtml(rule.action_steps)}
          </article>`
        )
        .join("")}</div>
    </section>`;
  }

  function renderTradeSummaryPanel() {
    const container = document.getElementById("trade-summary-panel");
    const summary = state.snapshot.trade_summary;
    const metrics = summary.metrics;
    const generation = summary.generation || { status: "unconfigured" };
    const meta = generationMeta[generation.status] || generationMeta.unconfigured;
    const range = rangeFor(state.sharedTimeMode, state.customSharedStart, state.customSharedEnd);
    const rules =
      summary.evidence_status === "eligible"
        ? `<div class="cloudSummaryRuleGrid">${ruleColumnHtml("推荐执行规则", summary.execution_rules || [], "execute")}${ruleColumnHtml("推荐规避错误", summary.avoidance_rules || [], "avoid")}</div>`
        : `<section><div class="tradeSummarySectionHeading"><div><p class="eyebrow">经典基线</p><h3>样本达标前的复盘检查单</h3></div></div><div class="cloudBaselineGrid">${(summary.classic_baselines || [])
            .map(
              (rule) => `<article class="cloudBaselineCard"><span class="sourcePill">${escapeHtml(rule.family)}</span><strong>${escapeHtml(rule.title)}</strong><p>${escapeHtml(rule.condition)}</p>${actionGridHtml(rule.action_steps)}</article>`
            )
            .join("")}</div></section>`;
    container.innerHTML = `<div class="tradeSummaryPanel cloudTradeSummary">
      <header class="tradeSummaryHeader cloudTradeSummaryHeader"><div><h2>☑ 交易总结</h2><p class="panelNote">本会话生成摘要表达；后端确定规则、排序与量化执行动作</p></div><span class="sourcePill">${escapeHtml(summary.rule_catalog_version)}</span></header>
      ${timeFilterHtml("shared", state.sharedTimeMode, state.customSharedStart, state.customSharedEnd, rangeLabel(range, "全部闭合交易"))}
      <section aria-label="交易总结样本概览">
        <div class="tradeSummarySectionHeading"><div><p class="eyebrow">样本概览</p><h3>闭合交易证据</h3></div><span class="statusPill ${summary.evidence_status === "eligible" ? "ok" : "warn"}">${summary.evidence_status === "eligible" ? "达到个性化门槛" : "样本准备中"}</span></div>
        <dl class="tradeSummaryMetrics">
          <div><dt>闭合交易</dt><dd>${formatInteger(metrics.closed_trade_count)}</dd></div>
          <div><dt>盈利</dt><dd class="ok">${formatInteger(metrics.win_count)}</dd></div>
          <div><dt>亏损</dt><dd class="bad">${formatInteger(metrics.loss_count)}</dd></div>
          <div><dt>持平</dt><dd>${formatInteger(metrics.flat_count)}</dd></div>
          <div><dt>PnL</dt><dd class="${tone(metrics.pnl)}">${formatPnl(metrics.pnl)}</dd></div>
          <div><dt>Profit Factor</dt><dd>${formatNumber(metrics.profit_factor)}</dd></div>
          <div><dt>分钟线评价覆盖率</dt><dd>${formatPercent(metrics.evaluation_coverage_ratio)}</dd></div>
          <div><dt>亏损 Journal 覆盖率</dt><dd>${formatPercent(metrics.loss_journal_coverage_ratio)}</dd></div>
        </dl>
      </section>
      <section class="cloudSummaryAiCard ${meta[2]}" aria-live="polite">
        <div class="drillDetailHead"><div><p class="eyebrow">AI 摘要</p><h3>${escapeHtml(generation.narrative?.headline || meta[0])}</h3><p>${escapeHtml(generation.narrative?.overview || meta[1])}</p></div><span class="statusPill ${meta[2]}">${escapeHtml(meta[0])}</span></div>
      </section>
      ${rules}
      <details class="tradeSummarySources"><summary>经典方法依据</summary><div class="tradeSummarySourceBody"><p>以下来源只提供方法背景，不作为盈利保证；个性化规则仍以当前后端证据门槛为准。</p><ul class="cloudSourceList">${(summary.sources || [])
        .map(
          (source) =>
            `<li><a href="${escapeHtml(source.url)}" rel="noreferrer" target="_blank">${escapeHtml(source.title)}</a> · ${source.kind === "risk" ? "风险提示" : "方法研究"}</li>`
        )
        .join("")}</ul></div></details>
      <p class="tradeSummaryDisclaimer">${escapeHtml(summary.disclaimer)}</p>
    </div>`;
  }

  function renderSnapshotMeta() {
    const meta = document.getElementById("snapshot-meta");
    meta.innerHTML = `<span>静态 read model 截止 ${escapeHtml(state.snapshot.as_of_date)}</span><code>source ${escapeHtml(state.snapshot.source_hash.slice(0, 12))}</code><span>· committed fills 只读 · 账户与原始证据字段已脱敏</span>`;
  }

  function renderTabs() {
    document.querySelectorAll("[data-review-tab]").forEach((button) => {
      const active = button.dataset.reviewTab === state.activeTab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      button.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll("[data-review-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.reviewPanel !== state.activeTab;
    });
  }

  function render() {
    if (!state.snapshot) return;
    renderTabs();
    renderSnapshotMeta();
    renderDataPanel();
    renderProfitLossPanel();
    renderTradeSummaryPanel();
  }

  function setActiveTab(value) {
    state.activeTab = value;
    const hash = value === "data" ? "#data-review" : value === "loss" ? "#profit-loss-review" : "#trade-summary";
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`);
    renderTabs();
  }

  function validateSnapshot(snapshot) {
    if (!snapshot || snapshot.schema_version !== "github_pages_review_snapshot_v1") {
      throw new Error("快照版本不匹配");
    }
    if (!snapshot.source_hash || !snapshot.as_of_date || !Array.isArray(snapshot.trade_groups)) {
      throw new Error("快照证据不完整");
    }
    const groups = snapshot.trade_groups.filter(
      (group) => group.status === "closed" && group.pnl !== null
    );
    const quantity = groups.reduce((total, group) => total + Number(group.total_quantity || 0), 0);
    const pnl = groups.reduce((total, group) => total + Number(group.pnl || 0), 0);
    if (
      groups.length !== Number(snapshot.summary.trade_group_count) ||
      quantity !== Number(snapshot.summary.traded_quantity) ||
      Math.abs(pnl - Number(snapshot.summary.pnl)) > 0.000001
    ) {
      throw new Error("快照汇总与交易组证据不一致");
    }
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      const tab = target.closest("[data-review-tab]");
      if (tab) {
        setActiveTab(tab.dataset.reviewTab);
        return;
      }
      const timeButton = target.closest("[data-time-mode]");
      if (timeButton) {
        const scope = timeButton.dataset.timeScope;
        if (scope === "data") state.dataTimeMode = timeButton.dataset.timeMode;
        else state.sharedTimeMode = timeButton.dataset.timeMode;
        state.page = 1;
        render();
        return;
      }
      const shift = target.closest("[data-calendar-shift]");
      if (shift) {
        state.calendarMonth = shiftMonth(state.calendarMonth, Number(shift.dataset.calendarShift));
        renderDataPanel();
        return;
      }
      const day = target.closest("[data-calendar-date]");
      if (day && !day.disabled) {
        state.selectedDate = day.dataset.calendarDate;
        state.calendarMonth = monthStart(state.selectedDate);
        renderDataPanel();
        return;
      }
      const symbol = target.closest("[data-select-symbol]");
      if (symbol) {
        state.selectedSymbol = symbol.dataset.selectSymbol;
        renderDataPanel();
        return;
      }
      const sort = target.closest("[data-sort-mode]");
      if (sort) {
        state.sortMode = sort.dataset.sortMode;
        state.page = 1;
        renderProfitLossPanel();
        return;
      }
      const page = target.closest("[data-page-shift]");
      if (page && !page.disabled) {
        state.page += Number(page.dataset.pageShift);
        renderProfitLossPanel();
      }
    });

    document.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
      if (target.dataset.profitLossMode) {
        state.profitLossMode = target.dataset.profitLossMode;
        state.page = 1;
        if (state.profitLossMode !== "all") state.matrixDimension = "atr";
        renderProfitLossPanel();
        return;
      }
      if (target.dataset.matrixDimension) {
        state.matrixDimension = target.dataset.matrixDimension;
        renderProfitLossPanel();
        return;
      }
      if (target.dataset.customDate) {
        const scope = target.dataset.timeScope;
        const key = target.dataset.customDate;
        if (scope === "data") {
          if (key === "start") state.customDataStart = target.value;
          else state.customDataEnd = target.value;
        } else {
          if (key === "start") state.customSharedStart = target.value;
          else state.customSharedEnd = target.value;
        }
        render();
        return;
      }
      if (target.matches("[data-selected-date]")) {
        state.selectedDate = target.value;
        state.calendarMonth = monthStart(target.value);
        renderDataPanel();
        return;
      }
      if (target.matches("[data-selected-symbol]")) {
        state.selectedSymbol = target.value;
        renderDataPanel();
      }
    });
  }

  async function init() {
    bindEvents();
    const loading = document.getElementById("snapshot-loading");
    try {
      const response = await fetch(`./review-snapshot.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`快照读取失败（HTTP ${response.status}）`);
      const snapshot = await response.json();
      validateSnapshot(snapshot);
      state.snapshot = snapshot;
      state.selectedDate = snapshot.as_of_date;
      state.calendarMonth = monthStart(snapshot.as_of_date);
      state.customDataStart = monthStart(snapshot.as_of_date);
      state.customDataEnd = snapshot.as_of_date;
      state.customSharedStart = monthStart(snapshot.as_of_date);
      state.customSharedEnd = snapshot.as_of_date;
      const requestedHash = window.location.hash;
      state.activeTab =
        requestedHash === "#profit-loss-review" || requestedHash === "#loss-review"
          ? "loss"
          : requestedHash === "#trade-summary"
            ? "summary"
            : "data";
      loading.hidden = true;
      document.getElementById("review-content").hidden = false;
      render();
    } catch (error) {
      loading.className = "cloudBlocked";
      loading.innerHTML = `<strong>云端复盘快照不可用</strong><span>${escapeHtml(error instanceof Error ? error.message : "未知错误")}</span><small>页面不会用旧数字或空图伪装成功，请重新导出并发布当前 read model。</small>`;
    }
  }

  void init();
})();
