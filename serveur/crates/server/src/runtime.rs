//! Runtime assembly; startup opens only declared local dependencies and never migrates.
use crate::{
    database,
    identity::{IdentityClient, IdentityError, RequestIdentity},
    runtime_config::RuntimeConfiguration,
    static_assets::StaticAssets,
};
use axum::{
    Json, Router,
    body::to_bytes,
    extract::{Request, State},
    http::StatusCode,
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{any, get, post},
};
use mrjam_vision::{
    Catalogue, ConfigurationVision, ErreurVision, Justificatif, PgVision, ServiceVision,
};
use sqlx::PgPool;
use std::{
    path::Path,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Clone)]
pub(crate) struct VisionRuntime {
    pool: PgPool,
    depot: PgVision,
    configuration: ConfigurationVision,
    pub(crate) catalogue: Catalogue,
    embeddings: Option<Arc<crate::embeddings::EmbeddingClient>>,
    journal: Option<Arc<mrjam_vision::PgJournalEffacement>>,
    journal_pool: Option<PgPool>,
    administration: Option<mrjam_vision::PgGestionVision>,
    administration_pool: Option<PgPool>,
}

impl VisionRuntime {
    pub(crate) fn service(&self, identity: crate::identity::VerifiedIdentity) -> ServiceVision {
        let mut service = ServiceVision::new(
            self.catalogue.clone(),
            Arc::new(RequestIdentity(identity)),
            Arc::new(self.depot.clone()),
            self.configuration.clone(),
        );
        if let Some(embeddings) = &self.embeddings {
            service = service.avec_embeddings(embeddings.clone());
        }
        if let Some(journal) = &self.journal {
            service = service.avec_journal_effacement(journal.clone());
        }
        service
    }
}

#[derive(Clone)]
struct RuntimeState {
    configuration: Arc<RuntimeConfiguration>,
    assets: Vec<StaticAssets>,
    identity: Option<IdentityClient>,
    mateval_pool: Option<PgPool>,
    mateval_bank: Option<Arc<serde_json::Value>>,
    mateval_admin: Option<Arc<mrjam_mateval::AdminService>>,
    vision: Option<VisionRuntime>,
    audition: Option<mrjam_audition::service::PgAudition>,
    admission_approval: Option<crate::vision_admission::ApprovalClient>,
    log: Option<LogRuntime>,
}

#[derive(Clone)]
struct LogRuntime {
    service: mrjam_log::LogService,
    native: Arc<mrjam_log::KanidmClient>,
    aliases: Arc<mrjam_log::SqliteLoginAliases>,
}

pub async fn load(path: &Path) -> Result<Router, &'static str> {
    let bytes = crate::runtime_files::read_regular(path, 65_536, false)?;
    let configuration = RuntimeConfiguration::from_bytes(&bytes)?;
    assemble(configuration).await
}

