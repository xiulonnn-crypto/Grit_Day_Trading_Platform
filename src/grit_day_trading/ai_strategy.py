from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .strategy import (
    BB_SQUEEZE_TEMPLATE_KEY,
    DEFAULT_BB_SQUEEZE_PARAMS,
    DEFAULT_BB_SQUEEZE_STRATEGY_ID,
    DEFAULT_ENTRY_CAPITAL_RATIO,
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_LIQUIDITY_SWEEP_PARAMS,
    DEFAULT_LIQUIDITY_SWEEP_STRATEGY_ID,
    DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS,
    DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID,
    DEFAULT_RANGE_FADER_PARAMS,
    DEFAULT_RANGE_FADER_STRATEGY_ID,
    DEFAULT_TREND_RIDER_PARAMS,
    DEFAULT_TREND_RIDER_STRATEGY_ID,
    DEFAULT_LAST_HOUR_MOMENTUM_PARAMS,
    DEFAULT_LAST_HOUR_MOMENTUM_STRATEGY_ID,
    DEFAULT_OPENING_RANGE_BREAKOUT_PARAMS,
    DEFAULT_OPENING_RANGE_BREAKOUT_STRATEGY_ID,
    DEFAULT_OPENING_RANGE_RETEST_PARAMS,
    DEFAULT_OPENING_RANGE_RETEST_STRATEGY_ID,
    DEFAULT_VWAP_OPENING_DRIVE_PARAMS,
    DEFAULT_VWAP_OPENING_DRIVE_STRATEGY_ID,
    DEFAULT_VWAP_TREND_PULLBACK_PARAMS,
    DEFAULT_VWAP_TREND_PULLBACK_STRATEGY_ID,
    LAST_HOUR_MOMENTUM_TEMPLATE_KEY,
    LIQUIDITY_SWEEP_TEMPLATE_KEY,
    MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
    OPENING_RANGE_BREAKOUT_TEMPLATE_KEY,
    OPENING_RANGE_RETEST_TEMPLATE_KEY,
    RANGE_FADER_TEMPLATE_KEY,
    TREND_RIDER_TEMPLATE_KEY,
    VWAP_OPENING_DRIVE_TEMPLATE_KEY,
    VWAP_TREND_PULLBACK_TEMPLATE_KEY,
    get_strategy_templates,
    list_strategy_configs,
)


AI_STRATEGY_CATALOG_VERSION = "ai_strategy_catalog_v2"
AI_STRATEGY_RANKING_VERSION = "profit_expectation_v2"
AI_STRATEGY_MIN_COMPLETED_DAYS = 10
AI_STRATEGY_MIN_CLOSED_GROUPS = 10
AI_STRATEGY_MAX_SYMBOLS = 20

SEC_DAY_TRADING_SOURCE = {
    "title": "SEC 日内交易风险说明",
    "url": "https://www.sec.gov/about/reports-publications/investorpubsdaytipshtm",
    "kind": "risk",
}


