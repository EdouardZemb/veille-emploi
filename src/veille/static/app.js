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
  collecte_en_cours: "Une collecte est déjà en cours.",
  configuration_non_designee: "Aucune configuration n'est désignée : cette console sert l'exemple. Pose VEILLE_CONFIG (docs/exploitation.md, « La configuration désignée »).",
  connexion_impossible: "La passkey n'a pas été reconnue.",
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
    return `<li><span class="pts ${cls}">${signe}${c.points}</span>
      <span><b>${echapper(c.libelle)}</b>${c.detail ? ` <span class="contrib-detail">${echapper(c.detail)}</span>` : ''}</span></li>`;
  }).join('');
}

function carteOffre(o) {
  const n = niveau(o.score);
  const meta = [o.employeur, o.lieu, o.type_contrat, o.date_publication, o.source]
    .filter(Boolean).map(x => `<span>${echapper(x)}</span>`).join('');

  const etiquettes = [etiquetteSalaire(o)];
  // L'atout mis en avant (choisi dans la configuration) passe en premier.
  if (ATOUT && (o.atouts || []).includes(ATOUT.cle)) {
    etiquettes.unshift(`<span class="etiquette atout-fort" title="${echapper(ATOUT.titre)}">${echapper(ATOUT.libelle)}</span>`);
  }
  (o.atouts || []).filter(a => !ATOUT || a !== ATOUT.cle).forEach(a => {
    etiquettes.push(`<span class="etiquette atout">${echapper(a.replace(/_/g, ' '))}</span>`);
  });
  if (o.donnees_partielles) {
    etiquettes.push('<span class="etiquette alerte" title="Le mail ne contenait qu\'un extrait : le score ne porte que sur l\'intitule et le lieu">donnees partielles</span>');
  }
  if (o.statut && o.statut !== 'nouveau') {
    etiquettes.push(`<span class="etiquette">${echapper(o.statut.replace(/_/g, ' '))}</span>`);
  }
  if (o.motif_ecartement) {
    etiquettes.push(`<span class="etiquette grave">${echapper(o.motif_ecartement)}</span>`);
  }
  if (o.date_relance_due) {
    etiquettes.push(`<span class="etiquette">relance le ${echapper(o.date_relance_due)}</span>`);
  }

  const contribs = listeContributions(o);

  const titre = o.url
    ? `<a href="${echapper(o.url)}" target="_blank" rel="noopener noreferrer">${echapper(o.titre)}</a>`
    : echapper(o.titre);

  return `
  <article class="offre ${n}" data-id="${o.id}">
    <div class="offre-haut">
      <div>
        <p class="offre-titre">${titre}</p>
        <div class="meta">${meta}</div>
      </div>
      <span class="score ${n}">${o.score}</span>
    </div>
    <div class="reperes">${pastilleVerification(o)}${pastilleCompletude(o.completude)}</div>
    <div class="etiquettes">${etiquettes.join('')}</div>
    <details class="explication">
      <summary>Pourquoi ce score</summary>
      <ul class="contribs">${contribs || '<li>aucune contribution</li>'}</ul>
    </details>
    <div class="actions">
      <button data-action="dossier">Generer le dossier</button>
      <button class="discret" data-action="statut" data-statut="interessante">Interessante</button>
      <button class="discret" data-action="statut" data-statut="a_traiter">A traiter</button>
      <button class="discret" data-action="envoyee">Candidature envoyee</button>
      <button class="discret" data-action="relance">Mot de relance</button>
      <button class="discret" data-action="ecarter">Ecarter</button>
      <button class="discret" data-action="entretien">Préparer l'entretien</button>
      <button class="discret" data-action="detail">${o.donnees_partielles ? `Lire l'annonce` : 'Detail'}</button>
      <button class="discret obsolete" data-action="obsolete" title="Tu as ouvert l'annonce et elle n'y est plus">Obsolète</button>
    </div>
  </article>`;
}

// ---------------------------------------------------------------------------
// Fraîcheur de vérification : trois états, pas un seul indicateur
//
//   • vérifiée automatiquement — on a pu sonder le site
//   • vérifiée par toi         — tu as regardé, ça vaut preuve
//   • jamais vérifiée          — dont « non vérifiable », site qui l'interdit
//
// Ces trois choses ne veulent pas dire la même chose et ne doivent pas se
// ressembler. Une annonce jamais vue et une annonce vue ce matin non plus :
// d'où l'âge en clair, et pas une date enfouie dans le détail.
// ---------------------------------------------------------------------------

function ageEnJours(horodatage) {
  if (!horodatage) return null;
  const t = Date.parse(horodatage);
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86400000);
}

function etatVerification(o) {
  if (o.verdict_verification === 'interdite') {
    return { cle: 'non-verifiable', texte: 'non vérifiable', titre:
      "Ce site interdit la lecture automatisée : seule ta vérification compte." };
  }
  if (!o.verifiee_le) {
    return { cle: 'jamais', texte: 'jamais vérifiée', titre:
      "Cette annonce n'a jamais été contrôlée." };
  }
  const j = ageEnJours(o.verifiee_le);
  const quand = j === 0 ? "aujourd'hui" : j === 1 ? 'hier' : `il y a ${j} j`;
  const qui = o.verifiee_par === 'edouard' ? 'par toi' : 'auto';
  const vieille = j !== null && j >= 7;
  return {
    cle: qui === 'par toi' ? 'par-edouard' : (vieille ? 'ancienne' : 'auto'),
    texte: `vérifiée ${quand} · ${qui}`,
    titre: o.motif_verification || '',
  };
}

function pastilleVerification(o) {
  const e = etatVerification(o);
  return `<span class="verif ${e.cle}" title="${echapper(e.titre)}">${echapper(e.texte)}</span>`;
}

// ---------------------------------------------------------------------------
// Complétude — DEUXIÈME axe, jamais mélangé au score de correspondance
//
// Le score dit si l'offre lui va. La complétude dit si on en sait assez pour
// écrire une candidature qui tienne. Une offre à 87 mal documentée et une
// offre à 25 bien documentée doivent rester lisibles séparément : aucune
// moyenne des deux n'existe nulle part.
// ---------------------------------------------------------------------------

function pastilleCompletude(c) {
  if (!c) return '';
  return `<span class="completude ${echapper(c.niveau)}"
    title="Information disponible sur le poste — sans rapport avec le score de correspondance">
    dossier ${c.score}/100 · ${echapper(c.niveau)}</span>`;
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
  message(enLigne ? 'Notée encore en ligne.' : 'Archivée — annulable dans Plus › Archive.');
}

// ---------------------------------------------------------------------------
// Chargement des listes
// ---------------------------------------------------------------------------

let offresCourantes = [];

async function chargerOffres() {
  const p = new URLSearchParams();
  const r = $('#f-recherche').value.trim();
  if (r) p.set('recherche', r);
  for (const [id, cle] of [['#f-statut', 'statut'], ['#f-zone', 'zone'],
                           ['#f-famille', 'famille'], ['#f-atout', 'atout']]) {
    if ($(id).value) p.set(cle, $(id).value);
  }
  if (aDocumenter) p.set('a_documenter', 'true');
  if ($('#f-verification').value) p.set('verification', $('#f-verification').value);
  if ($('#f-tri').value) p.set('tri', $('#f-tri').value);
  if ($('#f-ecartees').checked) p.set('inclure_ecartees', 'true');

  try {
    const d = await api('/api/offres?' + p);
    offresCourantes = d.offres;
    // Le compte vient AVEC la liste : le bouton dit toujours la verite, sans
    // requete supplementaire.
    const badge = $('#compte-documenter');
    badge.textContent = d.a_documenter ? String(d.a_documenter) : '';
    badge.classList.toggle('visible', Boolean(d.a_documenter));
    const actifs = filtresActifs();

    let vide;
    if (aDocumenter && !d.offres.length) {
      vide = `<p class="resume">Rien à documenter : toutes tes offres au-dessus du
        seuil ont assez d'information pour un dossier. Reclique sur
        <b>À documenter</b> pour revoir la liste complète.</p>`;
    } else if (actifs.length) {
      // Ne jamais laisser croire que la base est vide alors qu'un filtre la
      // restreint : c'est le piege classique d'un panneau replie.
      vide = `<p class="resume">Aucune offre avec
        ${actifs.map(a => `<b>${echapper(a.libelle.toLowerCase())} : ${echapper(a.valeur)}</b>`).join(' et ')}.
        <button class="discret" id="tout-effacer">Effacer les filtres</button></p>`;
    } else {
      vide = `<p class="resume">Aucune offre en base. La collecte n'a encore rien trouve :
        lance <code>veille collecter</code> sur le serveur, ou verifie que tes alertes mail
        arrivent bien dans le libelle configure.</p>`;
    }
    $('#liste-offres').innerHTML = d.offres.map(carteOffre).join('') || vide;
    const bouton = $('#tout-effacer');
    if (bouton) bouton.onclick = () => {
      CHAMPS_FILTRES.forEach(c => { $(c.id).value = ''; });
      $('#f-ecartees').checked = false;
      synchroniserFiltres();
      chargerOffres();
    };

    const bonnes = d.offres.filter(o => o.score >= SEUIL).length;
    $('#resume-offres').textContent =
      `${d.offres.length} offre(s) affichee(s), dont ${bonnes} au-dessus du seuil de ${SEUIL}.`
      + (actifs.length ? ` ${actifs.length} filtre(s) actif(s).` : '');
  } catch (e) { message(e.message, true); }
}

async function chargerRelances() {
  try {
    const d = await api('/api/relances');
    $('#liste-relances').innerHTML = d.relances.map(carteOffre).join('') ||
      '<p class="resume">Aucune relance due.</p>';
    $('#pastille-relances').textContent = d.relances.length || '';
  } catch (e) { message(e.message, true); }
}

function tableau(titre, lignes, colonnes) {
  if (!lignes.length) return '';
  const entetes = colonnes.map(c => `<th class="${c.n ? 'n' : ''}">${c.libelle}</th>`).join('');
  const corps = lignes.map(l =>
    '<tr>' + colonnes.map(c => `<td class="${c.n ? 'n' : ''}">${echapper(c.valeur(l))}</td>`).join('') + '</tr>'
  ).join('');
  return `<div class="bloc"><h2>${titre}</h2><table><thead><tr>${entetes}</tr></thead><tbody>${corps}</tbody></table></div>`;
}

async function chargerPilotage() {
  try {
    const e = await api('/api/entonnoir');
    let html = `<div class="bloc"><h2>Entonnoir</h2><div class="chiffres">
      <div class="chiffre"><b>${e.total}</b><span>offres collectees</span></div>
      <div class="chiffre"><b>${e.par_statut.nouveau || 0}</b><span>nouvelles</span></div>
      <div class="chiffre"><b>${e.envoyees}</b><span>candidatures</span></div>
      <div class="chiffre"><b>${e.repondues}</b><span>reponses</span></div>
      <div class="chiffre"><b>${e.taux_reponse_global}%</b><span>taux de reponse</span></div>
    </div></div>`;

    html += tableau('Par canal de candidature', e.par_canal, [
      { libelle: 'Canal', valeur: l => l.canal },
      { libelle: 'Envoyees', n: 1, valeur: l => l.envoyees },
      { libelle: 'Reponses', n: 1, valeur: l => l.reponses },
      { libelle: 'Taux', n: 1, valeur: l => l.taux_reponse + '%' },
    ]);
    html += tableau('Par famille de metier', e.par_famille, [
      { libelle: 'Famille', valeur: l => l.famille },
      { libelle: 'Envoyees', n: 1, valeur: l => l.envoyees },
      { libelle: 'Reponses', n: 1, valeur: l => l.reponses },
      { libelle: 'Taux', n: 1, valeur: l => l.taux_reponse + '%' },
    ]);
    html += tableau('Rendement des sources', e.par_source, [
      { libelle: 'Source', valeur: l => l.source },
      { libelle: 'Collectees', n: 1, valeur: l => l.collectees },
      { libelle: 'Retenues', n: 1, valeur: l => l.retenues },
      { libelle: 'Candidatures', n: 1, valeur: l => l.candidatures },
    ]);
    html += tableau("Motifs d'ecartement - ce que le scoring rate", e.motifs_ecartement, [
      { libelle: 'Motif', valeur: l => l.motif },
      { libelle: 'Nombre', n: 1, valeur: l => l.n },
      { libelle: 'Score moyen', n: 1, valeur: l => l.score_moyen },
    ]);
    if (e.motifs_ecartement.length >= 30) {
      html += `<div class="bloc"><p class="resume">Tu as passe les 30 offres ecartees :
        les motifs ci-dessus sont maintenant assez nombreux pour dire ce que le scoring rate.
        Regarde ceux qui reviennent avec un score eleve - ce sont des regles a ajouter
        dans le <code>criteres.yaml</code> de ta configuration (<code>VEILLE_CONFIG</code>).</p></div>`;
    }
    $('#entonnoir').innerHTML = html;
  } catch (e) { message(e.message, true); }
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
        <p class="resume">Aucun pour l'instant. Le bouton « Générer le dossier »
        d'une offre en crée un, et il apparaîtra ici.</p></div>`;
    }

    cible.innerHTML = html;
  } catch (e) { message(e.message, true); }
}

