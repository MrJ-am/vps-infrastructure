//! Audition's MCP adapter preserves the same transactional service and imposes
//! the MCP channel. Public JSON never supplies identity, MFA, role or channel.
use crate::identity::{IdentityClient, McpResource, VerifiedIdentity};
use axum::Router;
use mrjam_audition::{
    Timestamp, WriteChannel,
    service::{PgAudition, ServiceError, VerifiedActor},
};
use rmcp::{
    RoleServer, ServerHandler,
    model::{
        CallToolRequestParams, CallToolResponse, CallToolResult, ContentBlock, ErrorData,
        Implementation, ListToolsResult, PaginatedRequestParams, ServerCapabilities, ServerConfig,
        Tool,
    },
    service::RequestContext,
};
use serde_json::{Value, json};
use std::{
    future::Future,
    pin::Pin,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

type Outcome = Pin<Box<dyn Future<Output = Result<Value, ServiceError>> + Send>>;
type Executor = Arc<dyn Fn(VerifiedIdentity, String, Vec<u8>) -> Outcome + Send + Sync>;

#[derive(Clone)]
struct McpAudition {
    tools: Vec<Tool>,
    execute: Executor,
}

impl ServerHandler for McpAudition {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
            .with_protocol_version(rmcp::model::ProtocolVersion::V_2025_06_18)
            .with_server_info(Implementation::new("audition", env!("CARGO_PKG_VERSION")))
            .with_instructions("Commencer par contexte, puis travaux avec un groupe renvoyé par le serveur. Lire le cadre, les consignes effectives, les versions et la politique avant de travailler. Laisser répondre l'élève ; distinguer production, aides et interprétation. Ne pas demander de conversation privée ni de raisonnement interne. Une proposition MCP reste non officielle jusqu'à son enregistrement par l'enseignant dans l'interface web. Ne jamais annoncer un enregistrement sans confirmation. Après conflit ou timeout, relire contexte/consulter_seance puis réutiliser exactement le même contenu et la même clé ; un timeout ne prouve pas l'absence d'écriture. Les opérations administratives requièrent l'interface web et une vérification renforcée récente. Guide canonique : https://audition.mrj.am/#aide.")
    }

    async fn list_tools(
        &self,
        request: Option<PaginatedRequestParams>,
        context: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, ErrorData> {
        crate::mcp::identity(&context)?;
        if request.is_some_and(|request| request.cursor.is_some()) {
            return Err(ErrorData::invalid_params("CURSOR_UNSUPPORTED", None));
        }
        Ok(ListToolsResult::with_all_items(self.tools.clone()))
    }

    async fn call_tool(
        &self,
        request: CallToolRequestParams,
        context: RequestContext<RoleServer>,
    ) -> Result<CallToolResponse, ErrorData> {
        let identity = crate::mcp::identity(&context)?;
        if request.input_responses.is_some() || request.request_state.is_some() {
            return Err(ErrorData::invalid_params("REQUEST_STATE_UNSUPPORTED", None));
        }
        if !self.tools.iter().any(|tool| tool.name == request.name) {
            return Err(ErrorData::invalid_params("INVALID_TOOL_REQUEST", None));
        }
        let result = if matches!(
            request.name.as_ref(),
            "creer_groupe" | "habiliter" | "membres" | "diagnostic" | "supprimer_groupe"
        ) {
            // The catalogue retains the historical administrative contracts;
            // bearer authorization is never represented as a fresh web MFA.
            Err(ServiceError::new("verification_renforcee_requise", 403))
        } else {
            let arguments = Value::Object(request.arguments.unwrap_or_default());
            let bytes = serde_json::to_vec(&arguments)
                .map_err(|_| ErrorData::invalid_params("INVALID_TOOL_REQUEST", None))?;
            (self.execute)(identity, request.name.into_owned(), bytes).await
        };
        let (value, is_error) = match result {
            Ok(value) => (value, false),
            Err(error) => (
                json!({"erreur":error.code(),"statut":error.status(),"details":null,"reprise":"Relire contexte/consulter_seance ; un timeout ne prouve pas l'absence d'écriture."}),
                true,
            ),
        };
        let content = vec![ContentBlock::text(value.to_string())];
        let mut response = if is_error {
            CallToolResult::error(content)
        } else {
            CallToolResult::success(content)
        };
        response.structured_content = Some(value);
        Ok(response.into())
    }
}

pub(crate) fn routes(
    service: PgAudition,
    identity: IdentityClient,
) -> Result<Router, &'static str> {
    let execute: Executor = Arc::new(move |identity, operation, bytes| {
        let service = service.clone();
        Box::pin(async move {
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .ok()
                .and_then(|time| i64::try_from(time.as_secs()).ok())
                .and_then(|time| Timestamp::new(time).ok())
                .ok_or(ServiceError::new("horloge_indisponible", 503))?;
            let actor = VerifiedActor::from_authenticated_identity(identity.owner(), None)?;
            service
                .execute(&actor, WriteChannel::Mcp, &operation, &bytes, now)
                .await
        })
    });
    routes_with_executor(execute, identity)
}

