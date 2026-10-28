package org.mrjam.identite;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.Transport;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import org.keycloak.Config;
import org.keycloak.email.EmailException;
import org.keycloak.email.EmailSenderProvider;
import org.keycloak.email.EmailSenderProviderFactory;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.UserModel;

/** STARTTLS obligatoire, identité serveur vérifiée et aucune erreur privée en log. */
public final class CourrielSecurise implements EmailSenderProviderFactory {
    private static final ArrayDeque<Long> GLOBAL = new ArrayDeque<>();
    private static final Map<String, ArrayDeque<Long>> ADRESSES = new HashMap<>();

    private static boolean qualification(Map<String,String> c) {
        return "1".equals(System.getenv("MRJ_QUALIFICATION_COURRIEL")) &&
            "127.0.0.1".equals(c.get("host")) && c.getOrDefault("port", "").matches("38[0-9]{3}") &&
            c.getOrDefault("from", "").endsWith("@example.test");
    }
    private static void configuration(Map<String,String> c) throws EmailException {
        if (!qualification(c) && !("smtp.protonmail.ch".equals(c.get("host")) && "587".equals(c.get("port")) &&
            "true".equals(c.get("starttls")) && "true".equals(c.get("auth")) && !"true".equals(c.get("ssl"))))
            throw new EmailException("Configuration de courriel sécurisé invalide.");
    }
    private static synchronized void limiter(String realm, String adresse) throws Exception {
        long maintenant=System.currentTimeMillis()/1000;
        GLOBAL.removeIf(t -> t+86400<=maintenant);
        ADRESSES.values().forEach(v -> v.removeIf(t -> t+3600<=maintenant));
        ADRESSES.entrySet().removeIf(e -> e.getValue().isEmpty());
        String cle=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(
            (realm+":"+adresse.toLowerCase(java.util.Locale.ROOT)).getBytes(StandardCharsets.UTF_8)));
        var parAdresse=ADRESSES.computeIfAbsent(cle,k -> new ArrayDeque<>());
        if (GLOBAL.size()>=250 || parAdresse.size()>=10) throw new EmailException("Courriel temporairement indisponible.");
        GLOBAL.add(maintenant);parAdresse.add(maintenant);
    }
    @Override public EmailSenderProvider create(KeycloakSession keycloak) {
        return new EmailSenderProvider() {
            @Override public void validate(Map<String,String> c) throws EmailException { configuration(c); }
            @Override public void send(Map<String,String> c, UserModel u, String sujet, String texte, String html) throws EmailException {
                send(c,u.getEmail(),sujet,texte,html);
            }
            @Override public void send(Map<String,String> c, String destinataire, String sujet, String texte, String html) throws EmailException {
                configuration(c);
                try {
                    if (destinataire==null || destinataire.length()>254 || destinataire.contains("\n") || destinataire.contains("\r") ||
                        sujet==null || sujet.contains("\r") || sujet.contains("\n")) throw new IllegalArgumentException();
                    if (qualification(c) && !destinataire.endsWith("@example.test")) throw new IllegalArgumentException();
                    InternetAddress a=new InternetAddress(destinataire,true);a.validate();
                    limiter(keycloak.getContext().getRealm().getName(),destinataire);
                    boolean tls="true".equals(c.get("starttls")), auth="true".equals(c.get("auth"));
                    Properties p=new Properties();p.setProperty("mail.smtp.host",c.get("host"));p.setProperty("mail.smtp.port",c.get("port"));
                    p.setProperty("mail.smtp.auth",Boolean.toString(auth));
                    p.setProperty("mail.smtp.starttls.enable",Boolean.toString(tls));
                    p.setProperty("mail.smtp.starttls.required",Boolean.toString(tls));
                    p.setProperty("mail.smtp.ssl.checkserveridentity","true");p.setProperty("mail.smtp.ssl.protocols","TLSv1.3 TLSv1.2");
                    p.setProperty("mail.smtp.connectiontimeout","10000");p.setProperty("mail.smtp.timeout","10000");p.setProperty("mail.smtp.writetimeout","10000");
                    p.setProperty("mail.from",c.get("from"));
                    Session s=Session.getInstance(p);
                    MimeMessage message=new MimeMessage(s);
                    message.setFrom(new InternetAddress(c.get("from"),c.getOrDefault("fromDisplayName","MrJ.am"),"UTF-8"));
                    message.setRecipients(jakarta.mail.Message.RecipientType.TO,new InternetAddress[]{a});
                    message.setSubject(sujet,"UTF-8");
                    MimeMultipart corps=new MimeMultipart("alternative");
                    if (texte!=null) {MimeBodyPart part=new MimeBodyPart();part.setText(texte,"UTF-8");corps.addBodyPart(part);}
                    if (html!=null) {MimeBodyPart part=new MimeBodyPart();part.setContent(html,"text/html; charset=UTF-8");corps.addBodyPart(part);}
                    message.setContent(corps);message.setSentDate(new java.util.Date());message.saveChanges();
                    try (Transport transport=s.getTransport("smtp")) {
                        transport.connect(c.get("host"),Integer.parseInt(c.get("port")),auth?c.get("user"):null,auth?c.get("password"):null);
                        transport.sendMessage(message,new InternetAddress[]{a});
                    }
                } catch (Exception e) {
                    // Ni réponse du relais, adresse, mot de passe ou jeton en log.
                    throw new EmailException("Courriel temporairement indisponible.");
                }
            }
            @Override public void close() { }
        };
    }
    @Override public String getId() { return "default"; }
    @Override public int order() { return 100; }
    @Override public void init(Config.Scope c) { }
    @Override public void postInit(KeycloakSessionFactory f) { }
    @Override public void close() { }
}