pub async fn assemble(configuration: RuntimeConfiguration) -> Result<Router, &'static str> {
    configuration.validate()?;
    let mut assets = Vec::new();
    let mut total = 0usize;
    for config in &configuration.assets {
        let site = StaticAssets::load(config)?;
        total = total
            .checked_add(site.bytes())
            .ok_or("ASSET_BUDGET_EXCEEDED")?;
        if total > 64 * 1024 * 1024 {
            return Err("ASSET_BUDGET_EXCEEDED");
        }
        assets.push(site);
    }
    for capability in &configuration.required_capabilities {
        let required: Option<(&str, &str, &[&str])> = match capability.as_str() {
            "mateval-collection" => Some((
                "principiipetit.io",
                "/matheval/",
                &["index.html", "survey.js", "enquete.js", "data/bank.json"],
            )),
            "mateval-administration" => Some((
                "principiipetit.io",
                "/matheval/",
                &[
                    "admin/index.html",
                    "admin/administration.js",
                    "admin/admin.js",
                ],
            )),
            "vision-http" | "vision-administration" => {
                Some(("vision.mrj.am", "/", &["index.html", "app.js", "app.css"]))
            }
            "audition-http" => Some((
                "audition.mrj.am",
                "/",
                &[
                    "index.html",
                    "elm.js",
                    "pont.js",
                    "assets/mrjam/signature.css",
                    "assets/mrjam/ecriture.css",
                    "assets/mrjam/mathematiques.js",
                    "assets/mrjam/animations.js",
                    "vendor/katex/katex.min.css",
                    "vendor/katex/katex.min.js",
                ],
            )),
            "log-presentation" => Some((
                "log.mrj.am",
                "/",
                &[
                    "index.html",
                    "elm.js",
                    "pont.js",
                    "assets/mrjam/signature.css",
                    "assets/mrjam/animations.js",
                ],
            )),
            _ => None,
        };
        if required.is_some_and(|(host, mount, names)| {
            !assets
                .iter()
                .any(|asset| asset.includes(host, mount, names))
        }) {
            return Err("REQUIRED_ASSET_ENTRYPOINT_MISSING");
        }
    }
    let mateval_bank = if configuration
        .required_capabilities
        .iter()
        .any(|cap| cap == "mateval-collection")
    {
        let bytes = assets
            .iter()
            .find_map(|site| site.file("principiipetit.io", "/matheval/", "data/bank.json"))
            .ok_or("PUBLIC_CORPUS_MISSING")?;
        if bytes.len() > 2 * 1024 * 1024 {
            return Err("PUBLIC_CORPUS_TOO_LARGE");
        }
        let bank: crate::strict_json::SansDoublons =
            serde_json::from_slice(bytes).map_err(|_| "INVALID_PUBLIC_CORPUS")?;
        if !bank
            .0
            .get("version")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|version| !version.is_empty() && version.len() <= 64)
        {
            return Err("INVALID_PUBLIC_CORPUS");
        }
        Some(Arc::new(bank.0))
    } else {
        None
    };
    let identity = configuration
        .identity
        .as_ref()
        .map(IdentityClient::new)
        .transpose()?;
    let mut state = RuntimeState {
        configuration: Arc::new(configuration),
        assets,
        identity,
        mateval_pool: None,
        mateval_bank,
        mateval_admin: None,
        vision: None,
        audition: None,
        admission_approval: None,
        log: None,
    };
    let mut mateval_state = crate::mateval::MatevalState::default();
    if let Some(config) = &state.configuration.mateval {
        let pool = database::connect(&config.database).await?;
        database::mateval_ready(
            &pool,
            &config.database.schema,
            state.mateval_bank.as_deref(),
        )
        .await?;
        mateval_state =
            crate::mateval::MatevalState::with_service(mrjam_mateval::Service::new(pool.clone()));
        state.mateval_pool = Some(pool);
        if let Some(admin) = &config.administration_database {
            let pool = database::connect(admin).await?;
            let activation = config
                .activation_sha256_file
                .as_ref()
                .map(|path| crate::runtime_files::credential(path))
                .transpose()?;
            let service = mrjam_mateval::AdminService::new(pool, activation)
                .map_err(|_| "INVALID_ADMINISTRATION_CONFIGURATION")?;
            service
                .health()
                .await
                .map_err(|_| "MATEVAL_ADMINISTRATION_UNAVAILABLE")?;
            state.mateval_admin = Some(Arc::new(service));
        }
    }
    if let Some(config) = &state.configuration.vision {
        state.admission_approval = config
            .admission_approval_credential_file
            .as_ref()
            .map(|path| crate::vision_admission::ApprovalClient::load(path))
            .transpose()?;
        let pool = database::connect(&config.database).await?;
        let depot = PgVision::verifier_metier(pool.clone())
            .await
            .map_err(|_| "VISION_DATABASE_UNAVAILABLE")?;
        let journal_pool = match &config.deletion_journal {
            Some(config) => Some(database::connect(config).await?),
            None => None,
        };
        let journal = match &journal_pool {
            Some(pool) => Some(Arc::new(
                mrjam_vision::PgJournalEffacement::verifier(pool.clone())
                    .await
                    .map_err(|_| "DELETION_JOURNAL_UNAVAILABLE")?,
            )),
            None => None,
        };
        let administration_pool = match &config.administration_database {
            Some(config) => Some(database::connect(config).await?),
            None => None,
        };
        let administration = match &administration_pool {
            Some(pool) => Some(
                mrjam_vision::PgGestionVision::verifier(pool.clone())
                    .await
                    .map_err(|_| "VISION_ADMINISTRATION_UNAVAILABLE")?,
            ),
            None => None,
        };
        state.vision = Some(VisionRuntime {
            pool,
            depot,
            configuration: ConfigurationVision::nouvelle(
                Some(&config.public_mcp_url),
                "/mcp",
                "/",
                Some(&config.public_web_url),
            )
            .map_err(|_| "INVALID_VISION_CONFIGURATION")?,
            catalogue: Catalogue::officiel().map_err(|_| "INVALID_VISION_CATALOGUE")?,
            embeddings: config
                .embeddings
                .clone()
                .map(|config| Arc::new(crate::embeddings::EmbeddingClient::new(config))),
            journal,
            journal_pool,
            administration,
            administration_pool,
        });
    }
    if let Some(config) = &state.configuration.audition {
        let service = mrjam_audition::service::PgAudition::new(database::connect(config).await?);
        service
            .ready()
            .await
            .map_err(|_| "AUDITION_DATABASE_UNAVAILABLE")?;
        state.audition = Some(service);
    }
    if let Some(config) = &state.configuration.log {
        let ca = crate::runtime_files::read_regular(&config.ca_file, 65_536, false)?;
        if crate::runtime_files::digest(&ca) != config.ca_sha256 {
            return Err("LOG_CA_MISMATCH");
        }
        let native = Arc::new(
            mrjam_log::KanidmClient::from_ca_pem(config.endpoint, &ca)
                .map_err(|_| "INVALID_LOG_TLS_CONFIGURATION")?,
        );
        let aliases = Arc::new(
            mrjam_log::SqliteLoginAliases::open_read_only(&config.aliases_database_file)
                .await
                .map_err(|_| "LOG_ALIASES_UNAVAILABLE")?,
        );
        state.log = Some(LogRuntime {
            service: mrjam_log::LogService::new(native.clone(), aliases.clone()),
            native,
            aliases,
        });
    }
    let mateval = match &state.mateval_admin {
        Some(admin) => crate::mateval::collection_routes(mateval_state)
            .merge(crate::mateval_admin::routes(admin.clone())),
        None => crate::mateval::routes(mateval_state),
    };
    let mcp = crate::mcp::routes(
        state.vision.clone(),
        state.audition.clone(),
        state.identity.clone(),
    )?;
    let approval =
        crate::vision_admission::routes(state.identity.clone(), state.admission_approval.clone());
    let router = Router::new()
        .route("/healthz", get(crate::health))
        .route("/readyz", get(ready))
        .route("/api/web/{operation}", post(vision_web))
        .route("/api/v1/{operation}", post(vision_rest))
        .route("/api/gestion/{operation}", post(vision_management))
        .route("/api/audition/{operation}", post(audition))
        .route("/presentation/api", post(log_presentation))
        .route("/api", any(crate::unauthenticated))
        .route("/api/{*path}", any(crate::unauthenticated))
        .fallback(asset)
        .with_state(state.clone())
        .merge(mateval)
        .merge(mcp)
        .merge(approval)
        .method_not_allowed_fallback(crate::method_not_allowed)
        .layer(middleware::from_fn_with_state(state, host_policy));
    Ok(crate::transport_policy(router))
}

