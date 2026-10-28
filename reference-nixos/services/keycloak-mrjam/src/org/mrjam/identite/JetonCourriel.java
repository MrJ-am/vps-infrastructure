package org.mrjam.identite;

import java.util.UUID;
import org.keycloak.authentication.actiontoken.DefaultActionToken;

/** Jeton signé et lié à la session d'authentification native Keycloak. */
public final class JetonCourriel extends DefaultActionToken {
    public static final String TYPE = "mrjam-connexion-courriel";
    public JetonCourriel() { super(); }
    public JetonCourriel(String utilisateur, String courriel, int expiration, String session, String client, String execution) {
        super(utilisateur, TYPE, expiration, UUID.randomUUID(), session);
        setEmail(courriel);
        issuedFor(client);
        setNote("execution", execution);
    }
}
