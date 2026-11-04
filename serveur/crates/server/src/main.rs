use mrjam_server::{application, config::Configuration, serve, vision_catalogue};
use std::{
    env,
    io::{self, Write},
    path::Path,
    process::ExitCode,
};
use tokio::{
    net::TcpListener,
    signal::unix::{SignalKind, signal},
};

fn report(code: &'static str) {
    // Le diagnostic ne réémet ni argument ni variable ni erreur du système.
    let text = format!("{{\"code\":\"{code}\"}}\n");
    let _ = io::stderr().lock().write_all(text.as_bytes());
}

async fn run_server(runtime_config: Option<&Path>) -> Result<(), &'static str> {
    let configuration = Configuration::from_environment().map_err(|error| error.code())?;
    let router = match runtime_config {
        Some(path) => mrjam_server::runtime::load(path).await?,
        None => application(),
    };
    let mut term = signal(SignalKind::terminate()).map_err(|_| "SIGNAL_UNAVAILABLE")?;
    let mut interrupt = signal(SignalKind::interrupt()).map_err(|_| "SIGNAL_UNAVAILABLE")?;
    let listener = TcpListener::bind(configuration.listen)
        .await
        .map_err(|_| "LISTEN_FAILED")?;
    tracing::info!(event = "server_started");
    serve(listener, router, async move {
        tokio::select! {
            _ = term.recv() => {},
            _ = interrupt.recv() => {},
        }
    })
    .await
    .map_err(|_| "SERVE_FAILED")?;
    tracing::info!(event = "server_stopped");
    Ok(())
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> ExitCode {
    let arguments: Vec<_> = env::args_os().skip(1).collect();
    if arguments.len() == 2 && arguments[0] == "check-config" {
        let result =
            mrjam_server::runtime_files::read_regular(Path::new(&arguments[1]), 65_536, false)
                .and_then(|bytes| {
                    mrjam_server::runtime_config::RuntimeConfiguration::from_bytes(&bytes)
                });
        return match result {
            Ok(_) => {
                if io::stdout()
                    .lock()
                    .write_all(b"{\"code\":\"CONFIGURATION_VALID\"}\n")
                    .is_ok()
                {
                    ExitCode::SUCCESS
                } else {
                    ExitCode::from(2)
                }
            }
            Err(code) => {
                report(code);
                ExitCode::from(2)
            }
        };
    }
    if arguments.len() == 2 && arguments[0] == "catalogue" && arguments[1] == "vision" {
        let value = match vision_catalogue() {
            Ok(value) => value,
            Err(code) => {
                report(code);
                return ExitCode::from(2);
            }
        };
        let mut output = io::stdout().lock();
        if serde_json::to_writer(&mut output, &value).is_err() || output.write_all(b"\n").is_err() {
            return ExitCode::from(2);
        }
        return ExitCode::SUCCESS;
    }
    let runtime_config =
        if arguments.len() == 3 && arguments[0] == "serve" && arguments[1] == "--config" {
            Some(Path::new(&arguments[2]))
        } else if arguments.len() == 1 && arguments[0] == "serve" {
            None
        } else {
            report("INVALID_INVOCATION");
            return ExitCode::from(2);
        };
    match run_server(runtime_config).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(code) => {
            report(code);
            ExitCode::from(2)
        }
    }
}
