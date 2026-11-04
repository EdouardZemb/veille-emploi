/* Connexion par passkey, et enregistrement d'une passkey depuis un lien.
 *
 * Sert deux pages : /connexion (#btn-passkey) et /lien (#btn-enregistrer).
 * Aucune bibliothèque : l'API WebAuthn du navigateur et ses conversions JSON
 * (parseCreationOptionsFromJSON, parseRequestOptionsFromJSON, toJSON).
 *
 * Le jeton d'un lien est dans le fragment de l'adresse (#…) : le navigateur ne
 * l'envoie jamais au serveur dans l'adresse, seulement dans le corps de la
 * requête des options.
 */

(function () {
  'use strict';

  const MESSAGES = {
    lien_invalide: "Ce lien n'est plus valable. Demande-en un autre.",
    echec: 'La connexion a échoué. Réessaie.',
    trop_de_demandes: "Trop d'essais. Attends une minute.",
    origine_inconnue: "La connexion est indisponible : VEILLE_URL n'est pas définie sur le serveur.",
    deja_enregistree: 'Cet appareil a déjà une passkey. Connecte-toi depuis la page de connexion.',
  };

  // Le seul refus qui a une suite ailleurs : la passkey est déjà là, elle sert sur /connexion.
  const VERS_LA_CONNEXION = { adresse: '/connexion', texte: 'Aller à la connexion' };

  const message = document.getElementById('message');

  function dire(texte, lien) {
    if (!message) return;
    message.textContent = texte;
    if (lien) {
      const a = document.createElement('a');
      a.href = lien.adresse;
      a.textContent = lien.texte;
      message.append(' ', a);
    }
    message.hidden = !texte;
  }

  // Une requête refusée devient une erreur qui porte le code de l'API et le statut HTTP.
  async function envoyer(url, corps) {
    const rep = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corps || {}),
      credentials: 'same-origin',
    });
    let donnees = null;
    try { donnees = await rep.json(); } catch (_) { donnees = null; }
    if (!rep.ok) {
      const erreur = new Error('requête refusée (' + rep.status + ')');
      erreur.code = (donnees && donnees.erreur) || '';
      erreur.statut = rep.status;
      throw erreur;
    }
    return donnees;
  }

  function messagePour(erreur) {
    const code = (erreur && erreur.code) || '';
    const statut = (erreur && erreur.statut) || 0;
    if (code === 'lien_invalide') return MESSAGES.lien_invalide;
    if (code === 'deja_enregistree') return MESSAGES.deja_enregistree;
    if (code === 'trop_de_demandes' || statut === 429) return MESSAGES.trop_de_demandes;
    if (code === 'origine_inconnue' || statut === 503) return MESSAGES.origine_inconnue;
    // connexion_impossible, origine, une cérémonie annulée, un navigateur sans passkey…
    return MESSAGES.echec;
  }

  async function enregistrer() {
    const jeton = location.hash.slice(1);
    if (!jeton) {
      const erreur = new Error('lien sans jeton');
      erreur.code = 'lien_invalide';
      throw erreur;
    }
    const debut = await envoyer('/api/auth/lien/options', { jeton: jeton });
    const options = PublicKeyCredential.parseCreationOptionsFromJSON(debut.options);
    let credential;
    try {
      credential = await navigator.credentials.create({ publicKey: options });
    } catch (erreur) {
      // excludeCredentials : cet appareil porte déjà une passkey de la console.
      // Une DOMException a un `code` numérique en lecture seule : une erreur neuve.
      if (erreur && erreur.name === 'InvalidStateError') {
        const deja = new Error('passkey déjà enregistrée sur cet appareil');
        deja.code = 'deja_enregistree';
        throw deja;
      }
      throw erreur;
    }
    await envoyer('/api/auth/lien', { cle: debut.cle, reponse: credential.toJSON() });
  }

  async function seConnecter() {
    const debut = await envoyer('/api/auth/connexion/options');
    const options = PublicKeyCredential.parseRequestOptionsFromJSON(debut.options);
    const credential = await navigator.credentials.get({ publicKey: options });
    await envoyer('/api/auth/connexion', { cle: debut.cle, reponse: credential.toJSON() });
  }

  function brancher(id, action) {
    const bouton = document.getElementById(id);
    if (!bouton) return;
    bouton.addEventListener('click', async () => {
      bouton.disabled = true;
      dire('');
      try {
        await action();
        location.href = '/';
      } catch (erreur) {
        const deja = Boolean(erreur) && erreur.code === 'deja_enregistree';
        dire(messagePour(erreur), deja ? VERS_LA_CONNEXION : null);
        bouton.disabled = false;
      }
    });
  }

  brancher('btn-passkey', seConnecter);
  brancher('btn-enregistrer', enregistrer);
})();
