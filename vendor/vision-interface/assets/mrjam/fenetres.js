/* Cycle de vie du dialogue natif ; aucune donnée ni décision applicative. */
(() => {
  const ouverts = new Map();
  const synchroniser = () => {
    for (const [dialogue, cible] of ouverts) {
      if (!dialogue.isConnected) {
        ouverts.delete(dialogue);
        if (cible?.isConnected && !cible.closest('[inert]')) cible.focus();
      }
    }
    for (const dialogue of document.querySelectorAll('dialog[data-mrjam-modale]')) {
      if (!dialogue.open) {
        ouverts.set(dialogue, document.activeElement);
        dialogue.showModal();
        dialogue.addEventListener('keydown', evenement => {
          if (evenement.key !== 'Tab') return;
          const cibles = [...dialogue.querySelectorAll('button, input, textarea, select, a[href], [tabindex]')]
            .filter(cible => cible.tabIndex >= 0 && !cible.disabled && !cible.closest('[inert]') && cible.getClientRects().length);
          const premiere = cibles[0], derniere = cibles.at(-1);
          if (evenement.shiftKey && document.activeElement === premiere) {
            evenement.preventDefault(); derniere?.focus();
          } else if (!evenement.shiftKey && document.activeElement === derniere) {
            evenement.preventDefault(); premiere?.focus();
          }
        });
      }
    }
  };
  new MutationObserver(synchroniser).observe(document.body, {childList: true, subtree: true});
  synchroniser();
})();
