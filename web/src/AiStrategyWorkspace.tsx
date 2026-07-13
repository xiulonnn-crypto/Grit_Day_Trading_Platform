import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Database,
  ExternalLink,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { fetchAiStrategyRecommendations } from "./api";
import type {
  AiStrategyEvidenceStatus,
  AiStrategyRecommendationItem,
  AiStrategyRecommendations
} from "./types";

type AiStrategyWorkspaceProps = {
  date: string;
  symbolInput: string;
  onDateChange: (value: string) => void;
  onSymbolChange: (value: string) => void;
  onOpenStrategyTest: (strategyId: string) => void;
};

const evidenceMeta: Record<
  AiStrategyEvidenceStatus,
  { label: string; detail: string; tone: "ok" | "warn" | "info" }
> = {
  backtested: { label: "本地验证", detail: "达到可比证据门槛", tone: "ok" },
  partial: { label: "部分证据", detail: "样本或参数尚不可比", tone: "info" },
  research_only: { label: "研究排序", detail: "尚未通过本地归档验证", tone: "warn" }
};

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2
});

function canonicalSymbols(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((symbol) => symbol.trim().toUpperCase())
        .filter(Boolean)
    )
  ).slice(0, 20);
}

function formatCurrency(value: number | null): string {
  return value === null ? "尚未通过本地归档验证" : currencyFormatter.format(value);
}

function formatPercent(value: number | null): string {
  return value === null ? "尚无可比证据" : `${(value * 100).toFixed(1)}%`;
}

function formatParamValue(key: string, value: number | string): string {
  if (key === "initial_capital" && typeof value === "number") return currencyFormatter.format(value);
  if ((key === "entry_capital_ratio" || key.endsWith("_fraction")) && typeof value === "number") {
    return `${(value * 100).toFixed(0)}%`;
  }
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  return value;
}

function evidenceReasonLabel(reason: string): string {
  if (reason === "current_config_differs_from_recommended") return "当前配置已偏离建议参数基线";
  if (reason === "non_completed_strategy_test_batch") return "存在未完成的策略测试批次";
  if (reason === "template_version_mismatch") return "历史证据使用了不同模板版本";
  if (reason === "capital_evidence_mismatch") return "历史证据不是 100k / 20% 资本口径";
  if (reason.startsWith("completed_days_below_")) return "完成归档交易日不足 10 日";
  if (reason.startsWith("closed_groups_below_")) return "闭合信号不足 10 笔";
  if (reason.startsWith("missing_matching_batches:")) {
    return `缺少相同参数的测试批次：${reason.split(":", 2)[1]}`;
  }
  if (reason.startsWith("momentum_context_archive_required")) return "缺少 QQQ／SMH 动能上下文归档";
  if (reason.startsWith("momentum_context_archive_unavailable")) return "QQQ／SMH 动能上下文归档不可用";
  if (reason === "minute_archive_required") return "缺少目标标的分钟线归档";
  if (reason === "non_available_archive") return "目标标的分钟线归档不可用";
  if (reason === "insufficient_minute_bars") return "分钟线数量不足";
  if (reason === "profit_factor_unavailable") return "Profit Factor 缺少可比证据";
  if (reason === "engine_failed") return "策略测试引擎运行失败";
  if (reason.startsWith("strategy_test_day_status:")) return "存在未完成的单日策略测试";
  return "部分历史证据未达到可比门槛";
}

