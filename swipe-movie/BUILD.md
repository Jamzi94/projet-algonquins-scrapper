# SwipeNight — build de l'app & simulation (GitHub Actions)

Deux workflows GitHub Actions sont fournis dans `.github/workflows/` :

| Workflow | Fichier | Déclencheur | Rôle |
| --- | --- | --- | --- |
| **EAS Build (app mobile, cloud)** | `eas-build.yml` | manuel (`workflow_dispatch`) | Construit l'APK/AAB/IPA **dans le cloud Expo** — aucun SDK Android/Xcode requis. |
| **Tests & Simulation** | `ci.yml` | push / PR / manuel | Lance backend + frontend + moteur movie-reco de bout en bout, **sans clé ni MongoDB**. |

---

## 1. Construire l'app — EAS Build (voie simple, cloud)

EAS Build compile sur les serveurs d'Expo : **rien à installer** (ni Android
SDK, ni Xcode). Le workflow `eas-build.yml` se lance à la main depuis l'onglet
**Actions**.

### Réglage unique

1. **Compte + jeton Expo.** Crée un compte sur <https://expo.dev>, puis un
   jeton : *Account settings → Access tokens → Create token*.
2. **Secret GitHub.** Dépôt → *Settings → Secrets and variables → Actions →
   New repository secret* : nom `EXPO_TOKEN`, valeur = le jeton. (Le secret
   n'apparaît jamais dans les logs ni dans le code.)
3. **URL du backend** (pour que l'app installée joigne l'API). Par défaut les
   profils d'`eas.json` utilisent `EXPO_PUBLIC_BACKEND_URL=http://localhost:8000`
   (placeholder). Remplace-le par l'URL publique de ton backend, au choix :
   - dans `swipe-movie/frontend/eas.json` (clé `env.EXPO_PUBLIC_BACKEND_URL` du
     profil voulu), **ou**
   - comme variable d'environnement EAS (prioritaire) :
     `eas env:create --name EXPO_PUBLIC_BACKEND_URL --value https://mon-backend …`.

### Lancer un build

Onglet **Actions → EAS Build (app mobile, cloud) → Run workflow**, puis choisis :

- **platform** : `android` (défaut), `ios` ou `all`.
- **profile** (défini dans `eas.json`) :
  - `preview` → **APK** Android installable directement (`distribution: internal`) ;
  - `production` → **AAB** (Play Store) ;
  - `development` → build de dev (Expo Dev Client).
- **wait** : `false` (défaut) soumet le build et rend la main ; `true` attend la fin.

Le binaire se télécharge depuis le tableau de bord Expo
(<https://expo.dev> → *Projects → Builds*).

> Le workflow exécute `eas init --non-interactive` pour lier le projet Expo
> automatiquement au premier run. Identité de l'app : `com.swipenight.app`
> (`android.package` / `ios.bundleIdentifier` dans `app.json`).

### iOS / IPA

Un build iOS distribuable (`.ipa`) **exige un compte Apple Developer payant**
(99 $/an) pour la signature. Sans lui, on peut produire un build **simulateur**
(`profile: preview`, `ios.simulator: true`) qui tourne dans le simulateur iOS
sur macOS, mais ne s'installe pas sur un iPhone réel. Android n'a pas cette
contrainte : l'APK `preview` s'installe directement.

---

## 2. Convertir en SPA (web)

Le frontend Expo s'exporte en **site statique** (SPA) — c'est ce que produit le
job `frontend` du workflow `ci.yml` :

```bash
cd swipe-movie/frontend
npm install
EXPO_PUBLIC_BACKEND_URL=https://mon-backend npx expo export -p web   # -> dist/
```

Le dossier `dist/` (HTML + JS + assets) se sert avec n'importe quel hébergeur
statique (GitHub Pages, Netlify, Vercel, `npx serve dist`). En CI, il est publié
comme artefact `swipenight-web` téléchargeable depuis le run.

---

## 3. Lancer la simulation / les tests

Le workflow `ci.yml` reproduit exactement la simulation locale, **sans MongoDB
et sans clé externe** (Mongo en mémoire + catalogue Wikidata hors-ligne) :

**Backend** (`swipe-movie/backend`)
- `pip install -r requirements-sandbox.txt` (installe aussi movie-reco en
  éditable, backend tfidf **sans torch**) ;
- génère un catalogue synthétique déterministe (`movie-reco/data` est gitignoré,
  donc fabriqué à la volée pour que le test e2e s'exécute) ;
- `pytest tests/ -q` ;
- démarre `uvicorn server:app` et vérifie `GET /api/provider-status`
  (`data_source = wikidata`, `catalog_source = movreco`).

**Frontend** (`swipe-movie/frontend`)
- `npm install` ;
- `npx tsc --noEmit` (vérification de types) ;
- `npx expo export -p web` → artefact `dist/`.

**movie-reco** — suite de non-régression du moteur (`pytest -q`).

### À la main (local)

```bash
# Backend
cd swipe-movie/backend
pip install -r requirements-sandbox.txt
MONGO_URL=memory JWT_SECRET=dev DATA_SOURCE=wikidata uvicorn server:app --reload --port 8000
python -m pytest tests/ -q
curl localhost:8000/api/provider-status

# Frontend
cd swipe-movie/frontend
npm install
export EXPO_PUBLIC_BACKEND_URL=http://localhost:8000
npx expo start            # dev (Expo Go / navigateur)
npx expo export -p web    # build web statique -> dist/
```

---

## Notes

- **Gestionnaire de paquets.** Le dépôt fournit `package-lock.json` (npm) ;
  les workflows utilisent donc **npm**. EAS Build détecte le gestionnaire via le
  lockfile présent. Si tu préfères yarn, ajoute un `yarn.lock` cohérent.
- **TMDB reste toggleable.** Les workflows tournent en `EXTERNAL_APIS_ENABLED=false`
  (100 % Wikidata CC0 + Wikipedia CC BY-SA). Pour activer TMDB : `DATA_SOURCE=tmdb`
  + `TMDB_API_KEY` (cf. `backend/SANDBOX.md`). Aucune clé n'est jamais requise.
- **Aucun secret dans le binaire web/SPA.** Seules les variables `EXPO_PUBLIC_*`
  sont injectées côté client ; n'y mets jamais de secret serveur.
