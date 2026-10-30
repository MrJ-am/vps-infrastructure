# Reviewed settings proposal; no imports from inactive reference-nixos/.
{ renderCommand }:
{
  DEFAULT.APP_NAME = "Forgejo";
  server = {
    DOMAIN = "forge.mrj.am";
    ROOT_URL = "https://forge.mrj.am/";
    HTTP_ADDR = "127.0.0.1";
    HTTP_PORT = 3004;
    START_SSH_SERVER = true;
    SSH_DOMAIN = "forge.mrj.am";
    SSH_PORT = 2222;
    SSH_LISTEN_HOST = "0.0.0.0";
    SSH_LISTEN_PORT = 2222;
    DISABLE_SSH = false;
    OFFLINE_MODE = true;
  };
  database = {
    DB_TYPE = "postgres";
    HOST = "/run/postgresql";
    NAME = "forgejo";
    USER = "forgejo";
    SSL_MODE = "disable";
  };
  service = {
    DISABLE_REGISTRATION = true;
    REQUIRE_SIGNIN_VIEW = true;
    ENABLE_INTERNAL_SIGNIN = false;
    ENABLE_BASIC_AUTHENTICATION = false;
    ALLOW_ONLY_EXTERNAL_REGISTRATION = true;
    DEFAULT_ALLOW_CREATE_ORGANIZATION = false;
    DEFAULT_KEEP_EMAIL_PRIVATE = true;
    ENABLE_NOTIFY_MAIL = false;
  };
  repository = {
    DEFAULT_PRIVATE = "private";
    FORCE_PRIVATE = true;
    DISABLE_HTTP_GIT = false;
    ENABLE_PUSH_CREATE_USER = false;
    ENABLE_PUSH_CREATE_ORG = false;
    # Repository/storage quotas must be observed and adopted separately. Do
    # not carry the old unlimited default into a new runnable configuration.
  };
  "repository.upload".ENABLED = false;
  "repository.signing".SIGNING_KEY = "none";
  security = {
    INSTALL_LOCK = true;
    PASSWORD_HASH_ALGO = "argon2";
    REVERSE_PROXY_LIMIT = 1;
    REVERSE_PROXY_TRUSTED_PROXIES = "127.0.0.1/32";
  };
  session.COOKIE_SECURE = true;
  openid = { ENABLE_OPENID_SIGNIN = false; ENABLE_OPENID_SIGNUP = false; };
  oauth2_client = {
    ENABLE_AUTO_REGISTRATION = true;
    ACCOUNT_LINKING = "disabled";
    USERNAME = "nickname";
    OPENID_CONNECT_SCOPES = "openid profile email";
  };
  admin = {
    DISABLE_REGULAR_ORG_CREATION = true;
    EXTERNAL_USER_DISABLE_FEATURES = "manage_password";
  };
  actions.ENABLED = false;
  packages.ENABLED = false;
  federation.ENABLED = false;
  mailer.ENABLED = false;
  "markup.orgmode" = {
    ENABLED = true;
    FILE_EXTENSIONS = ".org";
    RENDER_COMMAND = renderCommand;
    IS_INPUT_FILE = false;
    NEED_POSTPROCESS = true;
    RENDER_CONTENT_MODE = "sanitized";
  };
  "markup.sanitizer.orgmode.math" = {
    ELEMENT = "span";
    ALLOW_ATTR = "class";
    REGEXP = "^math (inline|display)$";
  };
  log.LEVEL = "Warn";
}