// ---------------------------------------------------------------------------
// Réglages — ce qui s'ajuste sans SSH
// ---------------------------------------------------------------------------

async function chargerReglages() {
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

function afficherDossier(id, d) {
  const avert = d.avertissements.map(a => `<p class="avert">${echapper(a)}</p>`).join('');
  const fichiers = d.fichiers.map(f =>
    `<li><a href="/api/offres/${id}/dossier/${encodeURIComponent(f)}" download>${echapper(f)}</a></li>`).join('');
  const c = d.completude;
  // Quand le kit n'est pas branche, la lettre n'est qu'un squelette et aucun CV
  // n'est joint. Le dire FRANCHEMENT et en premier : sans ca, il voit un
  // resultat creux et conclut que « la generation ne fonctionne pas ».
  const provisoire = d.kit_provisoire ? `
    <p class="avert grave"><b>⚠ Ton kit de candidature n'est pas branché</b><br>
      Ce dossier contient un <b>squelette</b> de lettre — aucune phrase écrite — et
      <b>aucun CV</b>. Ce n'est pas une panne : la console n'a rien à joindre.
      Les pièces sont sur ton PC, pas sur le serveur.</p>` : '';

  $('#fenetre-contenu').innerHTML = `
    <h2>Dossier genere</h2>
    ${provisoire}
    <p class="resume">${echapper(d.dossier)}</p>
    ${c ? `<p class="resume"><span class="completude ${echapper(c.niveau)}">dossier ${c.score}/100 · ${echapper(c.niveau)}</span></p>` : ''}
    ${d.gabarit_lettre ? `<p class="resume">Lettre construite depuis le gabarit <code>${echapper(d.gabarit_lettre)}</code>.</p>` : ''}
    ${avert}
    <ul class="fichiers">${fichiers}</ul>
    <p><a href="${d.archive}" download><b>Télécharger le paquet d'envoi (.zip)</b></a>
       &nbsp;·&nbsp;
       <a class="discret" href="${d.archive_complete}" download>dossier complet, avec ta fiche de préparation</a></p>
    <div id="zone-affinement"></div>`;
  $('#fenetre').showModal();
  blocAffinement(id).then(h => { $('#zone-affinement').innerHTML = h; brancherAffinement(id); });
}

// Ce qui manque, nommé, avec l'action qui le comble. « Information
// insuffisante » sans dire laquelle ne sert à rien.
function afficherCompletudeInsuffisante(id, c, bouton) {
  const manques = c.manques.map(m =>
    `<li class="contre"><span class="pts moins">-${m.points}</span>
      <span><b>${echapper(m.libelle)}</b><br>
      <span class="citation">${echapper(m.quoi_faire)}</span></span></li>`).join('');
  $('#fenetre-contenu').innerHTML = `
    <h2>Information trop mince pour un dossier sérieux</h2>
    <p class="avert grave"><b>Dossier ${c.score}/100 — ${echapper(c.niveau)}</b><br>
      Le seuil est à ${c.seuil}. Une lettre écrite là-dessus sera générique, et
      ça se verra. Ce chiffre n'a <b>rien à voir</b> avec le score de
      correspondance : il dit ce qu'on <i>sait</i>, pas si le poste te va.</p>
    <p class="resume"><b>Ce qui manque, par ordre d'importance</b></p>
    <ul class="preuves">${manques}</ul>
    ${c.acquis.length ? `<p class="resume"><b>Déjà acquis</b> : ${echapper(c.acquis.join(', '))}.</p>` : ''}
    <div class="actions">
      <button id="btn-completer">Compléter l'annonce d'abord</button>
      <button class="discret" id="btn-forcer">Générer quand même</button>
    </div>`;
  $('#fenetre').showModal();
  $('#btn-completer').onclick = () => { $('#fenetre').close(); ouvrirDetail(id); };
  $('#btn-forcer').onclick = async () => {
    $('#fenetre').close();
    try {
      const d = await api(`/api/offres/${id}/dossier?forcer=true`, { method: 'POST' });
      afficherDossier(id, d);
    } catch (e) { message(e.message, true); }
  };
}

async function genererDossier(id, bouton) {
  // Le libellé revient tel qu'il était : « Générer » ou « Régénérer le dossier » (la fiche).
  const libelle = bouton.textContent;
  bouton.disabled = true;
  bouton.textContent = 'Generation...';
  try {
    const d = await api(`/api/offres/${id}/dossier`, { method: 'POST' });
    if (d.ok === false && d.raison === 'completude_insuffisante') {
      afficherCompletudeInsuffisante(id, d.completude, bouton);
      return;
    }
    afficherDossier(id, d);
  } catch (e) {
    message(e.message, true);
  } finally {
    bouton.disabled = false;
    bouton.textContent = libelle;
  }
}

function demanderMotif(id) {
  $('#fenetre-contenu').innerHTML = `
    <h2>Ecarter cette offre</h2>
    <p class="resume">Le motif est obligatoire : c'est lui qui dira, au bout d'une trentaine
    d'offres, ce que le scoring rate. Une offre ecartee ne remontera jamais.</p>
    <textarea id="motif" placeholder="Ex : trop junior / stack sans rapport / employeur deja contacte"></textarea>
    <div class="actions">
      <button id="valider-motif">Ecarter</button>
      <button class="discret" id="annuler-motif">Annuler</button>
    </div>`;
  $('#fenetre').showModal();
  $('#annuler-motif').onclick = () => $('#fenetre').close();
  $('#valider-motif').onclick = async () => {
    const motif = $('#motif').value.trim();
    if (!motif) { message('Un motif est necessaire.', true); return; }
    $('#fenetre').close();
    try { await changerStatut(id, 'ecartee', motif); }
    catch (e) { message(e.message, true); }
  };
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
  $('#fenetre').showModal();
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

// Les cinq états, et la mise de côté, tels que l'écran les nomme (`etats.py` les lit).
const LIBELLES_ETAT = {
  a_voir: 'À voir',
  je_postule: 'Je postule',
  envoyee: 'Envoyée',
  entretien: 'Entretien',
  close: 'Close',
  mise_de_cote: 'Mise de côté',
};

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
// dessous : « Toutes les offres », filtrée sur les nouvelles.
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
    $$('[data-vers-toutes]', cible).forEach(b => {
      b.onclick = () => {
        $('#f-statut').value = 'nouveau';
        synchroniserFiltres();
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
  if (!fenetre.open) fenetre.showModal();
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

// « Plus » : les pastilles de ses lignes, à chaque ouverture.
async function chargerPlus() {
  compterArchiveNouvelles();
  try {
    const [r, c] = await Promise.all([api('/api/relances'), api('/api/classement')]);
    $('#pastille-relances').textContent = r.relances.length || '';
    $('#pastille-classer').textContent = c.propositions.length || '';
  } catch (e) { message(e.message, true); }
}

// ---------------------------------------------------------------------------
// La fiche par état (ADR-0003, § 4)
//
// L'offre, son état, et une seule ligne d'actions : celle de cet état. Le reste attend,
// replié : pourquoi ce score, les notes, les autres actions. Un geste fait depuis la fiche
// la rouvre sur le nouvel état ; ceux qui ouvrent leur propre fenêtre (le dossier, le canal,
// la relance, l'entretien, « Non ») y prennent sa place.
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
      // Au lot 1, sans dossier, le geste actuel : « Préparer ma candidature » vient au lot 2.
      if (!o.dossier_chemin) return '<button data-action="dossier">Générer le dossier</button>';
      return `<button data-action="envoyee">Je l'ai envoyée</button>
        <a href="/api/offres/${Number(o.id)}/dossier/archive" download>Paquet d'envoi (.zip)</a>
        <button class="discret" data-action="dossier">Régénérer le dossier</button>`;
    case 'envoyee':
      return `<button data-action="relance">Mot de relance</button>
        ${boutonsReponse([['entretien', 'Entretien'], ['refus', 'Refus'], ['accepte', 'Acceptée']])}
        ${o.date_relance_due ? `<span class="menu">Relance le ${echapper(o.date_relance_due)}</span>` : ''}`;
    case 'entretien':
      return `<button data-action="entretien">Préparer l'entretien</button>
        ${boutonsReponse([['refus', 'Refus'], ['accepte', 'Acceptée']])}`;
    default:
      // Close : aucune action, le motif s'il existe.
      return o.motif_ecartement ? `<p class="motif">${echapper(o.motif_ecartement)}</p>` : '';
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
  // Remise à plus tard, l'offre reste « À voir », mais s'affiche « Plus tard » (ADR-0003, § 1).
  const etat = o.statut === 'a_traiter' ? 'Plus tard' : (LIBELLES_ETAT[o.etat] || o.etat);
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
  if (!fenetre.open) fenetre.showModal();
}

// Le statut, puis la fiche sur le nouvel état ; `changerStatut` recharge la vue de derrière.
async function changerStatutPuisFiche(id, statut) {
  await changerStatut(id, statut);
  await ouvrirFiche(id);
}

async function enregistrerNotes(id, bouton) {
  const notes = $('textarea', bouton.closest('.fiche')).value;
  await api(`/api/offres/${id}`, { method: 'POST', body: JSON.stringify({ notes }) });
  message('Notes enregistrées.');
  await ouvrirFiche(id);
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
  else if (groupe === 'envoyee' && o.date_relance_due) repere = `relance le ${o.date_relance_due}`;
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
    $('#fenetre').showModal();
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
    $('#fenetre').showModal();
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
  if (a === 'dossier') genererDossier(id, bouton);
  else if (a === 'statut') changerStatut(id, bouton.dataset.statut).catch(e => message(e.message, true));
  else if (a === 'ecarter') demanderMotif(id);
  else if (a === 'envoyee') demanderCanal(id);
  else if (a === 'relance') ouvrirRelance(id);
  else if (a === 'entretien') ouvrirEntretien(id);
  else if (a === 'detail') ouvrirDetail(id);
  else if (a === 'obsolete') constater(id, false).catch(e => message(e.message, true));
  else if (a === 'postuler') gesteNeuf(bouton, () => changerStatutPuisFiche(id, 'interessante'));
  else if (a === 'plus-tard') gesteNeuf(bouton, () => (dansFiche
    ? changerStatutPuisFiche(id, 'a_traiter') : changerStatut(id, 'a_traiter')));
  // Le panneau « Non » nomme l'offre : l'intitulé de sa carte, ou de sa fiche.
  else if (a === 'non') demanderNon(id, $('.offre-titre', offre)?.textContent.trim() || '');
  else if (a === 'reponse') gesteNeuf(bouton, () => changerStatutPuisFiche(id, bouton.dataset.statut));
  else if (a === 'revenir') gesteNeuf(bouton, () => changerStatutPuisFiche(id, 'nouveau'));
  else if (a === 'notes') gesteNeuf(bouton, () => enregistrerNotes(id, bouton));
  else if (a === 'fiche') ouvrirFiche(id).catch(e => message(e.message, true));
});

// ---------------------------------------------------------------------------
// Onglets, filtres
// ---------------------------------------------------------------------------

let vueCourante = 'offres';

// ---------------------------------------------------------------------------
// Archive : les annonces retirées de leur site
//
// Règle du dispositif : archiver à tort est bien pire que garder une annonce
// morte. Trois conséquences visibles ici —
//   1. le motif est TOUJOURS affiché, jamais une disparition muette ;
//   2. une pastille compte ce qui est parti depuis sa dernière visite, pour
//      qu'une archive automatique ne soit jamais invisible ;
//   3. « Remettre dans le flux » est définitif : la vérification ne réarchive
//      jamais ce qu'il vient de ressortir.
// ---------------------------------------------------------------------------

const CLE_VISITE_ARCHIVE = 'veille:archive-vue-le';

function derniereVisiteArchive() {
  try { return localStorage.getItem(CLE_VISITE_ARCHIVE) || ''; }
  catch { return ''; }
}

function marquerArchiveVue() {
  try { localStorage.setItem(CLE_VISITE_ARCHIVE, new Date().toISOString()); }
  catch { /* navigation privée : la pastille reste, ce n'est pas grave */ }
}

async function compterArchiveNouvelles() {
  const p = new URLSearchParams();
  const d = derniereVisiteArchive();
  if (d) p.set('depuis', d);
  p.set('limite', '1');
  try {
    const r = await api(`/api/archive?${p}`);
    const pastille = $('#pastille-archive');
    if (!pastille) return;
    pastille.textContent = r.nouvelles ? String(r.nouvelles) : '';
    pastille.classList.toggle('visible', Boolean(r.nouvelles));
  } catch { /* hors ligne : on ne casse pas la page */ }
}

async function chargerArchive() {
  const p = new URLSearchParams();
  const d = derniereVisiteArchive();
  if (d) p.set('depuis', d);
  const r = await api(`/api/archive?${p}`);
  const cible = $('#liste-archive');

  if (!r.offres.length) {
    cible.innerHTML = `<p class="resume">Aucune annonce archivée pour l'instant.</p>`;
    marquerArchiveVue();
    compterArchiveNouvelles();
    return;
  }

  cible.innerHTML = r.offres.map(o => `
    <article class="offre archivee" data-id="${o.id}">
      <div class="offre-haut">
        <h3>${echapper(o.titre)}</h3>
        <span class="score">${o.score}</span>
      </div>
      <p class="menu">${echapper(o.employeur || '')} ${echapper(o.lieu || '')}
        ${o.disparue_le ? `· disparue vers le ${echapper(o.disparue_le.slice(0, 10))}` : ''}</p>
      <p class="avert"><b>Pourquoi elle est ici</b><br>${echapper(o.archive_motif || 'motif non enregistré')}</p>
      <div class="actions">
        <button data-action="desarchiver">Remettre dans le flux</button>
        ${o.url ? `<a class="discret" href="${echapper(o.url)}" target="_blank" rel="noopener noreferrer">Ouvrir l'annonce</a>` : ''}
      </div>
    </article>`).join('');

  cible.querySelectorAll('[data-action="desarchiver"]').forEach(b => {
    b.onclick = async () => {
      const id = b.closest('.offre').dataset.id;
      await api(`/api/offres/${id}/desarchiver`, { method: 'POST' });
      chargerArchive();
      compterArchiveNouvelles();
    };
  });

  marquerArchiveVue();
  compterArchiveNouvelles();
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
//   1. sans identifiants, le bouton n'apparaît pas — pas d'erreur obscure ;
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

function blocDestinataire(o) {
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
    <div class="actions"><button class="discret" id="btn-destinataire">Enregistrer</button>
      <span class="menu" id="etat-destinataire"></span></div>
  </div>`;
}

function brancherDestinataire(id) {
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
      $('#etat-destinataire').textContent = 'enregistré — il sera repris à chaque génération';
    } catch (e) { message(e.message, true); }
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
// « À classer » : les offres qu'aucun motif n'a su ranger
//
// Mesure du 02/10/2026 : une part notable des offres sans famille, certaines
// encore actives. La
// plupart le méritent — une annonce de Hauswart ne relève d'aucune famille cherchée. Mais
// « Automation Tester » et « automatisation de tests » en faisaient partie.
//
// Chaque proposition montre les MOTS qui la justifient. Rien ne s'applique
// sans sa coche : une case préchée serait un classement automatique déguisé.
// ---------------------------------------------------------------------------

async function chargerClasser() {
  try {
    const d = await api('/api/classement');
    $('#pastille-classer').textContent = d.propositions.length || '';

    let html = `<div class="bloc">
      <h2>Offres sans famille — ${d.sans_famille}</h2>
      <p class="resume">Une famille est proposée quand l'intitulé recoupe les
        motifs de <b>criteres.yaml</b>. Les mots qui la justifient sont affichés :
        si tu ne les reconnais pas, ne coche pas. Le barème ne change pas —
        une famille validée rapporte ce que rapporte la même famille détectée.</p>`;

    if (!d.propositions.length) {
      html += `<p class="resume">Aucune proposition : les offres restantes ne
        recoupent aucun de tes métiers, et c'est probablement juste.</p>`;
    } else {
      html += `<ul class="preuves">${d.propositions.map(p => `
        <li class="pour"><span>
          <label><input type="checkbox" class="classer" checked
            data-offre="${p.offre_id}" data-famille="${echapper(p.famille)}">
            <b>${echapper(p.titre)}</b></label>
          <br><span class="menu">${echapper(p.employeur)} · score ${p.score}
            · proposé : <b>${echapper(p.libelle)}</b></span>
          <br>${p.preuves.map(x => `<i>${echapper(x)}</i>`).join('<br>')}
        </span></li>`).join('')}</ul>
        <div class="actions">
          <button id="btn-classer">Valider les cochées et rescorer</button>
          <button class="discret" id="btn-rien-cocher">Tout décocher</button>
        </div>`;
    }

    if (d.sans_proposition.length) {
      html += `<details class="explication">
        <summary>${d.sans_proposition.length} offre(s) sans aucune proposition</summary>
        <ul class="fichiers">${d.sans_proposition.map(o =>
          `<li>${echapper(o.titre)} — ${echapper(o.employeur)} (${o.score})</li>`).join('')}</ul>
      </details>`;
    }
    html += '</div>';
    $('#liste-classer').innerHTML = html;

    const decocher = $('#btn-rien-cocher');
    if (decocher) decocher.onclick = () =>
      document.querySelectorAll('.classer').forEach(c => { c.checked = false; });

    const b = $('#btn-classer');
    if (b) b.onclick = async () => {
      const decisions = [...document.querySelectorAll('.classer:checked')].map(c => ({
        offre_id: Number(c.dataset.offre), famille: c.dataset.famille,
      }));
      if (!decisions.length) { message('Rien de coché.'); return; }
      b.disabled = true;
      try {
        const r = await api('/api/classement/valider', {
          method: 'POST', body: JSON.stringify({ decisions }),
        });
        message(`${r.validees} offre(s) classée(s) et rescorée(s).`);
        chargerClasser();
      } catch (e) { message(e.message, true); }
      finally { b.disabled = false; }
    };
  } catch (e) { message(e.message, true); }
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
      $('#fenetre').showModal();
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
    $('#fenetre').showModal();

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
  plus: chargerPlus,
  offres: chargerOffres,
  archive: chargerArchive,
  relances: chargerRelances,
  classer: chargerClasser,
  pilotage: chargerPilotage,
  documents: chargerDocuments,
  reglages: chargerReglages,
};

function rafraichir() {
  compterArchiveNouvelles();
  (CHARGEURS[vueCourante] || chargerOffres)();
}

// Les anciens écrans vivent sous « Plus » : ils gardent son onglet allumé.
const ONGLET_DE_VUE = {
  offres: 'plus', relances: 'plus', archive: 'plus', classer: 'plus',
  pilotage: 'plus', documents: 'plus', reglages: 'plus',
};

function afficherVue(nom) {
  const vue = $(`#vue-${nom}`);
  if (!vue) return;
  vueCourante = nom;
  const onglet = ONGLET_DE_VUE[nom] || nom;
  $$('.onglet').forEach(o => o.classList.toggle('actif', o.dataset.vue === onglet));
  $$('.vue').forEach(v => v.classList.toggle('cachee', v !== vue));
  // Un écran s'ouvre par le haut : un lien touché au bas de la file ne mène pas au
  // milieu de la liste suivante.
  window.scrollTo(0, 0);
  rafraichir();
}

// Tout `[data-vue]` mène à son écran : les onglets, les lignes de « Plus », « ‹ Plus ».
document.addEventListener('click', ev => {
  const lien = ev.target.closest('[data-vue]');
  if (lien) afficherVue(lien.dataset.vue);
});

// ---------------------------------------------------------------------------
// Filtres : repliés par défaut sur téléphone
//
// Contrainte de conception, pas cosmétique : la console est consultée
// principalement depuis un téléphone. Les offres passent devant, toujours. Les
// réglages restent à un geste, et les filtres actifs restent visibles sous
// forme de puces — sinon une liste courte paraît vide sans qu'on comprenne
// qu'un filtre la restreint.
// ---------------------------------------------------------------------------

const CHAMPS_FILTRES = [
  { id: '#f-recherche', cle: 'recherche', libelle: 'Recherche' },
  { id: '#f-statut', cle: 'statut', libelle: 'Statut' },
  { id: '#f-zone', cle: 'zone', libelle: 'Zone' },
  { id: '#f-famille', cle: 'famille', libelle: 'Famille' },
  { id: '#f-atout', cle: 'atout', libelle: 'Atout' },
];

const surTelephone = () => window.matchMedia('(max-width: 640px)').matches;

function libelleValeur(champ) {
  const el = $(champ.id);
  if (el.tagName === 'SELECT') {
    return el.options[el.selectedIndex]?.textContent.trim() || el.value;
  }
  return el.value.trim();
}

function filtresActifs() {
  const actifs = CHAMPS_FILTRES
    .filter(c => $(c.id).value.trim())
    .map(c => ({ ...c, valeur: libelleValeur(c) }));
  if ($('#f-ecartees').checked) {
    actifs.push({ id: '#f-ecartees', cle: 'ecartees', libelle: 'Écartées', valeur: 'incluses' });
  }
  return actifs;
}

function effacerFiltre(id) {
  const el = $(id);
  if (el.type === 'checkbox') el.checked = false;
  else el.value = '';
  synchroniserFiltres();
  chargerOffres();
}

function synchroniserFiltres() {
  const actifs = filtresActifs();

  $('#compte-filtres').textContent = actifs.length || '';
  // Les libellés complets de la configuration débordent sur deux lignes au
  // téléphone : on tronque,
  // le libellé entier reste en infobulle.
  const court = t => (t.length > 26 ? t.slice(0, 25).trimEnd() + '…' : t);
  $('#puces-filtres').innerHTML = actifs.map(a =>
    `<span class="puce" title="${echapper(a.libelle)} : ${echapper(a.valeur)}">${echapper(court(a.valeur))}
       <button data-effacer="${a.id}" aria-label="Retirer le filtre ${echapper(a.libelle)}">×</button>
     </span>`).join('');

  const atoutActif = !!ATOUT && $('#f-atout').value === ATOUT.cle;
  $('#btn-atout').setAttribute('aria-pressed', String(atoutActif));
}

$('#puces-filtres').addEventListener('click', ev => {
  const b = ev.target.closest('[data-effacer]');
  if (b) effacerFiltre(b.dataset.effacer);
});

$('#btn-filtres').onclick = () => {
  const panneau = $('#panneau-filtres');
  const ouvert = !panneau.hidden;
  panneau.hidden = ouvert;
  $('#btn-filtres').setAttribute('aria-expanded', String(!ouvert));
};

// « À documenter » : score élevé, dossier trop mince. C'est la file de travail
// la plus rentable — dix minutes chacune et elles deviennent candidatables —
// donc elle est accessible en un geste, pas au fond du panneau des filtres.
let aDocumenter = false;
$('#btn-documenter').onclick = () => {
  aDocumenter = !aDocumenter;
  $('#btn-documenter').setAttribute('aria-pressed', String(aDocumenter));
  chargerOffres();
};

// Accès en un geste à l'atout mis en avant par la configuration : son avantage
// le plus rare, donc le filtre le plus utile au quotidien.
$('#btn-atout').onclick = () => {
  if (!ATOUT) return;
  const champ = $('#f-atout');
  champ.value = champ.value === ATOUT.cle ? '' : ATOUT.cle;
  synchroniserFiltres();
  chargerOffres();
};

let minuteur;
$('#f-recherche').oninput = () => {
  synchroniserFiltres();
  clearTimeout(minuteur);
  minuteur = setTimeout(chargerOffres, 280);
};
['#f-statut', '#f-zone', '#f-famille', '#f-atout', '#f-verification', '#f-tri', '#f-ecartees'].forEach(s => {
  $(s).onchange = () => { synchroniserFiltres(); chargerOffres(); };
});

// Replié sur téléphone, ouvert sur ordinateur où la place ne manque pas.
$('#panneau-filtres').hidden = surTelephone();
$('#btn-filtres').setAttribute('aria-expanded', String(!surTelephone()));

$('#btn-rescorer').onclick = async ev => {
  ev.target.disabled = true;
  try {
    const d = await api('/api/rescorer', { method: 'POST' });
    message(`${d.offres_recalculees} offre(s) recalculee(s).`);
    chargerOffres();
  } catch (e) { message(e.message, true); }
  finally { ev.target.disabled = false; }
};

// ---------------------------------------------------------------------------
// Notifications push
// ---------------------------------------------------------------------------

function base64EnOctets(base64) {
  const bourrage = '='.repeat((4 - base64.length % 4) % 4);
  const brut = atob((base64 + bourrage).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...brut].map(c => c.charCodeAt(0)));
}

async function activerPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    message("Ce navigateur ne gere pas le push web.", true); return;
  }
  if (!CLE_VAPID) {
    message("Pas de cle VAPID sur le serveur : lance `veille init`.", true); return;
  }
  if (!window.isSecureContext) {
    message("Le push exige HTTPS. Active les certificats HTTPS du tailnet, puis `tailscale serve`.", true);
    return;
  }
  try {
    const enregistrement = await navigator.serviceWorker.register('/sw.js');
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') { message('Notifications refusees par le navigateur.', true); return; }
    const abonnement = await enregistrement.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64EnOctets(CLE_VAPID),
    });
    await api('/api/push/abonnement', { method: 'POST', body: JSON.stringify(abonnement.toJSON()) });
    message('Notifications activees sur cet appareil.');
    await api('/api/push/test', { method: 'POST' });
  } catch (e) { message('Activation impossible : ' + e.message, true); }
}

$('#btn-push').onclick = activerPush;

if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ---------------------------------------------------------------------------

// La notification ouvre `/?filtre=nouveau` : la file, qu'elle annonce. Un autre filtre, ou
// un atout, mène à « Toutes les offres », filtrée comme avant.
const params = new URLSearchParams(location.search);
const filtreDemande = params.get('filtre');
const atoutDemande = params.get('atout');
const versOffres = Boolean((filtreDemande && filtreDemande !== 'nouveau') || atoutDemande);
if (versOffres) {
  if (filtreDemande) $('#f-statut').value = filtreDemande;
  if (atoutDemande) $('#f-atout').value = atoutDemande;
}
synchroniserFiltres();
afficherVue(versOffres ? 'offres' : 'a-faire');
