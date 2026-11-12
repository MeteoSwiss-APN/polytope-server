// SPDX-FileCopyrightText: 2026 European Centre for Medium-Range Weather Forecasts (ECMWF)
//
// SPDX-License-Identifier: Apache-2.0

use async_trait::async_trait;
use bytes::Bytes;
use clap::Parser;
use polytope_worker_common::config::{DEFAULT_CONFIG_PATH, WorkerConfigFile};
use polytope_worker_common::{
    ProcessResult, Processor, SourceError, WorkItem, WorkerConfig, run_worker_loop,
};
use rsfdb::{FDB, request::Request};
use tokio_stream::wrappers::ReceiverStream;
use tracing::{debug, info, warn};

struct FdbProcessor {
    fdb_config: String,
}

/// FDB's remote client keeps its connection to each store server for the whole process and does not replace it once
/// lost (e.g. after a store server restart, see ecmwf/fdb#421): every later retrieval then fails, and only a new
/// process recovers. Such errors request a worker restart.
///
/// NOTE: this relies on the error message of FDB's `ClientConnection::controlWrite()`
/// (`src/fdb5/remote/client/ClientConnection.cc`): "Connection to <host:port> is no longer valid".
/// If FDB changes that message, this no longer matches and the worker keeps failing until it is restarted.
fn is_lost_fdb_connection(message: &str) -> bool {
    message.contains("is no longer valid")
}

#[async_trait]
impl Processor for FdbProcessor {
    async fn process(&self, work: WorkItem) -> ProcessResult {
        let fdb_config = self.fdb_config.clone();

        let request = work.request;
        let (tx, rx) = tokio::sync::mpsc::channel::<Result<Bytes, std::io::Error>>(16);
        let source_error = SourceError::new();
        let source_error_for_task = source_error.clone();
        // Held by the blocking task, which can outlive the async job.
        let active = polytope_observability::active_request(&work.job_id);
        tokio::task::spawn_blocking(move || {
            let _active = active;
            let fail = |err: std::io::Error| {
                let message = err.to_string();
                if is_lost_fdb_connection(&message) {
                    source_error_for_task.set_unrecoverable_once(message);
                }
                let _ = tx.blocking_send(Err(err));
            };
            let fdb = match FDB::new(Some(&fdb_config)) {
                Ok(fdb) => fdb,
                Err(err) => {
                    fail(std::io::Error::other(err));
                    return;
                }
            };
            let request = match Request::from_json(request) {
                Ok(request) => request,
                Err(err) => {
                    let _ = tx.blocking_send(Err(std::io::Error::other(err)));
                    return;
                }
            };
            let mut reader = match fdb.retrieve(&request) {
                Ok(reader) => reader,
                Err(err) => {
                    fail(std::io::Error::other(err));
                    return;
                }
            };
            let mut buffer = vec![0u8; 256 * 1024];
            loop {
                match std::io::Read::read(&mut reader, &mut buffer) {
                    Ok(0) => break,
                    Ok(size) => {
                        if tx
                            .blocking_send(Ok(Bytes::copy_from_slice(&buffer[..size])))
                            .is_err()
                        {
                            break;
                        }
                    }
                    Err(err) => {
                        fail(err);
                        break;
                    }
                }
            }
        });

        let stream = ReceiverStream::new(rx);
        ProcessResult::success_with_source_error(
            "application/x-grib",
            Box::new(stream),
            source_error,
        )
    }
}

#[derive(Parser)]
struct Cli {
    #[arg(long, default_value = "http://127.0.0.1:9001")]
    broker_url: String,
    #[arg(long, default_value_t = polytope_worker_common::DEFAULT_POLL_TIMEOUT_MS)]
    poll_timeout_ms: u64,
    #[arg(long, default_value_t = 10.0)]
    heartbeat_secs: f64,
    #[arg(long, default_value = DEFAULT_CONFIG_PATH)]
    config_path: String,
    #[arg(long, default_value_t = 1)]
    worker_concurrency: usize,
}

fn resolved_worker_concurrency(cli_value: usize) -> usize {
    match std::env::var("POLYTOPE_WORKER_CONCURRENCY") {
        Ok(value) => match value.parse::<usize>() {
            Ok(parsed) if parsed >= 1 => parsed,
            _ => {
                warn!(value = %value, "ignoring invalid POLYTOPE_WORKER_CONCURRENCY");
                cli_value
            }
        },
        Err(std::env::VarError::NotPresent) => cli_value,
        Err(err) => {
            warn!(error = %err, "ignoring invalid POLYTOPE_WORKER_CONCURRENCY");
            cli_value
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    polytope_observability::init_tracing("polytope-worker-fdb");
    let cli = Cli::parse();
    let worker_concurrency = resolved_worker_concurrency(cli.worker_concurrency);
    info!(
        worker_concurrency,
        poll_timeout_ms = cli.poll_timeout_ms,
        "resolved worker settings"
    );
    let config = WorkerConfigFile::load(&cli.config_path).unwrap_or_else(|err| {
        tracing::error!("event.name" = "startup.config.failed", outcome = "error", config_path = %cli.config_path, error = %err, "failed to load config");
        std::process::exit(1);
    });
    tracing::info!("event.name" = "startup.config.loaded", outcome = "success", config_path = %cli.config_path, "config loaded");

    let fdb_section = config.section("fdb").expect("config missing 'fdb' section");
    let fdb_config =
        serde_yaml::to_string(fdb_section).expect("failed to serialize fdb config section");

    debug!(path = cli.config_path, "loaded fdb config section");

    run_worker_loop(
        WorkerConfig {
            broker_url: cli.broker_url,
            poll_timeout_ms: cli.poll_timeout_ms,
            heartbeat_interval: std::time::Duration::from_secs_f64(cli.heartbeat_secs),
            retry_backoff: std::time::Duration::from_secs(1),
            management_port: config.management_port,
            worker_concurrency,
        },
        config.delivery,
        FdbProcessor { fdb_config },
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::is_lost_fdb_connection;

    #[test]
    fn detects_lost_fdb_connection() {
        // Message as produced by FDB 5.25.3 after the store server restarted
        assert!(is_lost_fdb_connection(
            "Connection to fdbstore:30041 is no longer valid(RemoteException from fdbstore:30041)"
        ));
        assert!(!is_lost_fdb_connection("Exception: Unknown host fdbstore"));
    }

    #[test]
    fn missing_config_panics() {
        let result = std::panic::catch_unwind(|| {
            polytope_worker_common::config::WorkerConfigFile::load(
                "/definitely/missing/config.yaml",
            )
            .unwrap_or_else(|err| panic!("failed to load config: {err}"));
        });
        assert!(result.is_err());
    }
}
