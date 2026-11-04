mod config;
mod crypto;
mod error;
mod http;
mod json;
mod oauth;
mod oidc;
mod projection;
mod registration;
mod state;
#[cfg(test)]
mod tests;

use error::{Error, Result};
use std::{path::Path, sync::Arc};

async fn stop() {
    match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
        Ok(mut terminate) => {
            tokio::select! {_=terminate.recv()=>{},_=tokio::signal::ctrl_c()=>{}}
        }
        Err(_) => {
            let _ = tokio::signal::ctrl_c().await;
        }
    }
}
async fn run() -> Result<()> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    match args.as_slice() {
        [command, option, path] if command == "serve" && option == "--config" => {
            let config = config::Configuration::load(Path::new(path))?;
            let broker = Arc::new(state::Broker::connect(&config).await?);
            let listener = tokio::net::TcpListener::bind(config.listen)
                .await
                .map_err(|_| Error(503))?;
            let socket = match &config.principal_registration {
                Some(configuration) => Some(registration::Socket::bind(configuration).await?),
                None => None,
            };
            let server = async {
                axum::serve(listener, http::router(Arc::clone(&broker)))
                    .with_graceful_shutdown(stop())
                    .await
                    .map_err(|_| Error(503))
            };
            match socket {
                Some(socket) => {
                    tokio::select! {result=server=>result,result=socket.serve(Arc::clone(&broker))=>result}
                }
                None => server.await,
            }
        }
        [
            command,
            source_option,
            source,
            destination_option,
            destination,
        ] if command == "project-aliases"
            && source_option == "--source"
            && destination_option == "--destination" =>
        {
            projection::project(Path::new(source), Path::new(destination)).await
        }
        _ => Err(Error(400)),
    }
}
#[tokio::main]
async fn main() -> std::process::ExitCode {
    match run().await {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::FAILURE
        }
    }
}
