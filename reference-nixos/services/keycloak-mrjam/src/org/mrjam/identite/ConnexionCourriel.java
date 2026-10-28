package org.mrjam.identite;

import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.Objects;
import org.keycloak.Config;
import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.Authenticator;
import org.keycloak.authentication.AuthenticatorFactory;
import org.keycloak.common.util.Time;
import org.keycloak.email.EmailException;
import org.keycloak.email.EmailTemplateProvider;
import org.keycloak.models.AuthenticationExecutionModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.sessions.AuthenticationSessionCompoundId;

/** Le lien identifie le compte ; le formulaire natif confirme avant tout login. */
public final class ConnexionCourriel implements Authenticator, AuthenticatorFactory {
    public static final String ID = "mrjam-courriel";
    public static final String ATTENDU = "mrjam.courriel.attendu";
    public static final String VERIFIE = "mrjam.courriel.verifie";
    public static final String EXPIRE = "mrjam.courriel.expire";

    private void afficher(AuthenticationFlowContext c) {
        boolean pret = c.getAuthenticationSession().getAuthNote(VERIFIE) != null;
        c.challenge(c.form().setAttribute("courrielVerifie", pret)
            .setAttribute("courrielEnvoye", c.getAuthenticationSession().getAuthNote(ATTENDU) != null)
            .createForm("connexion-courriel.ftl"));
    }
    @Override public void authenticate(AuthenticationFlowContext c) { afficher(c); }
    @Override public void action(AuthenticationFlowContext c) {
        var auth = c.getAuthenticationSession();
        var p = c.getHttpRequest().getDecodedFormParameters();
        if (Objects.equals(p.getFirst("confirmerCourriel"), "oui")) {
            String verifie = auth.getAuthNote(VERIFIE), attendu = auth.getAuthNote(ATTENDU);
            int expiration;
            try { expiration = Integer.parseInt(auth.getAuthNote(EXPIRE)); }
            catch (RuntimeException e) { afficher(c); return; }
            if (verifie == null || !Objects.equals(verifie, attendu) || Time.currentTime() >= expiration || c.getUser() == null) {
                afficher(c); return;
            }
            // Une seconde visite ne peut pas réutiliser ce certificat, y compris
            // pendant l'étape OTP qui suit dans le flux commun.
            auth.removeAuthNote(VERIFIE); auth.removeAuthNote(ATTENDU); auth.removeAuthNote(EXPIRE);
            c.success(); return;
        }
        // Au plus un envoi par session de connexion. Le message et l'état
        // public sont identiques pour un compte inconnu, suspendu ou non vérifié.
        if (auth.getAuthNote(ATTENDU) != null) { afficher(c); return; }
        auth.setAuthNote(ATTENDU, "demande-enregistree");
        String courriel = p.getFirst("courriel");
        if (courriel != null && courriel.length() <= 254 && !courriel.contains("\n") && !courriel.contains("\r")) {
            UserModel u = c.getSession().users().getUserByEmail(c.getRealm(), courriel);
            if (u != null && u.isEnabled() && u.isEmailVerified()) {
                int expiration = Time.currentTime() + 600;
                String session = AuthenticationSessionCompoundId.fromAuthSession(auth).getEncodedId();
                JetonCourriel jeton = new JetonCourriel(u.getId(), u.getEmail(), expiration, session,
                    auth.getClient().getClientId(), c.getExecution().getId());
                auth.setAuthNote(ATTENDU, jeton.getActionVerificationNonce().toString());
                auth.setAuthNote(EXPIRE, Integer.toString(expiration));
                String lien = c.getActionTokenUrl(jeton.serialize(c.getSession(), c.getRealm(), c.getUriInfo())).toString();
                try {
                    c.getSession().getProvider(EmailTemplateProvider.class).setRealm(c.getRealm()).setUser(u)
                        .setAuthenticationSession(auth).send("connexionCourrielSujet", "connexion-courriel.ftl", new HashMap<>(Map.of("lien", lien)));
                } catch (EmailException e) {
                    // Aucun détail SMTP, courriel ni jeton dans les journaux.
                    auth.setAuthNote(ATTENDU, "demande-enregistree");
                }
            }
        }
        afficher(c);
    }
    @Override public boolean requiresUser() { return false; }
    @Override public boolean configuredFor(KeycloakSession s, RealmModel r, UserModel u) { return true; }
    @Override public void setRequiredActions(KeycloakSession s, RealmModel r, UserModel u) { }
    @Override public Authenticator create(KeycloakSession s) { return this; }
    @Override public String getId() { return ID; }
    @Override public String getDisplayType() { return "Recevoir un lien par courriel"; }
    @Override public String getReferenceCategory() { return "email"; }
    @Override public String getHelpText() { return "Lien signé, session d'origine, confirmation puis second facteur éventuel."; }
    @Override public boolean isConfigurable() { return true; }
    @Override public boolean isUserSetupAllowed() { return false; }
    @Override public List<ProviderConfigProperty> getConfigProperties() { return List.of(); }
    @Override public AuthenticationExecutionModel.Requirement[] getRequirementChoices() {
        return new AuthenticationExecutionModel.Requirement[] { AuthenticationExecutionModel.Requirement.ALTERNATIVE };
    }
    @Override public void init(Config.Scope c) { }
    @Override public void postInit(KeycloakSessionFactory f) { }
    @Override public void close() { }
}
