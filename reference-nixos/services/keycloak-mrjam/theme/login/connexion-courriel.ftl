<#import "template.ftl" as layout>
<@layout.registrationLayout displayInfo=false displayMessage=true; section>
  <#if section == "header">Connexion par courriel
  <#elseif section == "form">
    <#if courrielVerifie>
      <p>Confirmez la connexion que vous avez demandée. Le second facteur reste nécessaire s’il est configuré.</p>
      <form action="${url.loginAction}" method="post">
        <input type="hidden" name="confirmerCourriel" value="oui">
        <button type="submit" id="mrjam-confirmer">Confirmer ma connexion</button>
      </form>
    <#elseif courrielEnvoye>
      <p>Si cette adresse correspond à un compte actif et vérifié, un lien valable dix minutes lui a été envoyé.</p>
      <p>Ouvrez-le dans ce même navigateur. La visite du lien ne termine pas la connexion : vous devrez la confirmer.</p>
    <#else>
      <form action="${url.loginAction}" method="post">
        <label for="mrjam-courriel">Adresse de courrier</label>
        <input type="email" name="courriel" id="mrjam-courriel" maxlength="254" autocomplete="email" required>
        <button type="submit">Recevoir mon lien de connexion</button>
      </form>
    </#if>
  </#if>
</@layout.registrationLayout>