fn request_host(request: &Request) -> Option<&str> {
    crate::identity::unique_header(request.headers(), "host")
}

async fn host_policy(State(state): State<RuntimeState>, request: Request, next: Next) -> Response {
    if matches!(request.uri().path(), "/healthz" | "/readyz") {
        return next.run(request).await;
    }
    if !request_host(&request).is_some_and(|host| {
        state
            .configuration
            .public_hosts
            .iter()
            .any(|expected| expected == host)
    }) {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    if request.uri().path().starts_with("/matheval/api")
        && request_host(&request) != Some("principiipetit.io")
    {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    next.run(request).await
}

/// Readiness covers only the capabilities required by this runtime configuration.
/// Deployment also verifies the running artifact and the inactive slot before routing traffic.
/// A readiness response alone does not authorize deployment.
async fn ready(State(state): State<RuntimeState>) -> Response {
    let result = async {
        if let (Some(pool), Some(config)) = (&state.mateval_pool, &state.configuration.mateval) {
            database::mateval_ready(pool, &config.database.schema, state.mateval_bank.as_deref())
                .await?;
        }
        if let Some(admin) = &state.mateval_admin {
            admin
                .health()
                .await
                .map_err(|_| "MATEVAL_ADMINISTRATION_UNAVAILABLE")?;
        }
        if let Some(vision) = &state.vision {
            if let Some(approval) = &state.admission_approval {
                approval.ready().await?;
            }
            PgVision::verifier_metier(vision.pool.clone())
                .await
                .map_err(|_| "VISION_DATABASE_UNAVAILABLE")?;
            if let Some(pool) = &vision.journal_pool {
                mrjam_vision::PgJournalEffacement::verifier(pool.clone())
                    .await
                    .map_err(|_| "DELETION_JOURNAL_UNAVAILABLE")?;
            }
            if let Some(pool) = &vision.administration_pool {
                mrjam_vision::PgGestionVision::verifier(pool.clone())
                    .await
                    .map_err(|_| "VISION_ADMINISTRATION_UNAVAILABLE")?;
            }
            if let Some(embeddings) = &vision.embeddings {
                embeddings
                    .ready()
                    .await
                    .map_err(|_| "EMBEDDINGS_UNAVAILABLE")?;
            }
            state
                .identity
                .as_ref()
                .ok_or("IDENTITY_UNAVAILABLE")?
                .negative_probe("vision.mrj.am")
                .await
                .map_err(|_| "IDENTITY_UNAVAILABLE")?;
            let identity = state.identity.as_ref().ok_or("IDENTITY_UNAVAILABLE")?;
            identity
                .negative_probe_mcp(crate::identity::McpResource::Vision)
                .await
                .map_err(|_| "IDENTITY_UNAVAILABLE")?;
            if vision.administration.is_some() {
                identity
                    .negative_probe_management("vision.mrj.am")
                    .await
                    .map_err(|_| "IDENTITY_UNAVAILABLE")?;
            }
        }
        if let Some(audition) = &state.audition {
            audition
                .ready()
                .await
                .map_err(|_| "AUDITION_DATABASE_UNAVAILABLE")?;
            state
                .identity
                .as_ref()
                .ok_or("IDENTITY_UNAVAILABLE")?
                .negative_probe("audition.mrj.am")
                .await
                .map_err(|_| "IDENTITY_UNAVAILABLE")?;
            state
                .identity
                .as_ref()
                .ok_or("IDENTITY_UNAVAILABLE")?
                .negative_probe_mcp(crate::identity::McpResource::Audition)
                .await
                .map_err(|_| "IDENTITY_UNAVAILABLE")?;
            state
                .identity
                .as_ref()
                .ok_or("IDENTITY_UNAVAILABLE")?
                .negative_probe_management("audition.mrj.am")
                .await
                .map_err(|_| "IDENTITY_UNAVAILABLE")?;
        }
        if let Some(log) = &state.log {
            log.native
                .ready()
                .await
                .map_err(|_| "LOG_TLS_UNAVAILABLE")?;
            log.aliases
                .ready()
                .await
                .map_err(|_| "LOG_ALIASES_UNAVAILABLE")?;
        }
        Ok::<_, &'static str>(())
    }
    .await;
    if let Err(code) = result {
        // Only the static dependency code is logged; never a backend error,
        // credential, SQL value, identity, or response body.
        eprintln!("MRJAM_READINESS_UNAVAILABLE:{code}");
        return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "NOT_READY");
    }
    Json(serde_json::json!({"status":"ready","scope":"configured-capabilities-only","capabilities":state.configuration.required_capabilities})).into_response()
}

async fn asset(State(state): State<RuntimeState>, request: Request) -> Response {
    let Some(host) = request_host(&request) else {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    };
    for asset in &state.assets {
        if let Some(response) = asset.response(host, &request) {
            return response;
        }
    }
    crate::error_response(StatusCode::NOT_FOUND, "NOT_FOUND")
}

fn auth_error(error: IdentityError) -> Response {
    match error {
        IdentityError::Unauthenticated => {
            crate::error_response(StatusCode::UNAUTHORIZED, "UNAUTHENTICATED")
        }
        IdentityError::Forbidden => crate::error_response(StatusCode::FORBIDDEN, "FORBIDDEN"),
        IdentityError::Unavailable => {
            crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "IDENTITY_UNAVAILABLE")
        }
    }
}