fn routes_with_executor(
    execute: Executor,
    identity: IdentityClient,
) -> Result<Router, &'static str> {
    let tools = serde_json::from_str(include_str!("../contracts/audition-catalogue.json"))
        .map_err(|_| "INVALID_AUDITION_MCP_CATALOGUE")?;
    crate::mcp::sdk_routes(
        McpAudition { tools, execute },
        identity,
        McpResource::Audition,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::{Body, to_bytes},
        http::{HeaderMap, Request, StatusCode},
        routing::get,
    };
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use tower::ServiceExt;

    type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

    async fn request(
        router: &Router,
        host: &str,
        token: &str,
        body: Value,
    ) -> Result<(StatusCode, Value)> {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/mcp")
                    .header("host", host)
                    .header("authorization", token)
                    .header("content-type", "application/json")
                    .header("accept", "application/json, text/event-stream")
                    .header("mcp-protocol-version", "2025-06-18")
                    .header("x-mrj-user", "forged.admin")
                    .header("x-mrj-mfa", "true")
                    .body(Body::from(body.to_string()))?,
            )
            .await?;
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 262_144).await?;
        Ok((status, serde_json::from_slice(&bytes)?))
    }

    #[tokio::test]
    async fn separate_audience_sdk_negotiation_catalogue_and_closed_notifications() -> Result<()> {
        let active = Arc::new(AtomicBool::new(true));
        let auth_calls = Arc::new(AtomicUsize::new(0));
        let service_calls = Arc::new(AtomicUsize::new(0));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
        let identity = IdentityClient::new(&crate::runtime_config::IdentityConfiguration {
            endpoint: listener.local_addr()?,
            protocol: "mrj-auth-v1".into(),
        })?;
        let broker = Router::new().route(
            "/verify-mcp",
            get({
                let active = active.clone();
                let calls = auth_calls.clone();
                move |headers: HeaderMap| {
                    let active = active.clone();
                    let calls = calls.clone();
                    async move {
                        calls.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(headers["x-forwarded-host"], "audition.mrj.am");
                        assert!(!headers.contains_key("x-mrj-user"));
                        assert!(!headers.contains_key("x-mrj-mfa"));
                        if headers["authorization"] == "Bearer invented-audition-grant"
                            && active.load(Ordering::SeqCst)
                        {
                            (StatusCode::NO_CONTENT, [("x-mrj-user", "invented.teacher")])
                        } else {
                            (StatusCode::UNAUTHORIZED, [("cache-control", "no-store")])
                        }
                    }
                }
            }),
        );
        let task = tokio::spawn(async move {
            let _ = axum::serve(listener, broker).await;
        });
        let execute: Executor = Arc::new({
            let calls = service_calls.clone();
            move |identity, operation, _| {
                calls.fetch_add(1, Ordering::SeqCst);
                assert_eq!(identity.owner(), "invented.teacher");
                assert!(!identity.elevated());
                Box::pin(async move {
                    if operation == "contexte" {
                        Ok(json!({"elements":[],"total":0,"suivant":null}))
                    } else {
                        Err(ServiceError::new("conflit_revision", 409))
                    }
                })
            }
        });
        let router = routes_with_executor(execute, identity)?;
        let initialize = json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"synthetic","version":"1"}}});
        let (status, _) = request(
            &router,
            "vision.mrj.am",
            "Bearer invented-audition-grant",
            initialize.clone(),
        )
        .await?;
        assert_eq!(status, StatusCode::MISDIRECTED_REQUEST);
        assert_eq!(auth_calls.load(Ordering::SeqCst), 0);
        let (status, _) = request(
            &router,
            "audition.mrj.am",
            "Bearer invented-vision-grant",
            initialize.clone(),
        )
        .await?;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        let (status, value) = request(
            &router,
            "audition.mrj.am",
            "Bearer invented-audition-grant",
            initialize,
        )
        .await?;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["result"]["protocolVersion"], "2025-06-18");
        assert!(
            value["result"]["instructions"]
                .as_str()
                .is_some_and(|s| s.contains("proposition MCP"))
        );
        let (status, listed) = request(
            &router,
            "audition.mrj.am",
            "Bearer invented-audition-grant",
            json!({"jsonrpc":"2.0","id":2,"method":"tools/list"}),
        )
        .await?;
        assert_eq!(status, StatusCode::OK);
        let tools = listed["result"]["tools"]
            .as_array()
            .ok_or("catalogue missing")?;
        assert_eq!(tools.len(), 20);
        assert!(
            tools
                .iter()
                .all(|tool| tool["inputSchema"]["additionalProperties"] == false)
        );
        for operation in [
            "diagnostic",
            "creer_groupe",
            "habiliter",
            "membres",
            "supprimer_groupe",
        ] {
            let (_, result) = request(&router,"audition.mrj.am","Bearer invented-audition-grant",json!({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":operation,"arguments":{}}})).await?;
            assert_eq!(result["result"]["isError"], true);
            assert_eq!(result["result"]["structuredContent"]["statut"], 403);
            assert_eq!(
                result["result"]["structuredContent"]["erreur"],
                "verification_renforcee_requise"
            );
        }
        assert_eq!(service_calls.load(Ordering::SeqCst), 0);
        let notification = json!({"jsonrpc":"2.0","method":"tools/call","params":{"name":"activite","arguments":{}}});
        let (status, _) = request(
            &router,
            "audition.mrj.am",
            "Bearer invented-audition-grant",
            notification,
        )
        .await?;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(service_calls.load(Ordering::SeqCst), 0);
        for (operation, is_error) in [("contexte", false), ("activite", true)] {
            let (status,result) = request(&router,"audition.mrj.am","Bearer invented-audition-grant",json!({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":operation,"arguments":{}}})).await?;
            assert_eq!(status, StatusCode::OK);
            assert_eq!(result["result"]["isError"], is_error);
            if is_error {
                assert_eq!(result["result"]["structuredContent"]["statut"], 409);
                assert!(result["result"]["structuredContent"]["details"].is_null());
                assert!(
                    result["result"]["structuredContent"]["reprise"]
                        .as_str()
                        .is_some_and(|s| s.contains("timeout"))
                );
            }
        }
        assert_eq!(service_calls.load(Ordering::SeqCst), 2);
        let calls = auth_calls.load(Ordering::SeqCst);
        active.store(false, Ordering::SeqCst);
        let (status, _) = request(
            &router,
            "audition.mrj.am",
            "Bearer invented-audition-grant",
            json!({"jsonrpc":"2.0","id":5,"method":"tools/list"}),
        )
        .await?;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        assert_eq!(auth_calls.load(Ordering::SeqCst), calls + 1);
        assert_eq!(service_calls.load(Ordering::SeqCst), 2);
        task.abort();
        Ok(())
    }
}