export function AiStrategyWorkspace(props: AiStrategyWorkspaceProps) {
  const symbols = useMemo(() => canonicalSymbols(props.symbolInput), [props.symbolInput]);
  const symbolsKey = symbols.join(",");
  const [recommendations, setRecommendations] = useState<AiStrategyRecommendations | null>(null);
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError(null);
    void fetchAiStrategyRecommendations(props.date, symbols.length > 0 ? symbols : ["MU"], {
      signal: controller.signal
    })
      .then((payload) => {
        setRecommendations(payload);
        setSelectedTemplateKey((current) =>
          current && payload.items.some((item) => item.template_key === current)
            ? current
            : payload.items[0]?.template_key ?? null
        );
      })
      .catch((reason) => {
        if (controller.signal.aborted) return;
        setRecommendations(null);
        setError(reason instanceof Error ? reason.message : "AI策略推荐读取失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [props.date, reloadKey, symbolsKey]);

  const selectedItem = useMemo(
    () =>
      recommendations?.items.find((item) => item.template_key === selectedTemplateKey) ??
      recommendations?.items[0] ??
      null,
    [recommendations, selectedTemplateKey]
  );

  return (
    <section className="aiStrategyWorkspace" aria-label="AI策略推荐工作区">
      <section className="panel aiStrategyHero">
        <div className="aiStrategyHeroIntro">
          <span className="aiStrategyIcon" aria-hidden="true">
            <BrainCircuit size={20} />
          </span>
          <div>
            <h2>AI策略 Top 5</h2>
            <p className="panelNote">确定性推荐引擎，研究家族与本地回放证据分层展示</p>
          </div>
        </div>
        <div className="aiStrategyHeroControls">
          <div className="aiStrategyCapital" aria-label="资本假设">
            <span>假设本金</span>
            <strong>{currencyFormatter.format(100000)}</strong>
            <small>单次入场 20%，约 {currencyFormatter.format(20000)}</small>
          </div>
          <label>
            截止日期
            <input aria-label="AI策略截止日期" onChange={(event) => props.onDateChange(event.target.value)} type="date" value={props.date} />
          </label>
          <label>
            评估标的
            <input
              aria-label="AI策略评估标的"
              list="symbolOptions"
              onChange={(event) => props.onSymbolChange(event.target.value)}
              placeholder="MU,NVDA"
              value={props.symbolInput}
            />
          </label>
          <div className="aiStrategyRankingBasis">
            <span>排名依据</span>
            <strong>{recommendations?.ranking_basis === "local_backtest" ? "本地回放排序" : "研究排序"}</strong>
            <small>
              {recommendations?.ranking_basis === "local_backtest"
                ? "五个策略已满足同口径证据门槛"
                : "证据不足时不混排局部样本"}
            </small>
          </div>
        </div>
      </section>

      {recommendations?.catalog_note ? (
        <div className="aiStrategyCatalogNotice" role="status">
          <Sparkles size={17} />
          <span>{recommendations.catalog_note}</span>
        </div>
      ) : null}

      <div className="aiStrategyRiskNotice" role="note">
        <ShieldAlert size={17} />
        <span>
          {recommendations?.disclaimer ?? "研究支持策略家族；本地回放是样本内历史结果，未计佣金与滑点，不代表未来盈利。"}
          多标的并发资金占用尚未建模。
        </span>
      </div>

      {error ? (
        <div className="aiStrategyError" role="alert">
          <AlertTriangle size={18} />
          <div>
            <strong>推荐读取失败</strong>
            <span>{error}</span>
          </div>
          <button onClick={() => setReloadKey((value) => value + 1)} type="button">
            <RefreshCw size={15} />
            重试
          </button>
        </div>
      ) : null}

      {busy && !recommendations ? <AiStrategyLoading /> : null}

      {!busy && !error && recommendations?.items.length === 0 ? (
        <div className="panel aiStrategyEmpty">
          <Database size={20} />
          <strong>暂无策略推荐目录</strong>
          <span>策略目录不可用，未生成任何盈利期望。</span>
        </div>
      ) : null}

      {recommendations && selectedItem ? (
        <div className="aiStrategyLayout">
          <aside className="panel aiStrategyRanking" aria-label="AI策略 Top 5 榜单" data-testid="ai-strategy-ranking">
            <header>
              <div>
                <h2>
                  <Sparkles size={17} />
                  盈利期望 Top 5
                </h2>
                <p className="panelNote">
                  {recommendations.ranking_basis === "local_backtest"
                    ? "按每笔闭合信号期望 PnL 排序"
                    : "研究优先级；局部证据只作旁证"}
                </p>
              </div>
              <span className={`statusPill ${recommendations.evidence_status === "verified" ? "ok" : "warn"}`}>
                {recommendations.evidence_status === "verified" ? "证据可比" : "证据不足"}
              </span>
            </header>
            <div className="aiStrategyRankList">
              {recommendations.items.map((item) => (
                <AiStrategyRankItem
                  item={item}
                  key={item.template_key}
                  onSelect={() => setSelectedTemplateKey(item.template_key)}
                  selected={item.template_key === selectedItem.template_key}
                />
              ))}
            </div>
          </aside>

          <AiStrategyDetail item={selectedItem} onOpenStrategyTest={props.onOpenStrategyTest} />
        </div>
      ) : null}
    </section>
  );
}

function AiStrategyLoading() {
  return (
    <div className="aiStrategyLayout" aria-busy="true" aria-label="AI策略推荐加载中">
      <div className="panel aiStrategyLoadingPanel">
        <RefreshCw className="spin" size={18} />
        <strong>正在读取推荐目录</strong>
        <span>只读取已有策略配置与历史回放证据。</span>
      </div>
      <div className="panel aiStrategyLoadingPanel">
        <Database size={18} />
        <strong>正在核对证据口径</strong>
        <span>缺少可比批次时将回退为研究排序。</span>
      </div>
    </div>
  );
}

function AiStrategyRankItem(props: { item: AiStrategyRecommendationItem; selected: boolean; onSelect: () => void }) {
  const meta = evidenceMeta[props.item.evidence_status];
  const expectation = props.item.expectation.expected_pnl_per_closed_trade;
  return (
    <button
      aria-pressed={props.selected}
      className={props.selected ? "aiStrategyRankItem active" : "aiStrategyRankItem"}
      onClick={props.onSelect}
      type="button"
    >
      <span className="aiStrategyRankNumber">{props.item.rank}</span>
      <span className="aiStrategyRankMain">
        <strong>{props.item.strategy_name}</strong>
        <small>{props.item.research_family}</small>
        <span className={`statusPill ${meta.tone}`}>{meta.label}</span>
      </span>
      <span className="aiStrategyRankExpectation">
        <small>{props.item.evidence_status === "backtested" ? "每笔期望" : "证据状态"}</small>
        <strong>{props.item.evidence_status === "backtested" ? formatCurrency(expectation) : meta.detail}</strong>
      </span>
    </button>
  );
}

function AiStrategyDetail(props: {
  item: AiStrategyRecommendationItem;
  onOpenStrategyTest: (strategyId: string) => void;
}) {
  const meta = evidenceMeta[props.item.evidence_status];
  const hasComparableEvidence = props.item.evidence_status === "backtested";
  const evidenceReasons = Array.from(new Set(props.item.expectation.failure_reasons.map(evidenceReasonLabel)));
  return (
    <article className="panel aiStrategyDetail" aria-label={`${props.item.strategy_name} 推荐详情`}>
      <header className="aiStrategyDetailHeader">
        <div>
          <p className="eyebrow">
            {props.item.evidence_status === "backtested" ? `本地排名 #${props.item.rank}` : `研究排名 #${props.item.research_rank}`}
          </p>
          <h2>{props.item.strategy_name}</h2>
          <p className="panelNote">{props.item.summary}</p>
          <div className="aiStrategyDetailBadges">
            <span className={`statusPill ${meta.tone}`}>{meta.label}</span>
            <span className="statusPill info">{props.item.template_version}</span>
          </div>
        </div>
        <button className="primaryButton aiStrategyCta" onClick={() => props.onOpenStrategyTest(props.item.strategy_id)} type="button">
          去策略测试
          <ArrowRight size={16} />
        </button>
      </header>

      {!props.item.current_config_alignment.matches_recommended_params ? (
        <div className="aiStrategyEvidenceWarning">
          <AlertTriangle size={16} />
          <span>当前策略配置已偏离建议参数基线；历史样本不参与本地榜单排序，也不会自动套用参数。</span>
        </div>
      ) : null}

      <section className="aiStrategyEvidenceSummary" aria-label="本地回放证据">
        <EvidenceMetric
          detail={hasComparableEvidence ? "每笔闭合信号" : "仅在证据可比后用于排序"}
          label="盈利期望"
          value={hasComparableEvidence ? formatCurrency(props.item.expectation.expected_pnl_per_closed_trade) : "尚未通过本地归档验证"}
        />
        <EvidenceMetric
          detail="100k 本金、单次 20% 仓位"
          label="窗口总 PnL"
          value={hasComparableEvidence ? formatCurrency(props.item.expectation.total_pnl) : "尚未通过本地归档验证"}
        />
        <EvidenceMetric
          detail={`门槛 ${10} 日`}
          label="完成归档日"
          value={String(props.item.expectation.completed_day_count)}
        />
        <EvidenceMetric
          detail="只统计闭合信号"
          label="闭合信号"
          value={String(props.item.expectation.closed_group_count)}
        />
        <EvidenceMetric
          detail="不计入收益与信号"
          label="排除日期"
          value={String(props.item.expectation.excluded_day_count)}
        />
        <EvidenceMetric
          detail="闭合信号口径"
          label="胜率"
          value={hasComparableEvidence ? formatPercent(props.item.expectation.win_rate) : "尚无可比证据"}
        />
        <EvidenceMetric
          detail="null 不等于 0"
          label="Profit Factor"
          value={hasComparableEvidence && props.item.expectation.profit_factor !== null ? props.item.expectation.profit_factor.toFixed(2) : "尚无可比证据"}
        />
        <EvidenceMetric
          detail={props.item.expectation.metric_aggregation === "single_symbol" ? "单标的" : "独立标的最大值"}
          label="最大回撤"
          value={hasComparableEvidence ? formatCurrency(props.item.expectation.max_drawdown) : "尚未通过本地归档验证"}
        />
      </section>

      {props.item.evidence_status !== "backtested" ? (
        <section className="aiStrategyEvidenceReasons">
          <div>
            <Database size={16} />
            <strong>为何仍使用研究排序</strong>
          </div>
          <ul>
            {(evidenceReasons.length > 0 ? evidenceReasons : ["尚无相同参数、日期和标的口径的本地测试批次"]).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>
      ) : (
        <div className="aiStrategyVerifiedLine">
          <CheckCircle2 size={16} />
          <span>
            当前策略已达到同日期、同标的、同参数与 100k 资本口径的本地排序门槛。
            {props.item.expectation.excluded_day_count > 0
              ? ` ${props.item.expectation.excluded_day_count} 个非可用日期已明确排除，不计入收益。`
              : ""}
          </span>
        </div>
      )}

      <DetailSection icon={<Target size={17} />} title="策略逻辑">
        <div className="aiStrategyLogicGrid">
          <LogicCard label="入场" lines={props.item.logic.entry} />
          <LogicCard label="出场" lines={props.item.logic.exit} />
          <LogicCard label="止盈" lines={props.item.logic.take_profit} />
          <LogicCard label="止损" lines={props.item.logic.stop_loss} />
        </div>
      </DetailSection>

      <DetailSection icon={<ShieldAlert size={17} />} title="仓位与风险">
        <div className="aiStrategyCapitalGrid">
          <EvidenceMetric detail="固定评估本金" label="初始本金" value={currencyFormatter.format(props.item.capital.initial_capital)} />
          <EvidenceMetric detail="每笔信号" label="入场比例" value={`${(props.item.capital.entry_capital_ratio * 100).toFixed(0)}%`} />
          <EvidenceMetric detail="按入场价换算股数" label="名义仓位" value={currencyFormatter.format(props.item.capital.position_notional)} />
          <EvidenceMetric detail="不等同组合回报" label="并发资金" value="未建模" />
        </div>
        <p className="aiStrategyCapitalNote">{props.item.capital.note}</p>
      </DetailSection>

      <DetailSection icon={<Sparkles size={17} />} title="推荐品种">
        <div className="aiStrategyInstrumentGrid">
          {props.item.recommended_instruments.map((instrument) => (
            <article key={instrument.profile}>
              <strong>{instrument.profile}</strong>
              <div className="aiStrategyTickerList">
                {instrument.examples.map((ticker) => (
                  <span key={ticker}>{ticker}</span>
                ))}
              </div>
              <p>{instrument.reason}</p>
            </article>
          ))}
        </div>
      </DetailSection>

      <DetailSection icon={<BrainCircuit size={17} />} title="推荐参数">
        <div className="aiStrategyHighlights">
          {props.item.parameter_highlights.map((highlight) => (
            <span key={highlight}>{highlight}</span>
          ))}
        </div>
        <dl className="aiStrategyParamGrid">
          {props.item.recommended_param_items.map((param) => (
            <div key={param.key}>
              <dt>{param.label}</dt>
              <dd>{formatParamValue(param.key, param.value)}</dd>
            </div>
          ))}
        </dl>
      </DetailSection>

      <DetailSection icon={<CheckCircle2 size={17} />} title="推荐理由">
        <ul className="aiStrategyReasonList">
          {props.item.recommendation_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </DetailSection>

      <DetailSection icon={<ExternalLink size={17} />} title="研究与风险来源">
        <div className="aiStrategySourceList">
          {props.item.sources.map((source) => (
            <a href={source.url} key={source.url} rel="noreferrer" target="_blank">
              <span>{source.title}</span>
              <ExternalLink size={14} />
            </a>
          ))}
        </div>
        <p className="aiStrategySourceNote">研究只支持策略家族，不等于该模板、参数或未来市场环境必然盈利。</p>
      </DetailSection>
    </article>
  );
}

function DetailSection(props: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="aiStrategyDetailSection">
      <h3>
        {props.icon}
        {props.title}
      </h3>
      {props.children}
    </section>
  );
}

function EvidenceMetric(props: { label: string; value: string; detail: string }) {
  return (
    <div className="aiStrategyMetric">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <small>{props.detail}</small>
    </div>
  );
}

function LogicCard(props: { label: string; lines: string[] }) {
  return (
    <article>
      <strong>{props.label}</strong>
      <ul>
        {props.lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </article>
  );
}
