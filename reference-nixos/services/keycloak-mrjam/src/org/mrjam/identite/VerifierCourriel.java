package org.mrjam.identite;

import java.util.Objects;
import jakarta.ws.rs.core.Response;
import org.keycloak.TokenVerifier.Predicate;
import org.keycloak.authentication.AuthenticationProcessor;
import org.keycloak.authentication.actiontoken.AbstractActionTokenHandler;
import org.keycloak.authentication.actiontoken.ActionTokenContext;
import org.keycloak.authentication.actiontoken.TokenUtils;
import org.keycloak.events.Errors;
import org.keycloak.events.EventType;
import org.keycloak.services.messages.Messages;
import org.keycloak.services.resources.LoginActionsService;

/** Refuser un navigateur étranger et conserver PKCE, état et nonce d'origine. */
public final class VerifierCourriel extends AbstractActionTokenHandler<JetonCourriel> {
    public VerifierCourriel() {
        super(JetonCourriel.TYPE, JetonCourriel.class, Messages.INVALID_REQUEST, EventType.LOGIN, Errors.INVALID_TOKEN);
    }
    @Override public Predicate<? super JetonCourriel>[] getVerifiers(ActionTokenContext<JetonCourriel> c) {
        return TokenUtils.predicates(
            TokenUtils.checkThat(t -> !c.isAuthenticationSessionFresh() &&
                Objects.equals(c.getAuthenticationSession().getAuthNote(ConnexionCourriel.ATTENDU), t.getActionVerificationNonce().toString()) &&
                Objects.equals(c.getAuthenticationSession().getAuthenticatedUser().getEmail(), t.getEmail()) &&
                c.getAuthenticationSession().getAuthenticatedUser().isEmailVerified(), Errors.INVALID_TOKEN, Messages.INVALID_REQUEST));
    }
    @Override public Response handleToken(JetonCourriel t, ActionTokenContext<JetonCourriel> c) {
        c.getAuthenticationSession().setAuthNote(ConnexionCourriel.VERIFIE, t.getActionVerificationNonce().toString());
        c.setExecutionId(t.getNote("execution"));
        // Reprendre l'exécution choisie ; rejouer le flux complet afficherait
        // son premier choix (mot de passe). Sans paramètre de confirmation,
        // action() ne fait qu'afficher le formulaire natif, jamais un login.
        return c.processFlow(true, LoginActionsService.AUTHENTICATE_PATH,
            c.getRealm().getBrowserFlow(), null, new AuthenticationProcessor());
    }
    @Override public boolean canUseTokenRepeatedly(JetonCourriel t, ActionTokenContext<JetonCourriel> c) { return false; }
}
