use axum::{Router, routing::get};
use std::{sync::Arc, time::Duration};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::{Notify, oneshot},
};

#[tokio::test]
async fn an_in_flight_response_finishes_before_shutdown() -> Result<(), Box<dyn std::error::Error>>
{
    let started = Arc::new(Notify::new());
    let finish = Arc::new(Notify::new());
    let entered = Arc::clone(&started);
    let release = Arc::clone(&finish);
    let router = Router::new().route(
        "/synthetic-long-request",
        get(move || {
            let entered = Arc::clone(&entered);
            let release = Arc::clone(&release);
            async move {
                entered.notify_one();
                release.notified().await;
                "synthetic-response-complete"
            }
        }),
    );
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown, receive_shutdown) = oneshot::channel();
    let task = tokio::spawn(mrjam_server::serve(listener, router, async {
        let _ = receive_shutdown.await;
    }));
    let mut stream = TcpStream::connect(address).await?;
    stream
        .write_all(
            b"GET /synthetic-long-request HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
        )
        .await?;
    tokio::time::timeout(Duration::from_secs(3), started.notified()).await?;
    shutdown.send(()).map_err(|_| "shutdown receiver missing")?;
    tokio::task::yield_now().await;
    assert!(
        !task.is_finished(),
        "the in-flight response must not be discarded"
    );
    finish.notify_one();
    let mut response = Vec::new();
    tokio::time::timeout(Duration::from_secs(3), stream.read_to_end(&mut response)).await??;
    tokio::time::timeout(Duration::from_secs(3), task).await???;
    assert!(response.starts_with(b"HTTP/1.1 200"));
    assert!(response.ends_with(b"synthetic-response-complete"));
    Ok(())
}
