package org.mrjam.identite;

import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;
import java.util.Map;
import org.keycloak.authentication.RequiredActionContext;
import org.keycloak.authentication.requiredactions.DeleteAccount;
import org.keycloak.models.AccountRoles;
import org.keycloak.models.Constants;
import org.keycloak.services.Urls;
import org.keycloak.util.JsonSerialization;

/** Remplacer l'action native, avec intention durable AVANT la suppression IdP. */
public final class FermerCompte extends DeleteAccount {
    @Override public int order() { return 100; }
    @Override public String getDisplayText() { return "Fermer mon compte MrJ.am"; }

    private boolean autorise(RequiredActionContext c) {
        var role = c.getRealm().getClientByClientId(Constants.ACCOUNT_MANAGEMENT_CLIENT_ID).getRole(AccountRoles.DELETE_ACCOUNT);
        return role != null && c.getUser().hasRole(role);
    }
    @Override public void requiredActionChallenge(RequiredActionContext c) {
        if (!autorise(c)) { c.failure(); return; }
        c.challenge(c.form().createForm("fermer-compte.ftl"));
    }
    @Override public void processAction(RequiredActionContext c) {
        if (!autorise(c)) { c.failure(); return; }
        if (!Objects.equals(c.getHttpRequest().getDecodedFormParameters().getFirst("confirmation"), "FERMER MON COMPTE")) {
            c.challenge(c.form().setError("Saisissez exactement FERMER MON COMPTE après avoir récupéré les données souhaitées.").createForm("fermer-compte.ftl"));
            return;
        }
        String sujet = c.getUser().getId();
        if (!sujet.matches("[A-Za-z0-9_.-]{1,64}")) { c.failure(); return; }
        try {
            Path chemin = Path.of(System.getenv("MRJ_FERMETURE_SECRET_FILE"));
            if (!Files.isRegularFile(chemin, LinkOption.NOFOLLOW_LINKS)) throw new IllegalStateException();
            String secret = Files.readString(chemin).strip();
            if (!secret.matches("[A-Za-z0-9_-]{43}")) throw new IllegalStateException();
            HttpRequest requete = HttpRequest.newBuilder(URI.create("http://127.0.0.1:3028/fermer"))
                .timeout(Duration.ofSeconds(30)).header("Authorization", "Bearer "+secret)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(JsonSerialization.writeValueAsString(Map.of(
                    "emetteur", Urls.realmIssuer(c.getUriInfo().getBaseUri(), c.getRealm().getName()),
                    "sujet", sujet, "confirmation", "FERMER MON COMPTE")))).build();
            HttpResponse<Void> reponse = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build()
                .send(requete, HttpResponse.BodyHandlers.discarding());
            if (reponse.statusCode() != 200) {
                c.challenge(c.form().setError("La fermeture est enregistrée ou temporairement indisponible. Réessayez ; le compte n’est pas encore fermé. Une demande enregistrée reprendra automatiquement.").createForm("fermer-compte.ftl"));
                return;
            }
        } catch (Exception e) {
            // Aucun secret, sujet, contenu ou détail du service dans les logs.
            c.challenge(c.form().setError("La fermeture n’a pas pu être terminée. Réessayez ; une demande enregistrée reprendra automatiquement.").createForm("fermer-compte.ftl"));
            return;
        }
        // Le flux natif conserve ses contrôles CSRF, sa réauthentification
        // et sa suppression transactionnelle. Le registre couvre une panne.
        super.processAction(c);
    }
}
