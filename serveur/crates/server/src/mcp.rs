//! SDK MCP transport, with independent bearer verification on every HTTP request.
use crate::{
    identity::{IdentityClient, IdentityError, McpResource, VerifiedIdentity},
    runtime::VisionRuntime,
};
use axum::{
    Router,
    extract::{Request, State},
    http::{StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::any,
};
use mrjam_vision::{Catalogue, Justificatif, ServiceVision};
use rmcp::{
    RoleServer, ServerHandler,
    model::{
        CallToolRequestParams, CallToolResponse, CallToolResult, ContentBlock, ErrorData,
        Implementation, ListToolsResult, PaginatedRequestParams, ServerCapabilities, ServerConfig,
        Tool,
    },
    service::RequestContext,
    transport::streamable_http_server::{
        StreamableHttpServerConfig, StreamableHttpService, session::local::LocalSessionManager,
    },
};
use std::sync::Arc;
use tower::ServiceExt;

type ServiceFactory = Arc<dyn Fn(VerifiedIdentity) -> ServiceVision + Send + Sync>;

#[derive(Clone)]
struct McpVision {
    catalogue: Catalogue,
    service: ServiceFactory,
    tools: Vec<Tool>,
}

pub(crate) fn identity(
    context: &RequestContext<RoleServer>,
) -> Result<VerifiedIdentity, ErrorData> {
    context
        .extensions
        .get::<axum::http::request::Parts>()
        .and_then(|parts| parts.extensions.get::<VerifiedIdentity>())
        .cloned()
        .ok_or_else(|| ErrorData::invalid_request("AUTHENTICATION_REQUIRED", None))
}

impl ServerHandler for McpVision {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::new(
                "mrjam-vision",
                env!("CARGO_PKG_VERSION"),
            ))
            .with_instructions(include_str!(
                "../../../components/vision/docs/CONTRAT-SEANCE.md"
            ))
    }
    async fn list_tools(
        &self,
        request: Option<PaginatedRequestParams>,
        context: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, ErrorData> {
        identity(&context)?;
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
        let identity = identity(&context)?;
        if request.input_responses.is_some() || request.request_state.is_some() {
            return Err(ErrorData::invalid_params("REQUEST_STATE_UNSUPPORTED", None));
        }
        let arguments = serde_json::Value::Object(request.arguments.unwrap_or_default());
        let request = self
            .catalogue
            .valider(&request.name, &arguments)
            .map_err(|_| ErrorData::invalid_params("INVALID_TOOL_REQUEST", None))?;
        let credential = Justificatif::bearer("verified-mcp-request")
            .map_err(|_| ErrorData::internal_error("AUTHENTICATION_REQUIRED", None))?;
        let result = (self.service)(identity)
            .executer(Some(&credential), request)
            .await;
        let (value, is_error) = match result {
            Ok(value) => {
                let failure = mrjam_vision::statut_resultat(&value) >= 400;
                (value, failure)
            }
            Err(error) => (error.json(), true),
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

fn vision_routes(runtime: VisionRuntime, identity: IdentityClient) -> Result<Router, &'static str> {
    let catalogue = runtime.catalogue.clone();
    routes_with_service(
        catalogue,
        Arc::new(move |identity| runtime.service(identity)),
        identity,
    )
}

fn routes_with_service(
    catalogue: Catalogue,
    factory: ServiceFactory,
    identity: IdentityClient,
) -> Result<Router, &'static str> {
    let tools: Vec<Tool> =
        serde_json::from_value(serde_json::Value::Array(catalogue.outils().to_vec()))
            .map_err(|_| "INVALID_MCP_CATALOGUE")?;
    let server = McpVision {
        catalogue,
        service: factory,
        tools,
    };
    sdk_routes(server, identity, McpResource::Vision)
}

pub(crate) fn sdk_routes<H>(
    server: H,
    identity: IdentityClient,
    resource: McpResource,
) -> Result<Router, &'static str>
where
    H: ServerHandler + Clone + Send + Sync + 'static,
{
    let mut config = StreamableHttpServerConfig::default();
    config.legacy_session_mode = false;
    config.json_response = true;
    config.sse_keep_alive = None;
    config.max_request_body_bytes = 65_536;
    config.allowed_hosts = vec![resource.host().into()];
    config.allowed_origins = vec![format!("{}:443", resource.origin())];
    // Stateless requests preserve the legacy SDK negotiation; no session ID
    // ever substitutes for a fresh identity check or grants cross-user state.
    let service = StreamableHttpService::new(
        move || Ok(server.clone()),
        Arc::new(LocalSessionManager::default()),
        config,
    );
    Ok(Router::new()
        .route_service("/mcp", service)
        .layer(middleware::from_fn_with_state(
            (identity, resource),
            authenticate,
        )))
}

async fn authenticate(
    State((client, resource)): State<(IdentityClient, McpResource)>,
    mut request: Request,
    next: Next,
) -> Response {
    if crate::identity::unique_header(request.headers(), "host") != Some(resource.host()) {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    if request.headers().contains_key(header::ORIGIN)
        && crate::identity::unique_header(request.headers(), "origin") != Some(resource.origin())
    {
        return crate::error_response(StatusCode::FORBIDDEN, "ORIGIN_REFUSED");
    }
    if request.uri().query().is_some() {
        return crate::error_response(StatusCode::BAD_REQUEST, "QUERY_REFUSED");
    }
    let Some(token) = crate::identity::unique_header(request.headers(), "authorization")
        .and_then(|value| value.strip_prefix("Bearer "))
    else {
        return unauthenticated(resource);
    };
    let token = match Justificatif::bearer(token) {
        Ok(value) => value,
        Err(_) => return unauthenticated(resource),
    };
    let identity = match client.verify_mcp(resource, &token).await {
        Ok(value) => value,
        Err(IdentityError::Unavailable) => {
            return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "IDENTITY_UNAVAILABLE");
        }
        Err(IdentityError::Forbidden) => {
            return crate::error_response(StatusCode::FORBIDDEN, "FORBIDDEN");
        }
        Err(IdentityError::Unauthenticated) => return unauthenticated(resource),
    };
    if request.headers().contains_key("mcp-protocol-version")
        && !crate::identity::unique_header(request.headers(), "mcp-protocol-version").is_some_and(
            |value| {
                rmcp::model::ProtocolVersion::KNOWN_VERSIONS
                    .iter()
                    .any(|version| version.as_str() == value)
            },
        )
    {
        return crate::error_response(StatusCode::BAD_REQUEST, "INVALID_PROTOCOL_VERSION");
    }
    request.headers_mut().remove(header::AUTHORIZATION);
    request.headers_mut().remove(header::COOKIE);
    request.headers_mut().remove("x-mrj-user");
    request.headers_mut().remove("x-vision-authenticated");
    request.extensions_mut().insert(identity);
    if request.method() == axum::http::Method::POST {
        let (parts, body) = request.into_parts();
        let bytes = match axum::body::to_bytes(body, 65_536).await {
            Ok(bytes) => bytes,
            Err(_) => {
                return crate::error_response(StatusCode::PAYLOAD_TOO_LARGE, "REQUEST_TOO_LARGE");
            }
        };
        let parsed = match serde_json::from_slice::<crate::strict_json::SansDoublons>(&bytes) {
            Ok(value) => value.0,
            Err(_) => return (StatusCode::BAD_REQUEST, axum::Json(serde_json::json!({"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"INVALID_JSON"}}))).into_response(),
        };
        // A notification cannot hide a business write without a result. JSON-RPC
        // batches are unsupported, keeping one bounded authorization per call.
        if !parsed.is_object()
            || (parsed.get("method").and_then(serde_json::Value::as_str) == Some("tools/call")
                && parsed.get("id").is_none_or(serde_json::Value::is_null))
        {
            return (StatusCode::BAD_REQUEST, axum::Json(serde_json::json!({"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"REQUEST_ID_REQUIRED"}}))).into_response();
        }
        request = Request::from_parts(parts, axum::body::Body::from(bytes));
    }
    next.run(request).await
}

fn unauthenticated(resource: McpResource) -> Response {
    let mut response = crate::error_response(StatusCode::UNAUTHORIZED, "AUTHENTICATION_REQUIRED");
    response.headers_mut().insert(
        header::WWW_AUTHENTICATE,
        axum::http::HeaderValue::from_static(resource.challenge()),
    );
    response
}

#[derive(Clone)]
struct Multiplex {
    vision: Option<Router>,
    audition: Option<Router>,
}

pub(crate) fn routes(
    vision: Option<VisionRuntime>,
    audition: Option<mrjam_audition::service::PgAudition>,
    identity: Option<IdentityClient>,
) -> Result<Router, &'static str> {
    let mut multiplex = Multiplex {
        vision: None,
        audition: None,
    };
    if let Some(identity) = identity {
        multiplex.vision = vision
            .map(|vision| vision_routes(vision, identity.clone()))
            .transpose()?;
        multiplex.audition = audition
            .map(|audition| crate::mcp_audition::routes(audition, identity.clone()))
            .transpose()?;
    }
    Ok(Router::new()
        .route("/mcp", any(dispatch))
        .with_state(multiplex))
}

async fn dispatch(State(multiplex): State<Multiplex>, request: Request) -> Response {
    let service = match crate::identity::unique_header(request.headers(), "host") {
        Some("vision.mrj.am") => multiplex.vision,
        Some("audition.mrj.am") => multiplex.audition,
        _ => return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED"),
    };
    match service {
        Some(service) => match service.oneshot(request).await {
            Ok(response) => response,
            Err(never) => match never {},
        },
        None => crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "MCP_UNAVAILABLE"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::{Body, to_bytes},
        http::Request,
        routing::get,
    };
    use serde_json::{Value, json};
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use tower::ServiceExt;

    type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
    async fn request(
        router: &Router,
        body: &str,
        authenticated: bool,
    ) -> Result<(StatusCode, Value)> {
        let mut request = Request::builder()
            .method("POST")
            .uri("/mcp")
            .header("host", "vision.mrj.am")
            .header("content-type", "application/json")
            .header("accept", "application/json, text/event-stream")
            .header("mcp-protocol-version", "2025-11-25");
        if authenticated {
            request = request.header("authorization", "Bearer entirely-synthetic-mcp-token");
        }
        let response = router
            .clone()
            .oneshot(request.body(Body::from(body.to_owned()))?)
            .await?;
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 131_072).await?;
        let value = serde_json::from_slice(&bytes)?;
        Ok((status, value))
    }

    #[tokio::test]
    async fn mcp_negotiates_lists_calls_and_reauthenticates_every_request() -> Result<()> {
        let permitted = Arc::new(AtomicBool::new(true));
        let calls = Arc::new(AtomicUsize::new(0));
        let auth = Router::new().route(
            "/verify-mcp",
            get({
                let permitted = permitted.clone();
                let calls = calls.clone();
                move |headers: axum::http::HeaderMap| {
                    let permitted = permitted.clone();
                    let calls = calls.clone();
                    async move {
                        calls.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(headers["x-forwarded-host"], "vision.mrj.am");
                        assert_eq!(
                            headers["authorization"],
                            "Bearer entirely-synthetic-mcp-token"
                        );
                        let mut response = Response::builder();
                        if permitted.load(Ordering::SeqCst) {
                            response = response
                                .status(204)
                                .header("x-mrj-user", "synthetic_mcp_user");
                        } else {
                            response = response.status(401);
                        }
                        response.body(Body::empty()).unwrap_or_default()
                    }
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
        let identity = IdentityClient::new(&crate::runtime_config::IdentityConfiguration {
            endpoint: listener.local_addr()?,
            protocol: "mrj-auth-v1".into(),
        })?;
        let auth_task = tokio::spawn(async move {
            let _ = axum::serve(listener, auth).await;
        });
        let catalogue = Catalogue::officiel()?;
        let configuration = mrjam_vision::ConfigurationVision::nouvelle(
            Some("https://vision.mrj.am/mcp"),
            "/mcp",
            "/",
            Some("https://vision.mrj.am"),
        )?;
        let factory: ServiceFactory = Arc::new({
            let catalogue = catalogue.clone();
            move |identity| {
                ServiceVision::new(
                    catalogue.clone(),
                    Arc::new(crate::identity::RequestIdentity(identity)),
                    Arc::new(mrjam_vision::DepotIndisponible),
                    configuration.clone(),
                )
            }
        });
        let router = routes_with_service(catalogue, factory, identity)?;
        let initialize=json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"synthetic-client","version":"1"}}}).to_string();
        let (status, _) = request(&router, "not-json", false).await?;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        assert_eq!(calls.load(Ordering::SeqCst), 0);
        let (status, initialized) = request(&router, &initialize, true).await?;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(initialized["result"]["protocolVersion"], "2025-11-25");
        assert!(
            initialized["result"]["instructions"]
                .as_str()
                .is_some_and(|s| !s.is_empty())
        );
        let (status, listed) = request(
            &router,
            &json!({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}).to_string(),
            true,
        )
        .await?;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(listed["result"]["tools"].as_array().map(Vec::len), Some(21));
        let call=json!({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"tutoriel","arguments":{}}}).to_string();
        let (status, result) = request(&router, &call, true).await?;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(result["result"]["isError"], false);
        assert!(result["result"]["structuredContent"]["sections"].is_array());
        assert_eq!(calls.load(Ordering::SeqCst), 3);
        let (status, _) = request(&router, r#"{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"tutoriel","arguments":{},"arguments":{}}}"#, true).await?;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(calls.load(Ordering::SeqCst), 4);
        permitted.store(false, Ordering::SeqCst);
        let (status, _) = request(&router, "{SYNTHETIC_INVALID_JSON", true).await?;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        assert_eq!(calls.load(Ordering::SeqCst), 5);
        auth_task.abort();
        Ok(())
    }
}