fn vision_response(result: Result<serde_json::Value, ErreurVision>) -> Response {
    match result {
        Ok(value) => (
            StatusCode::from_u16(mrjam_vision::statut_resultat(&value))
                .unwrap_or(StatusCode::SERVICE_UNAVAILABLE),
            Json(value),
        )
            .into_response(),
        Err(error) => (
            StatusCode::from_u16(error.statut_http()).unwrap_or(StatusCode::SERVICE_UNAVAILABLE),
            Json(error.json()),
        )
            .into_response(),
    }
}

async fn vision_web(State(state): State<RuntimeState>, request: Request) -> Response {
    vision_request(state, request, true).await
}
async fn vision_rest(State(state): State<RuntimeState>, request: Request) -> Response {
    vision_request(state, request, false).await
}

async fn vision_request(state: RuntimeState, request: Request, browser: bool) -> Response {
    if request_host(&request) != Some("vision.mrj.am") {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    let Some(client) = &state.identity else {
        return crate::unauthenticated().await;
    };
    let identity = if browser {
        client
            .verify_browser("vision.mrj.am", request.method(), request.headers(), false)
            .await
    } else {
        let Some(token) = crate::identity::unique_header(request.headers(), "authorization")
            .and_then(|value| value.strip_prefix("Bearer "))
        else {
            return crate::unauthenticated().await;
        };
        let token = match Justificatif::bearer(token) {
            Ok(token) => token,
            Err(error) => return vision_response(Err(error)),
        };
        client.verify_bearer(&token).await
    };
    let identity = match identity {
        Ok(value) => value,
        Err(error) => return auth_error(error),
    };
    let Some(vision) = &state.vision else {
        return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "VISION_UNAVAILABLE");
    };
    if !crate::identity::unique_header(request.headers(), "content-type").is_some_and(|value| {
        value
            .split(';')
            .next()
            .is_some_and(|mime| mime.trim().eq_ignore_ascii_case("application/json"))
    }) || request.uri().query().is_some()
    {
        return vision_response(Err(ErreurVision::ParametresInvalides));
    }
    let operation = request
        .uri()
        .path()
        .rsplit('/')
        .next()
        .unwrap_or("")
        .to_owned();
    let bytes = match to_bytes(request.into_body(), 65_536).await {
        Ok(bytes) => bytes,
        Err(_) => return vision_response(Err(ErreurVision::RequeteTropGrande)),
    };
    let service = vision.service(identity);
    // Private request-scoped authority was constructed only after verification.
    let credential = match Justificatif::bearer("verified-request") {
        Ok(value) => value,
        Err(error) => return vision_response(Err(error)),
    };
    if browser && operation == "exporter_compte" {
        let request = match mrjam_vision::ExportCompte::depuis_json(&bytes) {
            Ok(value) => value,
            Err(error) => return vision_response(Err(error)),
        };
        return vision_response(service.exporter_compte(Some(&credential), request).await);
    }
    if browser && operation == "effacer_compte" {
        let request = match mrjam_vision::EffacementCompte::depuis_json(&bytes) {
            Ok(value) => value,
            Err(error) => return vision_response(Err(error)),
        };
        return vision_response(service.effacer_compte(Some(&credential), request).await);
    }
    let request = match vision.catalogue.valider_json(&operation, &bytes) {
        Ok(value) => value,
        Err(error) => return vision_response(Err(error)),
    };
    vision_response(service.executer(Some(&credential), request).await)
}

