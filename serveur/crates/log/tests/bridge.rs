use mrjam_log::*;
use serde_json::{Value, json};
use std::sync::{Arc, Mutex};

type Error = Box<dyn std::error::Error + Send + Sync>;
type RecordedRequest = (String, NativeMethod, Option<Value>, Option<String>);
struct FakeNative {
    seen: Mutex<Vec<RecordedRequest>>,
    responses: Mutex<Vec<NativeResponse>>,
}
impl NativeClient for FakeNative {
    fn exchange(&self, r: NativeRequest) -> NativeFuture<'_, NativeResponse> {
        Box::pin(async move {
            self.seen
                .lock()
                .map_err(|_| LogError::new("fixture_lock", 500))?
                .push((
                    r.path().to_owned(),
                    r.method(),
                    r.document().cloned(),
                    r.bearer().map(str::to_owned),
                ));
            let mut responses = self
                .responses
                .lock()
                .map_err(|_| LogError::new("fixture_lock", 500))?;
            if responses.is_empty() {
                Err(LogError::new("fixture_empty", 500))
            } else {
                Ok(responses.remove(0))
            }
        })
    }
}
struct FakeAliases;
impl LoginAliases for FakeAliases {
    fn resolve<'a>(&'a self, email: &'a str) -> NativeFuture<'a, Option<String>> {
        Box::pin(async move {
            Ok(if email == "invented@example.invalid" {
                Some("known-synthetic-subject".into())
            } else {
                None
            })
        })
    }
}
fn context() -> PresentationContext<'static> {
    PresentationContext {
        host: "log.mrj.am",
        origin: "https://log.mrj.am",
        cookie: Some("bearer=synthetic-cookie-token"),
        source_ip: None,
    }
}
fn native(responses: Vec<NativeResponse>) -> Arc<FakeNative> {
    Arc::new(FakeNative {
        seen: Mutex::new(Vec::new()),
        responses: Mutex::new(responses),
    })
}
fn response(document: Value) -> NativeResponse {
    NativeResponse {
        status: 200,
        body: document.to_string().into_bytes(),
        set_cookies: Vec::new(),
        location: None,
    }
}
async fn call(service: &LogService, p: Value) -> Result<PresentationResponse, LogError> {
    service
        .presentation(context(), p.to_string().as_bytes())
        .await
}
#[tokio::test]
async fn native_auth_uses_cookie_session_and_never_returns_success_token() -> Result<(), Error> {
    let client = native(vec![NativeResponse {
        set_cookies: vec!["bearer=synthetic-session; HttpOnly; Secure; SameSite=Strict".into()],
        ..response(json!({"state":{"success":"synthetic-jwt-never-returned"}}))
    }]);
    let service = LogService::new(client.clone(), Arc::new(FakeAliases));
    let result=call(&service,json!({"action":"auth","document":{"step":{"init2":{"username":"INVENTED@example.invalid","issue":"token","privileged":true}}}})).await?;
    assert_eq!(result.document, json!({"state":{"success":""}}));
    assert!(result.set_cookies[0].contains("Path=/"));
    assert!(result.set_cookies[0].contains("Max-Age=7776000"));
    let seen = client.seen.lock().map_err(|_| "poisoned")?;
    assert_eq!(seen[0].0, "/v1/auth");
    assert_eq!(
        seen[0].2,
        Some(
            json!({"step":{"init2":{"username":"known-synthetic-subject","issue":"cookie","privileged":false}}})
        )
    );
    Ok(())
}
#[tokio::test]
async fn subject_for_revocation_is_obtained_from_upstream_not_request() -> Result<(), Error> {
    let subject = "11111111-1111-4111-8111-111111111111";
    let session = "22222222-2222-4222-8222-222222222222";
    let client = native(vec![
        response(json!({"youare":{"attrs":{"uuid":[subject]}}})),
        response(Value::Null),
    ]);
    let service = LogService::new(client.clone(), Arc::new(FakeAliases));
    call(&service, json!({"action":"revoquer","parametre":session})).await?;
    let seen = client.seen.lock().map_err(|_| "poisoned")?;
    assert_eq!(seen[0].0, "/v1/self");
    assert_eq!(
        seen[1].0,
        format!("/v1/account/{subject}/_user_auth_token/{session}")
    );
    assert_eq!(seen[1].1, NativeMethod::Delete);
    Ok(())
}
#[tokio::test]
async fn origin_unknown_actions_arbitrary_paths_and_unconfigured_aliases_fail_closed()
-> Result<(), Error> {
    let client = native(Vec::new());
    let service = LogService::new(client.clone(), Arc::new(UnconfiguredAliases));
    let bad = PresentationContext {
        host: "log.mrj.am",
        origin: "https://other.invalid",
        cookie: None,
        source_ip: None,
    };
    assert!(service.presentation(bad, b"{}").await.is_err());
    for p in [
        json!({"action":"https://other.invalid"}),
        json!({"action":"profil","url":"https://other.invalid"}),
        json!({"action":"profil","parametre":"arbitrary"}),
        json!({"action":"auth","document":{"step":{"init2":{"username":"invented@example.invalid"}}}}),
    ] {
        assert!(call(&service, p).await.is_err());
    }
    assert!(client.seen.lock().map_err(|_| "poisoned")?.is_empty());
    Ok(())
}
#[tokio::test]
async fn oauth_cookie_is_forwarded_only_to_fixed_official_authorization_path() -> Result<(), Error>
{
    let client = native(vec![NativeResponse {
        status: 302,
        body: Vec::new(),
        set_cookies: Vec::new(),
        location: Some("https://client.invalid/callback?code=synthetic".into()),
    }]);
    let service = LogService::new(client.clone(), Arc::new(FakeAliases));
    let result = call(
        &service,
        json!({"action":"oauth","document":{"client_id":"synthetic","response_type":"code"}}),
    )
    .await?;
    assert_eq!(result.status, 200);
    assert_eq!(
        result.document["redirection"],
        "https://client.invalid/callback?code=synthetic"
    );
    let seen = client.seen.lock().map_err(|_| "poisoned")?;
    assert_eq!(seen[0].0, "/oauth2/authorise");
    assert_eq!(seen[0].3.as_deref(), Some("synthetic-cookie-token"));
    Ok(())
}
#[tokio::test]
async fn duplicate_bearer_insecure_redirect_and_wide_cookie_are_rejected() -> Result<(), Error> {
    let client = native(Vec::new());
    let service = LogService::new(client.clone(), Arc::new(FakeAliases));
    let mut duplicate = context();
    duplicate.cookie = Some("bearer=one; bearer=two");
    assert!(
        service
            .presentation(duplicate, br#"{"action":"oauth"}"#)
            .await
            .is_err()
    );
    assert!(client.seen.lock().map_err(|_| "poisoned")?.is_empty());
    for result in [
        NativeResponse {
            status: 302,
            body: Vec::new(),
            set_cookies: Vec::new(),
            location: Some("http://client.invalid/callback".into()),
        },
        NativeResponse {
            set_cookies: vec!["bearer=synthetic; Domain=.mrj.am".into()],
            ..response(Value::Null)
        },
    ] {
        let service = LogService::new(native(vec![result]), Arc::new(FakeAliases));
        assert!(
            call(&service, json!({"action":"oauth","document":{}}))
                .await
                .is_err()
        );
    }
    Ok(())
}

#[tokio::test]
async fn duplicate_nested_auth_steps_are_rejected_before_upstream() -> Result<(), Error> {
    let client = native(Vec::new());
    let service = LogService::new(client.clone(), Arc::new(FakeAliases));
    assert!(service.presentation(context(),br#"{"action":"auth","document":{"step":{"init2":{"username":"first","username":"second"}}}}"#).await.is_err());
    assert!(client.seen.lock().map_err(|_| "poisoned")?.is_empty());
    Ok(())
}

#[tokio::test]
async fn cookie_attribute_whitespace_and_ambiguity_do_not_widen_scope() -> Result<(), Error> {
    for cookie in [
        "bearer=synthetic; Domain = .mrj.am",
        "bearer=synthetic; SameSite = None",
        "bearer=synthetic; Path=/; Path=/wide",
    ] {
        let service = LogService::new(
            native(vec![NativeResponse {
                set_cookies: vec![cookie.into()],
                ..response(Value::Null)
            }]),
            Arc::new(FakeAliases),
        );
        assert!(call(&service, json!({"action":"profil"})).await.is_err());
    }
    Ok(())
}
