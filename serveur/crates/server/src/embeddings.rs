//! Legacy local embedding protocol, exact model and dimensions selected by config.
use crate::runtime_config::EmbeddingConfiguration;
use axum::{
    body::Bytes,
    http::{Request, StatusCode, header},
};
use http_body_util::{BodyExt, Full, Limited};
use hyper_util::rt::TokioIo;
use mrjam_vision::{Embedding, ErreurVision, FournirEmbedding, FuturVision};
use serde::Deserialize;
use std::{sync::Arc, time::Duration};
use tokio::{net::TcpStream, sync::Semaphore};

#[derive(Clone)]
pub struct EmbeddingClient {
    config: EmbeddingConfiguration,
    active: Arc<Semaphore>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply {
    embedding: Vec<f64>,
    modele: String,
}

impl EmbeddingClient {
    pub fn new(config: EmbeddingConfiguration) -> Self {
        Self {
            config,
            active: Arc::new(Semaphore::new(2)),
        }
    }
    async fn calculate(&self, content: &str) -> Result<Embedding, ErreurVision> {
        if content.is_empty() || content.len() > 65_536 {
            return Err(ErreurVision::ParametresInvalides);
        }
        let _permit = self
            .active
            .try_acquire()
            .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
        let body = serde_json::to_vec(&serde_json::json!({"contenu":content}))
            .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
        let request = Request::builder()
            .method("POST")
            .uri("/embedding")
            .header(header::HOST, "mrjam-embeddings.internal")
            .header(header::CONTENT_TYPE, "application/json")
            .body(Full::new(Bytes::from(body)))
            .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
        tokio::time::timeout(Duration::from_secs(8), async {
            let stream = TcpStream::connect(self.config.endpoint)
                .await
                .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
            let (mut sender, connection) = hyper::client::conn::http1::Builder::new()
                .max_headers(32)
                .max_buf_size(32_768)
                .handshake(TokioIo::new(stream))
                .await
                .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
            struct Abort(tokio::task::JoinHandle<()>);
            impl Drop for Abort {
                fn drop(&mut self) {
                    self.0.abort();
                }
            }
            let _guard = Abort(tokio::spawn(async move {
                let _ = connection.await;
            }));
            let response = sender
                .send_request(request)
                .await
                .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
            if response.status() != StatusCode::OK
                || response.headers().contains_key(header::LOCATION)
                || !crate::identity::unique_header(response.headers(), "content-type").is_some_and(
                    |v| {
                        v.split(';')
                            .next()
                            .is_some_and(|m| m.trim().eq_ignore_ascii_case("application/json"))
                    },
                )
            {
                return Err(ErreurVision::ServiceEmbeddingsIndisponible);
            }
            let bytes = Limited::new(response.into_body(), 131_072)
                .collect()
                .await
                .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?
                .to_bytes();
            let unique: crate::strict_json::SansDoublons = serde_json::from_slice(&bytes)
                .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
            let reply: Reply = serde_json::from_value(unique.0)
                .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?;
            if reply.modele != self.config.model || reply.embedding.len() != self.config.dimensions
            {
                return Err(ErreurVision::ServiceEmbeddingsIndisponible);
            }
            Embedding::valider(reply.embedding, reply.modele)
        })
        .await
        .map_err(|_| ErreurVision::ServiceEmbeddingsIndisponible)?
    }
    pub async fn ready(&self) -> Result<(), ErreurVision> {
        self.calculate("MRJAM_DEPENDENCY_CHECK_SYNTHETIC_TEXT")
            .await
            .map(|_| ())
    }
}
impl FournirEmbedding for EmbeddingClient {
    fn calculer<'a>(&'a self, content: &'a str) -> FuturVision<'a, Embedding> {
        Box::pin(self.calculate(content))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        Router,
        body::{Body, to_bytes},
        routing::post,
    };
    use std::sync::atomic::{AtomicUsize, Ordering};
    use tokio::net::TcpListener;

    #[tokio::test]
    async fn embedding_protocol_checks_exact_model_dimensions_and_closed_reply()
    -> Result<(), Box<dyn std::error::Error>> {
        for (reply, success) in [
            (r#"{"embedding":[0.2,-0.1],"modele":"synthetic-v1"}"#, true),
            (
                r#"{"embedding":[0.2,-0.1],"modele":"unreviewed-v2"}"#,
                false,
            ),
            (r#"{"embedding":[0.2],"modele":"synthetic-v1"}"#, false),
            (r#"{"embedding":[0,0],"modele":"synthetic-v1"}"#, false),
            (
                r#"{"embedding":[0.2,-0.1],"modele":"synthetic-v1","secret":"invented"}"#,
                false,
            ),
            (
                r#"{"embedding":[0.2,-0.1],"modele":"synthetic-v1","modele":"synthetic-v1"}"#,
                false,
            ),
        ] {
            let calls = Arc::new(AtomicUsize::new(0));
            let app = Router::new().route("/embedding", post({
                let calls = calls.clone();
                move |request: axum::extract::Request| {
                    let calls = calls.clone();
                    async move {
                        calls.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(request.headers()["host"], "mrjam-embeddings.internal");
                        let bytes = to_bytes(request.into_body(), 4096).await.unwrap_or_default();
                        let value: serde_json::Value = serde_json::from_slice(&bytes).unwrap_or_default();
                        assert_eq!(value, serde_json::json!({"contenu":"MRJAM_DEPENDENCY_CHECK_SYNTHETIC_TEXT"}));
                        ([(header::CONTENT_TYPE,"application/json")], Body::from(reply))
                    }
                }
            }));
            let listener = TcpListener::bind("127.0.0.1:0").await?;
            let client = EmbeddingClient::new(EmbeddingConfiguration {
                endpoint: listener.local_addr()?,
                model: "synthetic-v1".into(),
                dimensions: 2,
            });
            let task = tokio::spawn(async move {
                let _ = axum::serve(listener, app).await;
            });
            assert_eq!(client.ready().await.is_ok(), success);
            assert_eq!(calls.load(Ordering::SeqCst), 1);
            task.abort();
        }
        Ok(())
    }
}