_RETIRED_AI_STRATEGY_CATALOG_V1: tuple[dict[str, Any], ...] = (
    {
        "research_rank": 1,
        "template_key": TREND_RIDER_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_TREND_RIDER_STRATEGY_ID,
        "research_family": "日内动量与开盘区间延续",
        "summary": "用 VWAP、EMA20、开盘区间和缩量二级回调确认趋势中继。",
        "logic": {
            "entry": [
                "价格、VWAP 与 EMA20 同向，EMA20 斜率满足趋势门槛。",
                "连续 2 根强势放量 K 线突破 30 根 K 的开盘区间后，等待缩量 H2/L2 二级回调确认。",
            ],
            "exit": ["不设置静态止盈；硬止损或收盘跌破／突破 EMA9 时退出。"],
            "take_profit": ["使用 EMA9 追踪趋势，让盈利仓位继续运行。"],
            "stop_loss": ["止损放在二级回调结构或 EMA20 外侧更保守一侧，并增加 4 ticks 缓冲。"],
        },
        "recommended_instruments": [
            {
                "profile": "高流动性指数与行业 ETF",
                "examples": ["SPY", "QQQ", "SMH"],
                "reason": "点差较窄，适合观察开盘区间和 VWAP 趋势延续。",
            },
            {
                "profile": "高 RVOL 大盘股",
                "examples": ["NVDA", "AMD", "TSLA"],
                "reason": "催化日更容易形成可持续的突破与二级回调结构。",
            },
        ],
        "recommended_params": DEFAULT_TREND_RIDER_PARAMS,
        "parameter_highlights": [
            "EMA20 趋势生命线",
            "EMA9 追踪出场",
            "突破量能 2×",
            "回调量能 ≤ 0.8×",
            "开盘区间 30 根 K",
            "止损缓冲 4 ticks",
        ],
        "recommendation_reasons": [
            "日内动量与开盘区间延续具备直接研究支持。",
            "趋势、量能、回调和出场条件完整，适合高流动性标的。",
            "追踪出场保留趋势尾部收益，同时以结构止损控制单次风险。",
        ],
        "sources": [
            {
                "title": "Market Intraday Momentum",
                "url": "https://www.researchwithrutgers.org/en/publications/market-intraday-momentum/",
                "kind": "research",
            },
            {
                "title": "美股 Opening Range Breakout 研究",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 2,
        "template_key": BB_SQUEEZE_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_BB_SQUEEZE_STRATEGY_ID,
        "research_family": "波动率收缩与顺势突破",
        "summary": "在低波动 setup 后，用 VWAP、量能、实体强度和 RSI 确认扩张突破。",
        "logic": {
            "entry": [
                "BB(20,2) 带宽位于历史 10% 收缩分位，且绝对带宽大于 2。",
                "价格沿 VWAP 同侧突破外轨，成交量至少 2×，K 线实体占比至少 0.5，RSI 同向。",
            ],
            "exit": ["触及 ATR 目标、硬止损，或收盘失守 EMA9／布林中轨时退出。"],
            "take_profit": ["第一目标为 ATR14 × 1.5，并允许 EMA9 缓冲继续持有。"],
            "stop_loss": ["入场价外 ATR14 × 1.0。"],
        },
        "recommended_instruments": [
            {
                "profile": "高流动性成长 ETF",
                "examples": ["QQQ", "SMH"],
                "reason": "收缩与扩张阶段清晰，分钟线成交连续。",
            },
            {
                "profile": "高流动性半导体股",
                "examples": ["NVDA", "AMD", "MU"],
                "reason": "事件驱动时更容易出现量价确认后的波动率扩张。",
            },
        ],
        "recommended_params": DEFAULT_BB_SQUEEZE_PARAMS,
        "parameter_highlights": [
            "BB(20,2)",
            "收缩分位 10%",
            "最小绝对带宽 2",
            "成交量 2×",
            "ATR 止损 1.0×",
            "ATR 目标 1.5×",
        ],
        "recommendation_reasons": [
            "Bollinger BandWidth 可用于识别 Squeeze 与潜在波动率扩张。",
            "量能、VWAP 和 RSI 共同确认，减少单一带宽信号的误触发。",
            "ATR 止损与目标让不同价格尺度的标的使用一致风险口径。",
        ],
        "sources": [
            {
                "title": "Bollinger Bands 官方规则",
                "url": "https://www.bollingerbands.com/bollinger-band-rules",
                "kind": "methodology",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 3,
        "template_key": MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_MOMENTUM_MEAN_REVERSION_STRATEGY_ID,
        "research_family": "午盘均值回归与市场动能过滤",
        "summary": "在午盘震荡 regime 中，用 QQQ、SMH 市场方向过滤布林带反转。",
        "logic": {
            "entry": [
                "仅在 11:30–13:30 ET、ADX 低于 20 的震荡 regime 中启用，ADX 高于 25 时熔断。",
                "QQQ 与 SMH 必须位于 VWAP 同侧，目标标的越过布林外轨后以 Pin Bar 或吞没形态收回。",
            ],
            "exit": ["中轨部分止盈后把剩余仓位止损移到入场价，对侧外轨或保本止损完成退出。"],
            "take_profit": ["50% 仓位在布林中轨止盈，余仓以对侧外轨为目标。"],
            "stop_loss": ["初始硬止损为 ATR14 × 1.5；第一目标触达后移至 break-even。"],
        },
        "recommended_instruments": [
            {
                "profile": "高流动性半导体与成长股",
                "examples": ["MU", "NVDA", "AMD", "AVGO", "TSM"],
                "reason": "与 QQQ、SMH 上下文联动明显，适合在午盘震荡中做条件化反转。",
            }
        ],
        "recommended_params": DEFAULT_MOMENTUM_MEAN_REVERSION_PARAMS,
        "parameter_highlights": [
            "11:30–13:30 ET",
            "ADX 熔断 25",
            "ADX 激活 20",
            "ATR 止损 1.5×",
            "中轨止盈 50%",
            "QQQ + SMH 过滤",
        ],
        "recommendation_reasons": [
            "短期反转收益与流动性、波动率和市场状态密切相关。",
            "时间窗口、ADX 熔断和指数动能过滤避免无条件逆势抄底。",
            "分批止盈与保本止损降低均值未完全回归时的尾部风险。",
        ],
        "sources": [
            {
                "title": "Short-Term Reversals and Liquidity",
                "url": "https://www.nber.org/papers/w30917",
                "kind": "research",
            },
            {
                "title": "What Drives Momentum and Reversal?",
                "url": "https://academic.oup.com/rfs/advance-article-abstract/doi/10.1093/rfs/hhag036/8626980",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 4,
        "template_key": LIQUIDITY_SWEEP_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_LIQUIDITY_SWEEP_STRATEGY_ID,
        "research_family": "流动性扫单后的快速反转",
        "summary": "识别局部高低点被扫穿并迅速收回的短周期流动性反转。",
        "logic": {
            "entry": [
                "顺 VWAP 方向，扫过前 20 根 K 的局部高低点后收回。",
                "反转影线占比至少 0.6，成交量至少为前 20 根均量的 1.5×。",
            ],
            "exit": ["使用历史 OCO 模型，命中止损、布林中轨／1.5R 目标，或持有 3 根 K 后退出。"],
            "take_profit": ["布林中轨或 1.5R 中较近的目标。"],
            "stop_loss": ["扫单极值外 2 ticks。"],
        },
        "recommended_instruments": [
            {
                "profile": "深度充足的 ETF 与超大盘股",
                "examples": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"],
                "reason": "局部高低点、成交量异常和快速收回更容易在连续盘口中解释。",
            }
        ],
        "recommended_params": DEFAULT_LIQUIDITY_SWEEP_PARAMS,
        "parameter_highlights": [
            "局部窗口 20",
            "影线占比 0.6",
            "成交量 1.5×",
            "目标 1.5R",
            "止损 2 ticks",
            "最多持有 3 根 K",
        ],
        "recommendation_reasons": [
            "短期反转可被解释为对流动性冲击的补偿，但结果高度依赖市场状态。",
            "VWAP、扫单结构、影线与放量条件共同约束反转质量。",
            "三根 K 的时间止损限制了流动性未快速回补时的暴露。",
        ],
        "sources": [
            {
                "title": "Short-Term Reversals and Liquidity",
                "url": "https://www.nber.org/papers/w30917",
                "kind": "research",
            },
            {
                "title": "Evaporating Liquidity",
                "url": "https://academic.oup.com/rfs/article-pdf/25/7/2005/24431763/hhs066.pdf",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 5,
        "template_key": RANGE_FADER_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_RANGE_FADER_STRATEGY_ID,
        "research_family": "震荡区间边缘反转",
        "summary": "只在 EMA20 钝化、价格反复穿越均线的区间边缘做反转。",
        "logic": {
            "entry": [
                "使用 45 根 K 识别区间，上下沿至少各有 2 次触碰，入场区域为边缘 25%。",
                "EMA20 必须平坦且价格至少 8 次穿越均线；边缘假突破或拒绝后，下一根 K 开盘入场。",
            ],
            "exit": ["中轴部分止盈后，余仓在对侧边缘、break-even 止损或最多 30 根 K 时退出。"],
            "take_profit": ["50% 仓位在区间中轴止盈，余仓目标为对侧区间边缘。"],
            "stop_loss": ["区间边缘外 2 ticks；第一目标触达后移至入场价。"],
        },
        "recommended_instruments": [
            {
                "profile": "高流动性且常见日内平衡区间的标的",
                "examples": ["SPY", "QQQ", "IWM", "AAPL", "MSFT"],
                "reason": "连续成交有助于稳定识别区间边缘、触碰次数和 EMA 穿越。",
            }
        ],
        "recommended_params": DEFAULT_RANGE_FADER_PARAMS,
        "parameter_highlights": [
            "区间窗口 45",
            "边缘触碰 2 次",
            "边缘区域 25%",
            "EMA20 穿越 8 根",
            "中轴止盈 50%",
            "最长持有 30 根 K",
        ],
        "recommendation_reasons": [
            "区间反转属于条件化流动性提供，不适合趋势日无条件使用。",
            "EMA 钝化、穿越次数和触边次数共同确认震荡 regime。",
            "中轴分批止盈和 break-even 止损降低假区间破位风险。",
        ],
        "sources": [
            {
                "title": "Short-Term Reversals and Liquidity",
                "url": "https://www.nber.org/papers/w30917",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
)


AI_STRATEGY_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "research_rank": 1,
        "template_key": OPENING_RANGE_BREAKOUT_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_OPENING_RANGE_BREAKOUT_STRATEGY_ID,
        "research_family": "5分钟开盘区间突破与量能确认",
        "summary": "首 5 分钟定区间，只交易 VWAP 同向且相对成交量达标的突破。",
        "logic": {
            "entry": [
                "09:30–09:34 ET 形成首 5 分钟高低区间；其后收盘突破区间才进入候选。",
                "多头须位于 VWAP 上方、空头须位于 VWAP 下方，当前成交量至少为前序均量的 0.7 倍。",
            ],
            "exit": ["命中 ATR 止损、1.6R 目标或 11:30 ET 时间止损时退出。"],
            "take_profit": ["固定目标为初始每股风险的 1.6 倍。"],
            "stop_loss": ["初始止损为 ATR14 × 0.8，且每股风险不低于 0.05 USD。"],
        },
        "recommended_instruments": [
            {
                "profile": "高 RVOL 的流动性大盘股",
                "examples": ["MU", "NVDA", "AMD", "TSLA", "PLTR"],
                "reason": "开盘催化与成交量集中时，5 分钟区间突破更容易形成可复查的方向性。",
            }
        ],
        "recommended_params": DEFAULT_OPENING_RANGE_BREAKOUT_PARAMS,
        "parameter_highlights": ["开盘区间 5 分钟", "最晚入场 11:00 ET", "RVOL ≥ 0.7", "ATR 止损 0.8×", "目标 1.6R"],
        "recommendation_reasons": [
            "大样本美股 ORB 研究直接覆盖 5 分钟开盘区间策略家族。",
            "VWAP 与量能门槛避免把无成交支持的瞬时越界当成突破。",
            "一次入场、固定风险和时间止损让回放结果易比较。",
        ],
        "sources": [
            {
                "title": "A Profitable Day Trading Strategy for the U.S. Equity Market",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 2,
        "template_key": VWAP_OPENING_DRIVE_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_VWAP_OPENING_DRIVE_STRATEGY_ID,
        "research_family": "VWAP 开盘驱动延续",
        "summary": "用首半小时收益定方向，在 10:00 ET 仍处于 VWAP 同侧时参与延续。",
        "logic": {
            "entry": [
                "首半小时绝对涨跌幅至少 0.05%，方向作为当日开盘驱动。",
                "10:00–10:05 ET 内，多头价格必须高于 VWAP、空头价格必须低于 VWAP。",
            ],
            "exit": ["命中 ATR 止损、1.5R 目标或 12:30 ET 时间止损时退出。"],
            "take_profit": ["固定目标为初始每股风险的 1.5 倍。"],
            "stop_loss": ["初始止损为 ATR14 × 1.0，且每股风险不低于 0.05 USD。"],
        },
        "recommended_instruments": [
            {
                "profile": "成交连续的指数 ETF 与活跃大盘股",
                "examples": ["QQQ", "SPY", "MU", "NVDA"],
                "reason": "VWAP 和首半小时价格发现更稳定，适合固定时点做方向确认。",
            }
        ],
        "recommended_params": DEFAULT_VWAP_OPENING_DRIVE_PARAMS,
        "parameter_highlights": ["首半小时阈值 0.05%", "10:00 ET 确认", "VWAP 同向", "ATR 止损 1.0×", "目标 1.5R"],
        "recommendation_reasons": [
            "首半小时是开盘信息消化与高成交时段，可作为日内方向条件。",
            "VWAP 同侧确认把开盘涨跌与当日成交重心结合。",
            "固定观察窗口避免全天反复追逐 VWAP 穿越。",
        ],
        "sources": [
            {
                "title": "Market Intraday Momentum",
                "url": "https://www.researchwithrutgers.org/en/publications/market-intraday-momentum/",
                "kind": "research",
            },
            {
                "title": "VWAP: The Holy Grail for Day Trading Systems",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 3,
        "template_key": LAST_HOUR_MOMENTUM_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_LAST_HOUR_MOMENTUM_STRATEGY_ID,
        "research_family": "首半小时到尾盘的日内动量",
        "summary": "用首半小时收益方向预测最后交易时段，并在收盘前强制平仓。",
        "logic": {
            "entry": [
                "首半小时绝对涨跌幅至少 0.05%，正收益做多、负收益做空。",
                "14:45–14:50 ET 建立同向仓位，每日最多一笔。",
            ],
            "exit": ["命中 ATR 止损、1.2R 目标或 15:55 ET 时退出，绝不过夜。"],
            "take_profit": ["固定目标为初始每股风险的 1.2 倍。"],
            "stop_loss": ["初始止损为 ATR14 × 0.8，且每股风险不低于 0.05 USD。"],
        },
        "recommended_instruments": [
            {
                "profile": "高流动性市场 ETF",
                "examples": ["SPY", "QQQ", "IWM", "SMH"],
                "reason": "研究证据主要来自市场 ETF，尾盘流动性和收盘价格形成更稳定。",
            }
        ],
        "recommended_params": DEFAULT_LAST_HOUR_MOMENTUM_PARAMS,
        "parameter_highlights": ["首半小时阈值 0.05%", "14:45 ET 入场", "ATR 止损 0.8×", "目标 1.2R", "15:55 ET 平仓"],
        "recommendation_reasons": [
            "同行评审研究发现首半小时市场收益可预测最后半小时收益。",
            "只在尾盘单次入场，避免把该研究外推为全天连续信号。",
            "收盘前强制退出消除隔夜跳空风险。",
        ],
        "sources": [
            {
                "title": "Market Intraday Momentum",
                "url": "https://www.researchwithrutgers.org/en/publications/market-intraday-momentum/",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 4,
        "template_key": OPENING_RANGE_RETEST_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_OPENING_RANGE_RETEST_STRATEGY_ID,
        "research_family": "15分钟开盘区间突破回踩",
        "summary": "不追第一根突破 K，等待突破位在 20 根 K 内回踩并重新收回。",
        "logic": {
            "entry": [
                "首 15 分钟形成开盘区间，价格先在 VWAP 同向收盘突破。",
                "突破后最多等待 20 根 K；回踩距离允许 0.15 ATR 容差，重新收回区间边缘才入场。",
            ],
            "exit": ["命中 ATR 止损、1.8R 目标或 12:30 ET 时间止损时退出。"],
            "take_profit": ["固定目标为初始每股风险的 1.8 倍。"],
            "stop_loss": ["初始止损为 ATR14 × 0.8，且每股风险不低于 0.05 USD。"],
        },
        "recommended_instruments": [
            {
                "profile": "开盘成交深度高、回踩结构清晰的标的",
                "examples": ["QQQ", "SPY", "NVDA", "MU"],
                "reason": "连续盘口有利于区分真实回踩与报价空洞造成的跳变。",
            }
        ],
        "recommended_params": DEFAULT_OPENING_RANGE_RETEST_PARAMS,
        "parameter_highlights": ["开盘区间 15 分钟", "回踩等待 20 根 K", "ATR 容差 0.15×", "ATR 止损 0.8×", "目标 1.8R"],
        "recommendation_reasons": [
            "回踩版保留 ORB 家族的方向信息，同时降低首次越界追价。",
            "回踩时限与 ATR 容差把形态转为确定性、可回放规则。",
            "较高的 1.8R 目标补偿较低的信号频率。",
        ],
        "sources": [
            {
                "title": "A Profitable Day Trading Strategy for the U.S. Equity Market",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284",
                "kind": "research",
            },
            {
                "title": "Anatomy of the Retest in the QQQ Opening Range Breakout",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6745958",
                "kind": "exploratory",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
    {
        "research_rank": 5,
        "template_key": VWAP_TREND_PULLBACK_TEMPLATE_KEY,
        "default_strategy_id": DEFAULT_VWAP_TREND_PULLBACK_STRATEGY_ID,
        "research_family": "VWAP 趋势回踩与重新收回",
        "summary": "用 EMA20 斜率确认趋势，在 VWAP 附近出现同向收回 K 时入场。",
        "logic": {
            "entry": [
                "09:30 后 30–240 分钟内，EMA20 斜率决定只做多或只做空。",
                "价格触及 VWAP 的 0.15 ATR 容差区后，以同向实体重新收回 VWAP。",
            ],
            "exit": ["命中 ATR 止损、1.5R 目标或持仓满 60 分钟时退出。"],
            "take_profit": ["固定目标为初始每股风险的 1.5 倍。"],
            "stop_loss": ["初始止损为 ATR14 × 0.8，且每股风险不低于 0.05 USD。"],
        },
        "recommended_instruments": [
            {
                "profile": "VWAP 交易活跃的 ETF 与超大盘股",
                "examples": ["QQQ", "SPY", "MU", "NVDA", "MSFT"],
                "reason": "成交连续时 VWAP 更能代表当日成交重心，回踩证据也更可解释。",
            }
        ],
        "recommended_params": DEFAULT_VWAP_TREND_PULLBACK_PARAMS,
        "parameter_highlights": ["EMA20 趋势", "VWAP 容差 0.15 ATR", "09:30 后 30–240 分钟", "ATR 止损 0.8×", "目标 1.5R"],
        "recommendation_reasons": [
            "VWAP 可作为当日成交重心和趋势状态的条件变量。",
            "EMA 斜率与同向收回 K 限制无趋势环境中的反复穿越。",
            "最长持仓 60 分钟控制趋势未恢复时的时间暴露。",
        ],
        "sources": [
            {
                "title": "VWAP: The Holy Grail for Day Trading Systems",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351",
                "kind": "research",
            },
            {
                "title": "Reversals and the Returns to Liquidity Provision",
                "url": "https://www.nber.org/papers/w30917",
                "kind": "research",
            },
            SEC_DAY_TRADING_SOURCE,
        ],
    },
)


def get_ai_strategy_recommendations(
    conn: sqlite3.Connection,
    *,
    end_date: str,
    symbols: str | list[str] | tuple[str, ...],
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    window_calendar_days: int = 30,
) -> dict[str, Any]:
    canonical_symbols = _canonical_symbols(symbols)
    templates = {template["template_key"]: template for template in get_strategy_templates()}
    configs = list_strategy_configs(conn)
    items: list[dict[str, Any]] = []

    for catalog_entry in AI_STRATEGY_CATALOG:
        template_key = catalog_entry["template_key"]
        template = templates[template_key]
        config = _select_strategy_config(configs, catalog_entry)
        recommended_params = dict(catalog_entry["recommended_params"])
        recommended_params["initial_capital"] = float(initial_capital)
        recommended_params["entry_capital_ratio"] = DEFAULT_ENTRY_CAPITAL_RATIO
        recommended_params_hash = _payload_hash(recommended_params)
        expectation = _strategy_expectation(
            conn,
            strategy_id=config["strategy_id"],
            end_date=end_date,
            symbols=canonical_symbols,
            window_calendar_days=window_calendar_days,
            recommended_params_hash=recommended_params_hash,
            recommended_template_version=template["template_version"],
            current_params_hash=config["params_hash"],
        )
        items.append(
            {
                "rank": catalog_entry["research_rank"],
                "research_rank": catalog_entry["research_rank"],
                "strategy_id": config["strategy_id"],
                "strategy_name": config["name"],
                "template_key": template_key,
                "template_version": template["template_version"],
                "research_family": catalog_entry["research_family"],
                "summary": catalog_entry["summary"],
                "evidence_status": expectation["status"],
                "current_config_alignment": {
                    "matches_recommended_params": config["params_hash"] == recommended_params_hash,
                    "current_params_hash": config["params_hash"],
                    "recommended_params_hash": recommended_params_hash,
                },
                "expectation": expectation,
                "capital": {
                    "initial_capital": float(initial_capital),
                    "entry_capital_ratio": DEFAULT_ENTRY_CAPITAL_RATIO,
                    "position_notional": round(float(initial_capital) * DEFAULT_ENTRY_CAPITAL_RATIO, 2),
                    "concurrency_modeled": False,
                    "note": "多标的指标按独立回放汇总，未建模组合并发资金占用。",
                },
                "logic": catalog_entry["logic"],
                "recommended_instruments": catalog_entry["recommended_instruments"],
                "recommended_params": recommended_params,
                "recommended_param_items": [
                    {
                        "key": schema["key"],
                        "label": schema["label"],
                        "value": recommended_params[schema["key"]],
                    }
                    for schema in template["param_schema"]
                    if schema["key"] in recommended_params
                ],
                "parameter_highlights": catalog_entry["parameter_highlights"],
                "recommended_params_hash": recommended_params_hash,
                "recommendation_reasons": catalog_entry["recommendation_reasons"],
                "sources": catalog_entry["sources"],
                "deep_link": {"workspace": "strategy", "strategy_id": config["strategy_id"]},
            }
        )

    local_ranking_eligible = all(item["expectation"]["status"] == "backtested" for item in items)
    ranking_basis = "local_backtest" if local_ranking_eligible else "research_prior"
    if local_ranking_eligible:
        items.sort(key=_local_ranking_key)
    else:
        items.sort(key=lambda item: item["research_rank"])
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank

    evidence_status = (
        "verified"
        if local_ranking_eligible
        else "partial"
        if any(item["expectation"]["status"] != "research_only" for item in items)
        else "insufficient"
    )
    recommendation_key = _payload_hash(
        {
            "catalog_version": AI_STRATEGY_CATALOG_VERSION,
            "ranking_version": AI_STRATEGY_RANKING_VERSION,
            "ranking_basis": ranking_basis,
            "end_date": end_date,
            "symbols": canonical_symbols,
            "initial_capital": float(initial_capital),
            "window_calendar_days": window_calendar_days,
            "items": [
                {
                    "template_key": item["template_key"],
                    "template_version": item["template_version"],
                    "recommended_params_hash": item["recommended_params_hash"],
                    "batch_ids": item["expectation"]["matching_batch_ids"],
                    "archive_scope_hashes": item["expectation"]["archive_scope_hashes"],
                    "expectation_evidence": {
                        key: item["expectation"][key]
                        for key in (
                            "status",
                            "expected_pnl_per_closed_trade",
                            "total_pnl",
                            "win_rate",
                            "profit_factor",
                            "max_drawdown",
                            "available_day_count",
                            "completed_day_count",
                            "closed_group_count",
                            "excluded_day_count",
                            "excluded_day_reasons",
                            "failure_reasons",
                        )
                    },
                }
                for item in items
            ],
        }
    )
    return {
        "catalog_version": AI_STRATEGY_CATALOG_VERSION,
        "ranking_version": AI_STRATEGY_RANKING_VERSION,
        "ranking_basis": ranking_basis,
        "evidence_status": evidence_status,
        "end_date": end_date,
        "symbols": canonical_symbols,
        "initial_capital": float(initial_capital),
        "entry_capital_ratio": DEFAULT_ENTRY_CAPITAL_RATIO,
        "position_notional": round(float(initial_capital) * DEFAULT_ENTRY_CAPITAL_RATIO, 2),
        "window_calendar_days": window_calendar_days,
        "recommendation_key": recommendation_key,
        "ranking_qualification": {
            "minimum_completed_days_per_strategy": AI_STRATEGY_MIN_COMPLETED_DAYS,
            "minimum_closed_groups_per_strategy": AI_STRATEGY_MIN_CLOSED_GROUPS,
            "requires_all_five_strategies": True,
            "requires_matching_params": True,
            "allows_excluded_non_available_days": True,
            "metric_aggregation": "多标的 total_pnl 相加、win_rate 按闭合信号加权、profit_factor 取保守最小值、max_drawdown 取单标的最大值。",
        },
        "retired_catalog_template_keys": [
            TREND_RIDER_TEMPLATE_KEY,
            BB_SQUEEZE_TEMPLATE_KEY,
            MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
            LIQUIDITY_SWEEP_TEMPLATE_KEY,
            RANGE_FADER_TEMPLATE_KEY,
        ],
        "catalog_note": "v2 已用五个新策略模板替换 AI Top 5；旧模板和历史 artifact 仅保留追溯，不参与当前推荐排名。",
        "disclaimer": "研究支持策略家族；本地回放是样本内历史结果，未计佣金与滑点，不代表未来盈利。日内交易可能导致重大损失。",
        "items": items,
    }


def _select_strategy_config(configs: list[dict[str, Any]], catalog_entry: dict[str, Any]) -> dict[str, Any]:
    candidates = [config for config in configs if config["template_key"] == catalog_entry["template_key"]]
    if not candidates:
        raise KeyError("strategy_not_found")
    return next(
        (config for config in candidates if config["strategy_id"] == catalog_entry["default_strategy_id"]),
        candidates[0],
    )


def _strategy_expectation(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    end_date: str,
    symbols: list[str],
    window_calendar_days: int,
    recommended_params_hash: str,
    recommended_template_version: str,
    current_params_hash: str,
) -> dict[str, Any]:
    batches: list[sqlite3.Row] = []
    any_batch_count = 0
    missing_symbols: list[str] = []
    for symbol in symbols:
        any_batch_count += _matching_batch_count(
            conn,
            strategy_id=strategy_id,
            end_date=end_date,
            symbol=symbol,
            window_calendar_days=window_calendar_days,
        )
        batch = _latest_recommended_batch(
            conn,
            strategy_id=strategy_id,
            end_date=end_date,
            symbol=symbol,
            window_calendar_days=window_calendar_days,
            recommended_params_hash=recommended_params_hash,
        )
        if batch is None:
            missing_symbols.append(symbol)
        else:
            batches.append(batch)

    closed_group_counts = {
        batch["id"]: _batch_closed_group_count(conn, batch["id"])
        for batch in batches
    }
    completed_day_count = sum(int(batch["completed_day_count"]) for batch in batches)
    available_day_count = sum(int(batch["available_day_count"]) for batch in batches)
    closed_group_count = sum(closed_group_counts.values())
    total_pnl = round(sum(float(batch["total_pnl"]) for batch in batches), 6)
    weighted_wins = sum(float(batch["win_rate"]) * closed_group_counts[batch["id"]] for batch in batches)
    win_rate = round(weighted_wins / closed_group_count, 6) if closed_group_count else 0.0
    finite_profit_factors = [float(batch["profit_factor"]) for batch in batches if batch["profit_factor"] is not None]
    profit_factor = min(finite_profit_factors) if finite_profit_factors else None
    max_drawdown = max((float(batch["max_drawdown"]) for batch in batches), default=0.0)
    completed_batches = [batch for batch in batches if batch["status"] == "completed"]
    matching_template_versions = all(batch["template_version"] == recommended_template_version for batch in batches)
    current_config_matches = current_params_hash == recommended_params_hash
    capital_matches = all(_batch_capital_matches(batch) for batch in batches)
    artifact_failure_reasons = _batch_failure_reasons(conn, batches)
    excluded_day_evidence = _batch_excluded_day_evidence(conn, batches)
    failure_reasons: list[str] = []

    if not current_config_matches:
        failure_reasons.append("current_config_differs_from_recommended")
    if missing_symbols:
        failure_reasons.append("missing_matching_batches:" + ",".join(missing_symbols))
    if len(completed_batches) != len(batches):
        failure_reasons.append("non_completed_strategy_test_batch")
    if not matching_template_versions:
        failure_reasons.append("template_version_mismatch")
    if not capital_matches:
        failure_reasons.append("capital_evidence_mismatch")
    if completed_day_count < AI_STRATEGY_MIN_COMPLETED_DAYS:
        failure_reasons.append(f"completed_days_below_{AI_STRATEGY_MIN_COMPLETED_DAYS}")
    if closed_group_count < AI_STRATEGY_MIN_CLOSED_GROUPS:
        failure_reasons.append(f"closed_groups_below_{AI_STRATEGY_MIN_CLOSED_GROUPS}")
    if batches and profit_factor is None:
        failure_reasons.append("profit_factor_unavailable")
    failure_reasons.extend(artifact_failure_reasons)

    backtested = (
        current_config_matches
        and len(batches) == len(symbols)
        and len(completed_batches) == len(symbols)
        and matching_template_versions
        and capital_matches
        and completed_day_count >= AI_STRATEGY_MIN_COMPLETED_DAYS
        and closed_group_count >= AI_STRATEGY_MIN_CLOSED_GROUPS
        and profit_factor is not None
        and not artifact_failure_reasons
    )
    if backtested:
        status = "backtested"
    elif batches or any_batch_count:
        status = "partial"
    else:
        status = "research_only"

    return {
        "status": status,
        "expected_pnl_per_closed_trade": round(total_pnl / closed_group_count, 6) if closed_group_count else None,
        "total_pnl": total_pnl if batches else None,
        "win_rate": win_rate if batches else None,
        "profit_factor": None if profit_factor is None else round(profit_factor, 6),
        "max_drawdown": round(max_drawdown, 6) if batches else None,
        "available_day_count": available_day_count,
        "completed_day_count": completed_day_count,
        "closed_group_count": closed_group_count,
        "excluded_day_count": excluded_day_evidence["count"],
        "excluded_day_reasons": excluded_day_evidence["reasons"],
        "coverage_ratio": round(completed_day_count / (window_calendar_days * len(symbols)), 6),
        "params_hash": recommended_params_hash,
        "matching_batch_ids": [batch["id"] for batch in batches],
        "archive_scope_hashes": [batch["archive_scope_hash"] for batch in batches],
        "failure_reasons": list(dict.fromkeys(failure_reasons)),
        "metric_aggregation": "single_symbol" if len(symbols) == 1 else "independent_symbol_sum",
    }


def _latest_recommended_batch(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    end_date: str,
    symbol: str,
    window_calendar_days: int,
    recommended_params_hash: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM strategy_test_batches
        WHERE strategy_id = ? AND end_date = ? AND symbol = ?
          AND window_trading_days = ? AND params_hash = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (strategy_id, end_date, symbol, window_calendar_days, recommended_params_hash),
    ).fetchone()


def _matching_batch_count(
    conn: sqlite3.Connection,
    *,
    strategy_id: str,
    end_date: str,
    symbol: str,
    window_calendar_days: int,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM strategy_test_batches
        WHERE strategy_id = ? AND end_date = ? AND symbol = ? AND window_trading_days = ?
        """,
        (strategy_id, end_date, symbol, window_calendar_days),
    ).fetchone()
    return int(row["count"] if row else 0)


def _batch_closed_group_count(conn: sqlite3.Connection, batch_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(closed_group_count), 0) AS count FROM strategy_test_day_results WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    return int(row["count"] if row else 0)


def _batch_failure_reasons(conn: sqlite3.Connection, batches: list[sqlite3.Row]) -> list[str]:
    if not batches:
        return []
    reasons = [str(batch["failure_reason"]) for batch in batches if batch["failure_reason"]]
    batch_ids = [str(batch["id"]) for batch in batches]
    placeholders = ",".join("?" for _ in batch_ids)
    rows = conn.execute(
        f"""
        SELECT DISTINCT status, failure_reason
        FROM strategy_test_day_results
        WHERE batch_id IN ({placeholders})
          AND (
            status NOT IN ('completed', 'non_available_archive')
            OR (status = 'completed' AND failure_reason IS NOT NULL AND failure_reason != '')
          )
        ORDER BY status, failure_reason
        """,
        batch_ids,
    ).fetchall()
    reasons.extend(
        str(row["failure_reason"])
        if row["failure_reason"]
        else f"strategy_test_day_status:{row['status']}"
        for row in rows
    )
    return list(dict.fromkeys(reasons))


def _batch_excluded_day_evidence(conn: sqlite3.Connection, batches: list[sqlite3.Row]) -> dict[str, Any]:
    if not batches:
        return {"count": 0, "reasons": []}
    batch_ids = [str(batch["id"]) for batch in batches]
    placeholders = ",".join("?" for _ in batch_ids)
    rows = conn.execute(
        f"""
        SELECT COALESCE(failure_reason, status) AS reason, COUNT(*) AS count
        FROM strategy_test_day_results
        WHERE batch_id IN ({placeholders}) AND status = 'non_available_archive'
        GROUP BY COALESCE(failure_reason, status)
        ORDER BY reason
        """,
        batch_ids,
    ).fetchall()
    return {
        "count": sum(int(row["count"]) for row in rows),
        "reasons": [f"{row['reason']}:{row['count']}" for row in rows],
    }


def _batch_capital_matches(batch: sqlite3.Row) -> bool:
    try:
        params = json.loads(batch["params_json"])
    except (TypeError, json.JSONDecodeError):
        return False
    return (
        float(params.get("initial_capital", 0.0)) == DEFAULT_INITIAL_CAPITAL
        and float(params.get("entry_capital_ratio", 0.0)) == DEFAULT_ENTRY_CAPITAL_RATIO
    )


def _canonical_symbols(symbols: str | list[str] | tuple[str, ...]) -> list[str]:
    raw_items = symbols.split(",") if isinstance(symbols, str) else list(symbols)
    canonical = sorted({str(item).strip().upper() for item in raw_items if str(item).strip()})
    if not canonical:
        raise ValueError("strategy_symbol_required")
    if len(canonical) > AI_STRATEGY_MAX_SYMBOLS:
        raise ValueError("strategy_symbol_count_out_of_range")
    if any(len(symbol) > 16 for symbol in canonical):
        raise ValueError("strategy_symbol_out_of_range")
    return canonical


def _local_ranking_key(item: dict[str, Any]) -> tuple[Any, ...]:
    expectation = item["expectation"]
    expected_pnl = float(expectation["expected_pnl_per_closed_trade"])
    profit_factor = expectation["profit_factor"]
    return (
        -expected_pnl,
        profit_factor is None,
        -float(profit_factor or 0.0),
        float(expectation["max_drawdown"] or 0.0),
        -int(expectation["closed_group_count"]),
        int(item["research_rank"]),
    )


def _payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
