import sqlite3

import pytest

from grit_day_trading.storage import STORAGE_SCHEMA_VERSION, connect, initialize_database


def test_storage_contract_creates_required_indexes_triggers_and_migration_marker(tmp_path):
    conn = connect(tmp_path / "trading.db")
    try:
        initialize_database(conn)

        assert conn.execute("PRAGMA user_version").fetchone()[0] == STORAGE_SCHEMA_VERSION
        migration = conn.execute(
            "SELECT description FROM storage_migrations WHERE version = ?",
            (STORAGE_SCHEMA_VERSION,),
        ).fetchone()
        expected_current_migrations = {
            3: "p1_yahoo_minute_archive_contract_v3",
            4: "p2_strategy_signal_contract_v4",
            5: "p2_strategy_testing_optimization_contract_v5",
            6: "p2_strategy_config_history_contract_v6",
            7: "p2_strategy_config_history_rollback_contract_v7",
            8: "p3_trade_review_journal_contract_v8",
        }
        assert migration["description"] == expected_current_migrations[STORAGE_SCHEMA_VERSION]
        p0_migration = conn.execute("SELECT description FROM storage_migrations WHERE version = 1").fetchone()
        assert p0_migration["description"] == "p0_storage_contract_v1"
        p1_migration = conn.execute("SELECT description FROM storage_migrations WHERE version = 2").fetchone()
        assert p1_migration["description"] == "p1_market_context_contract_v2"
        yahoo_migration = conn.execute("SELECT description FROM storage_migrations WHERE version = 3").fetchone()
        assert yahoo_migration["description"] == "p1_yahoo_minute_archive_contract_v3"
        if STORAGE_SCHEMA_VERSION >= 4:
            strategy_migration = conn.execute("SELECT description FROM storage_migrations WHERE version = 4").fetchone()
            assert strategy_migration["description"] == "p2_strategy_signal_contract_v4"
        if STORAGE_SCHEMA_VERSION >= 5:
            strategy_test_migration = conn.execute("SELECT description FROM storage_migrations WHERE version = 5").fetchone()
            assert strategy_test_migration["description"] == "p2_strategy_testing_optimization_contract_v5"
        if STORAGE_SCHEMA_VERSION >= 6:
            strategy_history_migration = conn.execute(
                "SELECT description FROM storage_migrations WHERE version = 6"
            ).fetchone()
            assert strategy_history_migration["description"] == "p2_strategy_config_history_contract_v6"
        if STORAGE_SCHEMA_VERSION >= 7:
            strategy_history_rollback_migration = conn.execute(
                "SELECT description FROM storage_migrations WHERE version = 7"
            ).fetchone()
            assert strategy_history_rollback_migration["description"] == "p2_strategy_config_history_rollback_contract_v7"
        if STORAGE_SCHEMA_VERSION >= 8:
            trade_review_migration = conn.execute("SELECT description FROM storage_migrations WHERE version = 8").fetchone()
            assert trade_review_migration["description"] == "p3_trade_review_journal_contract_v8"
        assert {
            "ux_import_batches_file_hash",
            "ux_import_rows_batch_line_hash",
            "ux_orders_idempotency_key",
            "ux_orders_account_order",
        }.issubset(_index_names(conn, "orders") | _index_names(conn, "import_batches") | _index_names(conn, "import_rows"))
        assert {
            "ux_fills_idempotency_key",
            "ux_fills_account_execution",
            "ux_fills_source_import_row",
            "ux_quarantine_import_row",
        }.issubset(_index_names(conn, "fills") | _index_names(conn, "quarantine_rows"))
        assert {
            "ux_market_context_snapshot_window",
            "ix_market_context_symbol_created",
            "ix_market_attempts_symbol_created",
            "ux_market_minute_archive_window",
            "ux_market_minute_archive_idempotency",
            "ix_market_minute_archive_date_symbol",
            "ux_watchlist_run_contract",
            "ux_watchlist_items_run_symbol",
            "ix_watchlist_items_date_rank",
            "ix_strategy_configs_template_enabled",
            "ux_strategy_signal_run_idempotency",
            "ix_strategy_signal_runs_lookup",
            "ix_strategy_signals_run_time",
            "ux_strategy_test_batch_idempotency",
            "ix_strategy_test_batches_lookup",
            "ux_strategy_test_day_batch_date",
            "ix_strategy_test_day_results_run",
            "ux_strategy_optimization_idempotency",
            "ix_strategy_optimization_lookup",
            "ux_strategy_optimization_candidate_params",
            "ix_strategy_optimization_candidate_rank",
            "ux_strategy_config_history_idempotency",
            "ix_strategy_config_history_strategy_created",
            "ux_trade_reviews_group",
            "ux_trade_reviews_idempotency",
            "ix_trade_reviews_symbol_date",
        }.issubset(
            _index_names(conn, "market_context_snapshots")
            | _index_names(conn, "market_minute_archives")
            | _index_names(conn, "market_data_provider_attempts")
            | _index_names(conn, "watchlist_runs")
            | _index_names(conn, "watchlist_items")
            | _index_names(conn, "strategy_configs")
            | _index_names(conn, "strategy_signal_runs")
            | _index_names(conn, "strategy_signals")
            | _index_names(conn, "strategy_test_batches")
            | _index_names(conn, "strategy_test_day_results")
            | _index_names(conn, "strategy_optimization_runs")
            | _index_names(conn, "strategy_optimization_candidates")
            | _index_names(conn, "strategy_config_history")
            | _index_names(conn, "trade_reviews")
        )
        assert "params_json" in _column_names(conn, "strategy_signal_runs")
        assert {"previous_params_json", "next_params_json", "source_history_id"}.issubset(
            _column_names(conn, "strategy_config_history")
        )
        assert {
            "trade_group_id",
            "reason_category",
            "reason_code",
            "reason_label",
            "parser_versions_json",
            "field_mapper_versions_json",
            "idempotency_key",
        }.issubset(_column_names(conn, "trade_reviews"))
        conn.execute(
            """
            INSERT INTO strategy_configs (
                id, name, template_key, template_version, enabled,
                params_json, params_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                "strategy_storage_contract",
                "Storage Contract Strategy",
                "bb_squeeze_breakout_v1",
                "bb_squeeze_breakout_v1",
                "{}",
                "strategy_storage_hash",
                "2026-06-10T00:00:00Z",
                "2026-06-10T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO strategy_config_history (
                id, strategy_id, change_source, previous_template_version,
                next_template_version, previous_params_hash, next_params_hash,
                previous_params_json, next_params_json, change_reason, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "stratchg_history_rollback",
                "strategy_storage_contract",
                "history_rollback",
                "template_v1",
                "template_v2",
                "old_hash",
                "new_hash",
                "{}",
                "{}",
                "history_rollback",
                "history_rollback_key",
            ),
        )
        assert {
            "trg_import_rows_account_canonical_insert",
            "trg_orders_account_canonical_insert",
            "trg_fills_account_canonical_insert",
        }.issubset(_trigger_names(conn))
    finally:
        conn.close()


def test_storage_contract_rejects_non_canonical_account_fields(tmp_path):
    conn = connect(tmp_path / "trading.db")
    try:
        initialize_database(conn)
        _insert_batch(conn)
        _insert_import_row(conn, row_id="row_1", raw_line_number=1, order_id="O-1", execution_id="E-1")
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError, match="account_canonical_mismatch"):
            _insert_order(
                conn,
                record_id="order_bad",
                source_row_id="row_1",
                account_raw=" acct-01 \n",
                account_canonical="acct-01",
                order_id="O-1",
                idempotency_key="bad-order-key",
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="account_canonical_mismatch"):
            _insert_fill(
                conn,
                record_id="fill_bad",
                source_row_id="row_1",
                account_raw="\tacct-01 ",
                account_canonical="ACCT_01",
                execution_id="E-1",
                idempotency_key="bad-fill-key",
            )
    finally:
        conn.close()


def test_p1_storage_contract_enforces_market_snapshot_and_watchlist_keys(tmp_path):
    conn = connect(tmp_path / "p1.db")
    try:
        initialize_database(conn)
        _insert_batch(conn)
        _insert_import_row(conn, row_id="row_1", raw_line_number=1, order_id="O-1", execution_id="E-1")
        _insert_fill(
            conn,
            record_id="fill_1",
            source_row_id="row_1",
            account_raw="acct-01",
            account_canonical="ACCT-01",
            execution_id="E-1",
            idempotency_key="fill-key-1",
        )
        conn.execute(
            """
            INSERT INTO market_context_snapshots (
                id, fill_id, provider, symbol, requested_start, requested_end, provider_timezone,
                bar_count, bars_hash, bars_json, vwap, day_high, day_low,
                volume_context, data_status, failure_reason
            ) VALUES (
                'mctx_1', 'fill_1', 'fake', 'NVDA', '2026-06-01T09:00:00',
                '2026-06-01T10:00:00', 'America/New_York', 1, 'hash_1', '[]',
                100, 101, 99, '{}', 'available', NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO watchlist_runs (
                id, trade_date, provider, rules_version, status, item_count
            ) VALUES ('watchrun_1', '2026-06-01', 'fake', 'rules_v1', 'completed', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO watchlist_items (
                id, run_id, trade_date, symbol, rank, reason_codes_json,
                metrics_json, source, status
            ) VALUES (
                'watchitem_1', 'watchrun_1', '2026-06-01', 'NVDA', 1,
                '{"codes":["relative_volume_spike"]}', '{"relative_volume":2.0}',
                'provider_summary', 'included'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO market_minute_archives (
                id, provider, symbol, trade_date, requested_start, requested_end, provider_timezone,
                bar_count, bars_hash, bars_json, volume_context, data_status, source_fill_count,
                archive_version, idempotency_key
            ) VALUES (
                'minbar_1', 'yahoo', 'NVDA', '2026-06-01', '2026-06-01T04:00:00',
                '2026-06-01T20:00:00', 'America/New_York', 1, 'hash_1', '[]',
                '{}', 'available', 1, 'market_minute_archive_v1',
                'yahoo:NVDA:2026-06-01:2026-06-01T04:00:00:2026-06-01T20:00:00'
            )
            """
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO market_context_snapshots (
                    id, fill_id, provider, symbol, requested_start, requested_end, provider_timezone,
                    bar_count, bars_hash, bars_json, volume_context, data_status
                ) VALUES (
                    'mctx_duplicate', 'fill_1', 'fake', 'NVDA', '2026-06-01T09:00:00',
                    '2026-06-01T10:00:00', 'America/New_York', 0, 'hash_2', '[]',
                    '{}', 'missing'
                )
                """
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO market_context_snapshots (
                    id, fill_id, provider, symbol, requested_start, requested_end, provider_timezone,
                    bar_count, bars_hash, bars_json, volume_context, data_status
                ) VALUES (
                    'mctx_bad_status', 'fill_1', 'fake', 'NVDA', '2026-06-01T08:00:00',
                    '2026-06-01T08:30:00', 'America/New_York', 0, 'hash_3', '[]',
                    '{}', 'empty_chart_success'
                )
                """
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO market_minute_archives (
                    id, provider, symbol, trade_date, requested_start, requested_end, provider_timezone,
                    bar_count, bars_hash, bars_json, volume_context, data_status, source_fill_count,
                    archive_version, idempotency_key
                ) VALUES (
                    'minbar_duplicate', 'yahoo', 'NVDA', '2026-06-01', '2026-06-01T04:00:00',
                    '2026-06-01T20:00:00', 'America/New_York', 1, 'hash_2', '[]',
                    '{}', 'available', 1, 'market_minute_archive_v1',
                    'duplicate-key'
                )
                """
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO market_minute_archives (
                    id, provider, symbol, trade_date, requested_start, requested_end, provider_timezone,
                    bar_count, bars_hash, bars_json, volume_context, data_status, source_fill_count,
                    archive_version, idempotency_key
                ) VALUES (
                    'minbar_bad_status', 'yahoo', 'NVDA', '2026-06-02', '2026-06-02T04:00:00',
                    '2026-06-02T20:00:00', 'America/New_York', 0, 'hash_3', '[]',
                    '{}', 'empty_chart_success', 1, 'market_minute_archive_v1',
                    'yahoo:NVDA:2026-06-02:2026-06-02T04:00:00:2026-06-02T20:00:00'
                )
                """
            )
    finally:
        conn.close()


def test_p2_storage_contract_enforces_strategy_run_status_and_idempotency(tmp_path):
    conn = connect(tmp_path / "p2.db")
    try:
        initialize_database(conn)
        conn.execute(
            """
            INSERT INTO strategy_configs (
                id, name, template_key, template_version, enabled, params_json, params_hash
            ) VALUES (
                'strategy_1', 'BB', 'bb_squeeze_breakout_v1', 'bb_squeeze_breakout_v1',
                1, '{}', 'params_hash_1'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO strategy_signal_runs (
                id, strategy_id, provider, symbol, trade_date, source_archive_id,
                bars_hash, params_hash, indicator_engine_version, status,
                indicator_series_json, indicator_hash, signal_count, idempotency_key
            ) VALUES (
                'stratrun_1', 'strategy_1', 'yahoo', 'NVDA', '2026-06-01', NULL,
                'bars_hash_1', 'params_hash_1', 'strategy_indicator_engine_v1',
                'completed', '[]', 'indicator_hash_1', 0, 'strategy-run-key'
            )
            """
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO strategy_signal_runs (
                    id, strategy_id, provider, symbol, trade_date, bars_hash,
                    params_hash, indicator_engine_version, status, indicator_series_json,
                    indicator_hash, signal_count, idempotency_key
                ) VALUES (
                    'stratrun_duplicate', 'strategy_1', 'yahoo', 'NVDA', '2026-06-01',
                    'bars_hash_2', 'params_hash_1', 'strategy_indicator_engine_v1',
                    'completed', '[]', 'indicator_hash_2', 0, 'strategy-run-key'
                )
                """
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO strategy_signal_runs (
                    id, strategy_id, provider, symbol, trade_date, bars_hash,
                    params_hash, indicator_engine_version, status, indicator_series_json,
                    indicator_hash, signal_count, idempotency_key
                ) VALUES (
                    'stratrun_bad_status', 'strategy_1', 'yahoo', 'NVDA', '2026-06-01',
                    'bars_hash_3', 'params_hash_1', 'strategy_indicator_engine_v1',
                    'empty_chart_success', '[]', 'indicator_hash_3', 0, 'bad-status-key'
                )
                """
            )
    finally:
        conn.close()


def test_p2_strategy_testing_optimization_storage_contract(tmp_path):
    conn = connect(tmp_path / "p2_v5.db")
    try:
        initialize_database(conn)
        conn.execute(
            """
            INSERT INTO strategy_configs (
                id, name, template_key, template_version, enabled, params_json, params_hash
            ) VALUES (
                'strategy_1', 'BB', 'bb_squeeze_breakout_v1', 'bb_squeeze_breakout_v1',
                1, '{}', 'params_hash_1'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO strategy_test_batches (
                id, strategy_id, provider, symbol, end_date, window_trading_days,
                archive_scope_hash, params_json, params_hash, template_version,
                indicator_engine_version, status, idempotency_key
            ) VALUES (
                'test_1', 'strategy_1', 'yahoo', 'NVDA', '2026-06-30', 30,
                'scope_hash_1', '{}', 'params_hash_1', 'bb_squeeze_breakout_v1',
                'strategy_indicator_engine_v2', 'completed', 'test-key'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO strategy_optimization_runs (
                id, strategy_id, provider, symbol, end_date, window_trading_days,
                archive_scope_hash, search_space_json, search_space_hash, objective,
                template_version, indicator_engine_version, status, idempotency_key
            ) VALUES (
                'opt_1', 'strategy_1', 'yahoo', 'NVDA', '2026-06-30', 30,
                'scope_hash_1', '{}', 'search_hash_1', 'stable_profitability_v1',
                'bb_squeeze_breakout_v1', 'strategy_indicator_engine_v2', 'completed',
                'opt-key'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO strategy_optimization_candidates (
                id, optimization_run_id, rank, params_json, params_hash, day_results_json,
                status
            ) VALUES (
                'cand_1', 'opt_1', 1, '{}', 'params_hash_1', '[]', 'eligible'
            )
            """
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO strategy_test_batches (
                    id, strategy_id, provider, symbol, end_date, window_trading_days,
                    archive_scope_hash, params_json, params_hash, template_version,
                    indicator_engine_version, status, idempotency_key
                ) VALUES (
                    'test_dup', 'strategy_1', 'yahoo', 'NVDA', '2026-06-30', 30,
                    'scope_hash_2', '{}', 'params_hash_1', 'bb_squeeze_breakout_v1',
                    'strategy_indicator_engine_v2', 'completed', 'test-key'
                )
                """
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO strategy_optimization_candidates (
                    id, optimization_run_id, rank, params_json, params_hash, day_results_json,
                    status
                ) VALUES (
                    'cand_dup', 'opt_1', 2, '{}', 'params_hash_1', '[]', 'eligible'
                )
                """
            )
        conn.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO strategy_optimization_runs (
                    id, strategy_id, provider, symbol, end_date, window_trading_days,
                    archive_scope_hash, search_space_json, search_space_hash, objective,
                    template_version, indicator_engine_version, status, idempotency_key
                ) VALUES (
                    'opt_bad', 'strategy_1', 'yahoo', 'NVDA', '2026-06-30', 30,
                    'scope_hash_1', '{}', 'search_hash_2', 'stable_profitability_v1',
                    'bb_squeeze_breakout_v1', 'strategy_indicator_engine_v2',
                    'rendered_fake_success', 'bad-opt-key'
                )
                """
            )
    finally:
        conn.close()


def test_storage_contract_blocks_duplicate_order_and_fill_business_keys(tmp_path):
    conn = connect(tmp_path / "trading.db")
    try:
        initialize_database(conn)
        _insert_batch(conn)
        _insert_import_row(conn, row_id="row_1", raw_line_number=1, order_id="O-1", execution_id="E-1")
        _insert_import_row(conn, row_id="row_2", raw_line_number=2, order_id="O-1", execution_id="E-1")
        _insert_import_row(conn, row_id="row_3", raw_line_number=3, order_id="O-2", execution_id="E-1")
        conn.commit()

        _insert_order(
            conn,
            record_id="order_1",
            source_row_id="row_1",
            account_raw=" acct-01 ",
            account_canonical="ACCT-01",
            order_id="O-1",
            idempotency_key="order-key-1",
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_order(
                conn,
                record_id="order_2",
                source_row_id="row_2",
                account_raw="acct-01",
                account_canonical="ACCT-01",
                order_id="O-1",
                idempotency_key="order-key-2",
            )
        conn.rollback()

        _insert_fill(
            conn,
            record_id="fill_1",
            source_row_id="row_1",
            account_raw=" acct-01 ",
            account_canonical="ACCT-01",
            execution_id="E-1",
            idempotency_key="fill-key-1",
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _insert_fill(
                conn,
                record_id="fill_2",
                source_row_id="row_3",
                account_raw="acct-01",
                account_canonical="ACCT-01",
                execution_id="E-1",
                idempotency_key="fill-key-2",
            )
    finally:
        conn.close()


def test_initialize_database_migrates_legacy_schema_with_contract_indexes(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy.db")
    conn.row_factory = sqlite3.Row
    try:
        _create_legacy_schema(conn)
        _insert_batch(conn)
        _insert_import_row(conn, row_id="row_1", raw_line_number=1, order_id="O-1", execution_id="E-1")
        conn.commit()

        initialize_database(conn)

        assert conn.execute("PRAGMA user_version").fetchone()[0] == STORAGE_SCHEMA_VERSION
        assert "ux_import_batches_file_hash" in _index_names(conn, "import_batches")
        with pytest.raises(sqlite3.IntegrityError, match="account_canonical_mismatch"):
            _insert_order(
                conn,
                record_id="order_bad",
                source_row_id="row_1",
                account_raw=" acct-01 ",
                account_canonical="acct-01",
                order_id="O-1",
                idempotency_key="bad-order-key",
            )
    finally:
        conn.close()


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA index_list({table_name})").fetchall()}


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _trigger_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    return {row["name"] for row in rows}


def _insert_batch(conn: sqlite3.Connection, batch_id: str = "batch_1", file_hash: str = "hash_1") -> None:
    conn.execute(
        """
        INSERT INTO import_batches (
            id, file_name, file_hash, uploaded_at, parser_version, field_mapper_version,
            status, status_reason, row_count, accepted_rows, quarantined_rows
        ) VALUES (?, 'sample.tsv', ?, '2026-06-01T09:30:00Z', 'parser_v1', 'mapper_v1',
            'committed', NULL, 1, 1, 0)
        """,
        (batch_id, file_hash),
    )


def _insert_import_row(
    conn: sqlite3.Connection,
    *,
    row_id: str,
    raw_line_number: int,
    order_id: str,
    execution_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO import_rows (
            id, batch_id, raw_line_number, raw_text, raw_line_hash, parser_version,
            field_mapper_version, account_raw, account_canonical, parsed_payload_json,
            row_status, order_id, execution_id
        ) VALUES (?, 'batch_1', ?, ?, ?, 'parser_v1', 'mapper_v1',
            ' acct-01 ', 'ACCT-01', '{}', 'accepted', ?, ?)
        """,
        (row_id, raw_line_number, f"raw-{raw_line_number}", f"hash-{raw_line_number}", order_id, execution_id),
    )


def _insert_order(
    conn: sqlite3.Connection,
    *,
    record_id: str,
    source_row_id: str,
    account_raw: str,
    account_canonical: str,
    order_id: str,
    idempotency_key: str,
) -> None:
    conn.execute(
        """
        INSERT INTO orders (
            id, account_raw, account_canonical, symbol, side, order_id, order_status,
            submitted_at, source_batch_id, source_import_row_id, idempotency_key
        ) VALUES (?, ?, ?, 'NVDA', 'BUY', ?, 'FILLED',
            '2026-06-01T09:30:00Z', 'batch_1', ?, ?)
        """,
        (record_id, account_raw, account_canonical, order_id, source_row_id, idempotency_key),
    )


def _insert_fill(
    conn: sqlite3.Connection,
    *,
    record_id: str,
    source_row_id: str,
    account_raw: str,
    account_canonical: str,
    execution_id: str,
    idempotency_key: str,
) -> None:
    conn.execute(
        """
        INSERT INTO fills (
            id, account_raw, account_canonical, symbol, side, order_id, execution_id,
            filled_at, quantity, price, source_batch_id, source_import_row_id, idempotency_key
        ) VALUES (?, ?, ?, 'NVDA', 'BUY', 'O-1', ?,
            '2026-06-01T09:30:00Z', 10, 100.5, 'batch_1', ?, ?)
        """,
        (record_id, account_raw, account_canonical, execution_id, source_row_id, idempotency_key),
    )


def _create_legacy_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE import_batches (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            field_mapper_version TEXT NOT NULL,
            status TEXT NOT NULL,
            status_reason TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            accepted_rows INTEGER NOT NULL DEFAULT 0,
            quarantined_rows INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE import_rows (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            raw_line_number INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            raw_line_hash TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            field_mapper_version TEXT NOT NULL,
            account_raw TEXT,
            account_canonical TEXT,
            parsed_payload_json TEXT NOT NULL,
            row_status TEXT NOT NULL,
            order_id TEXT,
            execution_id TEXT,
            order_record_id TEXT,
            fill_record_id TEXT
        );

        CREATE TABLE orders (
            id TEXT PRIMARY KEY,
            account_raw TEXT NOT NULL,
            account_canonical TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_id TEXT NOT NULL,
            order_status TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            source_batch_id TEXT NOT NULL,
            source_import_row_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL
        );

        CREATE TABLE fills (
            id TEXT PRIMARY KEY,
            account_raw TEXT NOT NULL,
            account_canonical TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_id TEXT NOT NULL,
            execution_id TEXT,
            filled_at TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            source_batch_id TEXT NOT NULL,
            source_import_row_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL
        );

        CREATE TABLE quarantine_rows (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            import_row_id TEXT,
            raw_line_number INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            failed_field TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            reason TEXT NOT NULL,
            repair_hint TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'open'
        );
        """
    )