async fn audition(State(state): State<RuntimeState>, request: Request) -> Response {
    if request_host(&request) != Some("audition.mrj.am") {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    let Some(client) = &state.identity else {
        return crate::unauthenticated().await;
    };
    let operation = request
        .uri()
        .path()
        .rsplit('/')
        .next()
        .unwrap_or("")
        .to_owned();
    let admin = matches!(
        operation.as_str(),
        "creer_groupe" | "habiliter" | "membres" | "diagnostic" | "supprimer_groupe"
    );
    let identity = match client
        .verify_browser(
            "audition.mrj.am",
            request.method(),
            request.headers(),
            admin,
        )
        .await
    {
        Ok(identity) => identity,
        Err(error) => return auth_error(error),
    };
    let Some(service) = &state.audition else {
        return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "AUDITION_UNAVAILABLE");
    };
    if !crate::identity::unique_header(request.headers(), "content-type").is_some_and(|value| {
        value
            .split(';')
            .next()
            .is_some_and(|mime| mime.trim().eq_ignore_ascii_case("application/json"))
    }) || request.uri().query().is_some()
    {
        return crate::error_response(StatusCode::BAD_REQUEST, "INVALID_INPUT");
    }
    let now = match SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .and_then(|duration| i64::try_from(duration.as_secs()).ok())
    {
        Some(value) => value,
        None => return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "CLOCK_UNAVAILABLE"),
    };
    let actor = if identity.elevated() {
        mrjam_audition::service::VerifiedActor::from_recent_mfa_verification(
            identity.owner(),
            now,
            300,
        )
    } else {
        mrjam_audition::service::VerifiedActor::from_authenticated_identity(identity.owner(), None)
    };
    let actor = match actor {
        Ok(value) => value,
        Err(_) => return crate::unauthenticated().await,
    };
    let bytes = match to_bytes(request.into_body(), 65_536).await {
        Ok(bytes) => bytes,
        Err(_) => return crate::error_response(StatusCode::PAYLOAD_TOO_LARGE, "PAYLOAD_TOO_LARGE"),
    };
    let timestamp = match mrjam_audition::Timestamp::new(now) {
        Ok(value) => value,
        Err(_) => {
            return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "CLOCK_UNAVAILABLE");
        }
    };
    match service
        .execute(
            &actor,
            mrjam_audition::WriteChannel::Web,
            &operation,
            &bytes,
            timestamp,
        )
        .await
    {
        Ok(value) => Json(value).into_response(),
        Err(error) => (
            StatusCode::from_u16(error.status()).unwrap_or(StatusCode::SERVICE_UNAVAILABLE),
            Json(serde_json::json!({"erreur":error.code()})),
        )
            .into_response(),
    }
}

