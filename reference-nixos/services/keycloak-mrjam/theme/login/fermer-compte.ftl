<#import "template.ftl" as layout>
<@layout.registrationLayout displayInfo=false displayMessage=true; section>
  <#if section == "header">Fermer mon compte MrJ.am
  <#elseif section == "form">
    <p>Cette demande est irréversible. Elle supprime votre identité commune, ses moyens de connexion et les données des outils qui lui sont rattachés (actuellement Vision).</p>
    <p>Récupérez les données souhaitées avant de confirmer. Votre compte peut être fermé ici même si vous avez déjà effacé votre espace Vision.</p>
    <p><a href="https://vision.mrj.am/#compte">Exporter mes données Vision</a> · <a href="https://vision.mrj.am/privacy">Confidentialité</a></p>
    <p>Un registre technique minimal est chiffré et envoyé dans la sauvegarde des effacements avant la suppression. Si l’envoi échoue, la demande enregistrée reprendra automatiquement. Une restauration doit appliquer les effacements avant toute réouverture.</p>
    <form action="${url.loginAction}" method="post">
      <label for="mrjam-fermeture">Saisissez FERMER MON COMPTE</label>
      <input id="mrjam-fermeture" name="confirmation" autocomplete="off" required>
      <button id="mrjam-fermer" type="submit">Fermer définitivement mon compte</button>
    </form>
  </#if>
</@layout.registrationLayout>
