'use strict';

const SEUIL = parseFloat(document.body.dataset.seuil || '45');
const CLE_VAPID = document.body.dataset.vapid || '';
// L'atout mis en avant, `{cle, libelle, titre, bouton, bouton_titre}`, ou null : il vient de
// la configuration (`app._atout_mis_en_avant`).
const ATOUT = (() => {
  try { return JSON.parse(document.body.dataset.atout || 'null'); } catch (e) { return null; }
})();

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function echapper(t) {
  return String(t ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function message(texte, erreur = false) {
  const d = document.createElement('div');
  d.className = 'message' + (erreur ? ' erreur' : '');
  d.textContent = texte;
  $('#messages').append(d);
  // `sortie` l'efface en 150 ms (style.css), puis il quitte la page : un message qui
  // disparaît d'un coup, au milieu de sa lecture, paraît cassé.
  setTimeout(() => {
    d.classList.add('sortie');
    setTimeout(() => d.remove(), 150);
  }, erreur ? 7000 : 3500);
}

// Les codes `erreur` de l'origine, dits en clair. Les autres routes répondent `detail`.
const ERREURS_API = {
  origine: "Refusé : l'adresse de la console n'est pas l'adresse publique déclarée sur le serveur (VEILLE_URL, ou VEILLE_EMPLOI_URL_PUBLIQUE en conteneur).",
  origine_inconnue: "Indisponible : l'adresse publique n'est pas définie sur le serveur (VEILLE_URL, ou VEILLE_EMPLOI_URL_PUBLIQUE en conteneur).",
  collecte_coupee: "La collecte est coupée sur cette console.",
  collecte_en_cours: "Une collecte ou une vérification est déjà en cours.",
  configuration_non_designee: "Aucune configuration n'est désignée : cette console sert l'exemple. Pose VEILLE_CONFIG (docs/exploitation.md, « La configuration désignée »).",
  connexion_impossible: "La passkey n'a pas été reconnue.",
  etat_incompatible: "Cette offre n'a plus de candidature à préparer : elle est envoyée, en entretien ou close.",
  preparation_en_cours: "La préparation de cette offre tourne déjà : attends qu'elle finisse.",
};

async function api(url, options = {}) {
  const rep = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (rep.status === 401) { location.href = '/connexion'; throw new Error('session expiree'); }
  if (!rep.ok) {
    let detail = rep.statusText;
    try {
      const corps = await rep.json();
      detail = corps.detail || ERREURS_API[corps.erreur] || corps.erreur || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return rep.status === 204 ? null : rep.json();
}

const niveau = s => (s >= SEUIL ? 'bonne' : s >= SEUIL / 2 ? 'moyenne' : 'faible');

// ---------------------------------------------------------------------------
// Rendu d'une offre
// ---------------------------------------------------------------------------

// Le salaire publié, ou son absence : la carte d'une offre et celle de « À voir ».
function etiquetteSalaire(o) {
  if (!o.salaire_min && !o.salaire_max) {
    return '<span class="etiquette alerte">salaire non publie</span>';
  }
  const s = o.salaire_min && o.salaire_max && o.salaire_min !== o.salaire_max
    ? `${Math.round(o.salaire_min).toLocaleString('fr-FR')} - ${Math.round(o.salaire_max).toLocaleString('fr-FR')}`
    : Math.round(o.salaire_max || o.salaire_min).toLocaleString('fr-FR');
  return `<span class="etiquette">${s} ${echapper(o.salaire_devise || '')}</span>`;
}

// Les lignes de « Pourquoi ce score » : une par contribution de `o.explication`.
function listeContributions(o) {
  return (o.explication || []).map(c => {
    const cls = c.points > 0 ? 'plus' : c.points < 0 ? 'moins' : 'zero';
    const signe = c.points > 0 ? '+' : '';
    return `<li><span class="pts ${cls}">${signe}${echapper(c.points)}</span>
      <span><b>${echapper(c.libelle)}</b>${c.detail ? ` <span class="contrib-detail">${echapper(c.detail)}</span>` : ''}</span></li>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Le geste manuel : un clic depuis la liste, réversible d'un autre clic
// ---------------------------------------------------------------------------

async function constater(id, enLigne) {
  // `api()` et pas `fetch()` : `fetch` ne leve RIEN sur un 404. C'est ce qui a
  // fait croire a des archivages qui n'avaient pas eu lieu.
  await api(`/api/offres/${id}/constat?en_ligne=${enLigne ? 'true' : 'false'}`,
            { method: 'POST' });
  // La vue courante, pas la liste des offres : le geste vient aussi de « À faire ».
  rafraichir();
  message(enLigne ? 'Notée encore en ligne.' : 'Archivée — annulable dans Plus › Bilan.');
}

// ---------------------------------------------------------------------------
// Toutes les offres (ADR-0003, § 6 ; décisions 2 à 6 du plan du lot 3)
//
// Trois filtres toujours visibles, la recherche, l'état et la famille, puis la bascule de
// l'atout mis en avant. Chaque offre est une ligne qui ouvre sa fiche (`ligneOffre`). Sans
// état, la liste montre les offres en cours ; une recherche sans état porte sur toutes les
// offres, closes et mises de côté comprises. Le résumé dit le vrai nombre (`total`), nomme
// les filtres actifs, et « Effacer les filtres » les retire, liste vide ou non.
// ---------------------------------------------------------------------------

// L'atout filtré : celui de la bascule, ou celui d'un ancien lien d'entrée (`?atout=`).
let atoutFiltre = '';
// Le numéro de la dernière demande : une réponse plus ancienne arrive trop tard (point
// d'attention 3 du plan du lot 3), elle ne remplace pas la liste.
let numeroOffres = 0;
// La recherche attend 280 ms de calme : une frappe rapide n'envoie qu'une demande.
let minuteurRecherche;

const PORTEE_RECHERCHE = 'La recherche porte sur toutes les offres, closes et mises de côté comprises.';

// Les filtres actifs, nommés comme le résumé les dit. L'atout mis en avant se nomme par son
// libellé ; un autre, que la page ne connaît pas, par sa clé (décision 3).
function filtresActifs() {
  const actifs = [];
  const recherche = $('#f-recherche').value.trim();
  if (recherche) actifs.push({ cle: 'recherche', libelle: 'Recherche', valeur: recherche });
  for (const [id, cle, libelle] of [['#f-etat', 'etat', 'État'], ['#f-famille', 'famille', 'Famille']]) {
    const champ = $(id);
    if (champ.value) {
      actifs.push({ cle, libelle, valeur: champ.options[champ.selectedIndex].textContent.trim() });
    }
  }
  if (atoutFiltre) {
    actifs.push({ cle: 'atout', libelle: 'Atout',
                  valeur: ATOUT && atoutFiltre === ATOUT.cle ? ATOUT.libelle : atoutFiltre });
  }
  return actifs;
}

// Ce que la liste demande. L'état part au serveur, qui le traduit en statuts (`etats.py`) ;
// `inclure_ecartees` ne part que pour une recherche sans état (décision 4).
function parametresOffres() {
  const p = new URLSearchParams();
  const recherche = $('#f-recherche').value.trim();
  const etat = $('#f-etat').value;
  if (recherche) p.set('recherche', recherche);
  if (etat) p.set('etat', etat);
  else if (recherche) p.set('inclure_ecartees', 'true');
  if ($('#f-famille').value) p.set('famille', $('#f-famille').value);
  if (atoutFiltre) p.set('atout', atoutFiltre);
  return p;
}

// Les trois champs et l'atout, vidés, sans recharger la liste.
function viderFiltres() {
  clearTimeout(minuteurRecherche);
  $('#f-recherche').value = '';
  $('#f-etat').value = '';
  $('#f-famille').value = '';
  atoutFiltre = '';
}

function effacerFiltres() {
  viderFiltres();
  chargerOffres();
}

// « a », « a et b », « a, b et c ».
function enumerer(textes) {
  return textes.length < 2 ? textes.join('')
    : `${textes.slice(0, -1).join(', ')} et ${textes[textes.length - 1]}`;
}

// Le résumé : le vrai nombre, le plafond s'il est atteint, la portée d'une recherche sans
// état, puis les filtres actifs et « Effacer les filtres ». Une liste vide se dit ici aussi :
// jamais une base qui paraît vide quand un filtre la restreint.
function resumeOffres(d, actifs, p) {
  const nommes = enumerer(actifs.map(a =>
    `<b>${echapper(a.libelle.toLowerCase())} : ${echapper(a.valeur)}</b>`));
  const portee = p.has('inclure_ecartees') ? ` ${PORTEE_RECHERCHE}` : '';
  const effacer = actifs.length
    ? ' <button class="discret" data-effacer-filtres>Effacer les filtres</button>' : '';
  if (!d.offres.length) {
    return actifs.length ? `Aucune offre avec ${nommes}.${portee}${effacer}`
      : "Aucune offre en cours. Les closes et les mises de côté se voient par le filtre d'état.";
  }
  const total = Number(d.total ?? d.offres.length);
  const bonnes = d.offres.filter(o => o.score >= SEUIL).length;
  let html = `${total} offre(s), dont ${bonnes} au-dessus du seuil de ${SEUIL}.`;
  // Plafonnée (200 lignes, `app.py`), la liste le dit : ses lignes viennent par score.
  if (total > d.offres.length) html += ` Les ${d.offres.length} premières, par score.`;
  return html + portee + (actifs.length ? ` Avec ${nommes}.` : '') + effacer;
}

function marquerBascule() {
  $('#btn-atout').setAttribute('aria-pressed', String(Boolean(ATOUT) && atoutFiltre === ATOUT.cle));
}

async function chargerOffres() {
  clearTimeout(minuteurRecherche);
  const numero = ++numeroOffres;
  const p = parametresOffres();
  const actifs = filtresActifs();
  marquerBascule();
  try {
    const d = await api('/api/offres?' + p);
    // Une demande plus récente est partie : c'est sa réponse qui dira la liste.
    if (numero !== numeroOffres) return;
    // `ligneOffre(o)`, pas `map(ligneOffre)` : l'indice deviendrait sa précision.
    $('#liste-offres').innerHTML = d.offres.map(o => ligneOffre(o)).join('');
    $('#resume-offres').innerHTML = resumeOffres(d, actifs, p);
  } catch (e) {
    if (numero === numeroOffres) message(e.message, true);
  }
}

// ---------------------------------------------------------------------------
// Chargement des listes
// ---------------------------------------------------------------------------

function tableau(titre, lignes, colonnes) {
  if (!lignes.length) return '';
  const entetes = colonnes.map(c => `<th class="${c.n ? 'n' : ''}">${c.libelle}</th>`).join('');
  const corps = lignes.map(l =>
    '<tr>' + colonnes.map(c => `<td class="${c.n ? 'n' : ''}">${echapper(c.valeur(l))}</td>`).join('') + '</tr>'
  ).join('');
  return `<div class="bloc"><h2>${titre}</h2><table><thead><tr>${entetes}</tr></thead><tbody>${corps}</tbody></table></div>`;
}

// L'entonnoir du Bilan et ses tableaux, repris de l'ancien Pilotage (décision 7 du plan du
// lot 3) : le canal demandé à « Je l'ai envoyée » ne servirait à rien sans le sien.
function blocsEntonnoir(e) {
  let html = `<div class="bloc"><h2>Entonnoir</h2><div class="chiffres">
    <div class="chiffre"><b>${echapper(e.total)}</b><span>offres collectées</span></div>
    <div class="chiffre"><b>${echapper(e.par_statut.nouveau || 0)}</b><span>nouvelles</span></div>
    <div class="chiffre"><b>${echapper(e.envoyees)}</b><span>candidatures</span></div>
    <div class="chiffre"><b>${echapper(e.repondues)}</b><span>réponses</span></div>
    <div class="chiffre"><b>${echapper(e.taux_reponse_global)}%</b><span>taux de réponse</span></div>
  </div></div>`;

  html += tableau('Par canal de candidature', e.par_canal, [
    { libelle: 'Canal', valeur: l => l.canal },
    { libelle: 'Envoyées', n: 1, valeur: l => l.envoyees },
    { libelle: 'Réponses', n: 1, valeur: l => l.reponses },
    { libelle: 'Taux', n: 1, valeur: l => l.taux_reponse + '%' },
  ]);
  html += tableau('Par famille de métier', e.par_famille, [
    { libelle: 'Famille', valeur: l => l.famille },
    { libelle: 'Envoyées', n: 1, valeur: l => l.envoyees },
    { libelle: 'Réponses', n: 1, valeur: l => l.reponses },
    { libelle: 'Taux', n: 1, valeur: l => l.taux_reponse + '%' },
  ]);
  html += tableau('Rendement des sources', e.par_source, [
    { libelle: 'Source', valeur: l => l.source },
    { libelle: 'Collectées', n: 1, valeur: l => l.collectees },
    { libelle: 'Retenues', n: 1, valeur: l => l.retenues },
    { libelle: 'Candidatures', n: 1, valeur: l => l.candidatures },
  ]);
  html += tableau("Motifs d'écartement : ce que le score rate", e.motifs_ecartement, [
    { libelle: 'Motif', valeur: l => l.motif },
    { libelle: 'Nombre', n: 1, valeur: l => l.n },
    { libelle: 'Score moyen', n: 1, valeur: l => l.score_moyen },
  ]);
  // Les critères arrivent par le déploiement, dans la configuration de l'instance : la
  // console ne les change pas (décision 10).
  if (e.motifs_ecartement.length >= 30) {
    html += `<div class="bloc"><p class="resume">Tu as passé les 30 motifs d'écartement :
      ils sont maintenant assez nombreux pour dire ce que le score rate. Regarde ceux qui
      reviennent avec un score élevé : ce sont des règles à ajouter au <code>criteres.yaml</code>
      de la configuration de l'instance, qui arrive par le déploiement.</p></div>`;
  }
  return html;
}

// ---------------------------------------------------------------------------
// Documents — ses pièces, accessibles depuis le téléphone
// ---------------------------------------------------------------------------

function ligneFichier(lien, f) {
  const contexte = f.contexte ? `<span class="etiquette">${echapper(f.contexte)}</span>` : '';
  // Téléchargement par défaut : un PDF se lit mal dans un onglet de téléphone.
  return `<li class="fichier">
    <a href="${lien}" download>${echapper(f.nom)}</a>
    ${contexte}
    <span class="menu">${echapper(f.taille)} · ${echapper(f.modifie_le)}</span>
  </li>`;
}

async function chargerDocuments() {
  const cible = $('#contenu-documents');
  try {
    const [kit, dossiers] = await Promise.all([
      api('/api/documents/kit'),
      api('/api/documents/dossiers'),
    ]);

    let html = '';

    if (!kit.present || !kit.total) {
      html += `<div class="bloc"><h2>Kit de candidature</h2>
        <p class="avert">${echapper(kit.message || 'Kit vide.')}</p>
        <p class="resume">Emplacement lu : <code>${echapper(kit.emplacement)}</code></p></div>`;
    } else {
      html += `<div class="bloc"><h2>Kit de candidature — ${kit.total} document(s)</h2>`;
      for (const g of kit.groupes) {
        html += `<h3 class="sous-titre">${echapper(g.categorie)}</h3><ul class="fichiers">`;
        html += g.documents.map(f =>
          ligneFichier(`/api/documents/kit/${encodeURIComponent(f.nom)}`, f)).join('');
        html += '</ul>';
      }
      html += `<p class="resume">Lu depuis <code>${echapper(kit.emplacement)}</code>
        — le dossier est relu à chaque ouverture, tu peux y ajouter des pièces quand tu veux.</p></div>`;
    }

    if (dossiers.dossiers.length) {
      html += `<div class="bloc"><h2>Dossiers générés — ${dossiers.dossiers.length}</h2>`;
      for (const d of dossiers.dossiers) {
        const statut = d.statut ? `<span class="etiquette">${echapper(d.statut.replace(/_/g, ' '))}</span>` : '';
        html += `<h3 class="sous-titre">${echapper(d.titre)}
          ${d.employeur ? '— ' + echapper(d.employeur) : ''} ${statut}
          <span class="menu">${echapper(d.cree_le)}</span></h3><ul class="fichiers">`;
        html += d.fichiers.map(f =>
          ligneFichier(`/api/documents/dossiers/${encodeURIComponent(d.dossier)}/${encodeURIComponent(f.nom)}`, f)).join('');
        html += '</ul>';
      }
      html += '</div>';
    } else {
      html += `<div class="bloc"><h2>Dossiers générés</h2>
        <p class="resume">Aucun pour l'instant. « Je postule », sur une offre,
        prépare son dossier, et il apparaîtra ici.</p></div>`;
    }

    cible.innerHTML = html;
  } catch (e) { message(e.message, true); }
}

// ---------------------------------------------------------------------------
// Réglages — ce qui s'ajuste sans SSH
// ---------------------------------------------------------------------------

// « Notifications » et « Quitter » sont écrits dans la page, hors de ce que cette fonction
// réécrit : ils restent quand `/api/reglages` échoue (décision 11 du plan du lot 3).
async function chargerReglages() {
  afficherEtatPush();
  const cible = $('#contenu-reglages');
  try {
    const r = await api('/api/reglages');

    const sources = r.sources.map(s => `
      <tr>
        <td>${echapper(s.libelle)}</td>
        <td>${s.pret ? '<span class="etiquette bon">prête</span>'
                     : `<span class="etiquette alerte">${echapper(s.manque)}</span>`}</td>
        <td class="menu">${echapper(s.dernier_resultat || '—')}</td>
      </tr>`).join('');

    const frequences = r.frequence.choix.map(c => `
      <label class="choix">
        <input type="radio" name="frequence" value="${c.cle}"
               ${c.cle === r.frequence.cle ? 'checked' : ''}>
        <span><b>${echapper(c.libelle)}</b><br>
        <span class="menu">${echapper(c.detail)}</span></span>
      </label>`).join('');

    cible.innerHTML = `
      <div class="bloc">
        <h2>Seuil de notification</h2>
        <p class="resume">Une offre ne fait sonner ton téléphone qu'au-dessus de ce score.
          Monte-le si tu es dérangé pour rien, descends-le si tu rates des choses.</p>
        <div class="formulaire enligne">
          <input type="number" id="seuil" value="${r.seuil}" min="0" max="200" step="5">
          <button id="btn-seuil">Enregistrer</button>
        </div>
      </div>

      <div class="bloc">
        <h2>Fréquence de collecte</h2>
        ${frequences}
        ${r.frequence.etat === 'indisponible'
          ? `<p class="avert">Fréquence indisponible : ${echapper(r.frequence.raison || '')}</p>` : ''}
        ${r.frequence.personnalise
          ? `<p class="avert">Réglage personnalisé en place :
             <code>${echapper(r.frequence.oncalendar)}</code>. Choisir ci-dessus le remplacera.</p>` : ''}
        <p class="resume">Prochain passage : ${echapper(r.frequence.prochain_passage || 'inconnu')}</p>
        <div class="actions">
          <button id="btn-frequence">Appliquer</button>
          <button class="discret" id="btn-collecter">Collecter maintenant</button>
        </div>
      </div>

      <div class="bloc">
        <h2>Sources</h2>
        <table><thead><tr><th>Source</th><th>État</th><th>Dernier passage</th></tr></thead>
        <tbody>${sources}</tbody></table>
      </div>

      <div class="bloc">
        <h2>Appareils</h2>
        <p class="resume">Les appareils connectés à la console. Déconnecte celui que tu ne reconnais pas.</p>
        <div id="liste-appareils"></div>
        <div class="actions">
          <button id="btn-ajouter-appareil">Ajouter un appareil</button>
        </div>
        <div id="zone-lien"></div>
      </div>

      <div class="bloc">
        <h2>Passkeys</h2>
        <p class="resume">Chacune ouvre une session sur son appareil. Déconnecter un appareil
          ne retire pas sa passkey : celle que tu ne reconnais pas se retire sur le serveur,
          par <code>veille passkeys --retirer &lt;n°&gt;</code>.</p>
        <div id="liste-passkeys"></div>
      </div>

      <div class="bloc">
        <h2>Emplacements</h2>
        <p class="resume">Kit lu depuis <code>${echapper(r.emplacement_kit)}</code><br>
        Base de données : <code>${echapper(r.emplacement_base)}</code></p>
      </div>`;

    $('#btn-seuil').onclick = async ev => {
      ev.target.disabled = true;
      try {
        const d = await api('/api/reglages/seuil', {
          method: 'POST', body: JSON.stringify({ valeur: Number($('#seuil').value) }),
        });
        message(`Seuil réglé sur ${d.seuil}. Recalcule les scores pour l'appliquer aux offres existantes.`);
      } catch (e) { message(e.message, true); }
      finally { ev.target.disabled = false; }
    };

    $('#btn-frequence').onclick = async ev => {
      const choisi = $$('input[name=frequence]').find(i => i.checked);
      if (!choisi) { message('Choisis une fréquence.', true); return; }
      ev.target.disabled = true;
      try {
        await api('/api/reglages/frequence', { method: 'POST', body: JSON.stringify({ cle: choisi.value }) });
        message('Fréquence appliquée.');
        chargerReglages();
      } catch (e) { message(e.message, true); }
      finally { ev.target.disabled = false; }
    };

    $('#btn-collecter').onclick = async ev => {
      ev.target.disabled = true;
      try {
        const d = await api('/api/reglages/collecter', { method: 'POST' });
        message(d.message);
      } catch (e) { message(e.message, true); }
      finally { ev.target.disabled = false; }
    };

    chargerAppareils();
    $('#btn-ajouter-appareil').onclick = ajouterAppareil;
  } catch (e) { message(e.message, true); }
}

// Appareils : les sessions ouvertes, un lien pour en ajouter un, et les
// passkeys en lecture seule (elles se retirent sur le serveur)
async function chargerAppareils() {
  const cible = $('#liste-appareils');
  if (!cible) return;
  try {
    const r = await api('/api/auth/appareils');
    cible.innerHTML = r.sessions.map(s => `
      <div class="ligne-appareil" style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin:8px 0">
        <span><b>${echapper(s.appareil)}</b>${s.courante ? ' <span class="etiquette bon">cet appareil</span>' : ''}<br>
        <span class="menu">Connecté le ${echapper(s.cree_le)} · vu le ${echapper(s.vue_le)}</span></span>
        <button class="discret" data-session="${Number(s.id)}"
                data-courante="${s.courante ? '1' : ''}">Déconnecter</button>
      </div>`).join('') || '<p class="menu">Aucun appareil.</p>';
    const passkeys = $('#liste-passkeys');
    if (passkeys) {
      passkeys.innerHTML = r.passkeys.map(p => `
        <div class="ligne-passkey" style="margin:8px 0">
          <b>${echapper(p.appareil)}</b> <span class="menu">n° ${Number(p.id)}</span><br>
          <span class="menu">Créée le ${echapper(p.cree_le)} · ${p.utilisee_le
            ? `utilisée le ${echapper(p.utilisee_le)}` : 'jamais utilisée'}</span>
        </div>`).join('') || '<p class="menu">Aucune passkey.</p>';
    }
    $$('button[data-session]', cible).forEach(b => {
      b.onclick = async () => {
        const courante = b.dataset.courante === '1';
        if (courante && !confirm('Te déconnecter de cet appareil ?')) return;
        b.disabled = true;
        try {
          await api(`/api/auth/sessions/${b.dataset.session}`, { method: 'DELETE' });
          if (courante) { location.href = '/connexion'; return; }
          message('Appareil déconnecté.');
          chargerAppareils();
        } catch (e) { message(e.message, true); b.disabled = false; }
      };
    });
  } catch (e) { message(e.message, true); }
}

async function ajouterAppareil(ev) {
  ev.target.disabled = true;
  try {
    // Une nouvelle touche de passkey d'abord : une session volée ne suffit pas.
    const debut = await api('/api/auth/connexion/options', { method: 'POST' });
    const options = PublicKeyCredential.parseRequestOptionsFromJSON(debut.options);
    const credential = await navigator.credentials.get({ publicKey: options });
    const d = await api('/api/auth/lien/creer', {
      method: 'POST',
      body: JSON.stringify({ cle: debut.cle, reponse: credential.toJSON() }),
    });
    $('#zone-lien').innerHTML = `
      <p class="resume">Ouvre ce lien sur le nouvel appareil. Il vaut 24 heures et ne sert qu'une fois.</p>
      <input type="text" id="adresse-lien" readonly value="${echapper(d.adresse)}">`;
    const champ = $('#adresse-lien');
    champ.onfocus = () => champ.select();
    champ.select();
    if (navigator.share) {
      try { await navigator.share({ url: d.adresse }); } catch (_) { /* partage annulé */ }
    }
  } catch (e) {
    if (e && e.name === 'NotAllowedError') message('Ajout annulé.');
    else message(e.message, true);
  }
  finally { ev.target.disabled = false; }
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function changerStatut(id, statut, motif, canal) {
  await api(`/api/offres/${id}/statut`, {
    method: 'POST',
    body: JSON.stringify({ statut, motif, canal }),
  });
  message('Statut mis a jour.');
  rafraichir();
}

function demanderCanal(id) {
  $('#fenetre-contenu').innerHTML = `
    <h2>Candidature envoyee</h2>
    <p class="resume">Par quel canal ? C'est ce qui permettra de savoir lesquels repondent.
    La relance sera programmee dans 10 jours.</p>
    <div class="actions">
      ${['site employeur', 'LinkedIn', 'mail direct', 'cabinet', 'cooptation', 'autre']
        .map(c => `<button class="discret" data-canal="${c}">${c}</button>`).join('')}
    </div>`;
  ouvrirFenetre();
  $$('#fenetre-contenu [data-canal]').forEach(b => {
    b.onclick = async () => {
      $('#fenetre').close();
      try { await changerStatut(id, 'candidature_envoyee', null, b.dataset.canal); }
      catch (e) { message(e.message, true); }
    };
  });
}

// ---------------------------------------------------------------------------
// La file « À faire » (ADR-0003, § 3)
//
// Ce qui attend un geste, puis les offres à voir au-dessus du seuil, puis celles
// remises à plus tard. Une offre à voir se décide d'un toucher : Je postule, Plus
// tard ou Non. Rien à montrer se dit en une phrase, jamais par un écran blanc.
// ---------------------------------------------------------------------------

const RAISONS = {
  relance_due: 'Relance due',
  a_envoyer: 'Dossier prêt à envoyer',
  a_preparer: 'Dossier à préparer',
};

// Les cinq états, et la mise de côté, tels que l'écran les nomme (`etats.py` produit ces clés).
const LIBELLES_ETAT = {
  a_voir: 'À voir',
  je_postule: 'Je postule',
  envoyee: 'Envoyée',
  entretien: 'Entretien',
  close: 'Close',
  mise_de_cote: 'Mise de côté',
};

// Remise à plus tard, l'offre reste « À voir », mais s'affiche « Plus tard » (ADR-0003, § 1).
function libelleEtat(o) {
  return o.statut === 'a_traiter' ? 'Plus tard' : (LIBELLES_ETAT[o.etat] || o.etat || '');
}

// Une ligne d'offre (décision 6 du plan du lot 3) : un bouton qui ouvre la fiche, avec
// l'intitulé, l'employeur, le score, l'état et, au Bilan, ce qui la situe (`precision`).
function ligneOffre(o, precision = '') {
  const n = niveau(o.score);
  return `<button class="offre ligne-offre" data-action="fiche" data-id="${Number(o.id)}">
    <span class="ligne-offre-haut">
      <span class="offre-titre">${echapper(o.titre)}</span>
      <span class="score ${n}">${echapper(o.score)}</span>
    </span>
    ${o.employeur ? `<span class="menu">${echapper(o.employeur)}</span>` : ''}
    <span class="ligne-offre-bas">
      <span class="etat-ligne">${echapper(libelleEtat(o))}</span>
      ${precision ? `<span class="precision">${echapper(precision)}</span>` : ''}
    </span>
  </button>`;
}

// Seules une candidature et une relance envoyées attendent une relance (`db.relances_dues`).
// Une réponse reçue garde en base la date de son envoi : l'écran ne la montre pas.
function relanceAttendue(o) {
  return (o.statut === 'candidature_envoyee' || o.statut === 'relance_envoyee')
    && Boolean(o.date_relance_due);
}

// Un geste neuf ne part qu'une fois : son bouton se désactive avant toute attente, et ne
// revient qu'en cas d'échec. Un succès recharge la vue, qui remplace le bouton.
function gesteNeuf(bouton, geste) {
  bouton.disabled = true;
  geste().catch(e => { bouton.disabled = false; message(e.message, true); });
}

function ligneAFinir(o) {
  return `<button class="offre ligne-a-finir" data-action="fiche" data-id="${Number(o.id)}">
    <span class="raison ${echapper(o.raison)}">${echapper(RAISONS[o.raison] || o.raison)}</span>
    <span class="offre-titre">${echapper(o.titre)}</span>
    ${o.employeur ? `<span class="menu">${echapper(o.employeur)}</span>` : ''}
  </button>`;
}

// De quoi décider, et rien de plus. Remise à plus tard, l'offre perd son bouton « Plus tard ».
function carteAVoir(o) {
  const n = niveau(o.score);
  const plusTard = o.statut === 'a_traiter';
  const meta = [o.employeur, o.lieu].filter(Boolean)
    .map(x => `<span>${echapper(x)}</span>`).join('');
  const fortes = (o.explication || []).filter(c => c.points > 0)
    .sort((a, b) => b.points - a.points).slice(0, 2);
  const contribs = listeContributions({ explication: fortes });
  return `
  <article class="offre ${plusTard ? 'carte-plus-tard' : 'carte-a-voir'} ${n}" data-id="${Number(o.id)}">
    <div class="offre-haut">
      <button class="offre-titre" data-action="fiche">${echapper(o.titre)}</button>
      <span class="score ${n}">${echapper(o.score)}</span>
    </div>
    <div class="meta">${meta}</div>
    <div class="etiquettes">${etiquetteSalaire(o)}</div>
    ${contribs ? `<ul class="contribs">${contribs}</ul>` : ''}
    <div class="actions">
      <button data-action="postuler">Je postule</button>
      ${plusTard ? '' : '<button class="discret" data-action="plus-tard">Plus tard</button>'}
      <button class="discret" data-action="non">Non</button>
    </div>
  </article>`;
}

// Les offres que la file ne montre pas, au-dessus du seuil au-delà des premières, ou
// dessous : « Toutes les offres », filtrée sur l'état « À voir ».
function liensVersToutes(d) {
  const textes = [];
  if (d.a_voir_restantes) {
    textes.push(d.a_voir_restantes === 1 ? "Voir l'autre offre au-dessus du seuil ›"
      : `Voir les ${Number(d.a_voir_restantes)} autres au-dessus du seuil ›`);
  }
  if (d.sous_le_seuil) {
    textes.push(d.sous_le_seuil === 1 ? "Voir l'offre sous le seuil ›"
      : `Voir les ${Number(d.sous_le_seuil)} sous le seuil ›`);
  }
  if (!textes.length) return '';
  return `<div class="vers-toutes">${textes.map(t =>
    `<button data-vers-toutes>${echapper(t)}</button>`).join('')}</div>`;
}

async function chargerAFaire() {
  const cible = $('#contenu-a-faire');
  try {
    const d = await api('/api/a-faire');
    const seuil = echapper(d.seuil);
    // Un rechargement après un geste ne referme pas « Plus tard ».
    const plusTardOuvert = Boolean($('details.plus-tard', cible)?.open);
    let html;
    if (!d.a_finir.length && !d.a_voir.length && !d.plus_tard.length) {
      html = `<p class="resume">Rien à faire pour l'instant : aucune offre au-dessus du seuil de ${seuil}.</p>`
        + liensVersToutes(d);
    } else {
      html = '';
      if (d.a_finir.length) {
        html += `<h2 class="titre-groupe">À finir</h2>
          <div class="liste">${d.a_finir.map(ligneAFinir).join('')}</div>`;
      }
      html += '<h2 class="titre-groupe">À voir</h2>';
      html += d.a_voir.length
        ? `<div class="liste">${d.a_voir.map(carteAVoir).join('')}</div>`
        : `<p class="resume">Aucune offre au-dessus du seuil de ${seuil}.</p>`;
      html += liensVersToutes(d);
      if (d.plus_tard.length) {
        html += `<details class="plus-tard"${plusTardOuvert ? ' open' : ''}>
          <summary>Plus tard (${d.plus_tard.length})</summary>
          <div class="liste">${d.plus_tard.map(carteAVoir).join('')}</div></details>`;
      }
    }
    cible.innerHTML = html;
    // L'état « À voir », les autres filtres vidés : il ramène aussi les « Plus tard » et les
    // offres au-dessus du seuil (décision 3 du plan du lot 3, réponse 25).
    $$('[data-vers-toutes]', cible).forEach(b => {
      b.onclick = () => {
        viderFiltres();
        $('#f-etat').value = 'a_voir';
        afficherVue('offres');
      };
    });
  } catch (e) {
    message(e.message, true);
    if (!cible.children.length) {
      cible.innerHTML = `<p class="avert">La file n'a pas pu se charger : ${echapper(e.message)}</p>`;
    }
  }
}

// « Non » : le motif reste obligatoire, c'est lui qui dit ce que le score rate. Les plus
// fréquents se choisissent d'un toucher. Une annonce disparue s'archive, sans motif.
// Le panneau s'ouvre tout de suite, au nom de l'offre : rien ne le lie à une autre offre
// touchée pendant que les motifs fréquents arrivent.
function demanderNon(id, titre) {
  $('#fenetre-contenu').innerHTML = `
    <h2>Pourquoi non ?</h2>
    <p class="titre-panneau">${echapper(titre)}</p>
    <p class="resume">Le motif est obligatoire : c'est lui qui dira ce que le score rate.</p>
    <div class="motifs" data-pour="${Number(id)}"></div>
    <textarea id="motif-non" placeholder="Ou écris-le : trop junior, stack sans rapport…"></textarea>
    <div class="actions">
      <button id="btn-ecarter-non">Écarter</button>
      <button class="discret" id="btn-plus-en-ligne">N'est plus en ligne</button>
      <button class="discret" id="btn-annuler-non">Annuler</button>
    </div>`;
  const fenetre = $('#fenetre');
  ouvrirFenetre();
  remplirMotifs(id);
  $('#btn-annuler-non').onclick = () => fenetre.close();
  $('#btn-ecarter-non').onclick = ev => {
    const motif = $('#motif-non').value.trim();
    if (!motif) { message('Un motif est nécessaire.', true); return; }
    gesteNeuf(ev.currentTarget, async () => {
      await changerStatut(id, 'ecartee', motif);
      fenetre.close();
    });
  };
  $('#btn-plus-en-ligne').onclick = ev => gesteNeuf(ev.currentTarget, async () => {
    await constater(id, false);
    fenetre.close();
  });
}

// Les motifs fréquents ne vont qu'au panneau de leur offre, s'il est encore affiché : un
// « Non » touché entre-temps sur une autre offre a pris sa place.
async function remplirMotifs(id) {
  let motifs;
  try { motifs = (await api('/api/motifs?limite=6')).motifs || []; }
  catch (e) { return; /* sans les motifs fréquents, le champ libre suffit */ }
  const zone = $(`#fenetre-contenu .motifs[data-pour="${Number(id)}"]`);
  if (!zone || !$('#fenetre').open) return;
  zone.innerHTML = motifs.map(m =>
    `<button class="discret" data-motif="${echapper(m)}">${echapper(m)}</button>`).join('');
  $$('[data-motif]', zone).forEach(b => {
    b.onclick = () => { $('#motif-non').value = b.dataset.motif; };
  });
}

// Les pastilles (décision 9 du plan du lot 3) : l'onglet « Plus » et la ligne « Mes
// critères » comptent les offres à classer, la ligne « Bilan » les archivées nouvelles depuis
// la dernière visite. `rafraichir()` les recompte : l'onglet dit juste depuis tout écran. Une
// panne ne dit rien, chacune pour son compte : elles tournent à chaque geste.
function poserPastille(selecteur, nombre) {
  const pastille = $(selecteur);
  if (pastille) pastille.textContent = nombre ? String(nombre) : '';
}

async function compterPastilles() {
  const p = new URLSearchParams();
  const visite = derniereVisiteArchive();
  if (visite) p.set('depuis', visite);
  p.set('limite', '1');
  await Promise.all([
    api('/api/classement').then(c => {
      poserPastille('#pastille-plus', c.propositions.length);
      poserPastille('#pastille-criteres', c.propositions.length);
    }).catch(() => { /* hors ligne : on ne casse pas la page */ }),
    api(`/api/archive?${p}`).then(r => poserPastille('#pastille-bilan', r.nouvelles))
      .catch(() => { /* hors ligne : on ne casse pas la page */ }),
  ]);
}

// ---------------------------------------------------------------------------
// La fiche par état (ADR-0003, § 4)
//
// L'offre, son état, et une seule ligne d'actions : celle de cet état. Le reste attend,
// replié : pourquoi ce score, les notes, les autres actions. Un geste fait depuis la fiche
// la rouvre sur le nouvel état ; ceux qui ouvrent leur propre fenêtre (la préparation, le
// canal, la relance, l'entretien, « Non ») y prennent sa place.
// ---------------------------------------------------------------------------

// La réponse du recruteur, d'un toucher : chaque bouton écrit son statut.
function boutonsReponse(reponses) {
  return '<span class="libelle-reponse">Réponse :</span>' + reponses.map(([statut, texte]) =>
    `<button class="discret" data-action="reponse" data-statut="${statut}">${texte}</button>`).join('');
}

function actionsDeFiche(o) {
  switch (o.etat) {
    case 'a_voir':
    case 'mise_de_cote':
      // Remise à plus tard, l'offre perd « Plus tard », comme sa carte.
      return `<button data-action="postuler">Je postule</button>
        ${o.statut === 'a_traiter' ? '' : '<button class="discret" data-action="plus-tard">Plus tard</button>'}
        <button class="discret" data-action="non">Non</button>`;
    case 'je_postule':
      // Sans dossier, la préparation ; avec, l'envoi, et « Dossier prêt », qui porte les pièces,
      // le destinataire et l'affinement (décision 12 du plan du lot 2). Les deux passent par
      // la même route : un dossier existant est rendu, jamais refait. Une candidature faite
      // sans dossier (un formulaire en ligne) se dit envoyée d'ici (décision 20 du plan du lot 3).
      if (!o.dossier_chemin) {
        return `<button data-action="preparer">Préparer ma candidature</button>
          <button class="discret" data-action="envoyee">Je l'ai envoyée</button>`;
      }
      return `<button data-action="envoyee">Je l'ai envoyée</button>
        <button class="discret" data-action="preparer">Dossier prêt ›</button>`;
    case 'envoyee':
      return `<button data-action="relance">Mot de relance</button>
        ${boutonsReponse([['entretien', 'Entretien'], ['refus', 'Refus'], ['accepte', 'Acceptée']])}
        ${relanceAttendue(o) ? `<span class="menu">Relance le ${echapper(o.date_relance_due)}</span>` : ''}`;
    case 'entretien':
      return `<button data-action="entretien">Préparer l'entretien</button>
        ${boutonsReponse([['refus', 'Refus'], ['accepte', 'Acceptée']])}`;
    default:
      // Close : aucune action. Le motif d'une écartée, s'il existe ; un refus ou une
      // acceptation peut garder en base le motif d'un ancien écartement, qui ne dit plus rien.
      return o.statut === 'ecartee' && o.motif_ecartement
        ? `<p class="motif">${echapper(o.motif_ecartement)}</p>` : '';
  }
}

function contenuFiche(o) {
  const n = niveau(o.score);
  const meta = [o.employeur, o.lieu].filter(Boolean)
    .map(x => `<span>${echapper(x)}</span>`).join('');
  const annonce = o.url
    ? `<a class="lien-annonce" href="${echapper(o.url)}" target="_blank" rel="noopener noreferrer">Voir l'annonce ›</a>`
    : '';
  const contribs = listeContributions(o);
  const etat = libelleEtat(o);
  return `
  <div class="offre fiche" data-id="${Number(o.id)}">
    <div class="offre-haut">
      <h2 class="offre-titre">${echapper(o.titre)}</h2>
      <span class="score ${n}">${echapper(o.score)}</span>
    </div>
    <div class="meta">${meta}</div>
    <div class="etat-et-annonce">
      <span class="etat-fiche">${echapper(etat)}</span>
      ${annonce}
    </div>
    <div class="actions ligne-actions">${actionsDeFiche(o)}</div>
    <details class="repli" data-repli="score">
      <summary>Pourquoi ce score</summary>
      <ul class="contribs">${contribs || '<li>aucune contribution</li>'}</ul>
    </details>
    <details class="repli" data-repli="notes">
      <summary>Notes</summary>
      <textarea id="notes-fiche" aria-label="Notes">${echapper(o.notes || '')}</textarea>
      <div class="actions"><button data-action="notes">Enregistrer</button></div>
    </details>
    <details class="repli" data-repli="autres">
      <summary>Autres actions</summary>
      <div class="actions">
        <button class="discret" data-action="detail">Texte, exigences, vérification, historique ›</button>
        ${o.etat === 'a_voir' ? '' : '<button class="discret" data-action="revenir">Revenir à « À voir »</button>'}
      </div>
    </details>
  </div>`;
}

async function ouvrirFiche(id) {
  const o = await api(`/api/offres/${id}`);
  const fenetre = $('#fenetre');
  const contenu = $('#fenetre-contenu');
  // Rouverte sur la même offre, après un geste, elle garde ouverts les volets qu'on avait ouverts.
  const avant = fenetre.open ? $('.fiche', contenu) : null;
  const ouverts = avant && Number(avant.dataset.id) === Number(o.id)
    ? $$('details[open]', avant).map(d => d.dataset.repli) : [];
  contenu.innerHTML = contenuFiche(o);
  $$('details[data-repli]', contenu).forEach(d => { d.open = ouverts.includes(d.dataset.repli); });
  ouvrirFenetre();
}

// Le statut, puis la fiche sur le nouvel état ; `changerStatut` recharge la vue de derrière.
// Si la fiche ne se recharge pas, le statut est pourtant écrit : la fiche d'avant, périmée,
// se ferme, et son bouton ne se réactive pas (un second toucher réécrirait le statut).
async function changerStatutPuisFiche(id, statut) {
  await changerStatut(id, statut);
  try {
    await ouvrirFiche(id);
  } catch (e) {
    $('#fenetre').close();
    message(`Statut enregistré, mais la fiche n'a pas pu se recharger : ${e.message}`, true);
  }
}

async function enregistrerNotes(id, bouton) {
  const notes = $('textarea', bouton.closest('.fiche')).value;
  await api(`/api/offres/${id}`, { method: 'POST', body: JSON.stringify({ notes }) });
  message('Notes enregistrées.');
  await ouvrirFiche(id);
}

// ---------------------------------------------------------------------------
// « Préparer ma candidature » (ADR-0003, § 5)
//
// « Je postule » met l'offre en `interessante` et lance la préparation, qui ne s'arrête que
// sur ce qui manque : le texte de l'annonce (`texte`), une information trop mince (`mince`),
// ou une génération en échec (`echec`). Sinon, le dossier est prêt (`pret`). Chaque écran
// prend la place de la fiche dans la fenêtre, et montre d'abord les avertissements de
// l'étape, l'alerte éliminatoire en tête (décision 5 du plan du lot 2).
// ---------------------------------------------------------------------------

// Le bouton se désactive pendant le travail, avec le temps écoulé : un double toucher ne
// lance rien deux fois. Il revient tel qu'il était s'il est encore dans la page, où l'écran
// de l'étape l'a souvent remplacé. La vue de derrière se recharge : « À finir » change.
async function preparerCandidature(id, bouton, options = {}) {
  const libelle = bouton.textContent;
  bouton.disabled = true;
  // Le minuteur de l'affinement (`brancherAffinement`) : un bouton muet passe pour cassé.
  const depart = Date.now();
  const rendreTemps = () => {
    bouton.textContent = `Préparation… ${Math.round((Date.now() - depart) / 1000)} s`;
  };
  rendreTemps();
  const minuteur = setInterval(rendreTemps, 1000);
  try {
    const r = await api(`/api/offres/${Number(id)}/preparer`, {
      method: 'POST',
      body: JSON.stringify(options),
    });
    afficherEtape(id, r, options);
    rafraichir();
  } catch (e) {
    message(e.message, true);
  } finally {
    clearInterval(minuteur);
    if (bouton.isConnected) {
      bouton.disabled = false;
      bouton.textContent = libelle;
    }
  }
}

function afficherEtape(id, r, options) {
  if (r.etape === 'texte') afficherEtapeTexte(id, r, options.texte);
  else if (r.etape === 'mince') afficherEtapeMince(id, r);
  else if (r.etape === 'echec') afficherEtapeEchec(id, r, options);
  else if (r.etape === 'pret') afficherDossierPret(id, r);
  else message(`Étape inconnue : ${r.etape}`, true);
}

// L'écran d'une étape, à la place de ce que montrait la fenêtre, ouverte s'il le faut. Il
// s'ouvre en haut, sur ses avertissements : la fenêtre (le `<dialog>`, qui défile) garderait
// sinon la position de l'écran d'avant, comme après « Enregistrer et régénérer » touché en bas.
function montrerEtape(html) {
  $('#fenetre-contenu').innerHTML = `<div class="etape">${html}</div>`;
  ouvrirFenetre();
  $('#fenetre').scrollTop = 0;
}

// Les avertissements de l'étape, dans l'ordre de la route : l'alerte éliminatoire d'abord.
function avertissementsEtape(r) {
  return (r.avertissements || []).map(a => `<p class="avert">${echapper(a)}</p>`).join('');
}

// Le lien de l'annonce ; sans adresse, rien.
function lienAnnonce(url, texte) {
  return url
    ? `<a class="lien-annonce" href="${echapper(url)}" target="_blank" rel="noopener noreferrer">${texte}</a>`
    : '';
}

// Le texte de l'annonce manque, et la lecture automatique n'a pas pu le prendre : il se colle.
// « Générer avec l'extrait » mène au dossier quand il ne se copie pas, comme une annonce
// LinkedIn ouverte dans son application (décision 4 du plan). Un texte refusé revient dans la
// zone : on le complète, plutôt que de le recopier au téléphone.
function afficherEtapeTexte(id, r, texte = '') {
  montrerEtape(`${avertissementsEtape(r)}
    <h2>Il manque le texte de l'annonce</h2>
    ${r.message ? `<p class="resume">${echapper(r.message)}</p>` : ''}
    ${lienAnnonce(r.url, "Ouvrir l'annonce ›")}
    <textarea id="texte-etape" aria-label="Texte de l'annonce"
              placeholder="Colle ici tout le texte de l'annonce, tel quel."></textarea>
    <div class="actions ligne-actions">
      <button id="btn-preparer-texte">Préparer avec ce texte</button>
      <button class="discret" id="btn-avec-extrait">Générer avec l'extrait</button>
    </div>
    <p class="menu">Avec l'extrait seul, la lettre sera plus générique.</p>`);
  $('#texte-etape').value = texte || '';
  $('#btn-preparer-texte').onclick = ev => {
    const colle = $('#texte-etape').value;
    if (!colle.trim()) { message("Colle d'abord le texte de l'annonce.", true); return; }
    preparerCandidature(id, ev.currentTarget, { texte: colle });
  };
  $('#btn-avec-extrait').onclick = ev => preparerCandidature(id, ev.currentTarget, { forcer: true });
}

// L'information reste trop mince pour une lettre qui tienne : ce qui manque, nommé, avec ce
// qui le comble. Le texte de l'annonce se colle, ou l'on génère quand même (`forcer`).
function afficherEtapeMince(id, r) {
  const c = r.completude || {};
  const manques = (r.manques || []).map(m =>
    `<li class="contre"><span class="pts moins">-${echapper(m.points)}</span>
      <span><b>${echapper(m.libelle)}</b><br>
      <span class="citation">${echapper(m.quoi_faire)}</span></span></li>`).join('');
  montrerEtape(`${avertissementsEtape(r)}
    <h2>Information trop mince pour un dossier sérieux</h2>
    <p class="avert grave"><b>Dossier ${echapper(c.score)}/100 — ${echapper(c.niveau)}</b><br>
      Le seuil est à ${echapper(c.seuil)}. Une lettre écrite là-dessus sera générique. Ce
      chiffre ne dit rien du score de correspondance : il dit ce qu'on sait du poste.</p>
    ${manques ? `<p class="resume"><b>Ce qui manque, par ordre d'importance</b></p>
      <ul class="preuves">${manques}</ul>` : ''}
    <div class="actions ligne-actions">
      <button id="btn-coller-texte">Coller le texte de l'annonce</button>
      <button class="discret" id="btn-quand-meme">Générer quand même</button>
    </div>`);
  $('#btn-coller-texte').onclick = () => afficherEtapeTexte(id, {
    ...r, message: "Colle tout le texte de l'annonce : la préparation reprend avec lui." });
  $('#btn-quand-meme').onclick = ev => preparerCandidature(id, ev.currentTarget, { forcer: true });
}

// La génération a échoué : sa cause, et « Réessayer » avec les mêmes options. Une
// régénération en échec se réessaie en régénérant : sans `regenerer`, la route rendrait
// l'ancien dossier, avec l'ancien destinataire sur la lettre, sans le dire. Elle a pu casser
// après avoir réécrit la lettre, avant le zip (le test T2-M2 de la préparation) : l'écran dit
// ce dossier à moitié refait, sans rien promettre de plus.
function afficherEtapeEchec(id, r, options = {}) {
  const moitie = options.regenerer
    ? `<p class="avert">Le dossier a pu rester à moitié refait : la lettre peut être déjà la
        nouvelle, et le zip encore l'ancien. Réessaie avant d'envoyer. La lettre d'avant est
        rangée dans l'historique du dossier.</p>` : '';
  montrerEtape(`${avertissementsEtape(r)}
    <h2>La génération a échoué</h2>
    <p class="avert grave">${echapper(r.message)}</p>
    ${moitie}
    <p class="resume">L'offre reste « Je postule », et un texte collé reste enregistré.</p>
    <div class="actions ligne-actions"><button id="btn-reessayer">Réessayer</button></div>`);
  $('#btn-reessayer').onclick = ev => preparerCandidature(id, ev.currentTarget, options);
}

// « Dossier prêt » : à qui la lettre est adressée, chaque pièce sous son nom d'envoi (un
// formulaire en ligne, au téléphone, les demande une à une), le paquet en zip, l'annonce,
// puis l'envoi. Le destinataire n'est jamais demandé avant : l'ajouter l'enregistre, puis
// régénère la lettre. Affiner la lettre ne régénère rien. Sans paquet d'envoi lisible (un
// dossier ancien, un paquet tronqué), ni pièce ni zip, mais « Régénérer le dossier »
// (décision 12 du plan).
//
// Le destinataire montré est celui de la lettre, d'après la note que chaque génération laisse
// (`destinataire_lettre`) : la base peut en porter un autre, enregistré depuis sans régénérer,
// et l'avertissement de la route le dit. Sans note (un dossier d'avant le lot 2), l'écran ne
// dit que le destinataire enregistré, sans affirmer que la lettre le porte. « Modifier le
// destinataire » préremplit toujours celui de la base (`destinataire`).
function afficherDossierPret(id, r) {
  const d = r.dossier || { pieces: [], archive: false, destinataire: {} };
  const dest = d.destinataire || {};
  const lettre = d.destinataire_lettre || null;
  const montre = lettre || dest;
  // À qui : le nom, sinon la formule d'appel, puis l'adresse, ligne à ligne.
  const qui = [montre.contact_nom || montre.contact_civilite,
               ...String(montre.adresse_entreprise || '').split('\n')]
    .map(l => String(l || '').trim()).filter(Boolean);
  const ecart = Boolean(lettre)
    && Object.keys(dest).some(cle => (lettre[cle] || '') !== (dest[cle] || ''));
  let adressee;
  if (qui.length) {
    adressee = `<p class="resume">${lettre ? 'Adressée à' : 'Destinataire enregistré :'} <b>${echapper(qui[0])}</b>${qui.slice(1).map(l => `<br>${echapper(l)}`).join('')}</p>`;
  } else if (lettre) {
    adressee = `<p class="resume">La lettre n'a pas de destinataire : elle le laisse en rouge dans le PDF, à compléter.</p>`;
  } else {
    // Sans note, la lettre peut porter un destinataire d'avant : n'en rien affirmer.
    adressee = `<p class="resume">Aucun destinataire n'est enregistré.</p>`;
  }
  // La référence part dans la lettre avec ou sans destinataire : elle se montre toujours.
  const reference = montre.reference_annonce
    ? `<p class="resume menu">Référence de l'annonce : ${echapper(montre.reference_annonce)}</p>` : '';
  const pieces = (d.pieces || []).length
    ? `<ul class="fichiers">${d.pieces.map(p => `<li class="fichier">
        <a href="/api/offres/${Number(id)}/dossier/${encodeURIComponent(p.fichier)}?pour_envoi=true" download>${echapper(p.nom)}</a></li>`).join('')}</ul>`
    : `<p class="resume">Aucune pièce à télécharger une à une${d.archive ? '.'
        : " : le paquet d'envoi manque ou ne se lit pas. Régénère le dossier pour le refaire."}</p>`;
  const paquet = d.archive
    ? `<a href="/api/offres/${Number(id)}/dossier/archive" download>Tout en un zip</a>`
    : '<button class="discret" id="btn-regenerer">Régénérer le dossier</button>';
  // Quand le kit n'est pas branché, la lettre n'est qu'un squelette et aucun CV n'est joint :
  // le dire d'abord, sans quoi un dossier creux passe pour une panne. Ce bloc est seul à le dire
  // (l'étape ne reprend pas la phrase de `dossier.generer`) : il porte aussi le remède.
  const provisoire = r.kit_provisoire ? `<p class="avert grave"><b>⚠ Ton kit de candidature n'est pas branché</b><br>
      Ce dossier contient un <b>squelette</b> de lettre et <b>aucun CV</b> : les pièces viennent du
      dossier <code>gabarits/</code> de la configuration de l'instance, pas de ton CV maître. Ce
      n'est pas une panne. Copie le vrai kit dans le dossier que désigne <code>VEILLE_KIT</code>
      (<code>/donnees/kit</code> en conteneur) dès qu'il est livré (<code>docs/CANDIDATURE.md</code>,
      « Copier ton kit sur le serveur »).</p>` : '';
  montrerEtape(`${avertissementsEtape(r)}
    <h2>Dossier prêt</h2>
    ${provisoire}
    ${adressee}
    ${reference}
    ${pieces}
    <div class="actions ligne-actions">${paquet}</div>
    ${lienAnnonce(r.url, "Voir l'annonce ›")}
    <div class="actions ligne-actions">
      <button id="btn-envoyee-pret">Je l'ai envoyée</button>
      <button class="discret" id="btn-destinataire-pret">${qui.length || ecart ? 'Modifier le destinataire' : 'Ajouter un destinataire'}</button>
      <button class="discret" id="btn-affiner-pret">Affiner la lettre</button>
    </div>
    <div id="zone-destinataire"></div>
    <div id="zone-affinement"></div>`);
  $('#btn-envoyee-pret').onclick = () => demanderCanal(id);
  const regenerer = $('#btn-regenerer');
  if (regenerer) regenerer.onclick = () => preparerCandidature(id, regenerer, { regenerer: true });
  // Chaque bouton s'efface devant ce qu'il montre : le bloc porte son propre titre.
  $('#btn-destinataire-pret').onclick = ev => {
    ev.currentTarget.hidden = true;
    $('#zone-destinataire').innerHTML = blocDestinataire(dest, 'Enregistrer et régénérer',
      "Régénérer remplace la lettre, même affinée : l'ancienne reste dans l'historique du dossier.");
    brancherDestinataire(id, bouton => preparerCandidature(id, bouton, { regenerer: true }));
  };
  $('#btn-affiner-pret').onclick = async ev => {
    ev.currentTarget.hidden = true;
    $('#zone-affinement').innerHTML = await blocAffinement(id);
    brancherAffinement(id);
  };
}

// ---------------------------------------------------------------------------
// « Candidatures » (ADR-0003, § 4)
//
// Les offres Je postule, Envoyée et Entretien, chacune avec ce qui la situe : son dossier,
// ou sa date de relance. Les candidatures closes n'y sont pas. Une ligne ouvre la fiche.
// ---------------------------------------------------------------------------

const GROUPES_CANDIDATURES = ['je_postule', 'envoyee', 'entretien'];

function ligneCandidature(o, groupe) {
  let repere = '';
  if (groupe === 'je_postule') repere = o.dossier ? 'dossier prêt' : 'à préparer';
  else if (groupe === 'envoyee' && relanceAttendue(o)) repere = `relance le ${o.date_relance_due}`;
  return `<button class="offre ligne-candidature" data-action="fiche" data-id="${Number(o.id)}">
    <span class="offre-titre">${echapper(o.titre)}</span>
    ${o.employeur ? `<span class="menu">${echapper(o.employeur)}</span>` : ''}
    ${repere ? `<span class="repere">${echapper(repere)}</span>` : ''}
  </button>`;
}

async function chargerCandidatures() {
  const cible = $('#contenu-candidatures');
  try {
    const d = await api('/api/candidatures');
    const groupes = GROUPES_CANDIDATURES.filter(cle => (d[cle] || []).length);
    cible.innerHTML = groupes.length
      ? groupes.map(cle => `<h2 class="titre-groupe">${LIBELLES_ETAT[cle]}</h2>
          <div class="liste" data-groupe="${cle}">${d[cle].map(o => ligneCandidature(o, cle)).join('')}</div>`).join('')
      : '<p class="resume">Aucune candidature en cours.</p>';
  } catch (e) {
    message(e.message, true);
    if (!cible.children.length) {
      cible.innerHTML = `<p class="avert">Les candidatures n'ont pas pu se charger : ${echapper(e.message)}</p>`;
    }
  }
}

// ---------------------------------------------------------------------------
// Texte complet de l'annonce
//
// La plupart des offres au-dessus du seuil n'ont qu'un extrait : les critères
// éliminatoires — astreinte, week-end, allemand exigé — sont dans le corps de
// l'annonce, qu'on ne lit jamais.
//
// Le collage doit être atteignable en un geste, accepter un collage brut avec
// la mise en forme du site, et rescorer immédiatement en montrant ce qui a
// changé. S'il faut quatre clics, il ne le fera pas.
// ---------------------------------------------------------------------------

function listePreuves(titre, preuves, classe) {
  if (!preuves.length) return '';
  // La phrase exacte de l'annonce : lui dire « astreinte détectée » ne vaut
  // rien s'il ne peut pas vérifier lui-même.
  return `<p class="resume"><b>${titre}</b></p>
    <ul class="preuves">${preuves.map(p => `
      <li class="${classe}">
        <span class="pts ${p.points > 0 ? 'plus' : p.points < 0 ? 'moins' : 'zero'}">${p.points > 0 ? '+' : ''}${p.points}</span>
        <span><b>${echapper(p.libelle)}</b>
        ${p.phrase ? `<br><span class="citation">${echapper(p.phrase)}</span>` : ''}</span>
      </li>`).join('')}</ul>`;
}

function afficherRapportTexte(r) {
  const monte = r.ecart > 0;
  const fleche = monte ? '▲' : (r.ecart < 0 ? '▼' : '=');
  const ecart = r.ecart > 0 ? `+${r.ecart}` : `${r.ecart}`;

  let html = `<p class="resume">${echapper(r.message)}</p>`;

  if (r.alerte_eliminatoire) {
    // LE cas a ne pas rater. Un critere eliminatoire s'applique : le score ne
    // veut plus rien dire, et l'afficher en vert avec une hausse dirait
    // exactement le contraire de la verite. On annonce l'ecartement d'abord,
    // et on range le chiffre derriere, en gris, en disant qu'il ne compte plus.
    html = `<p class="avert grave"><b>⚠ Écartée — ce que l'extrait ne montrait pas</b><br>
      ${echapper(r.alerte_eliminatoire)}</p>` + html +
      `<p class="resume menu">Score avant écartement : ${r.score_avant} → ${r.score_apres}.
      Il ne compte plus : un critère éliminatoire l'emporte sur le total.</p>`;
  } else {
    html += `<p class="resume">Score : <b class="${monte ? 'monte' : r.ecart < 0 ? 'descend' : ''}">
      ${r.score_avant} → ${r.score_apres} ${fleche} ${ecart}</b></p>`;
    if (monte) {
      html += `<p class="avert bonne"><b>▲ Cette offre vaut mieux que son extrait</b><br>
        Le texte complet révèle des éléments en ta faveur.</p>`;
    }
  }
  if (r.salaire_trouve) {
    html += `<p class="resume">Salaire trouvé dans le texte : <b>${echapper(r.salaire_trouve)}</b></p>`;
  }
  if (r.annexes_retires) {
    // S'il a collé une page entière, la colonne « Offres similaires » contient
    // d'AUTRES annonces. On l'a retirée — et on le dit, parce qu'une troncature
    // silencieuse serait pire que le bruit qu'elle enlève.
    html += `<p class="resume menu">${r.annexes_retires} caractères de rubriques annexes
      écartés à partir de « ${echapper(r.annexes_repere)} » : ces lignes parlent d'autres
      offres, elles n'ont pas compté dans le score.</p>`;
  }
  html += listePreuves('Ce qui joue contre', r.revelations_defavorables, 'contre');
  html += listePreuves('Ce qui joue pour', r.revelations_favorables, 'pour');
  if (!r.revelations_defavorables.length && !r.revelations_favorables.length) {
    html += `<p class="resume">Aucun critère nouveau : l'extrait disait déjà l'essentiel.</p>`;
  }
  return html;
}

function blocTexteComplet(id, o, enr) {
  const p = enr.politique;
  let action;
  if (enr.deja_enrichie) {
    action = `<p class="resume">Texte complet déjà enregistré (${echapper(enr.enrichi_par || '')},
      le ${echapper((enr.enrichi_le || '').slice(0, 10))}). Tu peux le remplacer ci-dessous.</p>`;
  } else if (p.autorise && enr.cadence_ok) {
    action = `<div class="actions"><button id="btn-recuperer">Récupérer le texte automatiquement</button>
      <span class="menu">${echapper(p.raison)}</span></div>`;
  } else if (p.autorise) {
    action = `<p class="avert">${echapper(enr.cadence_message)}</p>`;
  } else {
    action = `<p class="avert"><b>Lecture automatique impossible.</b><br>
      ${echapper(p.raison)}.<br>${echapper(p.conseil || '')}</p>`;
  }

  const lien = enr.url
    ? `<a href="${echapper(enr.url)}" target="_blank" rel="noopener noreferrer">Ouvrir l'annonce dans ton navigateur</a>`
    : '<span class="menu">pas de lien exploitable</span>';

  return `
    <h3>Texte complet de l'annonce</h3>
    <p class="resume">${o.donnees_partielles
      ? 'Cette offre n\'a qu\'un <b>extrait</b> : les critères éliminatoires n\'ont pas pu s\'appliquer.'
      : 'Le texte complet est disponible.'}</p>
    ${action}
    <p>${lien} — puis sélectionne tout, copie, et colle ci-dessous.</p>
    <textarea id="texte-annonce" placeholder="Colle ici le texte de l'annonce, mise en forme comprise — je m'occupe du nettoyage."></textarea>
    <div class="actions">
      <button id="btn-coller">Enregistrer et rescorer</button>
      ${enr.deja_enrichie ? `<button class="discret" id="btn-annuler-texte">Revenir a l'extrait</button>` : ''}
    </div>`;
}

// ---------------------------------------------------------------------------
// Les exigences relevées dans le texte collé
//
// Le modèle PROPOSE, Edouard coche, le scoring déterministe recalcule. Rien
// n'agit avant la coche : l'écran doit le dire, sinon la case ressemble à un
// résumé de ce qui est déjà pris en compte.
// ---------------------------------------------------------------------------

let etatExigencesCache = null;

async function etatExigences() {
  if (!etatExigencesCache) etatExigencesCache = await api('/api/exigences');
  return etatExigencesCache;
}

function ligneExigence(e, cochable) {
  const agit = e.agit_sur_le_score;
  return `<li class="${agit ? 'contre' : 'pour'}">
    <span>
      ${cochable ? `<label><input type="checkbox" class="exig" value="${echapper(e.attribut)}" checked>
        <b>${echapper(e.libelle || e.attribut)} : ${echapper(e.valeur)}</b></label>`
      : `<b>${echapper(e.libelle || e.attribut)} : ${echapper(e.valeur)}</b>`}
      <br><span class="menu">${agit ? 'agit sur le score' : 'pour information — n’agit pas sur le score'}</span>
      <br><i>« ${echapper(e.citation)} »</i>
    </span></li>`;
}

async function blocExigences(id, o) {
  const [e, deja] = await Promise.all([
    etatExigences().catch(() => ({ possible: false, raison: 'état indisponible' })),
    api(`/api/offres/${id}/exigences`).catch(() => ({ validees: [], propositions: [] })),
  ]);

  let html = `<h3>Exigences de l'annonce</h3>`;
  if (deja.validees.length) {
    html += `<p class="resume">Tu as validé ${deja.validees.length} exigence(s).
      Elles remplacent la détection automatique — le barème, lui, ne change pas.</p>
      <ul class="preuves">${deja.validees.map(x => ligneExigence(x, false)).join('')}</ul>
      <div class="actions"><button class="discret" id="btn-oublier-exig">Les oublier et rescorer</button></div>`;
  }

  if (!e.possible) {
    html += `<p class="menu">Relevé automatique indisponible — ${echapper(e.raison || '')}</p>`;
    return html;
  }
  if (!o.description || o.description.length < 200) {
    html += `<p class="menu">Colle d'abord le texte de l'annonce : le relevé a besoin du texte complet.</p>`;
    return html;
  }

  html += `<p class="resume">Un modèle relit le texte et <b>propose</b> ce que
    l'annonce exige — « deux jours sur site », « allemand courant ». Il ne donne
    aucun point : <b>tu coches, et c'est la règle déterministe qui recalcule</b>.
    Chaque proposition cite le texte, mot pour mot ; celles qui ne le citent pas
    sont jetées avant de t'être montrées.</p>
    <p class="avert"><b>Ce qui part</b><br>${echapper(e.ce_qui_part)}</p>
    <div class="actions">
      <button id="btn-relever">Relever les exigences</button>
      <span class="menu" id="etat-relever"></span>
    </div>
    <div id="resultat-exigences"></div>`;
  return html;
}

function brancherExigences(id) {
  const oublier = $('#btn-oublier-exig');
  if (oublier) oublier.onclick = async () => {
    try {
      const r = await api(`/api/offres/${id}/exigences/oublier`, { method: 'POST' });
      message(`Exigences oubliées — score revenu à ${r.score}.`);
      rafraichir();
    } catch (err) { message(err.message, true); }
  };

  const b = $('#btn-relever');
  if (!b) return;
  b.onclick = async () => {
    b.disabled = true;
    $('#etat-relever').textContent = 'lecture en cours…';
    const zone = $('#resultat-exigences');
    try {
      const r = await api(`/api/offres/${id}/exigences/relever`, { method: 'POST' });
      if (!r.ok) {
        zone.innerHTML = `<p class="avert">${echapper(r.message)}</p>`;
        return;
      }
      if (!r.propositions.length) {
        zone.innerHTML = `<p class="resume">${echapper(r.message)}</p>
          ${r.rejetees.length ? `<p class="menu">Rejetées : ${r.rejetees.map(echapper).join(' · ')}</p>` : ''}`;
        return;
      }
      zone.innerHTML = `<p class="resume">${echapper(r.message)}
        Décoche ce qui est faux — rien n'est pris en compte avant que tu valides.</p>
        <ul class="preuves">${r.propositions.map(x => ligneExigence(x, true)).join('')}</ul>
        ${r.rejetees.length ? `<p class="menu"><b>Jetées avant affichage</b> :
          ${r.rejetees.map(echapper).join(' · ')}</p>` : ''}
        <div class="actions"><button id="btn-valider-exig">Valider et rescorer</button></div>`;

      $('#btn-valider-exig').onclick = async () => {
        const attributs = [...document.querySelectorAll('.exig:checked')].map(c => c.value);
        try {
          const v = await api(`/api/offres/${id}/exigences/valider`, {
            method: 'POST', body: JSON.stringify({ attributs }),
          });
          message(`${v.validees} exigence(s) validée(s) — score : ${v.score}.`);
          rafraichir();
          ouvrirDetail(id);
        } catch (err) { message(err.message, true); }
      };
    } catch (err) { message(err.message, true); }
    finally { b.disabled = false; $('#etat-relever').textContent = ''; }
  };
}

// ---------------------------------------------------------------------------
// Préparer l'entretien
//
// Ce panneau ne part chez personne. Chaque point affiche l'ancrage qui
// justifie sa présence — une phrase de l'annonce, ou une ligne du fichier 17.
// Sans ancrage visible, il préparerait une question que personne ne posera.
// ---------------------------------------------------------------------------

const ETIQUETTE_ENTRETIEN = {
  attaque: ['⚠ On t’attendra là-dessus', 'contre'],
  appui: ['Ce que tu peux sortir', 'pour'],
  rituel: ['Rituel', 'pour'],
};

async function ouvrirEntretien(id) {
  try {
    const p = await api(`/api/offres/${id}/entretien`);
    let html = `<h2>Préparer l'entretien</h2>`;

    if (!p.kit_disponible) {
      html += `<p class="avert grave">${p.avertissements.map(echapper).join('<br>')}</p>`;
    } else {
      html += `<p class="resume">${p.points.length} point${p.points.length > 1 ? 's' : ''},
        dont <b>${p.attaques}</b> où l'on te poussera. Les réponses sont celles de
        ton fichier <b>17</b> : la console ne les réécrit pas.
        ${p.dossier_genere ? '' : '<br>Le dossier n’a pas encore été généré : la question sur ton code ne sort que si tu joins l’annexe technique.'}</p>`;

      if (p.ancrages_douteux && p.ancrages_douteux.length) {
        html += `<p class="avert grave"><b>Ancrages à vérifier</b><br>
          ${p.ancrages_douteux.map(echapper).join('<br>')}</p>`;
      }
      if (p.avertissements.length) {
        html += `<p class="avert">${p.avertissements.map(echapper).join('<br>')}</p>`;
      }

      for (const pt of p.points) {
        const [libelle, classe] = ETIQUETTE_ENTRETIEN[pt.categorie] || ['', 'pour'];
        html += `<details class="explication">
          <summary>${echapper(pt.question)}</summary>
          <p class="menu ${classe}">${echapper(libelle)} — ${echapper(pt.pourquoi)}</p>
          <p class="resume"><b>${pt.ancrage === 'annonce' ? "L'annonce dit" : 'Ton dossier dit'}</b></p>
          <pre class="citation" style="white-space:pre-wrap">${echapper(pt.citation)}</pre>
          <pre class="citation" style="white-space:pre-wrap">${echapper(pt.reponse)}</pre>
        </details>`;
      }
    }
    $('#fenetre-contenu').innerHTML = html;
    ouvrirFenetre();
  } catch (e) { message(e.message, true); }
}

async function ouvrirDetail(id) {
  try {
    const [o, enr] = await Promise.all([
      api(`/api/offres/${id}`),
      api(`/api/offres/${id}/enrichissement`),
    ]);
    const evts = (o.evenements || []).map(e =>
      `<li>${echapper(e.horodatage)} - ${echapper(e.type)} ${e.detail ? echapper(e.detail) : ''}</li>`).join('');
    $('#fenetre-contenu').innerHTML = `
      <h2>${echapper(o.titre)}</h2>
      <div class="meta"><span>${echapper(o.employeur || '?')}</span><span>${echapper(o.lieu || '?')}</span></div>
      ${blocTexteComplet(id, o, enr)}
      <div id="rapport-texte"></div>
      <div id="zone-exigences">${await blocExigences(id, o)}</div>
      ${blocDestinataire(o)}
      ${blocVerification(o)}
      <h3>Notes</h3>
      <textarea id="notes">${echapper(o.notes || '')}</textarea>
      <div class="actions"><button id="enregistrer-notes">Enregistrer</button></div>
      <h3>Historique</h3>
      <ul class="fichiers">${evts || '<li>aucun</li>'}</ul>
      <h3>Texte enregistré</h3>
      <p class="resume">${echapper((o.description || '(rien)').slice(0, 1200))}</p>`;
    ouvrirFenetre();
    brancherVerification(id);
    brancherDestinataire(id);
    brancherExigences(id);

    $('#enregistrer-notes').onclick = async () => {
      await api(`/api/offres/${id}`, { method: 'POST', body: JSON.stringify({ notes: $('#notes').value }) });
      message('Notes enregistrees.');
    };

    const traiter = r => {
      $('#rapport-texte').innerHTML = afficherRapportTexte(r);
      message(r.alerte_eliminatoire ? 'Attention : un critère éliminatoire apparaît.' : 'Offre rescorée.',
              Boolean(r.alerte_eliminatoire));
      rafraichir();
    };

    const bouton = $('#btn-recuperer');
    if (bouton) bouton.onclick = async ev => {
      ev.target.disabled = true;
      ev.target.textContent = 'Récupération...';
      try {
        const r = await api(`/api/offres/${id}/enrichir`, { method: 'POST' });
        if (!r.ok) { $('#rapport-texte').innerHTML = `<p class="avert">${echapper(r.message)}</p>`; }
        else traiter(r);
      } catch (e) { message(e.message, true); }
      finally { ev.target.disabled = false; ev.target.textContent = 'Récupérer le texte automatiquement'; }
    };

    const annuler = $('#btn-annuler-texte');
    if (annuler) annuler.onclick = async ev => {
      ev.target.disabled = true;
      try {
        const r = await api(`/api/offres/${id}/texte/annuler`, { method: 'POST' });
        message(r.message);
        rafraichir();
        ouvrirDetail(id);
      } catch (e) { message(e.message, true); }
      finally { ev.target.disabled = false; }
    };

    $('#btn-coller').onclick = async ev => {
      const texte = $('#texte-annonce').value;
      if (texte.trim().length < 200) { message('Texte trop court pour être exploité.', true); return; }
      ev.target.disabled = true;
      try {
        traiter(await api(`/api/offres/${id}/texte`, { method: 'POST', body: JSON.stringify({ texte }) }));
        $('#texte-annonce').value = '';
      } catch (e) { message(e.message, true); }
      finally { ev.target.disabled = false; }
    };
  } catch (e) { message(e.message, true); }
}

document.addEventListener('click', ev => {
  const bouton = ev.target.closest('[data-action]');
  if (!bouton) return;
  // Une action vit dans une offre (sa carte, sa ligne, sa fiche) : c'est elle qui porte l'id.
  const offre = bouton.closest('.offre[data-id]');
  if (!offre) return;
  const id = Number(offre.dataset.id);
  const a = bouton.dataset.action;
  // Un geste fait depuis la fiche la rouvre sur le nouvel état.
  const dansFiche = offre.classList.contains('fiche');
  if (a === 'envoyee') demanderCanal(id);
  else if (a === 'relance') ouvrirRelance(id);
  else if (a === 'entretien') ouvrirEntretien(id);
  else if (a === 'detail') ouvrirDetail(id);
  // « Je postule » lance la préparation ; la fiche « Je postule » la reprend (« Préparer ma
  // candidature », « Dossier prêt › »).
  else if (a === 'postuler' || a === 'preparer') preparerCandidature(id, bouton);
  else if (a === 'plus-tard') gesteNeuf(bouton, () => (dansFiche
    ? changerStatutPuisFiche(id, 'a_traiter') : changerStatut(id, 'a_traiter')));
  // Le panneau « Non » nomme l'offre : l'intitulé de sa carte, ou de sa fiche.
  else if (a === 'non') demanderNon(id, $('.offre-titre', offre)?.textContent.trim() || '');
  else if (a === 'reponse') gesteNeuf(bouton, () => changerStatutPuisFiche(id, bouton.dataset.statut));
  else if (a === 'revenir') gesteNeuf(bouton, () => changerStatutPuisFiche(id, 'nouveau'));
  else if (a === 'notes') gesteNeuf(bouton, () => enregistrerNotes(id, bouton));
  else if (a === 'fiche') ouvrirFiche(id).catch(e => message(e.message, true));
  else if (a === 'desarchiver') gesteNeuf(bouton, () => remettreDansLeFlux(id));
});

// ---------------------------------------------------------------------------
// Onglets, filtres
// ---------------------------------------------------------------------------

// La vue montrée : celle de l'entrée courante de l'historique. « À faire » est la première.
let vueCourante = 'a-faire';

// ---------------------------------------------------------------------------
// Le Bilan (ADR-0003, § 6 ; décisions 7 et 8 du plan du lot 3)
//
// L'entonnoir et ses tableaux, puis trois listes repliées : les archivées, les
// closes et les mises de côté. Chacune dit son vrai nombre dans son titre, et son
// plafond quand elle l'atteint. Une liste dépliée le reste quand le Bilan se
// recharge : un geste fait dans une fiche ouverte depuis lui passe par `rafraichir()`.
//
// Les archivées : archiver à tort est bien pire que garder une annonce morte.
// Trois conséquences visibles ici —
//   1. le motif est TOUJOURS affiché, jamais une disparition muette ;
//   2. une pastille compte ce qui est parti depuis sa dernière visite, pour
//      qu'une archive automatique ne soit jamais invisible : déplier la liste
//      vaut visite, ouvrir le Bilan non ;
//   3. « Remettre dans le flux » est définitif : la vérification ne réarchive
//      jamais ce qu'il vient de ressortir. Une close remise dans le flux reste close.
// ---------------------------------------------------------------------------

// La même clé qu'avant le lot 3 : la pastille d'un téléphone ne repart pas de zéro.
const CLE_VISITE_ARCHIVE = 'veille:archive-vue-le';

function derniereVisiteArchive() {
  try { return localStorage.getItem(CLE_VISITE_ARCHIVE) || ''; }
  catch { return ''; }
}

function marquerArchiveVue() {
  try { localStorage.setItem(CLE_VISITE_ARCHIVE, new Date().toISOString()); }
  catch { /* navigation privée : la pastille reste, ce n'est pas grave */ }
}

// Une archivée : son titre ouvre la fiche, son motif est toujours dit.
function carteArchivee(o) {
  return `
  <article class="offre archivee" data-id="${Number(o.id)}">
    <div class="offre-haut">
      <button class="offre-titre" data-action="fiche">${echapper(o.titre)}</button>
      <span class="score">${echapper(o.score)}</span>
    </div>
    <p class="menu">${echapper(o.employeur || '')} ${echapper(o.lieu || '')}
      ${o.disparue_le ? `· disparue vers le ${echapper(String(o.disparue_le).slice(0, 10))}` : ''}</p>
    <p class="avert"><b>Pourquoi elle est ici</b><br>${echapper(o.archive_motif || 'motif non enregistré')}</p>
    <div class="actions">
      <button data-action="desarchiver">Remettre dans le flux</button>
      ${o.url ? `<a class="lien-annonce" href="${echapper(o.url)}" target="_blank" rel="noopener noreferrer">Ouvrir l'annonce ›</a>` : ''}
    </div>
  </article>`;
}

// Ce qui situe une close : le motif d'une écartée, ou la réponse. Un refus ou une
// acceptation peut garder en base le motif d'un ancien écartement, qui ne dit plus rien.
function motifClose(o) {
  if (o.statut === 'refus') return 'Refus';
  if (o.statut === 'accepte') return 'Acceptée';
  return o.motif_ecartement || '';
}

// Les trois listes. Les archivées viennent par date d'archivage, les autres par score : le
// plafond (200 lignes, `app.py`) se dit selon l'ordre.
const LISTES_BILAN = {
  archivees: { libelle: 'Archivées', plafond: n => `les ${n} dernières archivées`,
               vide: 'Aucune annonce archivée pour l\'instant.' },
  closes: { libelle: 'Closes', plafond: n => `les ${n} premières, par score`,
            vide: 'Aucune offre close.' },
  'mises-de-cote': { libelle: 'Mises de côté', plafond: n => `les ${n} premières, par score`,
                     vide: 'Aucune offre mise de côté.' },
};

function listeBilan(nom, total, lignes, ouvertes, intro = '') {
  const l = LISTES_BILAN[nom];
  const n = Number(total) || 0;
  const resume = lignes.length < n ? `${l.libelle} (${n}, ${l.plafond(lignes.length)})`
    : `${l.libelle} (${n})`;
  return `<details class="repli" data-liste="${nom}"${ouvertes.includes(nom) ? ' open' : ''}>
    <summary>${echapper(resume)}</summary>
    ${intro}
    ${lignes.length ? `<div class="liste">${lignes.join('')}</div>`
      : `<p class="resume">${echapper(l.vide)}</p>`}
  </details>`;
}

async function chargerBilan() {
  const cible = $('#contenu-bilan');
  try {
    const [e, archive, closes, deCote] = await Promise.all([
      api('/api/entonnoir'),
      api('/api/archive'),
      api('/api/offres?etat=close'),
      api('/api/offres?etat=mise_de_cote'),
    ]);
    // Lues après l'attente : une liste dépliée pendant le chargement le reste aussi.
    const ouvertes = $$('details[data-liste][open]', cible).map(d => d.dataset.liste);
    cible.innerHTML = blocsEntonnoir(e) + `<div class="listes-bilan">
      ${listeBilan('archivees', archive.nouvelles, archive.offres.map(carteArchivee), ouvertes,
        `<p class="resume">Annonces retirées de leur site. Rien n'est supprimé : le score,
          l'explication et tes notes sont conservés. Si une offre est là à tort,
          <b>Remettre dans le flux</b> la ressort, et elle n'y retournera plus jamais toute seule.</p>`)}
      ${listeBilan('closes', closes.total, closes.offres.map(o => ligneOffre(o, motifClose(o))), ouvertes)}
      ${listeBilan('mises-de-cote', deCote.total,
        deCote.offres.map(o => ligneOffre(o, o.motif_ecartement || '')), ouvertes)}
    </div>`;
    // Déplier les archivées vaut visite. `toggle` part aussi pour une liste rouverte par ce
    // rechargement : elle est sous les yeux, la visite se marque de nouveau.
    const archivees = $('details[data-liste="archivees"]', cible);
    archivees.addEventListener('toggle', () => {
      if (!archivees.open) return;
      marquerArchiveVue();
      compterPastilles();
    });
  } catch (err) {
    message(err.message, true);
    if (!cible.children.length) {
      cible.innerHTML = `<p class="avert">Le Bilan n'a pas pu se charger : ${echapper(err.message)}</p>`;
    }
  }
}

// Le Bilan se recharge, la liste des archivées gardée ouverte (le geste s'y fait).
async function remettreDansLeFlux(id) {
  await api(`/api/offres/${id}/desarchiver`, { method: 'POST' });
  message("Remise dans le flux : elle ne repartira plus seule à l'archive.");
  rafraichir();
}

// ---------------------------------------------------------------------------
// Vérifier une offre à la demande
//
// C'est LA réponse pour les offres LinkedIn : on n'a pas le droit de les
// sonder, donc on ne peut pas prouver qu'elles sont retirées. La console lui
// dit franchement qu'elle ne sait pas, lui ouvre l'annonce, et enregistre SON
// constat s'il en fait un.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Ce qu'il a cherché pour cette offre — mémorisé, jamais obligatoire
//
// Trouver le nom d'un recruteur, c'est cinq minutes de travail. Ça ne doit pas
// se perdre à la régénération suivante. Mais ça ne doit pas non plus bloquer :
// il existe des offres où le nom n'est nulle part, et imposer la saisie
// transformerait une aide en obstacle. Le PDF signale les manques en rouge.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Affinement — un bouton, jamais une étape
//
// La lettre assemblée existe déjà et suffit. L'affinement est une demande, sur
// une candidature qui compte. Trois règles tenues ici :
//   1. sans identifiants, il se dit indisponible, avec sa raison — pas d'erreur obscure ;
//   2. ce qui part chez le tiers est dit AU MOMENT du clic, pas dans une doc ;
//   3. il propose, il ne remplace pas : la version assemblée reste, et le
//      retour arrière tient en un geste.
// ---------------------------------------------------------------------------

let affinementPossible = null;

async function etatAffinement() {
  if (affinementPossible !== null) return affinementPossible;
  try { affinementPossible = await api('/api/affinement'); }
  catch { affinementPossible = { possible: false, raison: 'indisponible' }; }
  return affinementPossible;
}

async function blocAffinement(id) {
  const e = await etatAffinement();
  if (!e.possible) {
    // On le dit, sobrement, au lieu de laisser un bouton qui échoue.
    return `<p class="menu">Affinement indisponible — ${echapper(e.raison)}</p>`;
  }
  return `<div class="bloc">
    <h3>Affiner la lettre</h3>
    <p class="resume">Retravaille les <b>transitions</b>, le <b>ton</b> et la
      <b>longueur</b> du texte déjà assemblé. Il ne peut ni inventer un fait, ni
      ajouter une compétence : un contrôle refuse le résultat s'il le fait.</p>
    <p class="avert"><b>Ce qui part</b><br>${echapper(e.ce_qui_part)}</p>
    <div class="actions">
      <button id="btn-affiner">Proposer une version affinée</button>
      <span class="menu" id="etat-affiner"></span>
    </div>
    <div id="resultat-affiner"></div>
  </div>`;
}

function brancherAffinement(id) {
  const b = $('#btn-affiner');
  if (!b) return;
  b.onclick = async () => {
    b.disabled = true;
    const zone = $('#resultat-affiner');
    // Un bouton muet pendant 90 secondes passe pour cassé. Mesures du 02/10
    // sur la MÊME lettre : 29 s, 42,7 s, 59,2 s, 60,2 s, 90,8 s, et une fois
    // au-delà de 120 s. La durée varie du simple au quadruple d'un appel à
    // l'autre, donc on ne peut rien promettre : on montre le temps qui passe,
    // et on dit ce qui est en jeu — rien, la lettre assemblée reste.
    const depart = Date.now();
    zone.innerHTML = `<p class="resume" id="progres-affiner"></p>`;
    const rendreProgres = () => {
      const s = Math.round((Date.now() - depart) / 1000);
      const p = $('#progres-affiner');
      if (!p) return;
      p.innerHTML = `<b>Lecture en cours — ${s} s.</b> Ça prend en général
        entre une et deux minutes. Ta lettre assemblée reste en place quoi
        qu'il arrive : tu ne risques rien à attendre.
        ${s > 150 ? '<br>Au-delà de 180 s l’appel est interrompu et tu pourras réessayer.' : ''}`;
    };
    rendreProgres();
    const minuteur = setInterval(rendreProgres, 1000);
    try {
      const r = await api(`/api/offres/${id}/affiner`, { method: 'POST' });
      if (r.depassement) {
        // Ce n'est pas un refus : rien n'a été proposé, donc rien n'a été
        // rejeté. Le dire autrement, et sans rouge.
        zone.innerHTML = `<p class="avert"><b>Trop long cette fois</b><br>
          ${echapper(r.message)}</p>
          <div class="actions"><button id="btn-reessayer-affiner">Réessayer</button></div>`;
        const re = $('#btn-reessayer-affiner');
        if (re) re.onclick = () => b.click();
      } else if (!r.ok) {
        zone.innerHTML = `<p class="avert grave"><b>Proposition refusée</b><br>
          ${echapper(r.message)}</p>
          ${r.refus && r.refus.length ? `<ul class="preuves">${r.refus.map(x =>
            `<li class="contre"><span><b>${echapper(x)}</b></span></li>`).join('')}</ul>` : ''}`;
      } else {
        zone.innerHTML = `<p class="resume">${echapper(r.message)}</p>
          <pre class="citation" style="white-space:pre-wrap">${echapper(r.texte.slice(0, 2500))}</pre>
          <div class="actions">
            <button id="btn-appliquer-affine">Garder cette version</button>
            <button class="discret" id="btn-revenir-assemble">Revenir à la version assemblée</button>
          </div>`;
        $('#btn-appliquer-affine').onclick = async () => {
          await api(`/api/offres/${id}/affiner/appliquer`, { method: 'POST' });
          message('Version affinée appliquée — la version assemblée est conservée.');
        };
        $('#btn-revenir-assemble').onclick = async () => {
          try {
            await api(`/api/offres/${id}/affiner/annuler`, { method: 'POST' });
            message('Retour à la version assemblée.');
          } catch (err) { message(err.message, true); }
        };
      }
    } catch (e) { message(e.message, true); }
    finally {
      clearInterval(minuteur);
      b.disabled = false;
      $('#etat-affiner').textContent = '';
      const p = $('#progres-affiner');
      if (p) p.remove();
    }
  };
}

// `libelle` nomme le bouton : « Enregistrer » dans la vue détaillée, « Enregistrer et
// régénérer » sur « Dossier prêt ». `precision`, facultative, se dit juste au-dessus : sur
// « Dossier prêt », ce que la régénération remplace.
function blocDestinataire(o, libelle = 'Enregistrer', precision = '') {
  const v = s => echapper(s || '');
  return `<div class="bloc">
    <h3>Le destinataire</h3>
    <p class="resume menu">Facultatif. Rempli ici, il part dans la lettre ;
      laissé vide, il apparaît en rouge dans le PDF pour que tu le voies.</p>
    <label class="champ">Nom du recruteur
      <input id="d-contact" placeholder="Marie Durand" value="${v(o.contact_nom)}"></label>
    <label class="champ">Formule d'appel
      <input id="d-civilite" placeholder="Ms Durand / Madame Durand"
             value="${v(o.contact_civilite)}"></label>
    <label class="champ">Adresse de l'entreprise
      <textarea id="d-adresse" rows="2"
                placeholder="Rue et numéro&#10;CH-4052 Bâle">${v(o.adresse_entreprise)}</textarea></label>
    <label class="champ">Référence de l'annonce
      <input id="d-reference" placeholder="laissé vide, la mention disparaît de la lettre"
             value="${v(o.reference_annonce)}"></label>
    <p class="menu" id="proposition-reference"></p>
    ${precision ? `<p class="menu">${echapper(precision)}</p>` : ''}
    <div class="actions"><button class="discret" id="btn-destinataire">${echapper(libelle)}</button>
      <span class="menu" id="etat-destinataire"></span></div>
  </div>`;
}

// `apres`, facultatif, suit l'enregistrement, avec le bouton : « Dossier prêt » y régénère la
// lettre. Le bouton se désactive le temps d'enregistrer : un double toucher n'enregistre
// qu'une fois.
function brancherDestinataire(id, apres) {
  const b = $('#btn-destinataire');
  if (!b) return;

  // La référence : on PROPOSE, on n'écrit pas. Le champ n'est prérempli que
  // s'il est vide, et la phrase d'où vient la proposition est affichée — une
  // référence fausse est pire qu'une référence absente.
  api(`/api/offres/${id}/reference`).then(r => {
    const zone = $('#proposition-reference');
    const champ = $('#d-reference');
    if (!zone || !champ) return;
    if (!r.proposition) {
      zone.textContent = "Aucune référence trouvée dans l'annonce — c'est le cas "
        + "de la quasi-totalité des siennes. Laissé vide, le segment disparaît.";
      return;
    }
    if (!champ.value) champ.value = r.proposition;
    zone.innerHTML = `Proposé d'après l'annonce : <b>${echapper(r.proposition)}</b>
      — vérifie-le.<br><i>« ${echapper(r.preuve)} »</i>`;
  }).catch(() => {});
  b.onclick = async () => {
    b.disabled = true;
    try {
      await api(`/api/offres/${id}`, {
        method: 'POST',
        body: JSON.stringify({
          contact_nom: $('#d-contact').value.trim(),
          contact_civilite: $('#d-civilite').value.trim(),
          adresse_entreprise: $('#d-adresse').value.trim(),
          reference_annonce: $('#d-reference').value.trim(),
        }),
      });
    } catch (e) {
      b.disabled = false;
      message(e.message, true);
      return;
    }
    b.disabled = false;
    $('#etat-destinataire').textContent = 'enregistré — il sera repris à chaque génération';
    if (apres) apres(b);
  };
}

function blocVerification(o) {
  const jamais = !o.verifiee_le;
  const interdite = o.verdict_verification === 'interdite';
  let etat;
  if (jamais) {
    etat = `<span class="menu">jamais vérifiée</span>`;
  } else if (interdite) {
    etat = `<span class="etiquette grave">non vérifiable</span>
      <span class="menu">${echapper(o.motif_verification || '')}</span>`;
  } else {
    etat = `<span class="menu">${echapper(o.verdict_verification)} — vérifiée le
      ${echapper((o.verifiee_le || '').slice(0, 10))}</span>`;
  }

  return `<div class="bloc">
    <h3>Encore en ligne ?</h3>
    <p>${etat}</p>
    ${o.probablement_retiree ? `<p class="avert grave"><b>⚠ Probablement retirée</b><br>
      ${echapper(o.archive_motif || '')}<br>
      Elle est conservée : tu l'as triée ou tu as généré un dossier dessus.</p>` : ''}
    ${interdite ? `<p class="resume">Ce site interdit la lecture automatisée, donc
      la console ne peut rien prouver — et elle n'archivera jamais cette offre
      d'elle-même. Ouvre l'annonce et dis-lui ce que tu vois.</p>` : ''}
    <div class="actions">
      ${!interdite ? `<button id="btn-verifier">Vérifier maintenant</button>` : ''}
      ${o.url ? `<a class="discret" href="${echapper(o.url)}" target="_blank" rel="noopener noreferrer">Ouvrir l'annonce</a>` : ''}
      <button class="discret" id="btn-retiree">Elle n'y est plus → archiver</button>
    </div>
    <p id="rapport-verification" class="resume"></p>
  </div>`;
}

function brancherVerification(id) {
  const bouton = $('#btn-verifier');
  if (bouton) {
    bouton.onclick = async () => {
      bouton.disabled = true;
      bouton.textContent = 'Vérification…';
      const r = await api(`/api/offres/${id}/verifier`, { method: 'POST' });
      const zone = $('#rapport-verification');
      const bon = r.verdict === 'vivante';
      zone.innerHTML = `<b class="${bon ? 'monte' : ''}">${echapper(r.verdict)}</b> —
        ${echapper(r.detail)}
        ${r.enrichie ? '<br>La page lue a complété l\'annonce : le score a été recalculé.' : ''}
        ${r.archivee ? '<br>Archivée.' : ''}`;
      bouton.disabled = false;
      bouton.textContent = 'Vérifier maintenant';
      if (r.archivee) rafraichir();
    };
  }
  const retiree = $('#btn-retiree');
  if (retiree) {
    retiree.onclick = async () => {
      // MEME appel que le bouton « Obsolète » de la carte : un seul chemin
      // vers l'archivage, pas deux qui peuvent diverger.
      try {
        await constater(id, false);
        $('#fenetre').close();
      } catch (e) { message(e.message, true); }
    };
  }
}


// ---------------------------------------------------------------------------
// Mes critères (ADR-0003, § 6 ; décision 10 du plan du lot 3)
//
// Les offres à classer d'abord, le seul geste qui y attend ; puis « Recalculer tous
// les scores » ; puis le rappel : les critères se changent dans la configuration de
// l'instance, qui arrive par le déploiement, pas dans la console.
//
// Les offres à classer : celles qu'aucun motif n'a su ranger. Mesure du 02/10/2026 :
// une part notable des offres sans famille, certaines encore actives. La plupart le
// méritent — une annonce de Hauswart ne relève d'aucune famille cherchée. Mais
// « Automation Tester » et « automatisation de tests » en faisaient partie.
//
// Chaque proposition montre les MOTS qui la justifient. Rien ne s'applique
// sans sa coche : une case préchée serait un classement automatique déguisé.
// ---------------------------------------------------------------------------

async function chargerCriteres() {
  const cible = $('#contenu-criteres');
  try {
    const d = await api('/api/classement');

    let html = `<div class="bloc">
      <h2>Offres sans famille — ${echapper(d.sans_famille)}</h2>
      <p class="resume">Une famille est proposée quand l'intitulé recoupe les
        motifs de <b>criteres.yaml</b>. Les mots qui la justifient sont affichés :
        si tu ne les reconnais pas, ne coche pas. Le barème ne change pas :
        une famille validée rapporte ce que rapporte la même famille détectée.</p>`;

    if (!d.propositions.length) {
      html += `<p class="resume">Aucune proposition : les offres restantes ne
        recoupent aucun de tes métiers, et c'est probablement juste.</p>`;
    } else {
      html += `<ul class="preuves">${d.propositions.map(p => `
        <li class="pour"><div class="proposition">
          <label class="case-classer"><input type="checkbox" class="classer" checked
            data-offre="${Number(p.offre_id)}" data-famille="${echapper(p.famille)}">
            <b>${echapper(p.titre)}</b></label>
          <span class="menu">${echapper(p.employeur)} · score ${echapper(p.score)}
            · proposé : <b>${echapper(p.libelle)}</b></span>
          <span>${p.preuves.map(x => `<i>${echapper(x)}</i>`).join('<br>')}</span>
        </div></li>`).join('')}</ul>
        <div class="actions">
          <button id="btn-classer">Valider les cochées et rescorer</button>
          <button class="discret" id="btn-rien-cocher">Tout décocher</button>
        </div>`;
    }

    if (d.sans_proposition.length) {
      html += `<details class="repli">
        <summary>${echapper(d.sans_proposition.length)} offre(s) sans aucune proposition</summary>
        <ul class="fichiers">${d.sans_proposition.map(o =>
          `<li>${echapper(o.titre)} — ${echapper(o.employeur)} (${echapper(o.score)})</li>`).join('')}</ul>
      </details>`;
    }
    html += `</div>
      <div class="bloc">
        <h2>Les scores</h2>
        <div class="actions"><button id="btn-recalculer">Recalculer tous les scores</button></div>
      </div>
      <div class="bloc"><p class="resume">Les critères se changent dans la configuration de
        l'instance (<code>criteres.yaml</code>), qui arrive par le déploiement. « Recalculer
        tous les scores » les applique ensuite aux offres déjà collectées.</p></div>`;
    cible.innerHTML = html;

    const decocher = $('#btn-rien-cocher', cible);
    if (decocher) decocher.onclick = () => $$('.classer', cible).forEach(c => { c.checked = false; });

    const valider = $('#btn-classer', cible);
    if (valider) valider.onclick = async () => {
      const decisions = $$('.classer:checked', cible).map(c => ({
        offre_id: Number(c.dataset.offre), famille: c.dataset.famille,
      }));
      if (!decisions.length) { message('Rien de coché.'); return; }
      valider.disabled = true;
      try {
        const r = await api('/api/classement/valider', {
          method: 'POST', body: JSON.stringify({ decisions }),
        });
        message(`${r.validees} offre(s) classée(s) et rescorée(s).`);
        // Les pastilles et la liste se relisent : une offre classée n'est plus à classer.
        rafraichir();
      } catch (e) { message(e.message, true); }
      finally { valider.disabled = false; }
    };

    const recalculer = $('#btn-recalculer', cible);
    recalculer.onclick = async () => {
      recalculer.disabled = true;
      try {
        const r = await api('/api/rescorer', { method: 'POST' });
        message(`${r.offres_recalculees} offre(s) recalculée(s).`);
        rafraichir();
      } catch (e) { message(e.message, true); }
      finally { recalculer.disabled = false; }
    };
  } catch (e) {
    message(e.message, true);
    if (!cible.children.length) {
      cible.innerHTML = `<p class="avert">Mes critères n'ont pas pu se charger : ${echapper(e.message)}</p>`;
    }
  }
}

// ---------------------------------------------------------------------------
// Le mot de relance
//
// La console n'envoie rien. Elle assemble le texte depuis un gabarit et les
// faits enregistrés — la bonne date, le bon poste — puis c'est lui qui envoie
// et qui marque. Le marquage manuel reste.
// ---------------------------------------------------------------------------

async function ouvrirRelance(id) {
  try {
    const r = await api(`/api/offres/${id}/relance`);
    let html = `<h2>Mot de relance</h2>`;
    if (r.avertissements.length) {
      html += `<p class="avert">${r.avertissements.map(echapper).join('<br>')}</p>`;
    }
    if (!r.texte) {
      $('#fenetre-contenu').innerHTML = html;
      ouvrirFenetre();
      return;
    }
    html += `<p class="resume">Assemblé depuis <b>${echapper(r.gabarit)}</b> et
      ce qui est enregistré. Relis-le, complète les crochets, puis envoie-le
      toi-même — la console n'envoie rien.</p>
      ${r.objet ? `<p class="resume"><b>Objet</b> : ${echapper(r.objet)}</p>` : ''}
      ${r.marqueurs_restants.length ? `<p class="avert">À compléter :
        ${r.marqueurs_restants.map(echapper).join(' · ')}</p>` : ''}
      <textarea id="texte-relance" rows="16">${echapper(r.texte)}</textarea>
      <div class="actions">
        <button id="btn-copier-relance">Copier</button>
        <button class="discret" id="btn-relance-envoyee">Je l'ai envoyée</button>
      </div>`;
    $('#fenetre-contenu').innerHTML = html;
    ouvrirFenetre();

    $('#btn-copier-relance').onclick = async () => {
      try {
        await navigator.clipboard.writeText($('#texte-relance').value);
        message('Copié.');
      } catch { message('Copie impossible — sélectionne le texte à la main.', true); }
    };
    $('#btn-relance-envoyee').onclick = async () => {
      try {
        await api(`/api/offres/${id}/relance/envoyee`, { method: 'POST' });
        message('Relance notée comme envoyée.');
        $('#fenetre').close();
        rafraichir();
      } catch (e) { message(e.message, true); }
    };
  } catch (e) { message(e.message, true); }
}

const CHARGEURS = {
  'a-faire': chargerAFaire,
  candidatures: chargerCandidatures,
  // « Plus » n'a rien à charger : ses pastilles se recomptent à chaque `rafraichir()`. Sans
  // cette entrée, `rafraichir()` retomberait sur `chargerOffres`.
  plus: () => {},
  offres: chargerOffres,
  criteres: chargerCriteres,
  bilan: chargerBilan,
  documents: chargerDocuments,
  reglages: chargerReglages,
};

function rafraichir() {
  compterPastilles();
  (CHARGEURS[vueCourante] || chargerOffres)();
}

// Les écrans de « Plus » gardent son onglet allumé.
const ONGLET_DE_VUE = {
  offres: 'plus', criteres: 'plus', bilan: 'plus', documents: 'plus', reglages: 'plus',
};

// La vue `nom`, rechargée, ouverte par le haut. Quand elle change, elle entre dans l'historique,
// au-dessus de celle d'avant ; `historique` faux, elle n'y entre pas : revenue par le retour, ou
// montrée par une page rechargée. Un nom inconnu, celui d'une entrée laissée par une version qui
// aurait renommé sa vue, montre « À faire », plutôt qu'une console vide.
function afficherVue(nom, { historique = true } = {}) {
  if (!$(`#vue-${nom}`)) nom = 'a-faire';
  const vue = $(`#vue-${nom}`);
  if (historique && nom !== vueCourante) {
    const ici = history.state || {};
    history.pushState({ vue: nom, precedente: vueCourante, profondeur: (ici.profondeur || 0) + 1 }, '');
  }
  vueCourante = nom;
  const onglet = ONGLET_DE_VUE[nom] || nom;
  $$('.onglet').forEach(o => o.classList.toggle('actif', o.dataset.vue === onglet));
  $$('.vue').forEach(v => v.classList.toggle('cachee', v !== vue));
  // Un écran s'ouvre par le haut : un lien touché au bas de la file ne mène pas au
  // milieu de la liste suivante.
  window.scrollTo(0, 0);
  rafraichir();
}

// ---------------------------------------------------------------------------
// Le retour d'Android (E10 ; décision 15 du plan du lot 3)
//
// Une entrée d'historique par changement de vue, `{vue, precedente, profondeur}`, et une par
// ouverture de la fenêtre : la même, marquée `fenetre`. Ce que la fenêtre montre ensuite (la
// fiche, puis « Non », une étape, « Dossier prêt », le mot de relance, le canal, le détail) n'en
// ajoute pas : le retour la ferme, quoi qu'elle montre, sans revenir à la fiche. Sans fenêtre, il
// revient à la vue d'avant, rechargée ; depuis « À faire », la première entrée, il quitte
// l'application.
// ---------------------------------------------------------------------------

// Vrai entre le retour que lance la fermeture de la fenêtre et son `popstate`.
let retourDeFermeture = false;
// « Chercher une offre » rejointe par le retour : le curseur va dans la recherche à son arrivée.
let curseurApresRetour = false;
// Un seul retour à la fois. Vrai entre un retour que lance la console (celui d'`allerA`, de la
// fermeture de la fenêtre, ou de l'entrée morte d'une page rechargée) et son `popstate` :
// `allerA` attend, sans rien faire. Un second toucher d'ici là lancerait un second retour, que
// Chromium compte depuis l'entrée où mène le premier, et la console dépasserait la vue d'avant ;
// un onglet touché pousserait sa vue au-dessus d'une entrée que le retour reprend.
let retourEnCours = false;
// Le filet du drapeau : un retour sans entrée à ce pas (la première oubliée, Chrome n'en gardant
// qu'une cinquantaine) ne donne aucun `popstate`. Un retour dans la page arrive en quelques
// millisecondes ; passé une seconde, il n'arrivera plus, et les onglets répondent de nouveau.
let filetDuRetour;
const DELAI_DU_FILET_MS = 1000;

function reculer(pas) {
  retourEnCours = true;
  clearTimeout(filetDuRetour);
  filetDuRetour = setTimeout(() => { retourEnCours = false; }, DELAI_DU_FILET_MS);
  history.go(-pas);
}

// Seule à ouvrir la fenêtre. Fermée, elle entre dans l'historique, puis s'ouvre ; déjà ouverte,
// elle n'y entre pas une seconde fois, et l'appelant ne fait qu'en remplacer le contenu.
function ouvrirFenetre() {
  const fenetre = $('#fenetre');
  if (fenetre.open) return;
  history.pushState({ ...history.state, fenetre: true }, '');
  fenetre.showModal();
}

// Fermée sans traverser l'historique (« Fermer », Échap, un geste qui la ferme, ou le retour
// d'Android quand Chrome la ferme lui-même, par `cancel` puis `close`), la fenêtre retire son
// entrée par un retour. Fermée par le retour, rien à retirer : `close` part après le `popstate`,
// et l'entrée courante est déjà celle de la vue.
$('#fenetre').addEventListener('close', () => {
  if (!history.state?.fenetre) return;
  retourDeFermeture = true;
  reculer(1);
});

// Le retour, et les vues qu'`allerA` rejoint par lui. Celui que lance la fermeture ne touche à
// rien ; mais si la fenêtre s'est rouverte avant qu'il n'arrive, il a pu atterrir sur l'entrée
// de la vue, la fenêtre ouverte : elle y repose la sienne. Un autre ferme la fenêtre ouverte, et
// montre la vue de l'entrée si elle diffère ; la vue sous une fenêtre fermée ne se recharge pas.
window.addEventListener('popstate', ev => {
  const fenetre = $('#fenetre');
  const entree = ev.state || {};
  retourEnCours = false;
  clearTimeout(filetDuRetour);
  if (retourDeFermeture) {
    retourDeFermeture = false;
    if (fenetre.open && !entree.fenetre) history.pushState({ ...ev.state, fenetre: true }, '');
    return;
  }
  if (fenetre.open) fenetre.close();
  if (entree.vue && entree.vue !== vueCourante) afficherVue(entree.vue, { historique: false });
  if (curseurApresRetour && vueCourante === 'offres') $('#f-recherche').focus();
  curseurApresRetour = false;
});

// Le geste de tout `[data-vue]` : les onglets, les lignes de « Plus », « ‹ Plus ». L'onglet
// « À faire » revient à la première entrée : le retour depuis lui quitte toujours l'application.
// La vue ouverte juste avant se rejoint par le retour, sans entrée de plus. Une autre entre dans
// l'historique. `chercher` : « Chercher une offre », le curseur dans la recherche (décision 5),
// posé une fois la vue montrée. Pendant un retour en cours, rien.
function allerA(nom, { chercher = false } = {}) {
  if (retourEnCours) return;
  const ici = history.state || {};
  if (nom === 'a-faire' && ici.profondeur > 0) {
    reculer(ici.profondeur);
  } else if (nom !== vueCourante && ici.precedente === nom) {
    curseurApresRetour = chercher;
    reculer(1);
  } else {
    afficherVue(nom);
    if (chercher) $('#f-recherche').focus();
  }
}

document.addEventListener('click', ev => {
  const lien = ev.target.closest('[data-vue]');
  if (lien) allerA(lien.dataset.vue, { chercher: lien.hasAttribute('data-chercher') });
});

// ---------------------------------------------------------------------------
// Toutes les offres : les gestes de ses trois filtres et de sa bascule
// ---------------------------------------------------------------------------

$('#f-recherche').oninput = () => {
  clearTimeout(minuteurRecherche);
  minuteurRecherche = setTimeout(chargerOffres, 280);
};
$('#f-etat').onchange = () => chargerOffres();
$('#f-famille').onchange = () => chargerOffres();

// L'atout mis en avant par la configuration, en un geste : son avantage le plus rare. Touchée
// pendant le filtre d'un autre atout (un ancien lien), la bascule le remplace.
$('#btn-atout').onclick = () => {
  if (!ATOUT) return;
  atoutFiltre = atoutFiltre === ATOUT.cle ? '' : ATOUT.cle;
  chargerOffres();
};

// « Effacer les filtres » vit dans le résumé, que chaque réponse réécrit.
$('#resume-offres').addEventListener('click', ev => {
  if (ev.target.closest('[data-effacer-filtres]')) effacerFiltres();
});

// ---------------------------------------------------------------------------
// Notifications push (E11 ; décisions 11 et 12 du plan du lot 3)
//
// Réglages dit ce que reçoit cet appareil, en cinq cas, chacun sa phrase. À l'ouverture, la
// console renvoie l'abonnement de cet appareil, ou se réabonne, sans jamais demander la
// permission : sans geste, Chrome la refuse ou l'ignore. Aucun de ces gestes n'écrit de message
// ni rien dans la console du navigateur : leur résultat se lit dans Réglages.
// ---------------------------------------------------------------------------

const ETATS_PUSH = {
  indisponible: 'Les notifications ne sont pas disponibles sur cet appareil.',
  bloquees: "Les notifications sont bloquées pour la console sur cet appareil. Autorise-les dans les réglages d'Android (Applications › Veille emploi › Notifications) ou dans ceux du site, dans Chrome, puis touche « Activer les notifications ».",
  inactives: 'Cet appareil ne reçoit pas les notifications.',
  actives: 'Cet appareil reçoit les notifications.',
  erreur: cause => `Cet appareil n'a pas pu s'abonner aux notifications : ${cause}. Touche « Activer les notifications » pour réessayer.`,
};
// Ce qui manque à un appareil où les notifications ne sont pas disponibles.
const RAISONS_PUSH = {
  navigateur: 'Ce navigateur ne gère pas le push web.',
  https: 'Il faut ouvrir la console en HTTPS.',
  vapid: "Le serveur n'a pas de clé VAPID : elle naît au démarrage de la console (sans conteneur, `veille init`).",
};
// Le premier essai n'était pas parti, le second, après un nouvel abonnement, l'est (réponse R3).
const REPARATION_PUSH = "Le premier essai n'était pas parti : l'abonnement de cet appareil vient d'être refait, et la notification d'essai est partie.";
const CAUSES_PUSH = {
  serviceWorker: "le service worker de la console ne s'est pas enregistré",
  essai: "la notification d'essai n'est pas partie, même avec un nouvel abonnement",
};

// `cle` : l'un des cinq cas d'`ETATS_PUSH`, ou '' tant que l'ouverture ne l'a pas lu (le renvoi
// de l'abonnement en cours) : aucune phrase, plutôt qu'une phrase fausse. `detail` : la raison
// d'un état indisponible, la cause d'une erreur, ou la phrase de la réparation d'un état actif.
let etatPush = { cle: '', detail: '' };
// Un seul geste du push à la fois (le renvoi de l'ouverture, ou un toucher du bouton) : le bouton
// reste éteint jusqu'à sa fin, même quand Réglages se recharge entre-temps.
let gestePush = false;

function base64EnOctets(base64) {
  const bourrage = '='.repeat((4 - base64.length % 4) % 4);
  const brut = atob((base64 + bourrage).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...brut].map(c => c.charCodeAt(0)));
}

// Un texte échappé, ses `…` rendus en code.
function avecCode(texte) {
  return echapper(texte).replace(/`([^`]+)`/g, '<code>$1</code>');
}

// La cause d'un échec, sans point final : la phrase « en erreur » met le sien.
function causeDe(erreur) {
  return String((erreur && erreur.message) || erreur || '').replace(/[\s.]+$/, '') || 'cause inconnue';
}

// Le cas d'`etatPush`, dans Réglages : sa phrase, et le bouton qui va avec. Le bouton essaie
// quand cet appareil reçoit, et active sinon ; il s'éteint pendant un geste, et quand le push
// n'est pas disponible.
function afficherEtatPush() {
  const { cle, detail } = etatPush;
  const phrase = cle === 'erreur'
    ? ETATS_PUSH.erreur(detail)
    : [ETATS_PUSH[cle], detail].filter(Boolean).join(' ');
  $('#etat-push').innerHTML = avecCode(phrase);
  const bouton = $('#btn-push');
  bouton.textContent = cle === 'actives' ? "Envoyer une notification d'essai" : 'Activer les notifications';
  bouton.disabled = gestePush || cle === 'indisponible';
}

// Ce qui manque au push sur cet appareil, ou '' : le contexte sûr d'abord, puisque hors HTTPS
// Chrome retire aussi le service worker et le push, puis les API, puis la clé du serveur.
function raisonPushIndisponible() {
  if (!window.isSecureContext) return RAISONS_PUSH.https;
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return RAISONS_PUSH.navigateur;
  }
  if (!CLE_VAPID) return RAISONS_PUSH.vapid;
  return '';
}

// Enregistre `/sw.js`, puis attend un service worker actif : Chrome rejette un `subscribe` sans
// lui. Rend l'enregistrement actif, ou null si `/sw.js` ne s'enregistre pas.
async function enregistrerServiceWorker() {
  try {
    await navigator.serviceWorker.register('/sw.js');
  } catch (e) {
    return null;
  }
  return navigator.serviceWorker.ready;
}

function envoyerAbonnement(abonnement) {
  return api('/api/push/abonnement', { method: 'POST', body: JSON.stringify(abonnement.toJSON()) });
}

// Abonne cet appareil avec la clé de la page, puis envoie l'abonnement au serveur.
async function abonner(enregistrement) {
  const abonnement = await enregistrement.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64EnOctets(CLE_VAPID),
  });
  await envoyerAbonnement(abonnement);
}

// Les clés se comparent sur leurs octets : `options.applicationServerKey` est un ArrayBuffer, la
// clé de la page du base64url. Comparées en chaînes, elles différeraient toujours. Une clé
// illisible (sans `options`, ou `null`) ne dit rien : l'abonnement se renvoie tel quel, et l'essai
// détectera un abonnement rejeté.
function porteUneAutreCle(abonnement) {
  const cle = abonnement.options && abonnement.options.applicationServerKey;
  if (!cle) return false;
  const sienne = new Uint8Array(cle);
  const attendue = base64EnOctets(CLE_VAPID);
  return sienne.length !== attendue.length || sienne.some((octet, i) => octet !== attendue[i]);
}

// Met l'abonnement de cet appareil au serveur : le crée s'il manque ; le refait s'il a été fait
// avec une autre clé VAPID que celle de la page (Chrome refuse un `subscribe` tant qu'il reste),
// puis retire l'ancien du serveur, qu'un push en 403 ne retirerait jamais (réponse 22) ; sinon,
// le renvoie tel quel. Un retrait refusé ne dit rien : la ligne morte qui reste est tolérée
// (décision 12, seconde limite).
async function mettreAJourAbonnement(enregistrement) {
  const abonnement = await enregistrement.pushManager.getSubscription();
  if (!abonnement) {
    await abonner(enregistrement);
  } else if (porteUneAutreCle(abonnement)) {
    await abonnement.unsubscribe();
    await abonner(enregistrement);
    try {
      await api(`/api/push/abonnement?endpoint=${encodeURIComponent(abonnement.endpoint)}`,
                { method: 'DELETE' });
    } catch (e) { /* tolérée : voir plus haut */ }
  } else {
    await envoyerAbonnement(abonnement);
  }
}

// Lancée une fois, à l'ouverture, jamais au retour au premier plan. Permission accordée, elle met
// l'abonnement de cet appareil au serveur (`mettreAJourAbonnement`) ; le bouton reste éteint, et
// Réglages ne dit rien, tant qu'elle n'a pas fini. Rend le cas atteint.
async function synchroniserPush() {
  const raison = raisonPushIndisponible();
  if (raison) {
    etatPush = { cle: 'indisponible', detail: raison };
  } else if (Notification.permission === 'denied') {
    etatPush = { cle: 'bloquees', detail: '' };
  } else if (Notification.permission !== 'granted') {
    etatPush = { cle: 'inactives', detail: '' };
  } else {
    gestePush = true;
    afficherEtatPush();
    try {
      const enregistrement = await enregistrerServiceWorker();
      if (!enregistrement) throw new Error(CAUSES_PUSH.serviceWorker);
      await mettreAJourAbonnement(enregistrement);
      etatPush = { cle: 'actives', detail: '' };
    } catch (e) {
      etatPush = { cle: 'erreur', detail: causeDe(e) };
    } finally {
      gestePush = false;
    }
  }
  afficherEtatPush();
  return etatPush.cle;
}

// « Envoyer une notification d'essai », et la fin d'« Activer les notifications ». L'essai lit sa
// réponse (réponse R3) : Chrome peut garder un abonnement que le service push a rejeté, et que le
// serveur a retiré. Si `envoyes` vaut 0 (jamais sur `echecs` : un essai parti ne répare rien),
// l'abonnement se refait, une fois, sans `DELETE` de l'ancien, que le serveur a retiré au 404 ou au
// 410, puis l'essai se relance, une fois.
async function envoyerEssai() {
  try {
    const essai = await api('/api/push/test', { method: 'POST' });
    if (essai.envoyes > 0) {
      etatPush = { cle: 'actives', detail: '' };
    } else {
      const enregistrement = await enregistrerServiceWorker();
      if (!enregistrement) throw new Error(CAUSES_PUSH.serviceWorker);
      const rejete = await enregistrement.pushManager.getSubscription();
      if (rejete) await rejete.unsubscribe();
      await abonner(enregistrement);
      const second = await api('/api/push/test', { method: 'POST' });
      etatPush = second.envoyes > 0
        ? { cle: 'actives', detail: REPARATION_PUSH }
        : { cle: 'erreur', detail: CAUSES_PUSH.essai };
    }
  } catch (e) {
    etatPush = { cle: 'erreur', detail: causeDe(e) };
  }
  afficherEtatPush();
}

// « Activer les notifications » : la permission, l'abonnement mis au serveur comme à l'ouverture
// (`mettreAJourAbonnement`, qui refait celui d'une autre clé), puis l'essai, par `envoyerEssai`.
// Ses refus se disent dans Réglages, par les phrases d'`ETATS_PUSH`.
async function activerPush() {
  const raison = raisonPushIndisponible();
  if (raison) {
    etatPush = { cle: 'indisponible', detail: raison };
    afficherEtatPush();
    return;
  }
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      etatPush = { cle: permission === 'denied' ? 'bloquees' : 'inactives', detail: '' };
      afficherEtatPush();
      return;
    }
    const enregistrement = await enregistrerServiceWorker();
    if (!enregistrement) throw new Error(CAUSES_PUSH.serviceWorker);
    await mettreAJourAbonnement(enregistrement);
  } catch (e) {
    etatPush = { cle: 'erreur', detail: causeDe(e) };
    afficherEtatPush();
    return;
  }
  await envoyerEssai();
}

// Le drapeau éteint le bouton pendant le geste ; il se rallume avec le nouvel état. La demande de
// permission d'`activerPush` part encore dans le geste : rien n'est attendu avant elle.
$('#btn-push').onclick = async () => {
  gestePush = true;
  afficherEtatPush();
  try {
    await (etatPush.cle === 'actives' ? envoyerEssai() : activerPush());
  } finally {
    gestePush = false;
    afficherEtatPush();
  }
};

synchroniserPush();

// ---------------------------------------------------------------------------

// L'entrée dans la console (décision 15). Une entrée qui porte déjà sa vue, celle d'une page
// rechargée, la montre, sans fenêtre ; si elle porte aussi la fenêtre, un retour retire cette
// entrée morte, et son `popstate`, sur la même vue, ne la recharge pas. Sinon, « À faire » est la
// première entrée, à l'adresse `/`. La notification ouvre `/?filtre=nouveau` : la file, qu'elle
// annonce. Un ancien lien d'entrée ouvre « Toutes les offres », posée au-dessus d'« À faire »
// (décision 3 du plan du lot 3) : `?filtre=<statut>`, que le serveur traduit en état
// (`data-etat-demande`, le JS ne traduit aucun statut), ou `?atout=`.
//
// Le défilement est à la console : revenue par le retour, une vue s'ouvre en haut (décision 15).
// Chromium restaurerait celui de son entrée à la première image après le `popstate`, par-dessus
// le `scrollTo(0, 0)` d'`afficherVue`. Posé ici, avant toute entrée, le mode vaut pour toutes
// celles que la console pousse ensuite. La vue sous une fenêtre fermée ne bouge pas pour autant :
// la fenêtre ne fait pas défiler la page, et le `popstate` ne remontre pas la même vue.
history.scrollRestoration = 'manual';
const entreeChargee = history.state;
if (entreeChargee && entreeChargee.vue) {
  afficherVue(entreeChargee.vue, { historique: false });
  if (entreeChargee.fenetre) reculer(1);
} else {
  const etatDemande = document.body.dataset.etatDemande || '';
  const atoutDemande = new URLSearchParams(location.search).get('atout') || '';
  history.replaceState({ vue: 'a-faire', precedente: null, profondeur: 0 }, '', '/');
  if (etatDemande) $('#f-etat').value = etatDemande;
  atoutFiltre = atoutDemande;
  afficherVue(etatDemande || atoutDemande ? 'offres' : 'a-faire');
}
