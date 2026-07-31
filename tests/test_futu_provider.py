from types import SimpleNamespace

from grit_day_trading import futu_provider
from grit_day_trading.futu_provider import FutuMarketDataProvider


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        return iter(enumerate(self._rows))


class _QuoteContext:
    def __init__(self, *, quota_data, history_result):
        self.quota_data = quota_data
        self.history_result = history_result
        self.history_calls = []
        self.closed = False

    def get_history_kl_quota(self, *, get_detail):
        assert get_detail is True
        return 0, self.quota_data

    def request_history_kline(self, code, **kwargs):
        self.history_calls.append((code, kwargs))
        return self.history_result

    def close(self):
        self.closed = True


def _fake_futu(context):
    return SimpleNamespace(
        AuType=SimpleNamespace(NONE="NONE"),
        KLType=SimpleNamespace(K_1M="K_1M"),
        OpenQuoteContext=lambda **_: context,
        RET_OK=0,
    )


def test_futu_provider_checks_quota_and_reads_one_minute_history(monkeypatch):
    rows = _Rows(
        [
            {
                "time_key": "2026-06-01 09:30:00",
                "open": 120.0,
                "high": 121.0,
                "low": 119.5,
                "close": 120.5,
                "volume": 1000,
            }
        ]
    )
    context = _QuoteContext(quota_data=(2, 98, []), history_result=(0, rows, None))
    monkeypatch.setattr(futu_provider, "_import_futu", lambda: _fake_futu(context))

    response = FutuMarketDataProvider().fetch_minute_bars(
        "MU",
        "2026-06-01T04:00:00",
        "2026-06-01T20:00:00",
    )

    assert response.status == "available"
    assert len(response.bars) == 1
    assert response.bars[0].timestamp == "2026-06-01T09:30:00"
    assert context.history_calls == [
        (
            "US.MU",
            {
                "start": "2026-06-01",
                "end": "2026-06-01",
                "ktype": "K_1M",
                "autype": "NONE",
                "max_count": 1000,
                "extended_time": True,
            },
        )
    ]
    assert context.closed is True


def test_futu_provider_rejects_new_symbol_when_history_quota_is_exhausted(monkeypatch):
    context = _QuoteContext(quota_data=(100, 0, [{"code": "US.AAPL"}]), history_result=(0, _Rows([]), None))
    monkeypatch.setattr(futu_provider, "_import_futu", lambda: _fake_futu(context))

    response = FutuMarketDataProvider().fetch_minute_bars(
        "MU",
        "2026-06-01T04:00:00",
        "2026-06-01T20:00:00",
    )

    assert response.status == "provider_failed"
    assert response.error_code == "futu_history_quota_exhausted"
    assert context.history_calls == []
    assert context.closed is True


def test_futu_provider_allows_symbol_already_counted_in_exhausted_quota(monkeypatch):
    context = _QuoteContext(
        quota_data=(100, 0, [{"code": "US.MU"}]),
        history_result=(0, _Rows([]), None),
    )
    monkeypatch.setattr(futu_provider, "_import_futu", lambda: _fake_futu(context))

    response = FutuMarketDataProvider().fetch_minute_bars(
        "MU",
        "2026-06-01T04:00:00",
        "2026-06-01T20:00:00",
    )

    assert response.status == "missing"
    assert len(context.history_calls) == 1
    assert context.closed is True


def test_futu_provider_auto_starts_local_opend_before_retry(monkeypatch):
    context = _QuoteContext(
        quota_data=(2, 98, []),
        history_result=(0, _Rows([]), None),
    )
    connect_count = 0

    def open_context(**_):
        nonlocal connect_count
        connect_count += 1
        if connect_count == 1:
            raise ConnectionRefusedError
        return context

    fake_futu = _fake_futu(context)
    fake_futu.OpenQuoteContext = open_context
    monkeypatch.setattr(futu_provider, "_import_futu", lambda: fake_futu)
    monkeypatch.setattr(futu_provider, "_start_futu_opend", lambda host, port: (host, port) == ("127.0.0.1", 11111))

    response = FutuMarketDataProvider(auto_start_opend=True).fetch_minute_bars(
        "MU",
        "2026-06-01T04:00:00",
        "2026-06-01T20:00:00",
    )

    assert response.status == "missing"
    assert connect_count == 2
    assert context.closed is True