async fn vision_management(State(state): State<RuntimeState>, request: Request) -> Response {
    if request_host(&request) != Some("vision.mrj.am") {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    let Some(client) = &state.identity else {
        return crate::unauthenticated().await;
    };
    let identity = match client
        .verify_browser("vision.mrj.am", request.method(), request.headers(), true)
        .await
    {
        Ok(identity) => identity,
        Err(error) => return auth_error(error),
    };
    let Some(depot) = state
        .vision
        .as_ref()
        .and_then(|vision| vision.administration.clone())
    else {
        return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "MANAGEMENT_UNAVAILABLE");
    };
    if !crate::identity::unique_header(request.headers(), "content-type").is_some_and(|value| {
        value
            .split(';')
            .next()
            .is_some_and(|mime| mime.trim().eq_ignore_ascii_case("application/json"))
    }) || request.uri().query().is_some()
    {
        return vision_response(Err(ErreurVision::ParametresInvalides));
    }
    let operation = request
        .uri()
        .path()
        .rsplit('/')
        .next()
        .unwrap_or("")
        .to_owned();
    let bytes = match to_bytes(request.into_body(), 65_536).await {
        Ok(bytes) => bytes,
        Err(_) => return vision_response(Err(ErreurVision::RequeteTropGrande)),
    };
    let request = match mrjam_vision::RequeteGestion::depuis_json(&operation, &bytes) {
        Ok(request) => request,
        Err(error) => return vision_response(Err(error)),
    };
    let service = match mrjam_vision::ServiceGestionVision::nouveau(
        Arc::new(RequestIdentity(identity)),
        depot,
        "https://vision.mrj.am/invitation",
    ) {
        Ok(service) => service,
        Err(error) => return vision_response(Err(error)),
    };
    let token = match Justificatif::bearer("verified-administration-request") {
        Ok(token) => token,
        Err(error) => return vision_response(Err(error)),
    };
    vision_response(service.executer(Some(&token), request).await)
}
async fn log_presentation(State(state): State<RuntimeState>, request: Request) -> Response {
    if request_host(&request) != Some("log.mrj.am") {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    let Some(log) = &state.log else {
        return crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "LOG_UNAVAILABLE");
    };
    if !crate::identity::unique_header(request.headers(), "content-type").is_some_and(|value| {
        value
            .split(';')
            .next()
            .is_some_and(|mime| mime.trim().eq_ignore_ascii_case("application/json"))
    }) || request.uri().query().is_some()
    {
        return crate::error_response(StatusCode::BAD_REQUEST, "INVALID_INPUT");
    }
    let Some(origin) =
        crate::identity::unique_header(request.headers(), "origin").map(str::to_owned)
    else {
        return crate::error_response(StatusCode::FORBIDDEN, "ORIGIN_REFUSED");
    };
    let cookie = if request.headers().contains_key("cookie") {
        match crate::identity::unique_header(request.headers(), "cookie") {
            Some(value) => Some(value.to_owned()),
            None => return crate::error_response(StatusCode::BAD_REQUEST, "INVALID_COOKIE"),
        }
    } else {
        None
    };
    let bytes = match to_bytes(request.into_body(), 65_536).await {
        Ok(bytes) => bytes,
        Err(_) => return crate::error_response(StatusCode::PAYLOAD_TOO_LARGE, "PAYLOAD_TOO_LARGE"),
    };
    let context = mrjam_log::PresentationContext {
        host: "log.mrj.am",
        origin: &origin,
        cookie: cookie.as_deref(),
        source_ip: None,
    };
    match log.service.presentation(context, &bytes).await {
        Ok(value) => {
            let mut response = (
                StatusCode::from_u16(value.status).unwrap_or(StatusCode::BAD_GATEWAY),
                Json(value.document),
            )
                .into_response();
            for cookie in value.set_cookies {
                let value = match axum::http::HeaderValue::from_str(&cookie) {
                    Ok(value) => value,
                    Err(_) => {
                        return crate::error_response(
                            StatusCode::BAD_GATEWAY,
                            "INVALID_UPSTREAM_COOKIE",
                        );
                    }
                };
                response
                    .headers_mut()
                    .append(axum::http::header::SET_COOKIE, value);
            }
            response
        }
        Err(error) => (
            StatusCode::from_u16(error.status()).unwrap_or(StatusCode::SERVICE_UNAVAILABLE),
            Json(serde_json::json!({"error":error.code()})),
        )
            .into_response(),
    }
}
